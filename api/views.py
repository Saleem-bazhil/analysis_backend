import os
import re
from datetime import datetime

import pandas as pd
from django.conf import settings
from django.http import FileResponse
from rest_framework import status
from rest_framework.decorators import api_view, parser_classes, permission_classes
from rest_framework.parsers import MultiPartParser, FormParser
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response

from .models import (
    UploadedFile, CallPlanRecord, WorkspaceState,
    UploadSession, AnalysisResult, ClosedCall,
)
from .serializers import (
    UploadedFileSerializer,
    UploadedFileListSerializer,
    UploadedFileDetailSerializer,
    CallPlanRecordSerializer,
    ProcessRequestSerializer,
    ExportRequestSerializer,
    UploadSessionSerializer,
    AnalysisResultSerializer,
    AnalysisResultListSerializer,
    ClosedCallSerializer,
    ManualWOSerializer,
    ClosedCallRequestSerializer,
    SaveAnalysisSerializer,
)
from .engine import process_call_plan, generate_export_df, read_file_to_df
from .models import UserProfile


def _get_user_region(user):
    """Return the user's assigned region, or '' if admin/unset."""
    try:
        return user.profile.region
    except UserProfile.DoesNotExist:
        return ''


def _is_admin(user):
    """Admin users (is_staff=True or no region) can access all regions."""
    return user.is_staff or not _get_user_region(user)


def _filter_by_region(queryset, user, city_field='city'):
    """Filter a queryset to the user's region. Admins see everything."""
    if _is_admin(user):
        return queryset
    region = _get_user_region(user)
    return queryset.filter(**{f'{city_field}__iexact': region})


def _enforce_region(user, requested_city):
    """Return the city to use. Non-admins always get their own region."""
    if _is_admin(user):
        return requested_city
    return _get_user_region(user)


# ── Upload Session ──

@api_view(['POST'])
@permission_classes([IsAuthenticated])
def create_upload_session(request):
    """
    POST /api/sessions/
    Create a new upload session to group flex + rtpl files together.
    """
    city = _enforce_region(request.user, request.data.get('city', 'Chennai'))
    report_date = request.data.get('report_date', None)

    session = UploadSession.objects.create(
        uploaded_by=request.user.username,
        city=city,
        report_date=report_date or None,
    )

    serializer = UploadSessionSerializer(session)
    return Response(serializer.data, status=status.HTTP_201_CREATED)


@api_view(['GET'])
@permission_classes([IsAuthenticated])
def list_upload_sessions(request):
    """
    GET /api/sessions/
    List all upload sessions.
    """
    qs = _filter_by_region(UploadSession.objects.all(), request.user)
    city = request.query_params.get('city')
    if city:
        qs = qs.filter(city__iexact=city)
    serializer = UploadSessionSerializer(qs, many=True)
    return Response(serializer.data)


@api_view(['GET'])
@permission_classes([IsAuthenticated])
def session_detail(request, pk):
    """
    GET /api/sessions/<id>/
    Get session detail with linked files and analyses.
    """
    try:
        session = UploadSession.objects.get(id=pk)
    except UploadSession.DoesNotExist:
        return Response({'error': 'Session not found.'}, status=status.HTTP_404_NOT_FOUND)

    session_data = UploadSessionSerializer(session).data
    analyses = AnalysisResultListSerializer(session.analyses.all(), many=True).data
    session_data['analyses'] = analyses
    return Response(session_data)


# ── File Upload ──

@api_view(['POST'])
@permission_classes([IsAuthenticated])
@parser_classes([MultiPartParser, FormParser])
def upload_file(request):
    """
    POST /api/upload/
    Upload an Excel/CSV file, store metadata in DB, return parsed preview data.
    Optionally pass session_id to link to an existing upload session.
    """
    file_obj = request.FILES.get('file')
    if not file_obj:
        return Response({'error': 'No file provided.'}, status=status.HTTP_400_BAD_REQUEST)

    file_type = request.data.get('file_type', 'flex_wip')
    city = _enforce_region(request.user, request.data.get('city', 'Chennai'))
    report_date = request.data.get('report_date', None)
    session_id = request.data.get('session_id', None)
    uploaded_by = request.user.username

    # Link to session if provided
    session = None
    if session_id:
        try:
            session = UploadSession.objects.get(id=session_id)
        except UploadSession.DoesNotExist:
            return Response({'error': 'Session not found.'}, status=status.HTTP_404_NOT_FOUND)

    # Create the UploadedFile record
    uploaded = UploadedFile.objects.create(
        session=session,
        file=file_obj,
        file_type=file_type,
        original_name=file_obj.name,
        uploaded_by=uploaded_by,
        city=city,
        report_date=report_date or None,
        file_size=file_obj.size,
    )

    # Parse the file to get row count and preview
    try:
        file_path = uploaded.file.path
        df = read_file_to_df(file_path)
        uploaded.row_count = len(df)
        uploaded.save(update_fields=['row_count'])

        # Return first 50 rows as preview
        preview = df.head(50).fillna('').to_dict(orient='records')
        columns = list(df.columns)
    except Exception:
        preview = []
        columns = []

    serializer = UploadedFileSerializer(uploaded)
    return Response({
        'file': serializer.data,
        'columns': columns,
        'preview': preview,
        'row_count': uploaded.row_count,
    }, status=status.HTTP_201_CREATED)


# ── Process Files ──

@api_view(['POST'])
@permission_classes([IsAuthenticated])
def process_files(request):
    """
    POST /api/process/
    Process call plan comparison.
    Receives flex_file_id, optional callplan_file_id, city, report_date, session_id.
    Returns classified rows and stores AnalysisResult in DB.
    """
    serializer = ProcessRequestSerializer(data=request.data)
    serializer.is_valid(raise_exception=True)
    data = serializer.validated_data

    # Fetch flex file
    try:
        flex_file = UploadedFile.objects.get(id=data['flex_file_id'])
    except UploadedFile.DoesNotExist:
        return Response({'error': 'Flex WIP file not found.'}, status=status.HTTP_404_NOT_FOUND)

    # Fetch optional call plan file
    callplan_path = None
    callplan_file = None
    callplan_file_id = data.get('callplan_file_id')
    if callplan_file_id:
        try:
            callplan_file = UploadedFile.objects.get(id=callplan_file_id)
            callplan_path = callplan_file.file.path
        except UploadedFile.DoesNotExist:
            return Response({'error': 'Call plan file not found.'}, status=status.HTTP_404_NOT_FOUND)

    city = _enforce_region(request.user, data.get('city', 'Chennai'))
    report_date = data.get('report_date')

    try:
        result = process_call_plan(
            flex_file_path=flex_file.file.path,
            callplan_file_path=callplan_path,
            city=city,
            report_date=report_date,
        )
    except Exception as e:
        return Response({'error': f'Processing failed: {str(e)}'}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

    # Resolve session
    session_id = data.get('session_id')
    session = None
    if session_id:
        try:
            session = UploadSession.objects.get(id=session_id)
        except UploadSession.DoesNotExist:
            pass

    # Store analysis result in DB
    summary = result['summary']
    analysis = AnalysisResult.objects.create(
        session=session,
        flex_file=flex_file,
        callplan_file=callplan_file,
        city=city,
        report_date=report_date,
        analyzed_by=request.user.username,
        total_count=summary.get('total', 0),
        pending_count=summary.get('pending', 0),
        new_count=summary.get('new', 0),
        dropped_count=summary.get('dropped', 0),
        result_data={
            'pending': result['pending'],
            'new': result['new'],
            'dropped': result['dropped'],
            'all_rows': result['all_rows'],
        },
    )

    return Response({
        'analysis_id': analysis.id,
        'summary': result['summary'],
        'pending': result['pending'],
        'new': result['new'],
        'dropped': result['dropped'],
        'all_rows': result['all_rows'],
    })


@api_view(['GET'])
@permission_classes([IsAuthenticated])
def list_files(request):
    """
    GET /api/files/
    List all uploaded files with metadata.
    Optional query params: file_type, city
    """
    qs = _filter_by_region(UploadedFile.objects.all(), request.user)

    uploaded_by = request.query_params.get('uploaded_by')
    if uploaded_by:
        qs = qs.filter(uploaded_by=uploaded_by)

    file_type = request.query_params.get('file_type')
    if file_type:
        qs = qs.filter(file_type=file_type)

    city = request.query_params.get('city')
    if city:
        qs = qs.filter(city__iexact=city)

    serializer = UploadedFileListSerializer(qs, many=True)
    return Response(serializer.data)


@api_view(['GET'])
@permission_classes([IsAuthenticated])
def file_detail(request, pk):
    """
    GET /api/files/<id>/
    Get file detail with associated records.
    """
    try:
        uploaded = UploadedFile.objects.get(id=pk)
    except UploadedFile.DoesNotExist:
        return Response({'error': 'File not found.'}, status=status.HTTP_404_NOT_FOUND)

    serializer = UploadedFileDetailSerializer(uploaded)
    return Response(serializer.data)


@api_view(['POST'])
@permission_classes([IsAuthenticated])
def export_file(request):
    """
    POST /api/export/
    Generate and export XLSX from processed rows.
    Stores as 'generated' type, returns file download.
    """
    serializer = ExportRequestSerializer(data=request.data)
    serializer.is_valid(raise_exception=True)
    data = serializer.validated_data

    rows = data['rows']
    city = _enforce_region(request.user, data.get('city', 'Chennai'))
    report_date = data.get('report_date')

    if not rows:
        return Response({'error': 'No rows to export.'}, status=status.HTTP_400_BAD_REQUEST)

    # Generate the DataFrame
    export_df = generate_export_df(rows)

    # Create output filename
    date_str = report_date.strftime('%Y-%m-%d') if report_date else datetime.now().strftime('%Y-%m-%d')
    filename = f"CallPlan_{city}_{date_str}.xlsx"

    # Ensure upload directory exists
    upload_dir = os.path.join(settings.MEDIA_ROOT, 'uploads', datetime.now().strftime('%Y/%m/%d'))
    os.makedirs(upload_dir, exist_ok=True)

    file_path = os.path.join(upload_dir, filename)

    # Write Excel file
    export_df.to_excel(file_path, index=False, engine='openpyxl')

    # Compute relative path for FileField
    relative_path = os.path.relpath(file_path, settings.MEDIA_ROOT)
    relative_path = relative_path.replace('\\', '/')

    # Store in DB as generated file
    generated = UploadedFile.objects.create(
        file=relative_path,
        file_type='generated',
        original_name=filename,
        uploaded_by=request.user.username,
        city=city,
        report_date=report_date,
        file_size=os.path.getsize(file_path),
        row_count=len(rows),
    )

    # Also store individual records + detect closed calls
    records_to_create = []
    closed_calls_to_create = []
    for row in rows:
        morning = row.get('morning_status', '')
        records_to_create.append(CallPlanRecord(
            upload=generated,
            ticket_no=row.get('ticket_no', ''),
            case_id=row.get('case_id', ''),
            product=row.get('product', ''),
            wip_aging=row.get('wip_aging', 0),
            location=row.get('location', ''),
            segment=row.get('segment', ''),
            classification=row.get('classification', 'NEW'),
            morning_status=morning,
            evening_status=row.get('evening_status', ''),
            engineer=row.get('engineer', ''),
            contact_no=row.get('contact_no', ''),
            parts=row.get('parts', ''),
            month=row.get('month', ''),
            wo_otc_code=row.get('wo_otc_code', ''),
            hp_owner=row.get('hp_owner', ''),
            flex_status=row.get('flex_status', ''),
            wip_changed=row.get('wip_changed', ''),
            current_status_tat=row.get('current_status_tat', ''),
            source='manual' if row.get('hp_owner', '') == 'Manual' else 'export',
        ))

        # Copy closed calls to separate tracking table
        if morning.lower() in ('closed', 'closed cancelled'):
            closed_calls_to_create.append(ClosedCall(
                ticket_no=row.get('ticket_no', ''),
                case_id=row.get('case_id', ''),
                product=row.get('product', ''),
                wip_aging=row.get('wip_aging', 0),
                location=row.get('location', ''),
                segment=row.get('segment', ''),
                engineer=row.get('engineer', ''),
                contact_no=row.get('contact_no', ''),
                parts=row.get('parts', ''),
                month=row.get('month', ''),
                wo_otc_code=row.get('wo_otc_code', ''),
                hp_owner=row.get('hp_owner', ''),
                flex_status=row.get('flex_status', ''),
                morning_status=morning,
                evening_status=row.get('evening_status', ''),
                current_status_tat=row.get('current_status_tat', ''),
                city=city,
                report_date=report_date,
                closed_by=request.user.username,
            ))

    CallPlanRecord.objects.bulk_create(records_to_create)
    if closed_calls_to_create:
        ClosedCall.objects.bulk_create(closed_calls_to_create)

    # Save analysis summary at export time
    pending_count = sum(1 for r in rows if r.get('classification') == 'PENDING')
    new_count = sum(1 for r in rows if r.get('classification') == 'NEW')
    AnalysisResult.objects.create(
        flex_file=None,
        callplan_file=None,
        city=city,
        report_date=report_date,
        analyzed_by=request.user.username,
        total_count=len(rows),
        pending_count=pending_count,
        new_count=new_count,
        dropped_count=0,
        result_data={'source': 'export', 'closed_count': len(closed_calls_to_create)},
    )

    # Return file download — FileResponse handles closing the file handle
    response = FileResponse(
        open(file_path, 'rb'),
        as_attachment=True,
        filename=filename,
        content_type='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
    )
    return response


# ── Manual WO Addition ──

@api_view(['POST'])
@permission_classes([IsAuthenticated])
def add_manual_wo(request):
    """
    POST /api/manual-wo/
    Save a manually added Work Order directly to DB as a CallPlanRecord.
    """
    serializer = ManualWOSerializer(data=request.data)
    serializer.is_valid(raise_exception=True)
    data = serializer.validated_data

    ticket_no = data['ticket_no'].strip().upper()

    # Validate WO format
    if not re.match(r'^WO-\d{9}$', ticket_no, re.IGNORECASE) and not re.match(r'^\d{9}$', ticket_no):
        return Response(
            {'error': 'Invalid Work Order format. Expected: WO-XXXXXXXXX or 9 digits.'},
            status=status.HTTP_400_BAD_REQUEST,
        )

    record = CallPlanRecord.objects.create(
        upload=None,
        ticket_no=ticket_no,
        case_id=data.get('case_id', ''),
        product=data.get('product', ''),
        wip_aging=data.get('wip_aging', 0),
        location=data.get('location', ''),
        segment=data.get('segment', ''),
        classification=data.get('classification', 'NEW'),
        morning_status=data.get('morning_status', 'To be scheduled'),
        evening_status=data.get('evening_status', ''),
        engineer=data.get('engineer', ''),
        contact_no=data.get('contact_no', ''),
        parts=data.get('parts', ''),
        month=data.get('month', ''),
        wo_otc_code=data.get('wo_otc_code', ''),
        hp_owner=data.get('hp_owner', 'Manual'),
        flex_status=data.get('flex_status', 'Manual Entry'),
        wip_changed=data.get('wip_changed', 'New'),
        current_status_tat=data.get('current_status_tat', ''),
        source='manual',
    )

    return Response(
        CallPlanRecordSerializer(record).data,
        status=status.HTTP_201_CREATED,
    )


# ── Closed Calls ──

@api_view(['POST'])
@permission_classes([IsAuthenticated])
def mark_closed_call(request):
    """
    POST /api/closed-calls/
    Copy a call to the ClosedCall table when morning report marks it as closed.
    """
    serializer = ClosedCallRequestSerializer(data=request.data)
    serializer.is_valid(raise_exception=True)
    data = serializer.validated_data

    closed_call = ClosedCall.objects.create(
        ticket_no=data.get('ticket_no', ''),
        case_id=data.get('case_id', ''),
        product=data.get('product', ''),
        wip_aging=data.get('wip_aging', 0),
        location=data.get('location', ''),
        segment=data.get('segment', ''),
        engineer=data.get('engineer', ''),
        contact_no=data.get('contact_no', ''),
        parts=data.get('parts', ''),
        month=data.get('month', ''),
        wo_otc_code=data.get('wo_otc_code', ''),
        hp_owner=data.get('hp_owner', ''),
        flex_status=data.get('flex_status', ''),
        morning_status=data.get('morning_status', 'Closed'),
        evening_status=data.get('evening_status', ''),
        current_status_tat=data.get('current_status_tat', ''),
        city=_enforce_region(request.user, data.get('city', 'Chennai')),
        report_date=data.get('report_date'),
        closed_by=request.user.username,
    )

    return Response(
        ClosedCallSerializer(closed_call).data,
        status=status.HTTP_201_CREATED,
    )


@api_view(['GET'])
@permission_classes([IsAuthenticated])
def list_closed_calls(request):
    """
    GET /api/closed-calls/
    List all closed calls. Optional filters: city, report_date.
    """
    qs = _filter_by_region(ClosedCall.objects.all(), request.user)

    city = request.query_params.get('city')
    if city:
        qs = qs.filter(city__iexact=city)

    report_date = request.query_params.get('report_date')
    if report_date:
        qs = qs.filter(report_date=report_date)

    serializer = ClosedCallSerializer(qs, many=True)
    return Response(serializer.data)


# ── Analysis History ──

@api_view(['POST'])
@permission_classes([IsAuthenticated])
def save_analysis(request):
    """
    POST /api/analyses/save/
    Save client-side analysis results to DB.
    Called after frontend processes data locally.
    """
    serializer = SaveAnalysisSerializer(data=request.data)
    serializer.is_valid(raise_exception=True)
    data = serializer.validated_data

    session = None
    session_id = data.get('session_id')
    if session_id:
        try:
            session = UploadSession.objects.get(id=session_id)
        except UploadSession.DoesNotExist:
            pass

    analysis = AnalysisResult.objects.create(
        session=session,
        flex_file=None,
        callplan_file=None,
        city=_enforce_region(request.user, data.get('city', 'Chennai')),
        report_date=data.get('report_date'),
        analyzed_by=request.user.username,
        total_count=data.get('total_count', 0),
        pending_count=data.get('pending_count', 0),
        new_count=data.get('new_count', 0),
        dropped_count=data.get('dropped_count', 0),
        result_data=data.get('result_data', {}),
    )

    return Response(
        AnalysisResultSerializer(analysis).data,
        status=status.HTTP_201_CREATED,
    )


@api_view(['GET'])
@permission_classes([IsAuthenticated])
def list_analyses(request):
    """
    GET /api/analyses/
    List all analysis results. Optional filters: city, report_date.
    """
    qs = _filter_by_region(AnalysisResult.objects.all(), request.user)

    city = request.query_params.get('city')
    if city:
        qs = qs.filter(city__iexact=city)

    report_date = request.query_params.get('report_date')
    if report_date:
        qs = qs.filter(report_date=report_date)

    serializer = AnalysisResultListSerializer(qs, many=True)
    return Response(serializer.data)


@api_view(['GET'])
@permission_classes([IsAuthenticated])
def analysis_detail(request, pk):
    """
    GET /api/analyses/<id>/
    Get full analysis result with result_data.
    """
    try:
        analysis = AnalysisResult.objects.get(id=pk)
    except AnalysisResult.DoesNotExist:
        return Response({'error': 'Analysis not found.'}, status=status.HTTP_404_NOT_FOUND)

    serializer = AnalysisResultSerializer(analysis)
    return Response(serializer.data)


@api_view(['GET'])
@permission_classes([IsAuthenticated])
def history(request):
    """
    GET /api/history/
    Get processing history (list of generated files).
    """
    uploaded_by = request.query_params.get('uploaded_by')
    qs = UploadedFile.objects.filter(file_type='generated').order_by('-uploaded_at')
    qs = _filter_by_region(qs, request.user)
    if uploaded_by:
        qs = qs.filter(uploaded_by=uploaded_by)
    serializer = UploadedFileListSerializer(qs, many=True)
    return Response(serializer.data)


@api_view(['GET', 'POST'])
@permission_classes([IsAuthenticated])
def workspace_state(request):
    """
    GET /api/workspace/
    POST /api/workspace/
    Get or update the global workspace state.
    """
    if request.method == 'GET':
        state_obj = WorkspaceState.objects.first()
        if state_obj:
            return Response(state_obj.state)
        return Response({})

    elif request.method == 'POST':
        # Update or create the single workspace state
        state_obj = WorkspaceState.objects.first()
        if state_obj:
            state_obj.state = request.data
            state_obj.save()
        else:
            WorkspaceState.objects.create(state=request.data)

        return Response({'status': 'success'})

import os
from datetime import datetime

import pandas as pd
from django.conf import settings
from django.http import FileResponse
from rest_framework import status
from rest_framework.decorators import api_view, parser_classes
from rest_framework.parsers import MultiPartParser, FormParser
from rest_framework.response import Response

from .models import UploadedFile, CallPlanRecord, WorkspaceState
from .serializers import (
    UploadedFileSerializer,
    UploadedFileListSerializer,
    UploadedFileDetailSerializer,
    CallPlanRecordSerializer,
    ProcessRequestSerializer,
    ExportRequestSerializer,
)
from .engine import process_call_plan, generate_export_df, read_file_to_df


@api_view(['POST'])
@parser_classes([MultiPartParser, FormParser])
def upload_file(request):
    """
    POST /api/upload/
    Upload an Excel/CSV file, store metadata in DB, return parsed preview data.
    """
    file_obj = request.FILES.get('file')
    if not file_obj:
        return Response({'error': 'No file provided.'}, status=status.HTTP_400_BAD_REQUEST)

    file_type = request.data.get('file_type', 'flex_wip')
    city = request.data.get('city', 'Chennai')
    report_date = request.data.get('report_date', None)
    uploaded_by = request.data.get('uploaded_by', 'admin')

    # Create the UploadedFile record
    uploaded = UploadedFile.objects.create(
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
    except Exception as e:
        preview = []
        columns = []

    serializer = UploadedFileSerializer(uploaded)
    return Response({
        'file': serializer.data,
        'columns': columns,
        'preview': preview,
        'row_count': uploaded.row_count,
    }, status=status.HTTP_201_CREATED)


@api_view(['POST'])
def process_files(request):
    """
    POST /api/process/
    Process call plan comparison.
    Receives flex_file_id, optional callplan_file_id, city, report_date.
    Returns classified rows (pending, new, dropped).
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
    callplan_file_id = data.get('callplan_file_id')
    if callplan_file_id:
        try:
            callplan_file = UploadedFile.objects.get(id=callplan_file_id)
            callplan_path = callplan_file.file.path
        except UploadedFile.DoesNotExist:
            return Response({'error': 'Call plan file not found.'}, status=status.HTTP_404_NOT_FOUND)

    city = data.get('city', 'Chennai')
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

    return Response({
        'summary': result['summary'],
        'pending': result['pending'],
        'new': result['new'],
        'dropped': result['dropped'],
        'all_rows': result['all_rows'],
    })


@api_view(['GET'])
def list_files(request):
    """
    GET /api/files/
    List all uploaded files with metadata.
    Optional query params: file_type, city
    """
    qs = UploadedFile.objects.all()

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
    city = data.get('city', 'Chennai')
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
        city=city,
        report_date=report_date,
        file_size=os.path.getsize(file_path),
        row_count=len(rows),
    )

    # Also store individual records
    records_to_create = []
    for row in rows:
        records_to_create.append(CallPlanRecord(
            upload=generated,
            ticket_no=row.get('ticket_no', ''),
            case_id=row.get('case_id', ''),
            product=row.get('product', ''),
            wip_aging=row.get('wip_aging', 0),
            location=row.get('location', ''),
            segment=row.get('segment', ''),
            classification=row.get('classification', 'NEW'),
            morning_status=row.get('morning_status', ''),
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
        ))
    CallPlanRecord.objects.bulk_create(records_to_create)

    # Return file download
    response = FileResponse(
        open(file_path, 'rb'),
        content_type='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
    )
    response['Content-Disposition'] = f'attachment; filename="{filename}"'
    return response


@api_view(['GET'])
def history(request):
    """
    GET /api/history/
    Get processing history (list of generated files).
    """
    uploaded_by = request.query_params.get('uploaded_by')
    qs = UploadedFile.objects.filter(file_type='generated').order_by('-uploaded_at')
    if uploaded_by:
        qs = qs.filter(uploaded_by=uploaded_by)
    serializer = UploadedFileListSerializer(qs, many=True)
    return Response(serializer.data)


@api_view(['GET', 'POST'])
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

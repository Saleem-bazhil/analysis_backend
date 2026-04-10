from rest_framework import serializers
from .models import UploadedFile, CallPlanRecord, UploadSession, AnalysisResult, ClosedCall


class UploadedFileSerializer(serializers.ModelSerializer):
    class Meta:
        model = UploadedFile
        fields = [
            'id', 'session', 'file', 'file_type', 'original_name', 'uploaded_by',
            'uploaded_at', 'city', 'report_date', 'file_size', 'row_count',
        ]
        read_only_fields = ['id', 'uploaded_at', 'file_size', 'row_count']


class UploadedFileListSerializer(serializers.ModelSerializer):
    """Lighter serializer for list views (no file field)."""

    class Meta:
        model = UploadedFile
        fields = [
            'id', 'session', 'file_type', 'original_name', 'uploaded_by',
            'uploaded_at', 'city', 'report_date', 'file_size', 'row_count',
        ]


class CallPlanRecordSerializer(serializers.ModelSerializer):
    class Meta:
        model = CallPlanRecord
        fields = [
            'id', 'upload', 'ticket_no', 'case_id', 'product', 'wip_aging',
            'location', 'segment', 'classification', 'morning_status',
            'evening_status', 'engineer', 'contact_no', 'parts', 'month',
            'wo_otc_code', 'hp_owner', 'flex_status', 'wip_changed',
            'current_status_tat', 'source', 'created_at',
        ]
        read_only_fields = ['id', 'created_at']


class UploadedFileDetailSerializer(serializers.ModelSerializer):
    """File detail with nested records."""

    records = CallPlanRecordSerializer(many=True, read_only=True)

    class Meta:
        model = UploadedFile
        fields = [
            'id', 'session', 'file', 'file_type', 'original_name', 'uploaded_at',
            'city', 'report_date', 'file_size', 'row_count', 'records',
        ]


class UploadSessionSerializer(serializers.ModelSerializer):
    """Session that groups flex + rtpl files together."""

    files = UploadedFileListSerializer(many=True, read_only=True)

    class Meta:
        model = UploadSession
        fields = [
            'id', 'uploaded_by', 'city', 'report_date', 'created_at', 'files',
        ]
        read_only_fields = ['id', 'created_at']


class AnalysisResultSerializer(serializers.ModelSerializer):
    class Meta:
        model = AnalysisResult
        fields = [
            'id', 'session', 'flex_file', 'callplan_file', 'city',
            'report_date', 'analyzed_by', 'analyzed_at',
            'total_count', 'pending_count', 'new_count', 'dropped_count',
            'result_data',
        ]
        read_only_fields = ['id', 'analyzed_at']


class AnalysisResultListSerializer(serializers.ModelSerializer):
    """Lighter serializer without result_data JSON blob."""

    class Meta:
        model = AnalysisResult
        fields = [
            'id', 'session', 'flex_file', 'callplan_file', 'city',
            'report_date', 'analyzed_by', 'analyzed_at',
            'total_count', 'pending_count', 'new_count', 'dropped_count',
        ]


class ClosedCallSerializer(serializers.ModelSerializer):
    class Meta:
        model = ClosedCall
        fields = [
            'id', 'ticket_no', 'case_id', 'product', 'wip_aging',
            'location', 'segment', 'engineer', 'contact_no', 'parts',
            'month', 'wo_otc_code', 'hp_owner', 'flex_status',
            'morning_status', 'evening_status', 'current_status_tat',
            'city', 'report_date', 'closed_by', 'closed_at',
        ]
        read_only_fields = ['id', 'closed_at']


class ProcessRequestSerializer(serializers.Serializer):
    """Validates the /api/process/ request body."""

    flex_file_id = serializers.IntegerField()
    callplan_file_id = serializers.IntegerField(required=False, allow_null=True)
    city = serializers.CharField(max_length=100, default='Chennai')
    report_date = serializers.DateField(required=False, allow_null=True)
    session_id = serializers.IntegerField(required=False, allow_null=True)


class SaveAnalysisSerializer(serializers.Serializer):
    """Validates saving client-side analysis results to DB."""

    city = serializers.CharField(max_length=100, default='Chennai')
    report_date = serializers.DateField(required=False, allow_null=True)
    session_id = serializers.IntegerField(required=False, allow_null=True)
    total_count = serializers.IntegerField(default=0)
    pending_count = serializers.IntegerField(default=0)
    new_count = serializers.IntegerField(default=0)
    dropped_count = serializers.IntegerField(default=0)
    result_data = serializers.DictField(required=False, default=dict)


class ExportRequestSerializer(serializers.Serializer):
    """Validates the /api/export/ request body."""

    rows = serializers.ListField(child=serializers.DictField())
    city = serializers.CharField(max_length=100, default='Chennai')
    report_date = serializers.DateField(required=False, allow_null=True)


class ManualWOSerializer(serializers.Serializer):
    """Validates manual WO addition."""

    ticket_no = serializers.CharField(max_length=20)
    case_id = serializers.CharField(max_length=20, required=False, default='', allow_blank=True)
    product = serializers.CharField(max_length=255, required=False, default='', allow_blank=True)
    wip_aging = serializers.IntegerField(required=False, default=0)
    location = serializers.CharField(max_length=255, required=False, default='', allow_blank=True)
    segment = serializers.CharField(max_length=50, required=False, default='', allow_blank=True)
    classification = serializers.CharField(max_length=10, default='NEW', allow_blank=True)
    morning_status = serializers.CharField(max_length=100, required=False, default='To be scheduled', allow_blank=True)
    evening_status = serializers.CharField(max_length=100, required=False, default='', allow_blank=True)
    engineer = serializers.CharField(max_length=100, required=False, default='', allow_blank=True)
    contact_no = serializers.CharField(max_length=20, required=False, default='', allow_blank=True)
    parts = serializers.CharField(required=False, default='', allow_blank=True)
    month = serializers.CharField(max_length=20, required=False, default='', allow_blank=True)
    wo_otc_code = serializers.CharField(max_length=100, required=False, default='', allow_blank=True)
    hp_owner = serializers.CharField(max_length=100, required=False, default='Manual', allow_blank=True)
    flex_status = serializers.CharField(max_length=100, required=False, default='Manual Entry', allow_blank=True)
    wip_changed = serializers.CharField(max_length=10, required=False, default='New', allow_blank=True)
    current_status_tat = serializers.CharField(max_length=255, required=False, default='', allow_blank=True)
    city = serializers.CharField(max_length=100, default='Chennai', allow_blank=True)
    report_date = serializers.DateField(required=False, allow_null=True)


class ClosedCallRequestSerializer(serializers.Serializer):
    """Validates request to mark a call as closed."""

    ticket_no = serializers.CharField(max_length=20)
    case_id = serializers.CharField(max_length=20, required=False, default='', allow_blank=True)
    product = serializers.CharField(max_length=255, required=False, default='', allow_blank=True)
    wip_aging = serializers.IntegerField(required=False, default=0)
    location = serializers.CharField(max_length=255, required=False, default='', allow_blank=True)
    segment = serializers.CharField(max_length=50, required=False, default='', allow_blank=True)
    engineer = serializers.CharField(max_length=100, required=False, default='', allow_blank=True)
    contact_no = serializers.CharField(max_length=20, required=False, default='', allow_blank=True)
    parts = serializers.CharField(required=False, default='', allow_blank=True)
    month = serializers.CharField(max_length=20, required=False, default='', allow_blank=True)
    wo_otc_code = serializers.CharField(max_length=100, required=False, default='', allow_blank=True)
    hp_owner = serializers.CharField(max_length=100, required=False, default='', allow_blank=True)
    flex_status = serializers.CharField(max_length=100, required=False, default='', allow_blank=True)
    morning_status = serializers.CharField(max_length=100, required=False, default='Closed', allow_blank=True)
    evening_status = serializers.CharField(max_length=100, required=False, default='', allow_blank=True)
    current_status_tat = serializers.CharField(max_length=255, required=False, default='', allow_blank=True)
    city = serializers.CharField(max_length=100, default='Chennai', allow_blank=True)
    report_date = serializers.DateField(required=False, allow_null=True)

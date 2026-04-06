from rest_framework import serializers
from .models import UploadedFile, CallPlanRecord


class UploadedFileSerializer(serializers.ModelSerializer):
    class Meta:
        model = UploadedFile
        fields = [
            'id', 'file', 'file_type', 'original_name', 'uploaded_by',
            'uploaded_at', 'city', 'report_date', 'file_size', 'row_count',
        ]
        read_only_fields = ['id', 'uploaded_at', 'file_size', 'row_count']


class UploadedFileListSerializer(serializers.ModelSerializer):
    """Lighter serializer for list views (no file field)."""

    class Meta:
        model = UploadedFile
        fields = [
            'id', 'file_type', 'original_name', 'uploaded_by',
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
            'current_status_tat', 'created_at',
        ]
        read_only_fields = ['id', 'created_at']


class UploadedFileDetailSerializer(serializers.ModelSerializer):
    """File detail with nested records."""

    records = CallPlanRecordSerializer(many=True, read_only=True)

    class Meta:
        model = UploadedFile
        fields = [
            'id', 'file', 'file_type', 'original_name', 'uploaded_at',
            'city', 'report_date', 'file_size', 'row_count', 'records',
        ]


class ProcessRequestSerializer(serializers.Serializer):
    """Validates the /api/process/ request body."""

    flex_file_id = serializers.IntegerField()
    callplan_file_id = serializers.IntegerField(required=False, allow_null=True)
    city = serializers.CharField(max_length=100, default='Chennai')
    report_date = serializers.DateField(required=False, allow_null=True)


class ExportRequestSerializer(serializers.Serializer):
    """Validates the /api/export/ request body."""

    rows = serializers.ListField(child=serializers.DictField())
    city = serializers.CharField(max_length=100, default='Chennai')
    report_date = serializers.DateField(required=False, allow_null=True)

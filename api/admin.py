from django.contrib import admin
from .models import UploadedFile, CallPlanRecord


@admin.register(UploadedFile)
class UploadedFileAdmin(admin.ModelAdmin):
    list_display = ['id', 'original_name', 'file_type', 'city', 'report_date', 'row_count', 'uploaded_at']
    list_filter = ['file_type', 'city', 'uploaded_at']
    search_fields = ['original_name']
    readonly_fields = ['uploaded_at', 'file_size', 'row_count']


@admin.register(CallPlanRecord)
class CallPlanRecordAdmin(admin.ModelAdmin):
    list_display = ['id', 'ticket_no', 'classification', 'product', 'wip_aging', 'segment', 'engineer']
    list_filter = ['classification', 'segment']
    search_fields = ['ticket_no', 'case_id', 'product', 'engineer']
    raw_id_fields = ['upload']

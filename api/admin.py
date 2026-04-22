from django.contrib import admin
from .models import UserProfile, UploadedFile, CallPlanRecord, UploadSession, AnalysisResult, ClosedCall


@admin.register(UserProfile)
class UserProfileAdmin(admin.ModelAdmin):
    list_display = ['user', 'region']
    list_filter = ['region']
    search_fields = ['user__username', 'region']


@admin.register(UploadSession)
class UploadSessionAdmin(admin.ModelAdmin):
    list_display = ['id', 'uploaded_by', 'city', 'report_date', 'created_at']
    list_filter = ['city', 'created_at']
    search_fields = ['uploaded_by']


@admin.register(UploadedFile)
class UploadedFileAdmin(admin.ModelAdmin):
    list_display = ['id', 'original_name', 'file_type', 'session', 'city', 'report_date', 'row_count', 'uploaded_at']
    list_filter = ['file_type', 'city', 'uploaded_at']
    search_fields = ['original_name']
    readonly_fields = ['uploaded_at', 'file_size', 'row_count']
    raw_id_fields = ['session']


@admin.register(CallPlanRecord)
class CallPlanRecordAdmin(admin.ModelAdmin):
    list_display = ['id', 'ticket_no', 'classification', 'source', 'product', 'wip_aging', 'segment', 'engineer']
    list_filter = ['classification', 'segment', 'source']
    search_fields = ['ticket_no', 'case_id', 'product', 'engineer']
    raw_id_fields = ['upload']


@admin.register(AnalysisResult)
class AnalysisResultAdmin(admin.ModelAdmin):
    list_display = ['id', 'city', 'report_date', 'analyzed_by', 'total_count', 'pending_count', 'new_count', 'dropped_count', 'analyzed_at']
    list_filter = ['city', 'analyzed_at']
    search_fields = ['analyzed_by']
    raw_id_fields = ['session', 'flex_file', 'callplan_file']


@admin.register(ClosedCall)
class ClosedCallAdmin(admin.ModelAdmin):
    list_display = ['id', 'ticket_no', 'city', 'report_date', 'engineer', 'closed_by', 'closed_at']
    list_filter = ['city', 'closed_at', 'report_date']
    search_fields = ['ticket_no', 'engineer', 'closed_by']

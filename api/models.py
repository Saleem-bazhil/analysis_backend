from django.conf import settings
from django.db import models


class UserProfile(models.Model):
    """Extends the built-in User with a region (city) assignment for RBAC."""

    user = models.OneToOneField(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='profile',
    )
    region = models.CharField(
        max_length=100, blank=True, default='',
        help_text='City/region this user belongs to. Empty means admin (all regions).',
    )

    def __str__(self):
        return f"{self.user.username} — {self.region or 'All Regions'}"


class UploadSession(models.Model):
    """Groups both uploaded files (flex + rtpl) together as one upload session."""

    uploaded_by = models.CharField(max_length=100, default='admin', db_index=True)
    city = models.CharField(max_length=100, default='Chennai')
    report_date = models.DateField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-created_at']

    def __str__(self):
        return f"Session #{self.id} by {self.uploaded_by} - {self.city} ({self.report_date})"


class UploadedFile(models.Model):
    """Stores every uploaded Excel/CSV file."""

    FILE_TYPES = [
        ('flex_wip', 'Flex WIP Report'),
        ('call_plan', 'Yesterday Call Plan'),
        ('generated', 'Generated Call Plan'),
    ]

    session = models.ForeignKey(
        UploadSession, on_delete=models.CASCADE, related_name='files',
        null=True, blank=True,
    )
    file = models.FileField(upload_to='uploads/%Y/%m/%d/')
    file_type = models.CharField(max_length=20, choices=FILE_TYPES)
    original_name = models.CharField(max_length=255)
    uploaded_by = models.CharField(max_length=100, default='admin', db_index=True)
    uploaded_at = models.DateTimeField(auto_now_add=True)
    city = models.CharField(max_length=100, default='Chennai')
    report_date = models.DateField(null=True, blank=True)
    file_size = models.IntegerField(default=0)
    row_count = models.IntegerField(default=0, help_text='Number of data rows')

    class Meta:
        ordering = ['-uploaded_at']

    def __str__(self):
        return f"{self.original_name} ({self.file_type}) by {self.uploaded_by} - {self.uploaded_at:%Y-%m-%d %H:%M}"


class CallPlanRecord(models.Model):
    """Stores individual call plan records for history."""

    CLASSIFICATION_CHOICES = [
        ('PENDING', 'Pending'),
        ('NEW', 'New'),
        ('DROPPED', 'Dropped'),
    ]

    SOURCE_CHOICES = [
        ('analysis', 'From Analysis'),
        ('manual', 'Manually Added'),
        ('export', 'From Export'),
    ]

    upload = models.ForeignKey(
        UploadedFile, on_delete=models.CASCADE, related_name='records',
        null=True, blank=True,
    )
    ticket_no = models.CharField(max_length=20, db_index=True)
    case_id = models.CharField(max_length=20, blank=True)
    product = models.CharField(max_length=255, blank=True)
    wip_aging = models.IntegerField(default=0)
    location = models.CharField(max_length=255, blank=True)
    segment = models.CharField(max_length=50, blank=True)
    classification = models.CharField(max_length=10, choices=CLASSIFICATION_CHOICES)
    morning_status = models.CharField(max_length=100, blank=True)
    evening_status = models.CharField(max_length=100, blank=True)
    engineer = models.CharField(max_length=100, blank=True)
    contact_no = models.CharField(max_length=20, blank=True)
    parts = models.TextField(blank=True)
    month = models.CharField(max_length=20, blank=True)
    wo_otc_code = models.CharField(max_length=100, blank=True)
    hp_owner = models.CharField(max_length=100, blank=True)
    flex_status = models.CharField(max_length=100, blank=True)
    wip_changed = models.CharField(max_length=10, blank=True)
    current_status_tat = models.CharField(max_length=255, blank=True)
    source = models.CharField(max_length=10, choices=SOURCE_CHOICES, default='export')
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-wip_aging']

    def __str__(self):
        return f"{self.ticket_no} - {self.classification} ({self.source})"


class AnalysisResult(models.Model):
    """Stores processed/analyzed data after /api/process/ is called."""

    session = models.ForeignKey(
        UploadSession, on_delete=models.CASCADE, related_name='analyses',
        null=True, blank=True,
    )
    flex_file = models.ForeignKey(
        UploadedFile, on_delete=models.SET_NULL, null=True, related_name='flex_analyses',
    )
    callplan_file = models.ForeignKey(
        UploadedFile, on_delete=models.SET_NULL, null=True, blank=True,
        related_name='callplan_analyses',
    )
    city = models.CharField(max_length=100, default='Chennai')
    report_date = models.DateField(null=True, blank=True)
    analyzed_by = models.CharField(max_length=100, default='admin')
    analyzed_at = models.DateTimeField(auto_now_add=True)

    # Summary counts
    total_count = models.IntegerField(default=0)
    pending_count = models.IntegerField(default=0)
    new_count = models.IntegerField(default=0)
    dropped_count = models.IntegerField(default=0)

    # Full result data stored as JSON
    result_data = models.JSONField(default=dict)

    class Meta:
        ordering = ['-analyzed_at']

    def __str__(self):
        return f"Analysis #{self.id} - {self.city} ({self.report_date}) by {self.analyzed_by}"


class ClosedCall(models.Model):
    """Separate tracking table for calls marked as closed in morning report."""

    ticket_no = models.CharField(max_length=20, db_index=True)
    case_id = models.CharField(max_length=20, blank=True)
    product = models.CharField(max_length=255, blank=True)
    wip_aging = models.IntegerField(default=0)
    location = models.CharField(max_length=255, blank=True)
    segment = models.CharField(max_length=50, blank=True)
    engineer = models.CharField(max_length=100, blank=True)
    contact_no = models.CharField(max_length=20, blank=True)
    parts = models.TextField(blank=True)
    month = models.CharField(max_length=20, blank=True)
    wo_otc_code = models.CharField(max_length=100, blank=True)
    hp_owner = models.CharField(max_length=100, blank=True)
    flex_status = models.CharField(max_length=100, blank=True)
    morning_status = models.CharField(max_length=100, blank=True)
    evening_status = models.CharField(max_length=100, blank=True)
    current_status_tat = models.CharField(max_length=255, blank=True)
    city = models.CharField(max_length=100, default='Chennai')
    report_date = models.DateField(null=True, blank=True)
    closed_by = models.CharField(max_length=100, default='admin')
    closed_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-closed_at']

    def __str__(self):
        return f"Closed: {self.ticket_no} - {self.city} ({self.report_date})"


class WorkspaceState(models.Model):
    """Stores the latest state of the global workspace for synchronization."""
    updated_at = models.DateTimeField(auto_now=True)
    state = models.JSONField(default=dict)

    class Meta:
        ordering = ['-updated_at']

    def __str__(self):
        return f"WorkspaceState last updated at {self.updated_at}"

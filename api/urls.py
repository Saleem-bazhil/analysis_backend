from django.urls import path
from . import views
from . import auth_views

urlpatterns = [
    # Auth
    path('auth/login/', auth_views.login, name='auth-login'),
    path('auth/refresh/', auth_views.token_refresh, name='auth-refresh'),
    path('auth/me/', auth_views.me, name='auth-me'),

    # Upload Sessions
    path('sessions/', views.create_upload_session, name='create-session'),
    path('sessions/list/', views.list_upload_sessions, name='list-sessions'),
    path('sessions/<int:pk>/', views.session_detail, name='session-detail'),

    # File Upload & Management
    path('upload/', views.upload_file, name='upload-file'),
    path('files/', views.list_files, name='list-files'),
    path('files/<int:pk>/', views.file_detail, name='file-detail'),

    # Processing & Analysis
    path('process/', views.process_files, name='process-files'),
    path('analyses/', views.list_analyses, name='list-analyses'),
    path('analyses/save/', views.save_analysis, name='save-analysis'),
    path('analyses/<int:pk>/', views.analysis_detail, name='analysis-detail'),

    # Manual WO
    path('manual-wo/', views.add_manual_wo, name='add-manual-wo'),

    # Closed Calls
    path('closed-calls/', views.mark_closed_call, name='mark-closed-call'),
    path('closed-calls/list/', views.list_closed_calls, name='list-closed-calls'),

    # Export & History
    path('export/', views.export_file, name='export-file'),
    path('history/', views.history, name='history'),

    # Workspace Sync
    path('workspace/', views.workspace_state, name='workspace-state'),
]

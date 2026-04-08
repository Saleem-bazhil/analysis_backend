from django.urls import path
from . import views
from . import auth_views

urlpatterns = [
    # Auth
    path('auth/login/', auth_views.login, name='auth-login'),
    path('auth/refresh/', auth_views.token_refresh, name='auth-refresh'),
    path('auth/me/', auth_views.me, name='auth-me'),

    # Existing API
    path('upload/', views.upload_file, name='upload-file'),
    path('process/', views.process_files, name='process-files'),
    path('files/', views.list_files, name='list-files'),
    path('files/<int:pk>/', views.file_detail, name='file-detail'),
    path('export/', views.export_file, name='export-file'),
    path('history/', views.history, name='history'),
    path('workspace/', views.workspace_state, name='workspace-state'),
]

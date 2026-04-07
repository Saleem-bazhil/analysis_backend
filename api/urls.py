from django.urls import path
from . import views

urlpatterns = [
    path('upload/', views.upload_file, name='upload-file'),
    path('process/', views.process_files, name='process-files'),
    path('files/', views.list_files, name='list-files'),
    path('files/<int:pk>/', views.file_detail, name='file-detail'),
    path('export/', views.export_file, name='export-file'),
    path('history/', views.history, name='history'),
    path('workspace/', views.workspace_state, name='workspace-state'),
]

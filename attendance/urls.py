from django.urls import path
from . import views

urlpatterns = [
    path('', views.student_dashboard_view, name='home'),
    path('student/dashboard/', views.student_dashboard_view, name='student_dashboard'),
    path('teacher/dashboard/', views.teacher_dashboard_view, name='teacher_dashboard'),
    path('teacher/take-attendance/', views.take_attendance_view, name='take_attendance'),
    path('teacher/dataset-manager/', views.teacher_dataset_view, name='teacher_dataset'),
    path('teacher/students/', views.student_list_view, name='student_list'),
    path('export-csv/<int:session_id>/', views.export_attendance_csv, name='export_attendance_csv'),
    
    # API Endpoints (No Django forms)
    path('api/process-frame/', views.api_process_frame, name='api_process_frame'),
    path('api/upload-classroom-image/', views.api_upload_classroom_image, name='api_upload_classroom_image'),
    path('api/upload-student-face/', views.api_upload_student_face, name='api_upload_student_face'),
    path('api/save-session/', views.api_save_session, name='api_save_session'),
    path('api/sync-dataset/', views.api_sync_dataset, name='api_sync_dataset'),
]

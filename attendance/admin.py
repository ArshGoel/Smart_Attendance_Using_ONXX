from django.contrib import admin
from .models import Subject, AttendanceSession, AttendanceEntry, StudentEmbedding

@admin.register(Subject)
class SubjectAdmin(admin.ModelAdmin):
    list_display = ('code', 'name', 'department', 'teacher')
    search_fields = ('code', 'name', 'department')
    list_filter = ('department',)

@admin.register(AttendanceSession)
class AttendanceSessionAdmin(admin.ModelAdmin):
    list_display = ('subject', 'date', 'time_slot', 'created_by', 'created_at')
    list_filter = ('date', 'subject', 'time_slot')
    search_fields = ('subject__code', 'subject__name')

@admin.register(AttendanceEntry)
class AttendanceEntryAdmin(admin.ModelAdmin):
    list_display = ('session', 'roll_number', 'student_name', 'status', 'confidence', 'marked_at')
    list_filter = ('status', 'session__date', 'session__subject')
    search_fields = ('roll_number', 'student_name', 'session__subject__code')

@admin.register(StudentEmbedding)
class StudentEmbeddingAdmin(admin.ModelAdmin):
    list_display = ('roll_number', 'student_name', 'image_url', 'updated_at')
    search_fields = ('roll_number', 'student_name')

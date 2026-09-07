from django.contrib import admin
from .models import UserProfile

@admin.register(UserProfile)
class UserProfileAdmin(admin.ModelAdmin):
    list_display = ('user', 'role', 'roll_number', 'teacher_id', 'full_name', 'department', 'created_at')
    list_filter = ('role', 'department')
    search_fields = ('user__username', 'roll_number', 'teacher_id', 'full_name')

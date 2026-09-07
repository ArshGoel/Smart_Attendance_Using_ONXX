from django.db import models
from django.contrib.auth.models import User

class UserProfile(models.Model):
    ROLE_CHOICES = (
        ('TEACHER', 'Teacher'),
        ('STUDENT', 'Student'),
    )
    
    user = models.OneToOneField(User, on_delete=models.CASCADE, related_name='profile')
    role = models.CharField(max_length=20, choices=ROLE_CHOICES, default='STUDENT')
    roll_number = models.CharField(max_length=50, blank=True, null=True, db_index=True)
    teacher_id = models.CharField(max_length=50, blank=True, null=True)
    full_name = models.CharField(max_length=150, blank=True, default='')
    department = models.CharField(max_length=100, default='Computer Science & Engineering')
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"{self.user.username} ({self.get_role_display()})"
    
    @property
    def is_teacher(self):
        return self.role == 'TEACHER'
        
    @property
    def is_student(self):
        return self.role == 'STUDENT'

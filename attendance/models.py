from django.db import models
from django.contrib.auth.models import User
import json

class Subject(models.Model):
    code = models.CharField(max_length=20, unique=True)
    name = models.CharField(max_length=150)
    department = models.CharField(max_length=100, default='Computer Science')
    teacher = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True, related_name='subjects')

    def __str__(self):
        return f"{self.code} - {self.name}"

class AttendanceSession(models.Model):
    subject = models.ForeignKey(Subject, on_delete=models.CASCADE, related_name='sessions')
    date = models.DateField()
    time_slot = models.CharField(max_length=50, default='09:30 AM - 10:30 AM')
    created_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True)
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"{self.subject.code} Session on {self.date} ({self.time_slot})"

class AttendanceEntry(models.Model):
    STATUS_CHOICES = (
        ('PRESENT', 'Present'),
        ('ABSENT', 'Absent'),
    )
    
    session = models.ForeignKey(AttendanceSession, on_delete=models.CASCADE, related_name='entries')
    student_user = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True)
    roll_number = models.CharField(max_length=50, db_index=True)
    student_name = models.CharField(max_length=150, blank=True, default='')
    status = models.CharField(max_length=10, choices=STATUS_CHOICES, default='ABSENT')
    confidence = models.FloatField(default=1.0)
    marked_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        unique_together = ('session', 'roll_number')

    def __str__(self):
        return f"{self.roll_number} - {self.session.subject.code}: {self.status}"

class StudentEmbedding(models.Model):
    roll_number = models.CharField(max_length=50, unique=True, db_index=True)
    student_name = models.CharField(max_length=150, blank=True, default='')
    embedding_json = models.TextField()  # JSON string of float vector
    image_path = models.CharField(max_length=255, blank=True, default='')
    image_url = models.URLField(max_length=500, blank=True, null=True)
    updated_at = models.DateTimeField(auto_now=True)

    def get_embedding(self):
        try:
            return json.loads(self.embedding_json)
        except Exception:
            return []

    def set_embedding(self, vector_list):
        self.embedding_json = json.dumps(vector_list)

    def __str__(self):
        return f"Embedding for {self.roll_number}"

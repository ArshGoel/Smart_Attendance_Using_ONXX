from django.core.management.base import BaseCommand
from django.conf import settings
from django.contrib.auth.models import User
from accounts.models import UserProfile
from attendance.models import Subject, StudentEmbedding
from attendance.face_engine import sync_dataset_to_db

class Command(BaseCommand):
    help = 'Syncs face embeddings from dataset/ directory to Database and initializes default accounts and subjects.'

    def handle(self, *args, **options):
        self.stdout.write(self.style.SUCCESS("Starting dataset embedding synchronization..."))
        
        # Sync face embeddings
        dataset_path = settings.BASE_DIR / 'dataset'
        result = sync_dataset_to_db(dataset_path, StudentEmbedding)
        self.stdout.write(self.style.SUCCESS(f"Embeddings Sync Result: {result}"))

        # Create Default Teacher Account
        teacher_user, t_created = User.objects.get_or_create(
            username='teacher',
            defaults={
                'first_name': 'Prof.',
                'last_name': 'Sharma',
                'email': 'teacher@cmrec.ac.in',
                'is_staff': True
            }
        )
        if t_created:
            teacher_user.set_password('teacher123')
            teacher_user.save()
            self.stdout.write(self.style.SUCCESS("Created default Teacher user: teacher / teacher123"))

        UserProfile.objects.get_or_create(
            user=teacher_user,
            defaults={
                'role': 'TEACHER',
                'teacher_id': 'T1001',
                'full_name': 'Dr. Rajesh Sharma',
                'department': 'Computer Science & Engineering'
            }
        )

        # Create Default Subjects
        default_subjects = [
            ('CS501', 'Computer Networks & Security'),
            ('CS502', 'Machine Learning & Deep Learning'),
            ('CS503', 'Database Management Systems'),
            ('CS504', 'Cloud Computing & Serverless Architecture'),
        ]

        for code, name in default_subjects:
            sub, created = Subject.objects.get_or_create(
                code=code,
                defaults={
                    'name': name,
                    'department': 'Computer Science & Engineering',
                    'teacher': teacher_user
                }
            )
            if created:
                self.stdout.write(self.style.SUCCESS(f"Created Subject: {code} - {name}"))

        # Ensure student accounts exist for all enrolled students
        all_embeddings = StudentEmbedding.objects.all()
        created_count = 0
        for emb in all_embeddings:
            roll = emb.roll_number
            user, u_created = User.objects.get_or_create(
                username=roll.lower(),
                defaults={
                    'first_name': 'Student',
                    'last_name': roll,
                    'email': f"{roll.lower()}@cmrec.ac.in"
                }
            )
            if u_created:
                user.set_password('student123')
                user.save()
                created_count += 1

            UserProfile.objects.get_or_create(
                user=user,
                defaults={
                    'role': 'STUDENT',
                    'roll_number': roll,
                    'full_name': f"Student {roll}",
                    'department': 'Computer Science & Engineering'
                }
            )

        self.stdout.write(self.style.SUCCESS(f"Dataset sync finished! Created {created_count} student accounts."))

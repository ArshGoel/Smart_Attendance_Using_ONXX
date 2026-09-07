import json
import csv
import logging
import numpy as np
import cv2
from datetime import datetime, date
from django.shortcuts import render, redirect, get_object_or_404
from django.http import JsonResponse, HttpResponse
from django.contrib.auth.decorators import login_required
from django.contrib.auth.models import User
from django.conf import settings
from accounts.models import UserProfile
from .models import Subject, AttendanceSession, AttendanceEntry, StudentEmbedding
from .face_engine import decode_base64_image, match_faces_in_frame, extract_faces_from_image, sync_dataset_to_db

logger = logging.getLogger(__name__)

@login_required
def student_dashboard_view(request):
    user = request.user
    if hasattr(user, 'profile') and user.profile.is_teacher:
        return redirect('teacher_dashboard')

    roll_number = getattr(user.profile, 'roll_number', '') or user.username

    # Fetch attendance entries for this student
    entries = AttendanceEntry.objects.filter(roll_number__iexact=roll_number).select_related('session', 'session__subject').order_by('-session__date')
    
    total_classes = entries.count()
    present_count = entries.filter(status='PRESENT').count()
    absent_count = total_classes - present_count
    attendance_percentage = round((present_count / total_classes * 100), 1) if total_classes > 0 else 100.0

    # Subject-wise breakdown
    subjects_data = []
    all_subjects = Subject.objects.all()
    for sub in all_subjects:
        sub_entries = entries.filter(session__subject=sub)
        sub_total = sub_entries.count()
        sub_present = sub_entries.filter(status='PRESENT').count()
        sub_pct = round((sub_present / sub_total * 100), 1) if sub_total > 0 else 0.0
        subjects_data.append({
            'code': sub.code,
            'name': sub.name,
            'total': sub_total,
            'present': sub_present,
            'absent': sub_total - sub_present,
            'percentage': sub_pct
        })

    context = {
        'student_name': user.profile.full_name or user.username,
        'roll_number': roll_number,
        'department': user.profile.department,
        'total_classes': total_classes,
        'present_count': present_count,
        'absent_count': absent_count,
        'attendance_percentage': attendance_percentage,
        'subjects_data': subjects_data,
        'recent_entries': entries[:10]
    }
    return render(request, 'student/dashboard.html', context)

@login_required
def teacher_dashboard_view(request):
    user = request.user
    if hasattr(user, 'profile') and not user.profile.is_teacher:
        return redirect('student_dashboard')

    subjects = Subject.objects.filter(teacher=user) if user.subjects.exists() else Subject.objects.all()
    total_students = StudentEmbedding.objects.count()
    total_sessions = AttendanceSession.objects.count()
    today_sessions = AttendanceSession.objects.filter(date=date.today()).count()

    recent_sessions = AttendanceSession.objects.select_related('subject').order_by('-created_at')[:5]

    context = {
        'teacher_name': user.profile.full_name or user.username,
        'department': user.profile.department,
        'total_students': total_students,
        'total_sessions': total_sessions,
        'today_sessions': today_sessions,
        'subjects': subjects,
        'recent_sessions': recent_sessions
    }
    return render(request, 'teacher/dashboard.html', context)

@login_required
def take_attendance_view(request):
    if hasattr(request.user, 'profile') and not request.user.profile.is_teacher:
        return redirect('student_dashboard')

    subjects = Subject.objects.all()
    students = StudentEmbedding.objects.all().order_by('roll_number')
    
    context = {
        'subjects': subjects,
        'students': students,
        'today_date': date.today().strftime('%Y-%m-%d')
    }
    return render(request, 'teacher/take_attendance.html', context)

@login_required
def teacher_dataset_view(request):
    if hasattr(request.user, 'profile') and not request.user.profile.is_teacher:
        return redirect('student_dashboard')

    students = StudentEmbedding.objects.all().order_by('roll_number')
    context = {
        'students': students,
        'total_count': students.count()
    }
    return render(request, 'teacher/dataset_manager.html', context)

@login_required
def api_process_frame(request):
    if request.method != 'POST':
        return JsonResponse({'status': 'error', 'message': 'Only POST allowed'}, status=405)

    try:
        body = json.loads(request.body)
        frame_base64 = body.get('frame', '')
        if not frame_base64:
            return JsonResponse({'status': 'error', 'message': 'No frame provided'}, status=400)

        img_bgr = decode_base64_image(frame_base64)
        if img_bgr is None:
            return JsonResponse({'status': 'error', 'message': 'Failed to decode image frame'}, status=400)

        # Retrieve registered embeddings from DB
        db_embeddings = StudentEmbedding.objects.all()
        registered = []
        for item in db_embeddings:
            emb = item.get_embedding()
            if emb:
                registered.append({
                    'roll_number': item.roll_number,
                    'name': item.student_name or f"Student {item.roll_number}",
                    'embedding': emb
                })

        matches = match_faces_in_frame(img_bgr, registered, threshold=0.38)
        return JsonResponse({'status': 'success', 'faces': matches})
    except Exception as e:
        return JsonResponse({'status': 'error', 'message': str(e)}, status=500)

@login_required
def api_upload_classroom_image(request):
    """
    Endpoint receiving single or MULTIPLE uploaded classroom group photos:
    1. Uploads each photo to Cloudinary
    2. Runs face recognition on each photo
    3. Deduplicates detected students across multiple photos (keeping highest confidence match)
    4. Returns photo details array and deduplicated list of unique presentees
    """
    if request.method != 'POST':
        return JsonResponse({'status': 'error', 'message': 'Only POST allowed'}, status=405)

    # Get multiple uploaded files or single file fallback
    image_files = request.FILES.getlist('classroom_images') or request.FILES.getlist('classroom_image')
    if not image_files and request.FILES.get('classroom_image'):
        image_files = [request.FILES.get('classroom_image')]

    if not image_files:
        return JsonResponse({'status': 'error', 'message': 'No image files uploaded'}, status=400)

    try:
        # Load registered embeddings from DB
        db_embeddings = StudentEmbedding.objects.all()
        registered = []
        for item in db_embeddings:
            emb = item.get_embedding()
            if emb:
                registered.append({
                    'roll_number': item.roll_number,
                    'name': item.student_name or f"Student {item.roll_number}",
                    'embedding': emb
                })

        photos_results = []
        merged_students_map = {} # roll_number -> student_dict (deduplicated)

        for idx, img_file in enumerate(image_files, start=1):
            file_bytes = img_file.read()
            nparr = np.frombuffer(file_bytes, np.uint8)
            img_bgr = cv2.imdecode(nparr, cv2.IMREAD_COLOR)

            if img_bgr is None:
                continue

            # Upload photo to Cloudinary if configured
            cloudinary_url = None
            if getattr(settings, 'CLOUDINARY_CLOUD_NAME', None):
                try:
                    import cloudinary.uploader
                    img_file.seek(0)
                    upload_res = cloudinary.uploader.upload(img_file, folder="scms_classroom_photos")
                    cloudinary_url = upload_res.get('secure_url')
                except Exception as e:
                    logger.error(f"Cloudinary upload failed for photo #{idx}: {e}")

            matches = match_faces_in_frame(img_bgr, registered, threshold=0.38)
            h, w = img_bgr.shape[:2]

            photos_results.append({
                'photo_index': idx,
                'file_name': img_file.name,
                'cloudinary_url': cloudinary_url,
                'image_width': w,
                'image_height': h,
                'faces': matches,
                'detected_count': len(matches)
            })

            # Deduplicate students across multiple photos
            for face in matches:
                roll = face.get('roll_number')
                if not roll or roll == 'UNKNOWN':
                    continue

                if roll not in merged_students_map:
                    merged_students_map[roll] = {
                        'roll_number': roll,
                        'student_name': face.get('student_name', f"Student {roll}"),
                        'confidence': face.get('confidence', 100.0),
                        'status': 'PRESENT',
                        'photo_appearances': [idx]
                    }
                else:
                    # Update highest confidence and append photo appearance
                    existing = merged_students_map[roll]
                    existing['confidence'] = max(existing['confidence'], face.get('confidence', 0.0))
                    if idx not in existing['photo_appearances']:
                        existing['photo_appearances'].append(idx)

        unique_students_list = list(merged_students_map.values())

        return JsonResponse({
            'status': 'success',
            'total_photos': len(photos_results),
            'photos': photos_results,
            'unique_students': unique_students_list,
            'total_unique_present': len(unique_students_list)
        })
    except Exception as e:
        return JsonResponse({'status': 'error', 'message': str(e)}, status=500)

@login_required
def api_upload_student_face(request):
    """
    Teacher Dataset Manager endpoint:
    Accepts single or MULTIPLE face photos for a student, uploads to Cloudinary,
    extracts 512D ArcFace vectors across all images, computes centroid embedding vector, and updates DB!
    """
    if request.method != 'POST':
        return JsonResponse({'status': 'error', 'message': 'Only POST allowed'}, status=405)

    roll_number = request.POST.get('roll_number', '').strip().upper()
    student_name = request.POST.get('student_name', '').strip()
    photo_files = request.FILES.getlist('student_photos') or request.FILES.getlist('student_photo')

    if not roll_number or not photo_files:
        return JsonResponse({'status': 'error', 'message': 'Roll Number and Student Photo(s) are required'}, status=400)

    try:
        cloudinary_urls = []
        extracted_vectors = []
        for idx, photo_file in enumerate(photo_files, start=1):
            file_bytes = photo_file.read()
            nparr = np.frombuffer(file_bytes, np.uint8)
            img_bgr = cv2.imdecode(nparr, cv2.IMREAD_COLOR)

            if img_bgr is None:
                continue

            # Upload photo to Cloudinary under scms_student_dataset/<roll_number>/
            if getattr(settings, 'CLOUDINARY_CLOUD_NAME', None):
                try:
                    import cloudinary.uploader
                    photo_file.seek(0)
                    res = cloudinary.uploader.upload(
                        photo_file,
                        public_id=f"{roll_number}_photo_{idx}",
                        folder=f"scms_student_dataset/{roll_number}",
                        overwrite=True
                    )
                    cloud_url = res.get('secure_url')
                    if cloud_url:
                        cloudinary_urls.append(cloud_url)
                except Exception as e:
                    logger.error(f"Cloudinary dataset photo upload error for {roll_number} (#{idx}): {e}")

            faces = extract_faces_from_image(img_bgr)
            if faces:
                extracted_vectors.append(faces[0]['embedding'])

        primary_cloudinary_url = cloudinary_urls[0] if cloudinary_urls else None

        if not extracted_vectors:
            return JsonResponse({'status': 'error', 'message': 'No face detected in uploaded photo(s)! Please upload clear frontal face images.'}, status=400)

        # Compute centroid embedding across all uploaded photos for maximum accuracy
        from .face_engine import compute_centroid_embedding
        final_embedding = compute_centroid_embedding(extracted_vectors)

        # Update or create StudentEmbedding record
        record, created = StudentEmbedding.objects.get_or_create(
            roll_number=roll_number,
            defaults={
                'student_name': student_name or f"Student {roll_number}",
                'image_url': primary_cloudinary_url or ''
            }
        )
        record.set_embedding(final_embedding)
        if student_name:
            record.student_name = student_name
        if primary_cloudinary_url:
            record.image_url = primary_cloudinary_url
        record.save()

        # Ensure User & UserProfile exist
        user, u_created = User.objects.get_or_create(
            username=roll_number.lower(),
            defaults={
                'first_name': student_name or 'Student',
                'last_name': roll_number,
                'email': f"{roll_number.lower()}@cmrec.ac.in"
            }
        )
        if u_created:
            user.set_password('student123')
            user.save()

        UserProfile.objects.get_or_create(
            user=user,
            defaults={
                'role': 'STUDENT',
                'roll_number': roll_number,
                'full_name': student_name or f"Student {roll_number}",
                'department': 'Computer Science & Engineering'
            }
        )

        return JsonResponse({
            'status': 'success',
            'roll_number': roll_number,
            'student_name': record.student_name,
            'image_url': primary_cloudinary_url,
            'photos_processed': len(extracted_vectors),
            'message': f"Enrolled {len(extracted_vectors)} photo(s) for {roll_number}! 512D Centroid Vector uploaded to Cloudinary & Database."
        })
    except Exception as e:
        return JsonResponse({'status': 'error', 'message': str(e)}, status=500)

@login_required
def api_save_session(request):
    if request.method != 'POST':
        return JsonResponse({'status': 'error', 'message': 'Only POST allowed'}, status=405)

    try:
        data = json.loads(request.body)
        subject_id = data.get('subject_id')
        session_date = data.get('date', str(date.today()))
        time_slot = data.get('time_slot', '09:30 AM - 10:30 AM')
        entries_data = data.get('entries', [])

        subject = get_object_or_404(Subject, id=subject_id)

        # Create or update session
        session, created = AttendanceSession.objects.get_or_create(
            subject=subject,
            date=session_date,
            time_slot=time_slot,
            defaults={'created_by': request.user}
        )

        for item in entries_data:
            roll = item.get('roll_number')
            if not roll or roll == 'UNKNOWN':
                continue
            status = item.get('status', 'ABSENT')
            confidence = float(item.get('confidence', 100.0))

            # Find matching student user if exists
            student_profile = UserProfile.objects.filter(roll_number__iexact=roll).first()
            student_user = student_profile.user if student_profile else None
            student_name = student_profile.full_name if student_profile else f"Student {roll}"

            AttendanceEntry.objects.update_or_create(
                session=session,
                roll_number=roll,
                defaults={
                    'student_user': student_user,
                    'student_name': student_name,
                    'status': status,
                    'confidence': confidence
                }
            )

        return JsonResponse({
            'status': 'success',
            'session_id': session.id,
            'message': f"Attendance session for {subject.name} saved successfully!"
        })
    except Exception as e:
        return JsonResponse({'status': 'error', 'message': str(e)}, status=500)

@login_required
def api_sync_dataset(request):
    try:
        dataset_path = settings.BASE_DIR / 'dataset'
        result = sync_dataset_to_db(dataset_path, StudentEmbedding)
        
        # Also ensure user accounts exist for all enrolled students
        all_embeddings = StudentEmbedding.objects.all()
        created_users = 0
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
                created_users += 1

            UserProfile.objects.get_or_create(
                user=user,
                defaults={
                    'role': 'STUDENT',
                    'roll_number': roll,
                    'full_name': f"Student {roll}",
                    'department': 'Computer Science & Engineering'
                }
            )
            
        result['users_created'] = created_users
        return JsonResponse({'status': 'success', 'data': result})
    except Exception as e:
        return JsonResponse({'status': 'error', 'message': str(e)}, status=500)

@login_required
def student_list_view(request):
    if hasattr(request.user, 'profile') and not request.user.profile.is_teacher:
        return redirect('student_dashboard')

    students = StudentEmbedding.objects.all().order_by('roll_number')
    context = {
        'students': students,
        'total_count': students.count()
    }
    return render(request, 'teacher/students.html', context)

@login_required
def export_attendance_csv(request, session_id):
    session = get_object_or_404(AttendanceSession, id=session_id)
    entries = session.entries.all().order_by('roll_number')

    response = HttpResponse(content_type='text/csv')
    response['Content-Disposition'] = f'attachment; filename="attendance_{session.subject.code}_{session.date}.csv"'

    writer = csv.writer(response)
    writer.writerow(['Roll Number', 'Student Name', 'Subject Code', 'Subject Name', 'Date', 'Time Slot', 'Status', 'Confidence Score (%)', 'Marked At'])

    for entry in entries:
        writer.writerow([
            entry.roll_number,
            entry.student_name,
            session.subject.code,
            session.subject.name,
            session.date,
            session.time_slot,
            entry.status,
            entry.confidence,
            entry.marked_at.strftime('%Y-%m-%d %H:%M:%S')
        ])

    return response

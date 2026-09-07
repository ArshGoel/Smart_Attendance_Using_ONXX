from django.shortcuts import render, redirect
from django.contrib import auth
from django.contrib.auth.models import User
from django.contrib import messages
from .models import UserProfile
from attendance.models import StudentEmbedding, Subject, AttendanceSession

def home_view(request):
    """
    Landing / Project Overview Home Page
    """
    context = {
        'total_students': StudentEmbedding.objects.count(),
        'total_subjects': Subject.objects.count(),
        'total_sessions': AttendanceSession.objects.count(),
    }
    return render(request, 'home.html', context)

def login_view(request):
    if request.user.is_authenticated:
        if hasattr(request.user, 'profile') and request.user.profile.is_teacher:
            return redirect('teacher_dashboard')
        return redirect('student_dashboard')

    error_message = None
    if request.method == 'POST':
        username = request.POST.get('username', '').strip()
        password = request.POST.get('password', '').strip()
        role = request.POST.get('role', 'STUDENT')

        if not username or not password:
            error_message = "Please provide both username/roll number and password."
        else:
            # Check authentication by username or roll number
            user = auth.authenticate(request, username=username, password=password)
            if user is None:
                # Try finding by roll number
                try:
                    profile = UserProfile.objects.filter(roll_number__iexact=username).first()
                    if profile:
                        user = auth.authenticate(request, username=profile.user.username, password=password)
                except Exception:
                    pass

            if user is not None:
                auth.login(request, user)
                # Ensure profile exists
                profile, created = UserProfile.objects.get_or_create(
                    user=user,
                    defaults={
                        'role': role,
                        'full_name': user.get_full_name() or user.username,
                        'roll_number': username if role == 'STUDENT' else ''
                    }
                )
                
                if profile.is_teacher:
                    return redirect('teacher_dashboard')
                else:
                    return redirect('student_dashboard')
            else:
                error_message = "Invalid credentials. Please check your Roll Number/ID and password."

    return render(request, 'accounts/login.html', {'error_message': error_message})

def register_view(request):
    if request.user.is_authenticated:
        if hasattr(request.user, 'profile') and request.user.profile.is_teacher:
            return redirect('teacher_dashboard')
        return redirect('student_dashboard')

    error_message = None
    success_message = None

    if request.method == 'POST':
        full_name = request.POST.get('full_name', '').strip()
        roll_number = request.POST.get('roll_number', '').strip().upper()
        email = request.POST.get('email', '').strip()
        department = request.POST.get('department', 'Computer Science & Engineering').strip()
        role = request.POST.get('role', 'STUDENT').upper()
        password = request.POST.get('password', '').strip()
        confirm_password = request.POST.get('confirm_password', '').strip()

        username = roll_number.lower() if role == 'STUDENT' else email.split('@')[0].lower()

        if not username or not password or not full_name:
            error_message = "All required fields must be filled out."
        elif password != confirm_password:
            error_message = "Passwords do not match."
        elif User.objects.filter(username=username).exists():
            error_message = f"An account with Roll Number/Username '{username}' already exists."
        else:
            try:
                user = User.objects.create_user(
                    username=username,
                    email=email or f"{username}@scms.edu",
                    password=password,
                    first_name=full_name.split()[0] if full_name else '',
                    last_name=' '.join(full_name.split()[1:]) if len(full_name.split()) > 1 else ''
                )

                profile = UserProfile.objects.create(
                    user=user,
                    role=role,
                    full_name=full_name,
                    roll_number=roll_number if role == 'STUDENT' else '',
                    department=department
                )

                if role == 'STUDENT' and roll_number:
                    StudentEmbedding.objects.get_or_create(
                        roll_number=roll_number,
                        defaults={'student_name': full_name}
                    )

                auth.login(request, user)
                messages.success(request, f"Welcome to SCMS, {full_name}! Account created successfully.")
                if profile.is_teacher:
                    return redirect('teacher_dashboard')
                return redirect('student_dashboard')
            except Exception as e:
                error_message = f"Failed to create account: {str(e)}"

    return render(request, 'accounts/register.html', {
        'error_message': error_message,
        'success_message': success_message
    })

def logout_view(request):
    auth.logout(request)
    messages.info(request, "You have been logged out successfully.")
    return redirect('login')

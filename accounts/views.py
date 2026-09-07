from django.shortcuts import render, redirect
from django.contrib import auth
from django.contrib.auth.models import User
from django.contrib import messages
from .models import UserProfile

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

def logout_view(request):
    auth.logout(request)
    messages.info(request, "You have been logged out successfully.")
    return redirect('login')

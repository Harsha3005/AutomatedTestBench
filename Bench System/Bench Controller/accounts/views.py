from django.conf import settings as django_settings
from django.contrib.auth import authenticate, login, logout
from django.contrib.auth.decorators import login_required
from django.shortcuts import render, redirect, get_object_or_404
from django.contrib import messages

from accounts.models import CustomUser
from accounts.permissions import role_required


def _user_list_redirect():
    """Redirect to bench settings page on bench deployment, else accounts:user_list."""
    if getattr(django_settings, 'DEPLOYMENT_TYPE', '') == 'bench':
        return redirect('bench_ui:settings')
    return redirect('accounts:user_list')


def login_view(request):
    if request.user.is_authenticated:
        return redirect('/')
    if request.method == 'POST':
        username = request.POST.get('username', '').strip()
        password = request.POST.get('password', '')
        user = authenticate(request, username=username, password=password)
        if user is not None:
            login(request, user)
            messages.success(request, f"Welcome, {user.full_name or user.username}!")
            try:
                from audit.utils import log_audit
                log_audit(user, 'login', ip_address=request.META.get('REMOTE_ADDR'))
            except Exception:
                pass
            next_url = request.GET.get('next', '/')
            # Never redirect a fresh login to the lock screen — go to dashboard
            if next_url and '/lock' in next_url:
                next_url = '/'
            return redirect(next_url)
        else:
            messages.error(request, "Invalid username or password.")
    return render(request, 'accounts/login.html')


def logout_view(request):
    try:
        from audit.utils import log_audit
        log_audit(request.user, 'logout', ip_address=request.META.get('REMOTE_ADDR'))
    except Exception:
        pass
    logout(request)
    return redirect('accounts:login')


@login_required
def profile_view(request):
    return render(request, 'accounts/profile.html')


@role_required('admin')
def user_list(request):
    users = CustomUser.objects.all().order_by('username')
    return render(request, 'accounts/user_list.html', {'users': users})


@role_required('admin')
def user_create(request):
    if request.method == 'POST':
        username = request.POST.get('username', '').strip()
        password = request.POST.get('password', '')
        first_name = request.POST.get('first_name', '').strip()
        last_name = request.POST.get('last_name', '').strip()
        email = request.POST.get('email', '').strip()
        role = request.POST.get('role', 'lab_tech')

        if CustomUser.objects.filter(username=username).exists():
            messages.error(request, "Username already exists.")
            return redirect('accounts:user_create')

        full_name = f"{first_name} {last_name}".strip()
        user = CustomUser.objects.create_user(
            username=username,
            password=password,
            first_name=first_name,
            last_name=last_name,
            full_name=full_name,
            email=email,
            role=role,
        )
        messages.success(request, f"User '{user.username}' created.")
        return _user_list_redirect()
    return render(request, 'accounts/user_form.html', {'roles': CustomUser.ROLE_CHOICES})


@role_required('admin')
def user_edit(request, pk):
    user = get_object_or_404(CustomUser, pk=pk)
    if request.method == 'POST':
        first_name = request.POST.get('first_name', '').strip()
        last_name = request.POST.get('last_name', '').strip()
        user.first_name = first_name
        user.last_name = last_name
        user.full_name = f"{first_name} {last_name}".strip()
        user.email = request.POST.get('email', '').strip()
        user.role = request.POST.get('role', user.role)
        user.is_active = request.POST.get('is_active') == 'on'
        new_password = request.POST.get('password', '').strip()
        if new_password:
            user.set_password(new_password)
        user.save()
        messages.success(request, f"User '{user.username}' updated.")
        return _user_list_redirect()
    return render(request, 'accounts/user_form.html', {
        'edit_user': user,
        'roles': CustomUser.ROLE_CHOICES,
    })


@role_required('admin')
def user_toggle_active(request, pk):
    user = get_object_or_404(CustomUser, pk=pk)
    if user == request.user:
        messages.error(request, "You cannot deactivate yourself.")
    else:
        user.is_active = not user.is_active
        user.save()
        status = "activated" if user.is_active else "deactivated"
        messages.success(request, f"User '{user.username}' {status}.")
    return _user_list_redirect()

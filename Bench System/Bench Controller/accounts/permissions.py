from functools import wraps

from django.contrib.auth.mixins import LoginRequiredMixin
from django.core.exceptions import PermissionDenied


def role_required(*allowed_roles):
    """Decorator for function-based views that checks user role."""
    def decorator(view_func):
        @wraps(view_func)
        def _wrapped(request, *args, **kwargs):
            if not request.user.is_authenticated:
                from django.shortcuts import redirect
                return redirect('accounts:login')
            if request.user.role not in allowed_roles:
                raise PermissionDenied
            return view_func(request, *args, **kwargs)
        return _wrapped
    return decorator


class RoleRequiredMixin(LoginRequiredMixin):
    """Mixin for class-based views that checks user role."""
    allowed_roles = []

    def dispatch(self, request, *args, **kwargs):
        response = super().dispatch(request, *args, **kwargs)
        if request.user.is_authenticated and request.user.role not in self.allowed_roles:
            raise PermissionDenied
        return response


class AdminRequiredMixin(RoleRequiredMixin):
    allowed_roles = ['admin']


class ManagerRequiredMixin(RoleRequiredMixin):
    allowed_roles = ['admin', 'manager']


class TechRequiredMixin(RoleRequiredMixin):
    allowed_roles = ['admin', 'manager', 'lab_tech']


class AnyAuthMixin(RoleRequiredMixin):
    allowed_roles = ['admin', 'manager', 'lab_tech', 'bench_tech']

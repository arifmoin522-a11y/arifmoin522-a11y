"""Accounts views: auth, dashboards and Phase 1 CRUD.

Role names are never compared in code — permission codes and the
data-driven Role.dashboard_template decide everything.
"""
from typing import Any

from django.contrib import messages
from django.contrib.auth import logout
from django.contrib.auth.views import LoginView as BaseLoginView
from django.core.exceptions import PermissionDenied
from django.core.paginator import Page, Paginator
from django.db import transaction
from django.db.models import Q
from django.shortcuts import get_object_or_404, redirect, render
from django.template import TemplateDoesNotExist
from django.template.loader import get_template
from django.views.decorators.http import require_POST

from apps.audit.models import AuditLog
from apps.audit.utils import log_to_audit
from core.decorators import permission_required_code
from core.permissions import (
    AUDIT_VIEW,
    DEPARTMENT_EDIT,
    DEPARTMENT_VIEW,
    ROLE_CREATE,
    ROLE_DELETE,
    ROLE_EDIT,
    ROLE_VIEW,
    APPOINTMENT_VIEW,
    APPOINTMENT_VIEW_OWN,
    STAFF_VIEW,
    STYLEGUIDE_VIEW,
    USER_CREATE,
    USER_DELETE,
    USER_EDIT,
    USER_VIEW,
    user_has_permission,
)
from .forms import (
    DepartmentForm,
    LoginAuthenticationForm,
    RoleForm,
    StaffProfileForm,
    UserCreateForm,
    UserEditForm,
)
from .lockout import clear_failures, is_locked, register_failure
from .models import Department, Role, StaffProfile, User


# ------------------------------------------------------------------- auth
class LoginView(BaseLoginView):
    """Email+password login with lockout and audit logging."""

    template_name = "auth/login.html"
    redirect_authenticated_user = True
    authentication_form = LoginAuthenticationForm
    lock_identifier: str = ""
    locked: bool = False

    def post(self, request: Any, *args: Any, **kwargs: Any):
        identifier = (request.POST.get("username") or "").casefold().strip()
        self.lock_identifier = identifier
        self.locked = is_locked(identifier)
        return super().post(request, *args, **kwargs)

    def form_valid(self, form: Any):
        if self.locked:
            form.add_error(
                None, "Too many failed attempts. Please try again in a few minutes."
            )
            return self.render_to_response(self.get_context_data(form=form))
        response = super().form_valid(form)
        clear_failures(self.lock_identifier)
        log_to_audit(
            user=self.request.user,
            action=AuditLog.Action.LOGIN,
            request=self.request,
            object_type="user",
            object_id=str(self.request.user.pk),
            details=f"Logged in; role={self.request.user.role_id or 'none'}",
        )
        return response

    def form_invalid(self, form: Any):
        if self.locked:
            form.add_error(
                None, "Too many failed attempts. Please try again in a few minutes."
            )
            return self.render_to_response(self.get_context_data(form=form))
        user = User.objects.filter(email=self.lock_identifier).first()
        if user is not None and not user.is_active:
            form.add_error(None, "This account is disabled.")
            return self.render_to_response(self.get_context_data(form=form))
        just_locked = register_failure(self.lock_identifier, user=user, request=self.request)
        if just_locked:
            form.add_error(
                None, "Too many failed attempts. Please try again in a few minutes."
            )
        return self.render_to_response(self.get_context_data(form=form))


@require_POST
def logout_view(request: Any):
    """Logout accepts POST only (CSRF-protected)."""
    if request.user.is_authenticated:
        log_to_audit(
            user=request.user,
            action=AuditLog.Action.LOGOUT,
            request=request,
            object_type="user",
            object_id=str(request.user.pk),
            details="Logged out",
        )
        logout(request)
    return redirect("login")


def dashboard(request: Any):
    """Role dashboard; the data-driven fallback keeps unknown values safe."""
    if not request.user.is_authenticated:
        return redirect("login")
    role = getattr(request.user, "role", None)
    template_name = (
        (role.dashboard_template or "dashboards/generic.html")
        if role
        else "dashboards/generic.html"
    )
    try:
        get_template(template_name)
    except TemplateDoesNotExist:
        template_name = "dashboards/generic.html"
    context = {"role": role, "desk_stats": None}
    if user_has_permission(
        request.user, APPOINTMENT_VIEW, request=request
    ) or user_has_permission(request.user, APPOINTMENT_VIEW_OWN, request=request):
        from apps.appointments.selectors import dashboard_counts

        context["desk_stats"] = dashboard_counts(request.user, request=request)
    return render(request, template_name, context)


def _log_write(
    request: Any, instance: Any, action: str, model_name: str
) -> None:
    log_to_audit(
        user=request.user,
        action=action,
        request=request,
        object_type=model_name,
        object_id=str(getattr(instance, "pk", "")),
        details=f"{action.title()} {model_name}: {instance}",
    )


def _page(request: Any, queryset: Any, page_size: int = 15) -> Page:
    paginator = Paginator(queryset, page_size)
    return paginator.get_page(request.GET.get("page"))


# ------------------------------------------------------------------ users
@permission_required_code(USER_VIEW)
def user_list(request: Any):
    queryset = User.objects.order_by("full_name").select_related("role")
    query = (request.GET.get("q") or "").strip()
    if query:
        queryset = queryset.filter(Q(email__icontains=query) | Q(full_name__icontains=query))
    return render(
        request, "users/list.html", {"page": _page(request, queryset), "q": query}
    )


@permission_required_code(STAFF_VIEW)
def staff_list(request: Any):
    queryset = (
        StaffProfile.objects.select_related("user", "user__role", "department")
        .filter(user__is_active=True)
        .order_by("user__full_name")
    )
    query = (request.GET.get("q") or "").strip()
    if query:
        queryset = queryset.filter(
            Q(user__email__icontains=query)
            | Q(user__full_name__icontains=query)
            | Q(department__name__icontains=query)
        )
    return render(
        request, "users/staff_list.html", {"page": _page(request, queryset), "q": query}
    )


@permission_required_code(STAFF_VIEW)
def staff_detail(request: Any, pk: int):
    profile = get_object_or_404(
        StaffProfile.objects.select_related("user", "user__role", "department"), pk=pk
    )
    return render(request, "users/staff_detail.html", {"profile": profile})


@permission_required_code(USER_VIEW)
def user_detail(request: Any, pk: int):
    user = get_object_or_404(User, pk=pk)
    profile = getattr(user, "staffprofile", None)
    can_edit = user_has_permission(request.user, USER_EDIT, request=request)
    logs = (
        AuditLog.objects.select_related("user")
        .filter(
            Q(user=user)
            | Q(action=AuditLog.Action.LOGIN, object_type="user", object_id=str(user.pk))
        )
        .order_by("-timestamp")[:10]
    )
    return render(
        request,
        "users/detail.html",
        {"a_user": user, "profile": profile, "can_edit": can_edit, "logs": logs},
    )


@permission_required_code(USER_CREATE)
def user_add(request: Any):
    form = UserCreateForm(request.POST or None, initial={"is_active": True})
    profile_form = StaffProfileForm(request.POST or None)
    if request.method == "POST" and form.is_valid():
        with transaction.atomic():
            user = form.save()
            _log_write(request, user, AuditLog.Action.CREATE, "user")
            if profile_form.is_valid():
                profile = profile_form.save(commit=False)
                profile.user = user
                profile.save()
                _log_write(request, profile, AuditLog.Action.CREATE, "staffprofile")
        messages.success(request, "User created")
        return redirect("user_detail", pk=user.pk)
    return render(
        request,
        "users/form.html",
        {"form": form, "profile_form": profile_form, "adding": True},
    )


@permission_required_code(USER_EDIT)
def user_edit(request: Any, pk: int):
    user = get_object_or_404(User, pk=pk)
    if user.is_superuser and not request.user.is_superuser:
        log_to_audit(
            user=request.user,
            action=AuditLog.Action.PERMISSION_DENIED,
            request=request,
            object_type="user",
            object_id=str(user.pk),
            details="Only superusers may edit superusers.",
        )
        raise PermissionDenied("Only superusers may edit superusers.")
    profile, _ = StaffProfile.all_objects.get_or_create(user=user)
    form = UserEditForm(
        request.POST or None,
        instance=user,
        can_change_staff=request.user.is_superuser,
    )
    profile_form = StaffProfileForm(request.POST or None, instance=profile)
    if request.method == "POST":
        user_ok = form.is_valid()
        profile_ok = profile_form.is_valid()
        if user_ok and profile_ok:
            with transaction.atomic():
                saved_user = form.save()
                saved_profile = profile_form.save(commit=False)
                saved_profile.user = saved_user
                saved_profile.save()
                _log_write(request, saved_user, AuditLog.Action.UPDATE, "user")
                _log_write(request, saved_profile, AuditLog.Action.UPDATE, "staffprofile")
            messages.success(request, "User updated")
            return redirect("user_detail", pk=user.pk)
    return render(
        request,
        "users/form.html",
        {"form": form, "profile_form": profile_form, "a_user": user, "adding": False},
    )


@permission_required_code(USER_DELETE)
def user_remove(request: Any, pk: int):
    """Soft-delete a user: deactivate the account and its staff profile."""
    user = get_object_or_404(User, pk=pk)
    if request.method == "GET":
        return render(request, "users/delete.html", {"a_user": user})
    if user.is_superuser and not request.user.is_superuser:
        log_to_audit(
            user=request.user,
            action=AuditLog.Action.PERMISSION_DENIED,
            request=request,
            object_type="user",
            object_id=str(user.pk),
            details="Superuser accounts cannot be removed here.",
        )
        raise PermissionDenied("Superuser accounts cannot be removed here.")
    if user.pk == request.user.pk:
        messages.error(request, "You cannot remove your own account.")
        return redirect("user_detail", pk=user.pk)
    with transaction.atomic():
        user.is_active = False
        user.save(update_fields=["is_active"])
        profile = getattr(user, "staffprofile", None)
        if profile and not profile.is_deleted:
            profile.soft_delete(user=request.user)
        log_to_audit(
            user=request.user,
            action=AuditLog.Action.DELETE,
            request=request,
            object_type="user",
            object_id=str(user.pk),
            details=f"Deactivated user {user.email}",
        )
    messages.success(request, "User deactivated")
    return redirect("user_list")


# ------------------------------------------------------------------ roles
@permission_required_code(ROLE_VIEW)
def role_list(request: Any):
    roles = Role.objects.order_by("name").prefetch_related("permissions", "users")
    return render(request, "roles/list.html", {"roles": roles})


@permission_required_code(ROLE_VIEW)
def role_detail(request: Any, pk: int):
    role = get_object_or_404(Role, pk=pk)
    return render(request, "roles/detail.html", {"role": role})


@permission_required_code(ROLE_CREATE)
def role_add(request: Any):
    form = RoleForm(request.POST or None)
    if request.method == "POST" and form.is_valid():
        with transaction.atomic():
            role = form.save()
            form.save_m2m()
            _log_write(request, role, AuditLog.Action.CREATE, "role")
        messages.success(request, "Role created")
        return redirect("role_detail", pk=role.pk)
    return render(request, "roles/form.html", {"form": form, "adding": True})


@permission_required_code(ROLE_EDIT)
def role_edit(request: Any, pk: int):
    role = get_object_or_404(Role, pk=pk)
    form = RoleForm(request.POST or None, instance=role)
    if request.method == "POST" and form.is_valid():
        with transaction.atomic():
            role = form.save()
            form.save_m2m()
            _log_write(request, role, AuditLog.Action.UPDATE, "role")
        messages.success(request, "Role updated")
        return redirect("role_detail", pk=role.pk)
    return render(request, "roles/form.html", {"form": form, "role": role, "adding": False})


@permission_required_code(ROLE_DELETE)
def role_remove(request: Any, pk: int):
    """Delete a role only when no user still depends on it."""
    role = get_object_or_404(Role, pk=pk)
    if request.method == "GET":
        return render(request, "roles/delete.html", {"role": role})
    if role.users.exists():
        messages.error(
            request, "Reassign its users first — a role with users cannot be deleted."
        )
        return redirect("role_detail", pk=role.pk)
    with transaction.atomic():
        details = f"Deleted role {role.name}"
        role.delete()
        log_to_audit(
            user=request.user,
            action=AuditLog.Action.DELETE,
            request=request,
            object_type="role",
            object_id=str(pk),
            details=details,
        )
    messages.success(request, "Role deleted")
    return redirect("role_list")


# ------------------------------------------------------------- departments
@permission_required_code(DEPARTMENT_VIEW)
def department_list(request: Any):
    queryset = Department.objects.order_by("name")
    query = (request.GET.get("q") or "").strip()
    if query:
        queryset = queryset.filter(name__icontains=query)
    return render(
        request,
        "departments/list.html",
        {
            "page": _page(request, queryset),
            "q": query,
            "can_edit": user_has_permission(request.user, DEPARTMENT_EDIT, request=request),
        },
    )


@permission_required_code(DEPARTMENT_EDIT)
def department_add(request: Any):
    form = DepartmentForm(request.POST or None)
    if request.method == "POST" and form.is_valid():
        department = form.save(commit=False)
        department.created_by = request.user
        department.save()
        _log_write(request, department, AuditLog.Action.CREATE, "department")
        messages.success(request, "Department created")
        return redirect("department_list")
    return render(request, "departments/form.html", {"form": form, "adding": True})


@permission_required_code(DEPARTMENT_EDIT)
def department_edit(request: Any, pk: int):
    department = get_object_or_404(Department, pk=pk)
    form = DepartmentForm(request.POST or None, instance=department)
    if request.method == "POST" and form.is_valid():
        department = form.save()
        _log_write(request, department, AuditLog.Action.UPDATE, "department")
        messages.success(request, "Department updated")
        return redirect("department_list")
    return render(
        request, "departments/form.html", {"form": form, "department": department, "adding": False}
    )


@permission_required_code(DEPARTMENT_EDIT)
def department_remove(request: Any, pk: int):
    """Soft-delete the record; dependent staff links stay intact."""
    department = get_object_or_404(Department, pk=pk)
    if request.method == "GET":
        return render(request, "departments/delete.html", {"department": department})
    with transaction.atomic():
        department.soft_delete(user=request.user)
        log_to_audit(
            user=request.user,
            action=AuditLog.Action.DELETE,
            request=request,
            object_type="department",
            object_id=str(department.pk),
            details=f"Soft-deleted department {department.name}",
        )
    messages.success(request, "Department archived")
    return redirect("department_list")


# ------------------------------------------------------------------- audit
@permission_required_code(AUDIT_VIEW)
def audit_list(request: Any):
    entries = AuditLog.objects.select_related("user").order_by("-timestamp")
    action = request.GET.get("action") or ""
    query = (request.GET.get("q") or "").strip()
    if action:
        valid = [choice[0] for choice in AuditLog.Action.choices]
        if action in valid:
            entries = entries.filter(action=action)
    if query:
        entries = entries.filter(
            Q(details__icontains=query)
            | Q(user__email__icontains=query)
            | Q(object_type__icontains=query)
        )
    return render(
        request,
        "audit/list.html",
        {
            "page": _page(request, entries, page_size=30),
            "actions": AuditLog.Action.choices,
            "action": action,
            "q": query,
        },
    )


# -------------------------------------------------------------- styleguide
@permission_required_code(STYLEGUIDE_VIEW)
def styleguide(request: Any):
    """Superuser-only component gallery for visual checking."""
    return render(request, "styleguide.html")

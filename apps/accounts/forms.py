"""Forms: admin forms plus the CRUD forms used by the main views."""
from django import forms
from django.contrib.auth.forms import AuthenticationForm, ReadOnlyPasswordHashField

from .models import Department, Role, StaffProfile, User


class LoginAuthenticationForm(AuthenticationForm):
    """AuthenticationForm that casefolds the email like stored users."""

    def clean_username(self) -> str:
        return (self.cleaned_data.get("username") or "").strip().casefold()


class UserAdminCreationForm(forms.ModelForm):
    """Admin form for creating users with an unhashed password field."""

    password1 = forms.CharField(label="Password", widget=forms.PasswordInput)
    password2 = forms.CharField(
        label="Password confirmation", widget=forms.PasswordInput
    )

    class Meta:
        model = User
        fields = ("email", "full_name", "role")

    def clean_email(self) -> str:
        return self.cleaned_data["email"].casefold().strip()

    def clean_password2(self) -> str:
        password1 = self.cleaned_data.get("password1")
        password2 = self.cleaned_data.get("password2")
        if password1 and password2 and password1 != password2:
            raise forms.ValidationError("Passwords do not match.")
        return password2

    def save(self, commit: bool = True) -> User:
        user = super().save(commit=False)
        user.set_password(self.cleaned_data["password1"])
        if commit:
            user.save()
        return user


class UserAdminChangeForm(forms.ModelForm):
    """Admin form for editing users; shows the password hash only."""

    password = ReadOnlyPasswordHashField(
        help_text="Raw passwords are not stored; use the password change form."
    )

    class Meta:
        model = User
        fields = ("email", "full_name", "role", "password", "is_active", "is_staff", "is_superuser")

    def clean_email(self) -> str:
        return self.cleaned_data["email"].casefold().strip()


# --------------------------------------------------------------- view forms
class UserCreateForm(forms.ModelForm):
    """User creation form for authenticated users with user.create."""

    password = forms.CharField(widget=forms.PasswordInput)

    class Meta:
        model = User
        fields = ("email", "full_name", "role", "is_active", "password")

    def clean_email(self) -> str:
        return self.cleaned_data["email"].casefold().strip()

    def save(self, commit: bool = True) -> User:
        user = super().save(commit=False)
        user.set_password(self.cleaned_data["password"])
        if commit:
            user.save()
        return user


class UserEditForm(forms.ModelForm):
    """Edit name/role/active state; passwords change via own-account flow."""

    class Meta:
        model = User
        fields = ("full_name", "role", "is_active", "is_staff")

    def __init__(self, *args, can_change_staff: bool = False, **kwargs) -> None:
        super().__init__(*args, **kwargs)
        if not can_change_staff:
            self.fields.pop("is_staff")


class StaffProfileForm(forms.ModelForm):
    """Staff profile fields edited alongside the user record."""

    class Meta:
        model = StaffProfile
        fields = ("department", "phone", "license_no")

    def __init__(self, *args, **kwargs) -> None:
        super().__init__(*args, **kwargs)
        self.empty_permitted = False


class RoleForm(forms.ModelForm):
    """Create/edit roles and their permission codes."""

    permissions = forms.ModelMultipleChoiceField(
        queryset=None,
        required=False,
        widget=forms.CheckboxSelectMultiple,
    )

    class Meta:
        model = Role
        fields = ("name", "description", "dashboard_template")

    def __init__(self, *args, **kwargs) -> None:
        super().__init__(*args, **kwargs)
        from apps.accounts.models import Permission

        self.fields["permissions"].queryset = Permission.objects.all()


class DepartmentForm(forms.ModelForm):
    """Create/edit hospital departments."""

    class Meta:
        model = Department
        fields = ("name", "description")

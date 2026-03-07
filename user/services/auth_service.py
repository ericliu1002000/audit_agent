"""Authentication service for both page views and DRF APIs."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from django.contrib.auth import login, logout, update_session_auth_hash

from user.forms import MingjianAuthenticationForm, MingjianPasswordChangeForm


@dataclass(frozen=True)
class LoginResult:
    form: MingjianAuthenticationForm
    user: Any | None

    @property
    def success(self) -> bool:
        return self.user is not None


@dataclass(frozen=True)
class PasswordChangeResult:
    form: MingjianPasswordChangeForm
    user: Any | None

    @property
    def success(self) -> bool:
        return self.user is not None


class AuthService:
    """Single source of truth for authentication-related business logic."""

    def build_authentication_form(
        self,
        request,
        *,
        username: str = "",
        password: str = "",
    ) -> MingjianAuthenticationForm:
        return MingjianAuthenticationForm(
            request=request,
            data={
                "username": username.strip(),
                "password": password or "",
            },
        )

    def authenticate_credentials(
        self,
        request,
        *,
        username: str,
        password: str,
    ) -> LoginResult:
        form = self.build_authentication_form(
            request,
            username=username,
            password=password,
        )
        if not form.is_valid():
            return LoginResult(form=form, user=None)
        return LoginResult(form=form, user=form.get_user())

    def login_with_form(self, request, form):
        user = form.get_user()
        login(request, user)
        return user

    def login_with_credentials(
        self,
        request,
        *,
        username: str,
        password: str,
    ) -> LoginResult:
        result = self.authenticate_credentials(
            request,
            username=username,
            password=password,
        )
        if result.success:
            self.login_with_form(request, result.form)
        return result

    def build_password_change_form(
        self,
        *,
        user,
        old_password: str = "",
        new_password1: str = "",
        new_password2: str = "",
    ) -> MingjianPasswordChangeForm:
        return MingjianPasswordChangeForm(
            user=user,
            data={
                "old_password": old_password or "",
                "new_password1": new_password1 or "",
                "new_password2": new_password2 or "",
            },
        )

    def validate_password_change(
        self,
        *,
        user,
        old_password: str,
        new_password1: str,
        new_password2: str,
    ) -> PasswordChangeResult:
        form = self.build_password_change_form(
            user=user,
            old_password=old_password,
            new_password1=new_password1,
            new_password2=new_password2,
        )
        if not form.is_valid():
            return PasswordChangeResult(form=form, user=None)
        return PasswordChangeResult(form=form, user=user)

    def change_password_with_form(self, request, form, *, keep_session: bool = True):
        updated_user = form.save()
        if keep_session:
            update_session_auth_hash(request, updated_user)
        return updated_user

    def logout_user(self, request) -> None:
        logout(request)

    def get_form_errors(self, form) -> dict[str, list[str]]:
        errors = form.errors.get_json_data(escape_html=False)
        return {
            field_name: [item["message"] for item in items]
            for field_name, items in errors.items()
        }

    def serialize_user(self, user) -> dict[str, Any]:
        return {
            "id": user.id,
            "username": user.get_username(),
            "display_name": user.get_full_name() or user.get_username(),
            "is_staff": bool(user.is_staff),
            "is_superuser": bool(user.is_superuser),
            "last_login": user.last_login.isoformat() if user.last_login else None,
        }


auth_service = AuthService()

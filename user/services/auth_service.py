"""Authentication related service helpers for the user app."""

from django.contrib.auth import login, logout, update_session_auth_hash


def login_user(request, user):
    """Persist the authenticated user in the current session."""

    login(request, user)


def logout_user(request):
    """Clear the current session."""

    logout(request)


def change_user_password(request, form, *, keep_session=True):
    """Save the form and optionally preserve the active session."""

    updated_user = form.save()
    if keep_session:
        update_session_auth_hash(request, updated_user)
    return updated_user

"""Custom forms for the user app."""

from django.contrib.auth.forms import AuthenticationForm, PasswordChangeForm
from django.utils.safestring import mark_safe


class _ChineseErrorMessagesMixin:
    """Inject common Chinese error messages for form fields."""

    field_error_messages = {
        'required': '这是必填项。',
        'invalid': '输入的格式不正确。',
    }

    def _localize_field_errors(self):
        for field in self.fields.values():
            for key, message in self.field_error_messages.items():
                field.error_messages.setdefault(key, message)


class MingjianAuthenticationForm(_ChineseErrorMessagesMixin, AuthenticationForm):
    """Authentication form with localized labels and errors."""

    error_messages = {
        'invalid_login': '用户名或密码不正确，请重新输入。',
        'inactive': '该账号已被禁用，请联系管理员。',
    }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['username'].label = '用户名'
        self.fields['password'].label = '密码'
        self._localize_field_errors()


class MingjianPasswordChangeForm(_ChineseErrorMessagesMixin, PasswordChangeForm):
    """Password change form with localized labels and errors."""

    error_messages = {
        'password_incorrect': '原密码输入错误，请重新输入。',
        'password_mismatch': '两次输入的新密码不一致。',
    }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['old_password'].label = '原密码'
        self.fields['new_password1'].label = '新密码'
        self.fields['new_password2'].label = '确认新密码'
        self.fields['new_password1'].help_text = mark_safe(
            '<br>1. 至少 8 个字符；<br>2. 不能全为数字。'
        )
        self.fields['new_password2'].help_text = '请再次输入新密码进行校验。'
        self._localize_field_errors()

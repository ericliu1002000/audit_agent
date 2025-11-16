from django.contrib import messages
from django.contrib.auth.mixins import LoginRequiredMixin
from django.shortcuts import redirect
from django.urls import reverse_lazy
from django.views import View
from django.views.generic import FormView

from .forms import MingjianAuthenticationForm, MingjianPasswordChangeForm
from .services import auth_service


def _style_form(form):
    for field in form.fields.values():
        existing = field.widget.attrs.get('class', '')
        field.widget.attrs['class'] = f"{existing} input-control".strip()
        field.widget.attrs.setdefault('placeholder', field.label)


class LoginView(FormView):
    template_name = 'user/login.html'
    form_class = MingjianAuthenticationForm
    success_url = reverse_lazy('indicators:fund_usage_recommendation_page')

    def dispatch(self, request, *args, **kwargs):
        if request.user.is_authenticated:
            return redirect(self.get_success_url())
        return super().dispatch(request, *args, **kwargs)

    def get_form_kwargs(self):
        kwargs = super().get_form_kwargs()
        kwargs['request'] = self.request
        return kwargs

    def get_form(self, form_class=None):
        form = super().get_form(form_class)
        _style_form(form)
        return form

    def form_valid(self, form):
        auth_service.login_user(self.request, form.get_user())
        messages.success(self.request, '欢迎回来，登录成功。')
        return super().form_valid(form)


class ChangePasswordView(LoginRequiredMixin, FormView):
    template_name = 'user/change_password.html'
    form_class = MingjianPasswordChangeForm
    success_url = reverse_lazy('user:login')

    def get_form_kwargs(self):
        kwargs = super().get_form_kwargs()
        kwargs['user'] = self.request.user
        return kwargs

    def get_form(self, form_class=None):
        form = super().get_form(form_class)
        _style_form(form)
        return form

    def form_valid(self, form):
        auth_service.change_user_password(self.request, form, keep_session=False)
        messages.success(self.request, '密码修改成功，请使用新密码重新登录。')
        auth_service.logout_user(self.request)
        return super().form_valid(form)


class ForgotPasswordView(LoginRequiredMixin, FormView):
    template_name = 'user/forgot_password.html'
    form_class = MingjianPasswordChangeForm
    success_url = reverse_lazy('user:login')

    def get_form_kwargs(self):
        kwargs = super().get_form_kwargs()
        kwargs['user'] = self.request.user
        return kwargs

    def get_form(self, form_class=None):
        form = super().get_form(form_class)
        _style_form(form)
        return form

    def form_valid(self, form):
        auth_service.change_user_password(self.request, form, keep_session=False)
        messages.success(self.request, '密码重置成功，请使用新密码登录。')
        auth_service.logout_user(self.request)
        return super().form_valid(form)


class LogoutView(View):
    def get(self, request, *args, **kwargs):
        auth_service.logout_user(request)
        messages.info(request, '您已退出明鉴系统。')
        return redirect('user:login')

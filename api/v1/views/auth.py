"""认证 API 视图。"""

from django.middleware.csrf import get_token
from django.utils.decorators import method_decorator
from django.views.decorators.csrf import csrf_protect, ensure_csrf_cookie
from django.views.decorators.debug import sensitive_post_parameters
from drf_spectacular.utils import extend_schema
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from api.authentication import ApiSessionAuthentication
from api.responses import error_response, success_response
from api.v1.serializers.auth import (
    ChangePasswordRequestSerializer,
    ChangePasswordSuccessResponseSerializer,
    CsrfSuccessResponseSerializer,
    LoginRequestSerializer,
    LoginSuccessResponseSerializer,
    LogoutSuccessResponseSerializer,
    MeSuccessResponseSerializer,
)
from api.v1.serializers.common import ApiErrorResponseSerializer
from user.services import auth_service


@method_decorator(ensure_csrf_cookie, name="dispatch")
class AuthCsrfView(APIView):
    """返回当前可用 CSRF token，并确保浏览器收到 csrftoken cookie。"""

    permission_classes = [AllowAny]
    authentication_classes = []

    @extend_schema(
        tags=["auth"],
        responses={200: CsrfSuccessResponseSerializer},
        operation_id="auth_csrf",
        summary="获取 CSRF Token",
    )
    def get(self, request) -> Response:
        """获取 CSRF token，供前端后续写请求使用。"""

        return success_response(
            message="CSRF token 获取成功。",
            data={"csrf_token": get_token(request)},
            no_store=True,
        )


@method_decorator(csrf_protect, name="dispatch")
@method_decorator(sensitive_post_parameters("password"), name="dispatch")
class AuthLoginView(APIView):
    """用户名密码登录接口。"""

    permission_classes = [AllowAny]
    authentication_classes = []

    @extend_schema(
        tags=["auth"],
        request=LoginRequestSerializer,
        responses={
            200: LoginSuccessResponseSerializer,
            400: ApiErrorResponseSerializer,
            403: ApiErrorResponseSerializer,
        },
        operation_id="auth_login",
        summary="登录",
    )
    def post(self, request) -> Response:
        """校验用户名密码，写入 session，并返回新的 CSRF token。"""

        serializer = LoginRequestSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        result = auth_service.login_with_credentials(
            request,
            username=serializer.validated_data["username"],
            password=serializer.validated_data["password"],
        )
        if not result.success:
            fields = auth_service.get_form_errors(result.form)
            message = (
                fields.get("__all__", [None])[0]
                or fields.get("username", [None])[0]
                or fields.get("password", [None])[0]
                or "登录失败，请检查用户名和密码。"
            )
            code = "invalid_credentials" if "__all__" in fields else "validation_error"
            return error_response(
                code,
                message,
                status=400,
                fields=fields,
                no_store=True,
            )

        return success_response(
            message="登录成功。",
            data={
                "csrf_token": get_token(request),
                "user": auth_service.serialize_user(request.user),
            },
            no_store=True,
        )


class AuthMeView(APIView):
    """获取当前登录用户，供 React 初始化登录态。"""

    permission_classes = [IsAuthenticated]
    authentication_classes = [ApiSessionAuthentication]

    @extend_schema(
        tags=["auth"],
        responses={
            200: MeSuccessResponseSerializer,
            401: ApiErrorResponseSerializer,
        },
        operation_id="auth_me",
        summary="获取当前登录用户",
    )
    def get(self, request) -> Response:
        """返回当前 session 对应的用户信息。"""

        return success_response(
            data={
                "authenticated": True,
                "user": auth_service.serialize_user(request.user),
            },
            no_store=True,
        )


class AuthLogoutView(APIView):
    """注销当前会话。"""

    permission_classes = [IsAuthenticated]
    authentication_classes = [ApiSessionAuthentication]

    @extend_schema(
        tags=["auth"],
        request=None,
        responses={
            200: LogoutSuccessResponseSerializer,
            401: ApiErrorResponseSerializer,
            403: ApiErrorResponseSerializer,
        },
        operation_id="auth_logout",
        summary="注销",
    )
    def post(self, request) -> Response:
        """退出登录并清空服务端 session。"""

        auth_service.logout_user(request)
        return success_response(
            message="已退出登录。",
            data={"authenticated": False},
            no_store=True,
        )


class AuthChangePasswordView(APIView):
    """修改当前登录用户密码。"""

    permission_classes = [IsAuthenticated]
    authentication_classes = [ApiSessionAuthentication]

    @extend_schema(
        tags=["auth"],
        request=ChangePasswordRequestSerializer,
        responses={
            200: ChangePasswordSuccessResponseSerializer,
            400: ApiErrorResponseSerializer,
            401: ApiErrorResponseSerializer,
            403: ApiErrorResponseSerializer,
        },
        operation_id="auth_change_password",
        summary="修改密码",
    )
    def post(self, request) -> Response:
        """校验旧密码与新密码，修改成功后强制重新登录。"""

        serializer = ChangePasswordRequestSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        result = auth_service.validate_password_change(
            user=request.user,
            old_password=serializer.validated_data["old_password"],
            new_password1=serializer.validated_data["new_password1"],
            new_password2=serializer.validated_data["new_password2"],
        )
        if not result.success:
            fields = auth_service.get_form_errors(result.form)
            message = (
                fields.get("old_password", [None])[0]
                or fields.get("new_password1", [None])[0]
                or fields.get("new_password2", [None])[0]
                or fields.get("__all__", [None])[0]
                or "密码修改失败，请检查输入。"
            )
            return error_response(
                "validation_error",
                message,
                status=400,
                fields=fields,
                no_store=True,
            )

        auth_service.change_password_with_form(
            request,
            result.form,
            keep_session=False,
        )
        auth_service.logout_user(request)
        return success_response(
            message="密码修改成功，请重新登录。",
            data={"authenticated": False},
            no_store=True,
        )

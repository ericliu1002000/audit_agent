"""认证接口的请求/响应序列化器定义。"""

from rest_framework import serializers


class UserSessionSerializer(serializers.Serializer):
    """当前登录用户在前端会话中的公开字段。"""

    id = serializers.IntegerField()
    username = serializers.CharField()
    display_name = serializers.CharField()
    is_staff = serializers.BooleanField()
    is_superuser = serializers.BooleanField()
    last_login = serializers.DateTimeField(allow_null=True)


class CsrfDataSerializer(serializers.Serializer):
    """CSRF token 数据体。"""

    csrf_token = serializers.CharField()


class CsrfSuccessResponseSerializer(serializers.Serializer):
    """获取 CSRF token 成功响应。"""

    success = serializers.BooleanField(default=True)
    message = serializers.CharField()
    data = CsrfDataSerializer()


class LoginRequestSerializer(serializers.Serializer):
    """登录请求体。"""

    username = serializers.CharField(max_length=150)
    password = serializers.CharField(write_only=True, trim_whitespace=False)


class LoginDataSerializer(serializers.Serializer):
    """登录成功后返回的新 CSRF token 和用户信息。"""

    csrf_token = serializers.CharField()
    user = UserSessionSerializer()


class LoginSuccessResponseSerializer(serializers.Serializer):
    """登录成功响应。"""

    success = serializers.BooleanField(default=True)
    message = serializers.CharField()
    data = LoginDataSerializer()


class MeDataSerializer(serializers.Serializer):
    """当前登录态探测响应体。"""

    authenticated = serializers.BooleanField()
    user = UserSessionSerializer()


class MeSuccessResponseSerializer(serializers.Serializer):
    """当前登录用户成功响应。"""

    success = serializers.BooleanField(default=True)
    data = MeDataSerializer()


class LogoutDataSerializer(serializers.Serializer):
    """注销后返回的登录态信息。"""

    authenticated = serializers.BooleanField()


class LogoutSuccessResponseSerializer(serializers.Serializer):
    """注销成功响应。"""

    success = serializers.BooleanField(default=True)
    message = serializers.CharField()
    data = LogoutDataSerializer()


class ChangePasswordRequestSerializer(serializers.Serializer):
    """修改密码请求体。"""

    old_password = serializers.CharField(write_only=True, trim_whitespace=False)
    new_password1 = serializers.CharField(write_only=True, trim_whitespace=False)
    new_password2 = serializers.CharField(write_only=True, trim_whitespace=False)


class ChangePasswordSuccessResponseSerializer(serializers.Serializer):
    """修改密码成功响应。"""

    success = serializers.BooleanField(default=True)
    message = serializers.CharField()
    data = LogoutDataSerializer()

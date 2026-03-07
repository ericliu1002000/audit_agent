"""API 通用响应序列化器。"""

from rest_framework import serializers


class ApiErrorDetailSerializer(serializers.Serializer):
    """统一错误体中的 error 对象。"""

    code = serializers.CharField()
    message = serializers.CharField()
    fields = serializers.DictField(
        child=serializers.ListField(child=serializers.CharField()),
        required=False,
    )
    details = serializers.DictField(required=False)


class ApiErrorResponseSerializer(serializers.Serializer):
    """统一失败响应结构。"""

    success = serializers.BooleanField(default=False)
    error = ApiErrorDetailSerializer()

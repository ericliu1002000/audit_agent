"""价格审核 API v1 序列化器。"""

from __future__ import annotations

from rest_framework import serializers

from price_audit.models import PriceAuditRowDecision, PriceAuditSubmission, PriceAuditSubmissionRow


class PriceAuditSubmissionCreateRequestSerializer(serializers.Serializer):
    """价格审核上传请求。"""

    file = serializers.FileField()

    def validate_file(self, value):
        filename = (value.name or "").lower()
        if not filename.endswith(".xlsx"):
            raise serializers.ValidationError("仅支持上传 .xlsx 格式文件。")
        return value


class PriceAuditRowDecisionSerializer(serializers.ModelSerializer):
    """价格审核结果序列化器。"""

    class Meta:
        model = PriceAuditRowDecision
        fields = (
            "status",
            "result_type",
            "reviewed_unit",
            "reviewed_unit_price",
            "reviewed_quantity",
            "reviewed_days",
            "reviewed_amount",
            "reduction_amount",
            "reason",
            "evidence_json",
            "error_message",
        )


class PriceAuditSubmissionRowItemSerializer(serializers.ModelSerializer):
    """送审行列表项序列化器。"""

    decision = PriceAuditRowDecisionSerializer(read_only=True)

    class Meta:
        model = PriceAuditSubmissionRow
        fields = (
            "id",
            "excel_row_no",
            "sequence_no",
            "parent_sequence_no",
            "row_type",
            "fee_type",
            "submitted_unit",
            "submitted_unit_price",
            "submitted_quantity",
            "submitted_days",
            "submitted_amount",
            "budget_note",
            "decision",
        )


class PriceAuditSubmissionDataSerializer(serializers.ModelSerializer):
    """送审单详情序列化器。"""

    detail_url = serializers.SerializerMethodField()
    rows_url = serializers.SerializerMethodField()
    audited_excel_download_url = serializers.SerializerMethodField()

    class Meta:
        model = PriceAuditSubmission
        fields = (
            "id",
            "status",
            "current_step",
            "progress_percent",
            "total_rows",
            "processed_rows",
            "failed_rows",
            "current_message",
            "project_name",
            "original_filename",
            "submitted_total_amount",
            "reviewed_total_amount",
            "reduction_total_amount",
            "report_json",
            "error_message",
            "created_at",
            "updated_at",
            "detail_url",
            "rows_url",
            "audited_excel_download_url",
        )

    def get_detail_url(self, obj) -> str:
        request = self.context.get("request")
        path = f"/api/v1/price-audit/submissions/{obj.id}/"
        return request.build_absolute_uri(path) if request is not None else path

    def get_rows_url(self, obj) -> str:
        request = self.context.get("request")
        path = f"/api/v1/price-audit/submissions/{obj.id}/rows/"
        return request.build_absolute_uri(path) if request is not None else path

    def get_audited_excel_download_url(self, obj) -> str | None:
        request = self.context.get("request")
        if not obj.audited_excel_file:
            return None
        path = f"/api/v1/price-audit/submissions/{obj.id}/download/audited-excel/"
        return request.build_absolute_uri(path) if request is not None else path


class PriceAuditSubmissionSuccessResponseSerializer(serializers.Serializer):
    """送审单详情成功响应。"""

    success = serializers.BooleanField(default=True)
    message = serializers.CharField(required=False)
    data = PriceAuditSubmissionDataSerializer()


class PriceAuditSubmissionRowsSuccessResponseSerializer(serializers.Serializer):
    """送审行列表成功响应。"""

    success = serializers.BooleanField(default=True)
    data = serializers.DictField()
    meta = serializers.DictField(required=False)

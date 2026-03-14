"""价格审核 API v1 视图。"""

from __future__ import annotations

from django.http import FileResponse
from drf_spectacular.utils import extend_schema
from rest_framework.parsers import FormParser, MultiPartParser
from rest_framework.permissions import IsAuthenticated
from rest_framework.views import APIView

from api.authentication import ApiSessionAuthentication
from api.pagination import StandardResultsSetPagination
from api.responses import error_response, success_response
from api.v1.serializers.common import ApiErrorResponseSerializer
from api.v1.serializers.price_audit import (
    PriceAuditSubmissionCreateRequestSerializer,
    PriceAuditSubmissionDataSerializer,
    PriceAuditSubmissionRowsSuccessResponseSerializer,
    PriceAuditSubmissionRowItemSerializer,
    PriceAuditSubmissionSuccessResponseSerializer,
)
from price_audit.models import PriceAuditSubmission
from price_audit.services.submission_service import create_submission_from_upload


def _get_submission_or_404(user, submission_id: int) -> PriceAuditSubmission | None:
    """按当前用户查询送审单。"""

    return PriceAuditSubmission.objects.filter(id=submission_id, created_by=user).first()


class PriceAuditSubmissionCreateView(APIView):
    """上传送审表并创建异步价格审核任务。"""

    permission_classes = [IsAuthenticated]
    authentication_classes = [ApiSessionAuthentication]
    parser_classes = [MultiPartParser, FormParser]

    @extend_schema(
        tags=["price-audit"],
        request=PriceAuditSubmissionCreateRequestSerializer,
        responses={
            202: PriceAuditSubmissionSuccessResponseSerializer,
            400: ApiErrorResponseSerializer,
            401: ApiErrorResponseSerializer,
        },
        operation_id="price_audit_submission_create",
        summary="上传价格送审表",
    )
    def post(self, request):
        serializer = PriceAuditSubmissionCreateRequestSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        try:
            submission = create_submission_from_upload(
                serializer.validated_data["file"],
                created_by=request.user,
                exhibition_center_id=serializer.validated_data["exhibition_center_id"],
                project_nature=serializer.validated_data["project_nature"],
            )
        except ValueError as exc:
            return error_response(
                "validation_error",
                str(exc),
                status=400,
                no_store=True,
            )

        return success_response(
            message="送审表上传成功，已开始审核。",
            data=PriceAuditSubmissionDataSerializer(
                submission,
                context={"request": request},
            ).data,
            status=202,
            no_store=True,
        )


class PriceAuditSubmissionDetailView(APIView):
    """查询送审单详情。"""

    permission_classes = [IsAuthenticated]
    authentication_classes = [ApiSessionAuthentication]

    @extend_schema(
        tags=["price-audit"],
        responses={
            200: PriceAuditSubmissionSuccessResponseSerializer,
            401: ApiErrorResponseSerializer,
            404: ApiErrorResponseSerializer,
        },
        operation_id="price_audit_submission_detail",
        summary="获取送审单详情",
    )
    def get(self, request, submission_id: int):
        submission = _get_submission_or_404(request.user, submission_id)
        if submission is None:
            return error_response(
                "not_found",
                "送审单不存在。",
                status=404,
                no_store=True,
            )

        return success_response(
            data=PriceAuditSubmissionDataSerializer(
                submission,
                context={"request": request},
            ).data,
            no_store=True,
        )


class PriceAuditSubmissionRowsView(APIView):
    """分页返回送审行与审核结果。"""

    permission_classes = [IsAuthenticated]
    authentication_classes = [ApiSessionAuthentication]
    pagination_class = StandardResultsSetPagination

    @extend_schema(
        tags=["price-audit"],
        responses={
            200: PriceAuditSubmissionRowsSuccessResponseSerializer,
            401: ApiErrorResponseSerializer,
            404: ApiErrorResponseSerializer,
        },
        operation_id="price_audit_submission_rows",
        summary="分页获取送审行与审核结果",
    )
    def get(self, request, submission_id: int):
        submission = _get_submission_or_404(request.user, submission_id)
        if submission is None:
            return error_response(
                "not_found",
                "送审单不存在。",
                status=404,
                no_store=True,
            )

        queryset = submission.rows.select_related("decision").order_by("excel_row_no")
        paginator = self.pagination_class()
        page = paginator.paginate_queryset(queryset, request, view=self)
        data = PriceAuditSubmissionRowItemSerializer(page, many=True).data
        return paginator.get_paginated_response(data)


class PriceAuditSubmissionAuditedExcelDownloadView(APIView):
    """下载回填后的审核表 Excel。"""

    permission_classes = [IsAuthenticated]
    authentication_classes = [ApiSessionAuthentication]

    @extend_schema(
        tags=["price-audit"],
        responses={
            200: {"type": "string", "format": "binary"},
            401: ApiErrorResponseSerializer,
            404: ApiErrorResponseSerializer,
        },
        operation_id="price_audit_submission_download_audited_excel",
        summary="下载审核表 Excel",
    )
    def get(self, request, submission_id: int):
        submission = _get_submission_or_404(request.user, submission_id)
        if submission is None:
            return error_response(
                "not_found",
                "送审单不存在。",
                status=404,
                no_store=True,
            )
        if not submission.audited_excel_file:
            return error_response(
                "not_found",
                "审核表文件尚未生成。",
                status=404,
                no_store=True,
            )

        response = FileResponse(
            submission.audited_excel_file.open("rb"),
            content_type=(
                "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
            ),
        )
        response["Content-Disposition"] = (
            f'attachment; filename="{submission.project_name or "price_audit"}_audited.xlsx"'
        )
        return response

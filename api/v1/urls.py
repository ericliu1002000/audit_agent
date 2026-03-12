"""API v1 路由入口。"""

from django.urls import path

from api.v1.views.auth import (
    AuthChangePasswordView,
    AuthCsrfView,
    AuthLoginView,
    AuthLogoutView,
    AuthMeView,
)
from api.v1.views.price_audit import (
    PriceAuditSubmissionAuditedExcelDownloadView,
    PriceAuditSubmissionCreateView,
    PriceAuditSubmissionDetailView,
    PriceAuditSubmissionRowsView,
)

app_name = "api_v1"

urlpatterns = [
    # 认证接口统一挂在 /api/v1/auth/* 下，方便 React 前端集中接入。
    path("auth/csrf/", AuthCsrfView.as_view(), name="auth-csrf"),
    path("auth/login/", AuthLoginView.as_view(), name="auth-login"),
    path("auth/me/", AuthMeView.as_view(), name="auth-me"),
    path("auth/logout/", AuthLogoutView.as_view(), name="auth-logout"),
    path(
        "auth/change-password/",
        AuthChangePasswordView.as_view(),
        name="auth-change-password",
    ),
    path(
        "price-audit/submissions/",
        PriceAuditSubmissionCreateView.as_view(),
        name="price-audit-submission-create",
    ),
    path(
        "price-audit/submissions/<int:submission_id>/",
        PriceAuditSubmissionDetailView.as_view(),
        name="price-audit-submission-detail",
    ),
    path(
        "price-audit/submissions/<int:submission_id>/rows/",
        PriceAuditSubmissionRowsView.as_view(),
        name="price-audit-submission-rows",
    ),
    path(
        "price-audit/submissions/<int:submission_id>/download/audited-excel/",
        PriceAuditSubmissionAuditedExcelDownloadView.as_view(),
        name="price-audit-submission-download-audited-excel",
    ),
]

from django.urls import path

from indicator_audit import views

app_name = "indicator_audit"

urlpatterns = [
    path(
        "audit/indicator/",
        views.AuditIndicatorPage.as_view(),
        name="audit_indicator_page",
    ),
    path(
        "api/audit/upload/",
        views.audit_upload,
        name="audit_upload",
    ),
    path(
        "api/audit/status/<str:task_id>/",
        views.audit_status,
        name="audit_status",
    ),
]


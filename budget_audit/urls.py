from django.urls import path

from budget_audit import views

app_name = "budget_audit"

urlpatterns = [
    path("audit/", views.BudgetAuditPage.as_view(), name="audit_page"),
    path("api/audit/", views.api_budget_audit, name="api_budget_audit"),
]


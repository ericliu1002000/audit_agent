from django.urls import path

from indicators import views

app_name = "indicators"

urlpatterns = [
    path(
        "fund-usage/recommendations/",
        views.FundUsageRecommendationPage.as_view(),
        name="fund_usage_recommendation_page",
    ),
    path(
        "api/fund-usage/recommendations/",
        views.fund_usage_recommendations,
        name="fund_usage_recommendations",
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

from django.urls import path

from indicators import views

urlpatterns = [
    path(
        "api/fund-usage/recommendations/",
        views.fund_usage_recommendations,
        name="fund_usage_recommendations",
    ),
]

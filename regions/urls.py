from django.urls import path

from . import views

app_name = "regions"

urlpatterns = [
    path("api/provinces/", views.province_list, name="province_list"),
    path(
        "api/provinces/<int:province_id>/cities/",
        views.province_cities,
        name="province_cities",
    ),
]

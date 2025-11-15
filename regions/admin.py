from django.contrib import admin

from .models import City, Province


@admin.register(Province)
class ProvinceAdmin(admin.ModelAdmin):
    list_display = ("name", "code", "id")
    search_fields = ("name", "code")

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False


@admin.register(City)
class CityAdmin(admin.ModelAdmin):
    list_display = ("name", "code", "province", "id")
    search_fields = ("name", "code")
    list_filter = ("province",)

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False

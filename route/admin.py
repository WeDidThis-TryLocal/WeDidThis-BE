from django.contrib import admin
from route.models import *


class RouteAdmin(admin.ModelAdmin):
    list_display = ("id", "name", "created_at")
    search_fields = ("name", "stops__place_name")
    list_filter = ("created_at",)
    date_hierarchy = "created_at"
    ordering = ("-created_at",)
    readonly_fields = ("created_at",)


class RouteStopAdmin(admin.ModelAdmin):
    list_display = ("id", "route", "order", "place_name")
    list_select_related = ("route",)
    ordering = ("route", "order")
    search_fields = ("place_name", "route__name")


admin.site.register(Route, RouteAdmin)
admin.site.register(RouteStop, RouteStopAdmin)
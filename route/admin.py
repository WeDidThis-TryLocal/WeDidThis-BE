from django.contrib import admin
from route.models import *


###################################
#            Inlines              #
###################################
class RouteStopInline(admin.TabularInline):
    model = RouteStop
    extra = 0
    fields = ("order", "place_name", "place")
    ordering = ("order",)
    raw_id_fields = ("place",)
    autocomplete_fields = ("place",)


class TravelPlanStopInline(admin.TabularInline):
    model = TravelPlanStop
    extra = 0
    fields = ("order", "place")
    ordering = ("order",)
    raw_id_fields = ("place",)
    autocomplete_fields = ("place",)


###################################
#              Route              #
###################################
@admin.register(Route)
class RouteAdmin(admin.ModelAdmin):
    list_display = ("id", "name", "stops_count", "created_at")
    search_fields = ("name", "stops__place_name")
    list_filter = ("created_at",)
    date_hierarchy = "created_at"
    ordering = ("-created_at",)
    readonly_fields = ("created_at",)
    inlines = [RouteStopInline]

    @admin.display(description="Stops")
    def stops_count(self, obj):
        return obj.stops.count()


@admin.register(RouteStop)
class RouteStopAdmin(admin.ModelAdmin):
    list_display = ("id", "route", "order", "place_name", "place_display")
    list_select_related = ("route", "place")
    ordering = ("route", "order")
    search_fields = ("place_name", "route__name", "place__name")
    raw_id_fields = ("route", "place")

    @admin.display(description="Place")
    def place_display(self, obj):
        return getattr(obj.place, "name", "-")
    

###################################
#        RouteDecisionMap         #
###################################
@admin.register(RouteDecisionMap)
class RouteDecisionMapAdmin(admin.ModelAdmin):
    list_display = ("id", "q1", "q2", "q3", "route")
    list_select_related = ("route",)
    list_filter = ("q1", "q2", "q3")
    search_fields = ("route__name",)
    raw_id_fields = ("route",)
    ordering = ("q1", "q2", "q3")


###################################
#     QuestionnaireSubmission     #
###################################
@admin.register(QuestionnaireSubmission)
class QuestionnaireSubmissionAdmin(admin.ModelAdmin):
    list_display = (
        "id", "user_display", "q1", "q2", "q3",
        "start_date", "end_date",
        "route", "travel_plan",
        "created_at",
    )
    list_select_related = ("user", "route", "travel_plan")
    list_filter = ("q1", "q2", "q3", "created_at", "start_date", "end_date")
    search_fields = (
        "user__username", "user__user_name", "user__email",
        "route__name",
    )
    raw_id_fields = ("user", "route", "travel_plan")
    date_hierarchy = "created_at"
    ordering = ("-created_at",)
    readonly_fields = ("created_at",)

    @admin.display(description="User")
    def user_display(self, obj):
        # user_name -> username -> email 우선순위
        u = obj.user
        if not u:
            return "-"
        for attr in ("user_name", "username", "email"):
            val = getattr(u, attr, None)
            if val:
                return val
        return str(u.pk)
    

###################################
#            TravelPlan           #
###################################
@admin.register(TravelPlan)
class TravelPlanAdmin(admin.ModelAdmin):
    list_display = (
        "id", "user_display",
        "start_date", "end_date",
        "has_lodging", "origin_address_short",
        "created_at",
    )
    list_select_related = ("user",)
    list_filter = ("created_at", "start_date", "end_date")
    search_fields = (
        "user__username", "user__user_name", "user__email",
        "origin_address", "lodging_address",
        "stops__place__name",
    )
    raw_id_fields = ("user",)
    date_hierarchy = "created_at"
    ordering = ("-created_at",)
    readonly_fields = ("created_at",)
    inlines = [TravelPlanStopInline]

    @admin.display(description="User")
    def user_display(self, obj):
        u = obj.user
        for attr in ("user_name", "username", "email"):
            val = getattr(u, attr, None)
            if val:
                return val
        return str(u.pk)

    @admin.display(boolean=True, description="Lodging?")
    def has_lodging(self, obj):
        return bool(obj.lodging_address)

    @admin.display(description="Origin")
    def origin_address_short(self, obj):
        return (obj.origin_address or "")[:20] + ("..." if obj.origin_address and len(obj.origin_address) > 20 else "")


@admin.register(TravelPlanStop)
class TravelPlanStopAdmin(admin.ModelAdmin):
    list_display = ("id", "plan", "order", "place_display")
    list_select_related = ("plan", "place")
    ordering = ("plan", "order")
    search_fields = ("plan__id", "place__name")
    raw_id_fields = ("plan", "place")

    @admin.display(description="Place")
    def place_display(self, obj):
        return getattr(obj.place, "name", "-")
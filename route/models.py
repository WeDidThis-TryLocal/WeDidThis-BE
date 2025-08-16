from django.db import models
from home.models import PlaceItem, PlaceImage


class Route(models.Model):
    name = models.CharField(max_length=100)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        return f"Route {self.id} - {self.name}"


class RouteStop(models.Model):
    route = models.ForeignKey(Route, related_name="stops", on_delete=models.CASCADE)
    order = models.PositiveIntegerField()
    place_name = models.CharField(max_length=200)

    place = models.ForeignKey(PlaceItem, null=True, blank=True, on_delete=models.SET_NULL, related_name="route_stops")

    class Meta:
        unique_together = ("route", "order")
        ordering = ["order"]

    def __str__(self):
        return f"[Route {self.route_id}] {self.order}. {self.place_name}"
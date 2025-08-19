from django.db import models
from home.models import PlaceItem
from accounts.models import User


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
    

class RouteDecisionMap(models.Model):
    q1 = models.PositiveSmallIntegerField()
    q2 = models.PositiveSmallIntegerField(null=True, blank=True)
    q3 = models.PositiveSmallIntegerField(null=True, blank=True)
    route = models.ForeignKey(Route, on_delete=models.CASCADE, related_name="decision_rules")

    class Meta:
        unique_together = ("q1", "q2", "q3")


class QuestionnaireSubmission(models.Model):
    user = models.ForeignKey(User, null=True, blank=True, on_delete=models.SET_NULL, related_name="route_submissions")
    created_at = models.DateTimeField(auto_now_add=True)

    q1 = models.PositiveSmallIntegerField()
    q2 = models.PositiveSmallIntegerField(null=True, blank=True)
    q3 = models.PositiveSmallIntegerField(null=True, blank=True)
    start_date = models.DateField()
    end_date   = models.DateField()
    route = models.ForeignKey(Route, null=True, blank=True, on_delete=models.PROTECT, related_name="submissions")

    def __str__(self):
        return f"Submission {self.id} (route={self.route_id})"
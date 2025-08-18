from django.urls import path
from .views import *


urlpatterns = [
    path("create", RouteCollectionView.as_view(), name="route_create"),
    path("/result", RouteByQuestionnaireView.as_view(), name="question_result_route")
]
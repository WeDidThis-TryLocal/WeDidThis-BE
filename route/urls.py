from django.urls import path
from .views import *


urlpatterns = [
    path("create", RouteCollectionView.as_view(), name="route_create"),
    path("<int:route_id>", RouteItemView.as_view())
]
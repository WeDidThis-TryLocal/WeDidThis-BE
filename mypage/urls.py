from django.urls import path
from .views import *


urlpatterns = [
    path("history", MyTripListView.as_view(), name="my_trip_history"),
    path("favorites", MyFavoriteListView.as_view(), name="my_favorite_places"),
]
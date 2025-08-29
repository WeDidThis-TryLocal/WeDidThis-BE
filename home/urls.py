from django.urls import path
from .views import *


urlpatterns = [
    path('', PlaceItemAllView.as_view(), name='place-all'),
    path('place/create', PlaceItemCreateView.as_view(), name='place-create'),
    path('place', PlaceItemDetailView.as_view(), name='place-detail'),
    path('place/favorite', TogglePlaceFavoriteView.as_view(), name='place-favorite'),
]
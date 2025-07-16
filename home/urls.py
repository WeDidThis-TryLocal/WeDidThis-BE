from django.urls import path
from .views import *


urlpatterns = [
    path('place/create', PlaceItemCreateView.as_view(), name='place-create'),
]
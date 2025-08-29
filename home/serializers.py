from rest_framework import serializers
from .models import *


class PlaceImageSerializer(serializers.ModelSerializer):
    class Meta:
        model = PlaceImage
        fields = ['image_url']  # Include only necessary fields
        

class PlaceItemSerializer(serializers.ModelSerializer):
    images = PlaceImageSerializer(many=True, read_only=True)  # Nested serializer for related images
    is_favorite = serializers.SerializerMethodField()

    class Meta:
        model = PlaceItem
        fields = [
            'id',
            'type',
            'name',
            'description',
            'address',
            'latitude',
            'longitude',
            'contact',
            'link',
            'period',
            'place',
            'organizer',
            'parking',
            'sales',
            'toilet',
            'coffee',
            'created_at',
            'updated_at',
            'images',  # Include related images
            'is_favorite',
        ]

    def get_is_favorite(self, obj):
            request = self.context.get("request")
            user = getattr(request, "user", None)
            if not user or not user.is_authenticated:
                return False
            return PlaceFavorite.objects.filter(user=user, place=obj).exists()
from rest_framework import serializers
from .models import PlaceItem, PlaceImage


class PlaceImageSerializer(serializers.ModelSerializer):
    class Meta:
        model = PlaceImage
        fields = ['image_url']  # Include only necessary fields
        

class PlaceItemSerializer(serializers.ModelSerializer):
    images = PlaceImageSerializer(many=True, read_only=True)  # Nested serializer for related images

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
            'created_at',
            'updated_at',
            'images',  # Include related images
        ]
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import status
from .models import PlaceItem, PlaceImage
from .serializers import PlaceItemSerializer
from django.shortcuts import get_object_or_404
from .services import get_address_from_place_name, get_coords_from_address, get_tour_info

# 인증
from rest_framework.decorators import permission_classes
from rest_framework.permissions import AllowAny, IsAuthenticated
from .permissions import IsTouristUser


@permission_classes([IsAuthenticated, IsTouristUser]) # 인증된 사용자만 접근 가능
class PlaceItemDetailView(APIView):
    def get(self, request, pk):
        placeitem = get_object_or_404(PlaceItem, pk=pk)
        serializer = PlaceItemSerializer(placeitem)
        return Response(serializer.data, status=status.HTTP_200_OK)


@permission_classes([AllowAny])  # 인증 없이 접근 가능
class PlaceItemCreateView(APIView):
    def post(self, request):
        data = request.data.copy()

        # 1. 주소가 없고 이름이 있으면: 이름(장소/축제/체험명) → 주소 자동 변환
        if not data.get('address') and data.get('place'):
            address = get_address_from_place_name(data['place'])
            if address:
                data['address'] = address

        # 2. 주소가 있고 위도/경도가 없으면: 주소 → 좌표 자동 변환
        if data.get('address') and (not data.get('latitude') or not data.get('longitude')):
            lat, lon = get_coords_from_address(data['address'])
            if lat is not None and lon is not None:
                data['latitude'] = lat
                data['longitude'] = lon

        # 3. 축제(type='festival')가 아니면 place, period, organizer 필드 비우기
        if data.get('type') != 'festival':
            data['place'] = None
            data['period'] = None
            data['organizer'] = None

        serializer = PlaceItemSerializer(data=data)
        if serializer.is_valid():
            placeitem = serializer.save()
            # 이미지가 있다면 PlaceImage 모델에 저장
            for url in request.data.get('images', []):
                PlaceImage.objects.create(place=placeitem, image_url=url)

            # 자동으로 관광공사 API에서 사진 가져오기
            auto_images_url = get_tour_info(placeitem.name)
            for url in auto_images_url:
                PlaceImage.objects.create(place=placeitem, image_url=url)
            return Response(serializer.data, status=status.HTTP_201_CREATED)
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

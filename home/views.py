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
    def get(self, request):
        pk = request.GET.get('pk')  # 또는 request.GET.get('pk')
        if not pk:
            return Response({"error": "pk parameter is required as query parameter."}, status=status.HTTP_400_BAD_REQUEST)

        # user_type 확인
        try:
            user_type = request.user.profile.user_type
        except AttributeError:
            return Response({"error": "User profile or user_type not found."}, status=status.HTTP_400_BAD_REQUEST)

        # (필요 시 user_type에 따라 다른 처리 가능)
        # 예를 들어, user_type == 0(관람객) 인 경우에만 진행하고 싶다면
        if user_type != 'tourist':
            return Response({"error": "You do not have permission to access this resource."}, status=status.HTTP_403_FORBIDDEN)

        placeitem = get_object_or_404(PlaceItem, pk=pk)
        serializer = PlaceItemSerializer(placeitem)
        data = serializer.data.copy()

        # 자동으로 관광공사 API에서 사진 가져오기
        auto_images_url = get_tour_info(placeitem.name)

        # 응답에 자동 이미지 URL 추가
        data['images'] = auto_images_url
        return Response(data, status=status.HTTP_200_OK)


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
            print(f"[DEBUG] geocoded {data['address']} → {lat}, {lon}")
            if lat is not None and lon is not None:
                data['latitude'] = lat
                data['longitude'] = lon

        # 3. 축제(type='festival')가 아니면 place, period, organizer 필드 비우기
        if data.get('type') != 'festival':
            data['place'] = None
            data['period'] = None
            data['organizer'] = None

        # 4. 체험(type='experience')이 아니면 toilet 필드 비우기
        if data.get('type') != 'experience':
            data['toilet'] = None

        # 5. 카페(type='cafe')가 아니면 coffee 필드 비우기
        if data.get('type') != 'cafe':
            data['coffee'] = None

        # 6. 체험 또는 카페가 아니면 parking, sales 필드 비우기
        if data.get('type') not in ['experience', 'cafe']:
            data['parking'] = None
            data['sales'] = None

        serializer = PlaceItemSerializer(data=data)
        if serializer.is_valid():
            placeitem = serializer.save()
            # 이미지가 있다면 PlaceImage 모델에 저장
            for url in request.data.get('images', []):
                PlaceImage.objects.create(place=placeitem, image_url=url)

            # 자동으로 관광공사 API에서 사진 가져오기
            # auto_images_url = get_tour_info(placeitem.name)
            # for url in auto_images_url:
            #     PlaceImage.objects.create(place=placeitem, image_url=url)
            return Response(serializer.data, status=status.HTTP_201_CREATED)
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

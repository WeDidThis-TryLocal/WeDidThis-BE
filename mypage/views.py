from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import status
from rest_framework.decorators import permission_classes
from rest_framework.permissions import IsAuthenticated

from route.models import *
from home.models import *
from home.permissions import IsTouristUser
from home.views import get_first_image

TYPE_LABEL_MAP = dict(PlaceItem.TYPE_CHOICES)


@permission_classes([IsAuthenticated, IsTouristUser])
class MyTripListView(APIView):
    def get(self, request):
        qs = (QuestionnaireSubmission.objects.select_related("route").filter(user=request.user, route__isnull=False).order_by("-start_date", "-end_date", "-id"))

        items = []
        for sub in qs:
            route_name = sub.route.name if sub.route else "나의 여정"
            date_str = f"{sub.start_date.isoformat()} ~ {sub.end_date.isoformat()}"
            items.append({
                "sumbission_id": sub.id,
                "name": route_name,
                "date": date_str,
            })
        
        return Response({
            "results": items
        }, status=status.HTTP_200_OK)
    

@permission_classes([IsAuthenticated, IsTouristUser])
class MyFavoriteListView(APIView):
    def get(self, request):
        favs = (PlaceFavorite.objects.select_related("place").filter(user=request.user).order_by("place__name"))

        results = []
        for f in favs:
            p = f.place
            results.append({
                "name": p.name,
                "type": p.type,
                "type_label": TYPE_LABEL_MAP.get(p.type),
                "description": p.description,
                "image": get_first_image(p.name)
            })

        return Response({
            "results": results
        }, status=status.HTTP_200_OK)
    

# 로그아웃
@permission_classes([IsAuthenticated, IsTouristUser])
class LogoutAPIView(APIView):
    # 로그아웃
    def delete(self, request):
        # 쿠키에 저장된 토큰 삭제 -> 로그아웃
        res = Response(
            {
                "message": "로그아웃되었습니다."
            },
            status=status.HTTP_202_ACCEPTED
        )
        res.delete_cookie("access_token")
        res.delete_cookie("user_type")
        return res
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import status
from django.db import transaction
from django.shortcuts import get_object_or_404
from django.db.models.functions import Lower

from .models import Route
from .serializers import *
from home.models import PlaceItem
from home.views import get_first_image

from rest_framework.decorators import permission_classes
from rest_framework.permissions import AllowAny, IsAuthenticated
from home.permissions import IsTouristUser

TYPE_LABEL_MAP = dict(PlaceItem.TYPE_CHOICES)
REST_CODE = PlaceItem.REST


def inject_type_label(item):
    code = item.get("type")
    type_label = TYPE_LABEL_MAP.get(code)

    recorded = {}
    for k, v in item.items():
        recorded[k] = v
        if k == "type":
            recorded["type_label"] = type_label
    return recorded


def attach_latlon(items):
    names = [it.get("name") for it in items if it.get("name")]
    by_name = {p.name: p for p in PlaceItem.objects.filter(name__in=names)}
    out = []
    for it in items:
        p = by_name.get(it.get("name"))
        lat = float(p.latitude) if (p and p.latitude is not None) else None
        lon = float(p.longitude) if (p and p.longitude is not None) else None
        out.append({**it, "latitude": lat, "longitude": lon})
    return out


# 고정 경로 등록
@permission_classes([AllowAny])  # 인증 없이 접근 가능
class RouteCollectionView(APIView):
    def post(self, request):
        s = RouteCreateSerializer(data=request.data)
        s.is_valid(raise_exception=True)
        route = s.save()
        resp = RouteDetailSerializer(route).data
        return Response(
            {
                "route_id": resp["id"],
                "name": resp["name"],
                "routes": resp["routes"],
            },
            status=status.HTTP_201_CREATED
        )
    

# 설문조사에 따른 경로
@permission_classes([IsAuthenticated, IsTouristUser])
class RouteByQuestionnaireView(APIView):
    def post(self, request):
        s = QuestionnaireSubmissionSerializer(data=request.data, context={"request": request})
        s.is_valid(raise_exception=True)
        submission = s.save()
        route = submission.route

        if route is None:
            route_data = {}
        else:
            route_data = RouteDetailSerializer(route, context={"request": request}).data

            routes = attach_latlon(route_data.get("routes", []))

            if submission.start_date != submission.end_date:
                # routes = route_data.get("routes", [])
                rest_idx = next((i for i, it in enumerate(routes) if it.get("type") == REST_CODE), None)

                if rest_idx is not None:
                    day1 = routes[:rest_idx + 1] # 숙소 포함
                    day2 = routes[rest_idx + 1:] # 숙소 이후
                else:
                    day1 = routes
                    day2 = []

                route_data["routes"] = {
                    "day1": [inject_type_label(it) for it in day1],
                    "day2": [inject_type_label(it) for it in day2],
                }
            else:
                route_data["routes"] = [inject_type_label(it) for it in route_data.get("routes", [])]

        return Response(
            {
                "submission_id": submission.id,
                "user": {"username": submission.user.user_name},
                "answers": {"q1": submission.q1, "q2": submission.q2, "q3": submission.q3},
                "date": {"start_date": submission.start_date, "end_date": submission.end_date},
                "route": route_data,
            },
            status=status.HTTP_201_CREATED
        )


# 직접 경로 설정 - 장소 리스트
@permission_classes([IsAuthenticated, IsTouristUser])
class AllPlacesSimpleView(APIView):
    def get(self, request):
        qs = PlaceItem.objects.exclude(type=PlaceItem.FESTIVAL).order_by(Lower("name"))

        result = []
        for p in qs:
            result.append({
                "name": p.name,
                "type": p.type,
                "type_label": p.get_type_display(),
                "description": p.description,
                "image": get_first_image(p.name)
            })
        return Response(result, status=status.HTTP_200_OK)
    

# 직접 경로 설정 - 정보 저장
@permission_classes([IsAuthenticated, IsTouristUser])
class TravelPlanCreateView(APIView):
    def post(self, request):
        ser = TravelPlanCreateSerializer(data=request.data, context={"request": request})
        ser.is_valid(raise_exception=True)
        plan = ser.save()

        detail = TravelPlanDetailSerializer(plan).data
        detail["message"] = "저장완료"

        return Response(detail, status=status.HTTP_201_CREATED)





# (수정 필요)
@permission_classes([IsAuthenticated, IsTouristUser])
class RouteSubmissionDetailView(APIView):
    def get(self, request, route_id):
        # user_type 확인
        try:
            user_type = request.user.profile.user_type
        except AttributeError:
            return Response({"error": "User profile or user_type not found."}, status=status.HTTP_400_BAD_REQUEST)
        
        # (필요 시 user_type에 따라 다른 처리 가능)
        # 예를 들어, user_type == 0(관람객) 인 경우에만 진행하고 싶다면
        if user_type != 'tourist':
            return Response({"error": "You do not have permission to access this resource."}, status=status.HTTP_403_FORBIDDEN)
        
        route = get_object_or_404(Route.objects.prefetch_related("stops"), pk=route_id)
        data = RouteDetailSerializer(route).data
        return Response({
            "route_id": data["id"],
            "name": data["name"],
            "routes": data["routes"],  # order 붙은 리스트
        })
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import status
from django.db import transaction
from django.shortcuts import get_object_or_404

from .models import Route
from .serializers import *

from rest_framework.decorators import permission_classes
from rest_framework.permissions import AllowAny, IsAuthenticated
from home.permissions import IsTouristUser


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
    

# 설문조사에 따른 고정 경로
@permission_classes([IsAuthenticated, IsTouristUser])
class RouteByQuestionnaireView(APIView):
    def post(self, request):
        s = QuestionnaireSubmissionSerializer(data=request.data, context={"request": request})
        s.is_valid(raise_exception=True)
        submission = s.save()
        route = submission.route

        route_data = RouteDetailSerializer(route, context={"request": request}).data

        return Response(
            {
                "submission_id": submission.id,
                "answers": {
                    "q1": submission.q1,
                    "q2": submission.q2,
                    "q3": submission.q3
                },
                "route": {
                    "id": route_data["id"],
                    "name": route_data["name"],
                    "routes": route_data["routes"],
                }
            },
            status=status.HTTP_201_CREATED
        )


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
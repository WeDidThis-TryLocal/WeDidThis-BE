from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import status
from rest_framework.decorators import permission_classes
from rest_framework.permissions import IsAuthenticated

from route.models import *
from home.permissions import IsTouristUser


@permission_classes([IsAuthenticated, IsTouristUser])
class MyTripListView(APIView):
    def get(self, request):
        qs = (QuestionnaireSubmission.objects.select_related("route").filter(User=request.user, route__isnull=False).order_by("-start_date", "-end_date", "-id"))

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
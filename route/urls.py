from django.urls import path
from .views import *


urlpatterns = [
    # 고정 경로
    path("create", RouteCollectionView.as_view(), name="route_create"),
    # 설문 결과
    path("result", RouteByQuestionnaireView.as_view(), name="question_result_route"),
    # 직접 경로 설정 - 위치 선택
    path("select", AllPlacesSimpleView.as_view(), name="select_places_in_list"),
    # 직접 경로 설정 - 위치 저장
    path("save", TravelPlanCreateView.as_view(), name='save-place'),
    # 직접 경로 설정 - GPT 경로 생성
    path("build", SubmissionBuildRouteView.as_view(), name="build_route_by_gpt"),
    # 경로 삭제
    path("delete", TravelPlanDeleteView.as_view(), name="delete_travel_plan"),
]
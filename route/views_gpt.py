from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import status
from django.db import transaction
from django.shortcuts import get_object_or_404
from django.db.models.functions import Lower
from openai import OpenAI
import json
import logging

import copy

from .models import Route, RouteStop
from .serializers import *
from home.models import PlaceItem
from home.views import get_first_image
from django.conf import settings

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


def is_overnight(submission):
    return(
        (submission.q1 == 1 and submission.q2 == 1 and submission.q3 == 2) or
        (submission.q1 == 2 and submission.q2 == 2 and submission.q3 is None)
    )


def clean_for_response_list(lst):
    cleaned = []
    for it in lst:
        base = dict(it)
        if not base.get("image_url") and base.get("name"):
            base["image_url"] = get_first_image(base["name"])
        base = inject_type_label(base)
        cleaned.append(base)
    for idx, it in enumerate(cleaned, 1):
        it.setdefault("order", idx)
    return cleaned


def flatten_routes_for_save(routes_out):
    if isinstance(routes_out, dict) and "day1" in routes_out:
        flat = list(routes_out.get("day1", [])) + list(routes_out.get("day2", []))
    else:
        flat = list(routes_out or [])
    for i, it in enumerate(flat, 1):
        it["order"] = i
    return flat


def save_gpt_route_as_route(routes_out, route_name="나의 여정"):
    route = Route.objects.create(name=route_name)
    flat = flatten_routes_for_save(routes_out)
    names = [it.get("name") for it in flat if it.get("name")]
    place_by_name = {p.name: p for p in PlaceItem.objects.filter(name__in=names)}
    stops = []
    for it in flat:
        name = it.get("name") or ""
        p = place_by_name.get(name)
        stops.append(RouteStop(
            route=route,
            order=it.get("order"),
            place_name=name,
            place=p if p else None
        ))
    RouteStop.objects.bulk_create(stops)
    return route


def ensure_lodging_included(items, lodging_address, lat, lon):
    if not lodging_address:
        return items
    
    exists = next((x for x in items if x.get("type") == REST_CODE or x.get("name") == lodging_address), None)
    if exists:
        return items
    
    lodging = {
        "name": "오늘의 휴식처",
        "type": REST_CODE,
        "address": lodging_address,
        "image_url": [],
        "latitude": float(lat) if lat is not None else None,
        "longitude": float(lon) if lon is not None else None,
    }
    return items + [lodging]


def call_gpt(system_prompt, payload):
    client = OpenAI(api_key=settings.OPENAI_API_KEY)
    try:
        resp = client.chat.completions.create(
            model="gpt-5",
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": json.dumps(payload, ensure_ascii=False, separators=(',', ':'))}
            ],
            response_format={"type": "json_object"},
        )
        return json.loads(resp.choices[0].message.content)
    except Exception as e:
        logging.getLogger(__name__).exception("OpenAI 호출 실패")
        raise


def place_item_to_payload(p):
    """GPT places payload 아이템으로 변환"""
    return {
        "name": p.name,
        "type": p.type,
        "type_label": p.get_type_display(),
        "address": p.address,
        "latitude": float(p.latitude) if p.latitude is not None else None,
        "longitude": float(p.longitude) if p.longitude is not None else None,
        "image_url": get_first_image(p.name)
    }


def build_places_from_plan(plan):
    """TravelPlan의 stops를 GPT places 배열 구성"""
    items = []
    for stop in plan.stops.select_related("place").all():
        items.append(place_item_to_payload(stop.place))
    return items


def origin_from_plan(plan):
    return {
        "address": plan.origin_address,
        "latitude": float(plan.origin_latitude) if plan.origin_latitude is not None else None,
        "longitude": float(plan.origin_longitude) if plan.origin_longitude is not None else None,
    }


def is_overnight_for_submission(sub, plan):
    # q2 == 2 (1박2일) 이고 날짜도 실제로 다르면 overnight
    return (sub.q2 == 2) and bool(plan.start_date and plan.end_date and plan.start_date != plan.end_date)


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

        route_body = {}

        if route is not None:
            route_data = RouteDetailSerializer(route, context={"request": request}).data
            routes = attach_latlon(route_data.get("routes", []))

            if submission.start_date != submission.end_date:
                rest_idx = next((i for i, it in enumerate(routes) if it.get("type") == REST_CODE), None)

                if rest_idx is not None:
                    day1 = routes[:rest_idx + 1] # 숙소 포함
                    day2 = routes[rest_idx + 1:] # 숙소 이후
                else:
                    day1 = routes
                    day2 = []

                routes_out = {
                    "day1": [inject_type_label(it) for it in day1],
                    "day2": [inject_type_label(it) for it in day2],
                }
            else:
                routes_out = [inject_type_label(it) for it in route_data.get("routes", [])]

            route_body = {
                "id": route_data.get("id"),
                "name": route_data.get("name") or "나의 여정",
                "routes": routes_out,
            }

        payload_key = "route_overnight" if is_overnight(submission) else "route"

        return Response(
            {
                "submission_id": submission.id,
                "user": {"username": submission.user.user_name},
                "answers": {"q1": submission.q1, "q2": submission.q2, "q3": submission.q3},
                "date": {"start_date": submission.start_date, "end_date": submission.end_date},
                payload_key: route_body,
            },
            status=status.HTTP_201_CREATED
        )


# 직접 경로 설정 - 장소 리스트
@permission_classes([IsAuthenticated, IsTouristUser])
class AllPlacesSimpleView(APIView):
    def get(self, request):
        qs = PlaceItem.objects.exclude(type__in=[PlaceItem.FESTIVAL, PlaceItem.REST]).order_by(Lower("name"))

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

        submission_id = request.GET.get("submission_id") or request.data.get("submission_id")
        if submission_id:
            try:
                sub = QuestionnaireSubmission.objects.get(id=int(submission_id), user=request.user)
                if sub.travel_plan_id:
                    return Response({"error": "이미 여행 계획이 연결된 설문조사입니다."}, status=status.HTTP_400_BAD_REQUEST)
                sub.travel_plan = plan
                sub.start_date = plan.start_date
                sub.end_date = plan.end_date
                sub.save(update_fields=["travel_plan", "start_date", "end_date"])
            except (QuestionnaireSubmission.DoesNotExist, ValueError):
                return Response({"error": "해당 submission_id에 대한 설문조사 결과가 없습니다."}, status=status.HTTP_404_NOT_FOUND)

        detail = TravelPlanDetailSerializer(plan).data
        detail["message"] = "저장완료"

        return Response(detail, status=status.HTTP_201_CREATED)
    

# 직접 경로 설정 - GPT 경로 생성
@permission_classes([IsAuthenticated, IsTouristUser])
class SubmissionBuildRoutebyGPTView(APIView):
    """
    저장된 TravelPlan을 기반으로 GPT에 경로를 요청하고,
    Route / routeStop을 생성하여 QuestionnaireSubmission.route에 연결한뒤
    route / route_overnight 형태로 응답
    """
    def post(self, request):
        submission_id = request.GET.get("submission_id")
        if not submission_id:
            return Response(
                {
                    "error": "submission_id 값이 존재하지 않습니다."
                },
                status=status.HTTP_400_BAD_REQUEST
            )
        
        # 설문 + 연결된 플랜 조회
        try:
            sub = (QuestionnaireSubmission.objects.select_related("travel_plan", "user").get(id=int(submission_id), user=request.user))
        except (QuestionnaireSubmission.DoesNotExist, ValueError):
            return Response(
                {
                    "error": "해당 submission_id에 대한 설문조사 결과가 없습니다."
                },
                status=status.HTTP_404_NOT_FOUND
            )
        
        plan: TravelPlan | None = sub.travel_plan
        if not plan:
            return Response(
                {
                    "error": "해당 설문조사에 연결된 여행 계획이 없습니다."
                },
                status=status.HTTP_400_BAD_REQUEST
            )
        
        # 기존 route가 있을 때
        rebuild = str(request.GET.get("rebuild")).lower() == "true"
        if sub.route_id and not rebuild:
            route_data = RouteDetailSerializer(sub.route, context={"request": request}).data
            overnight_now = is_overnight_for_submission(sub, plan)
            if overnight_now:
                body = {
                    "id": route_data["id"],
                    "name": route_data["name"],
                    "routes": route_data["routes"]
                }
                top_key = "route_overnight"
            else:
                body = {
                    "id": route_data["id"],
                    "name": route_data["name"],
                    "routes": route_data["routes"]
                }
                top_key = "route"

            return Response(
                {
                    "submission_id": sub.id,
                    "user": {"username": getattr(sub.user, "user_name", getattr(sub.user, "username", "unknown"))},
                    "answers": {"q1": sub.q1, "q2": sub.q2, "q3": sub.q3},
                    "date": {"start_date": sub.start_date, "end_date": sub.end_date},
                    top_key: body,
                    "message": "기존 경로를 반환합니다."
                },
                status=status.HTTP_200_OK
            )
        
        # q1=2 &q3=None & q2 in (1,2) 만 빌드 허용
        if not (sub.q1 == 2 and sub.q3 is None and sub.q2 in (1, 2)):
            return Response(
                {
                    "error": "이 설문에 대해서는 경로 생성을 할 수 없습니다."
                },
                status=status.HTTP_400_BAD_REQUEST
            )
        
        # 1) origin / places / overnight 구성
        origin = origin_from_plan(plan)
        places = build_places_from_plan(plan)
        overnight = is_overnight_for_submission(sub, plan)
        if overnight and not plan.lodging_address:
            return Response(
                {
                    "error": "1박 2일 여행의 경우 숙소 정보는 필수입니다."
                },
                status=status.HTTP_400_BAD_REQUEST
            )
        
        if overnight:
            places = ensure_lodging_included(places, plan.lodging_address, plan.lodging_latitude, plan.lodging_longitude)

        # 2) GPT 호출
        payload = build_gpt_payload(origin=origin, places=places, overnight=overnight)
        gpt_out = call_gpt(GPT_SYSTEM_PROMPT, payload)
        routes_out = gpt_out.get("routes")
        if routes_out is None:
            return Response(
                {
                    "error": "GPT 응답에 routes 데이터가 없습니다."
                },
                status=status.HTTP_502_BAD_GATEWAY
            )
        
        # 3) DB 저장 (Route / RouteStop) + 설문 연결
        route = save_gpt_route_as_route(routes_out, route_name="나의 여정")
        sub.route = route
        sub.save(update_fields=["route"])

        # 4) 응답 구성
        def _inject_list(lst):
            return [inject_type_label(it) for it in lst]
        
        if overnight and isinstance(routes_out, dict):
            resp_routes = {
                "day1": _inject_list(routes_out.get("day1", [])),
                "day2": _inject_list(routes_out.get("day2", [])),
            }
            route_body = {"id": route.id, "name": route.name or "나의 여정", "routes": resp_routes}
            top_key = "route_overnight"
        else:
            resp_routes = _inject_list(routes_out if isinstance(routes_out, list) else [])
            route_body = {"id": route.id, "name": route.name or "나의 여정", "routes": resp_routes}
            top_key = "route"


        return Response(
            {
                "submission_id": sub.id,
                "user": {"username": getattr(sub.user, "user_name", getattr(sub.user, "username", "unknown"))},
                "answers": {"q1": sub.q1, "q2": sub.q2, "q3": sub.q3},
                "date": {"start_date": sub.start_date, "end_date": sub.end_date},
                top_key: route_body,
                "message": "답변완료",
            },
            status=status.HTTP_201_CREATED
        )
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import status
from django.db import transaction
from django.shortcuts import get_object_or_404
from django.db.models.functions import Lower
from openai import OpenAI
import json

from .models import Route
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
    resp = client.chat.completions.create(
        model="gpt-5",
        messages=[
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": json.dumps(payload, ensure_ascii=False, separators=(',', ':'))}
        ],
        response_format={"type": "json_object"}
    )
    return json.loads(resp.choices[0].message.content)


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


# 직접 경로 설정 - GPT route 추가
@permission_classes([IsAuthenticated, IsTouristUser])
class SubmissionBuildRouteView(APIView):
    def post(self, request):
        submission_id = request.GET.get("submission_id")
        if not submission_id:
            return Response(
                {"error": "submission_id 쿼리 파라미터가 필요합니다."},
                status=status.HTTP_400_BAD_REQUEST
            )
        
        try:
            submission = QuestionnaireSubmission.objects.select_related("travel_plan", "user").get(id=submission_id, user=request.user)
        except QuestionnaireSubmission.DoesNotExist:
            return Response(
                {"error": "해당 submission_id에 대한 설문조사 결과가 없습니다."},
                status=status.HTTP_404_NOT_FOUND
            )

        # 이미 route가 생성된 경우 중복 생성 방지
        if submission.route_id:
            return Response({"error": "이미 경로가 생성되었습니다."}, status=status.HTTP_400_BAD_REQUEST)
        
        # 설문조사 조건 확인
        if not (submission.q1 == 2 and submission.q3 is None and submission.q2 in(1, 2)):
            return Response({"error": "해당 설문조사 조건에 맞지 않습니다."}, status=status.HTTP_400_BAD_REQUEST)
        
        plan = submission.travel_plan
        if not plan:
            return Response({"error": "연결된 여행 계획이 없습니다."}, status=status.HTTP_400_BAD_REQUEST)

        # # 임시 추가(type_labels)
        TYPE_LABELS = {
            "experience": "체험",
            "cafe": "카페",
            "restaurant": "식당",
            "sightseeing": "관광",
            "shopping": "쇼핑",
            "park": "공원",
            "museum": "박물관",
            "rest": "숙소",
            "lodging": "숙소",
        }

        # DB에서 GPT 입력 구성
        items = []
        for st in plan.stops.select_related("place"):
            p = st.place
            items.append({
                "order": st.order,
                "name": p.name,
                "type": p.type,
                # 임시추가(type_labels)
                "type_label": TYPE_LABELS.get(p.type),
                "address": p.address,
                "image_url": get_first_image(p.name),
                "latitude": float(p.latitude) if p.latitude is not None else None,
                "longitude": float(p.longitude) if p.longitude is not None else None,
            })

        origin = None
        if plan.origin_latitude is not None and plan.origin_longitude is not None:
            origin = {"latitude": float(plan.origin_latitude), "longitude": float(plan.origin_longitude)}

        overnight = bool(plan.start_date and plan.end_date and str(plan.start_date) != str(plan.end_date))
        if overnight:
            items = ensure_lodging_included(
                items,
                lodging_address=plan.lodging_address,
                lat=float(plan.lodging_latitude) if plan.lodging_latitude is not None else None,
                lon=float(plan.lodging_longitude) if plan.lodging_longitude is not None else None,
            )
        # GPT 사용할 경우(시작)
        # payload = build_gpt_payload(origin=origin, places=items, overnight=overnight)

        # gpt_result = call_gpt(GPT_SYSTEM_PROMPT, payload)
        # computed = gpt_result.get("routes")

        # # 응답 포맷 정리
        # if isinstance(computed, dict) and "day1" in computed:
        #     routes_out = {
        #         "day1": clean_for_response_list(computed["day1"]),
        #         "day2": clean_for_response_list(computed.get("day2", []))
        #     }
        # else:
        #     routes_out = clean_for_response_list(computed or [])
        # GPT 사용할 경우(끝)

        # 숙소 이름/라벨 보정
        for it in items:
            if it.get("type") in ("rest", "lodging"):
                if not (it.get("name") or "").strip():
                    it["name"] = "오늘의 휴식처"
                it["type"] = "rest"  # 통일
                it["type_label"] = TYPE_LABELS["rest"]

        # ---------- 가나다순 정렬 ----------
        items_sorted = sorted(items, key=lambda x: x.get("name") or "")

        # ---------- 포맷: 당일 / 1박2일 ----------
        has_lodging = any(it.get("type") =="rest" for it in items_sorted)
        if overnight and has_lodging:
            # 첫 번째 숙소를 기준으로 day1/day2 분리 (숙소는 day1 마지막에 포함)
            lodging_idx = next(
                (i for i, it in enumerate(items_sorted) if it.get("type") == "rest"),
                len(items_sorted) - 1
            )
            day1 = items_sorted[:lodging_idx + 1]
            day2 = items_sorted[lodging_idx + 1:]

            # order 연속 부여
            order_no = 1
            for it in day1:
                it["order"] = order_no
                order_no += 1
            for it in day2:
                it["order"] = order_no
                order_no += 1

            routes_out = {
                "day1": day1,
                "day2": day2
            }
        else:
            # 당일치기: 단일 리스트 + order 재부여
            for idx, it in enumerate(items_sorted, start=1):
                it["order"] = idx
            routes_out = items_sorted

        # 가나다순 정렬
        # routes_out = sorted(items, key=lambda x: x["name"])

        # DB 저장
        with transaction.atomic():
            saved_route = save_gpt_route_as_route(routes_out, route_name="나의 여정")
            submission.route = saved_route
            submission.start_date = plan.start_date
            submission.end_date = plan.end_date
            submission.save(update_fields=["route", "start_date", "end_date"])

        route_body = {
            "id": saved_route.id,
            "name": "나의 여정",
            "routes": routes_out,
        }
        payload_key = "route_overnight" if is_overnight(submission) else "route"

        # 응답
        out = {
            "submission_id": submission.id,
            "user": {"username": getattr(submission.user, "user_name", getattr(submission.user, "username", ""))},
            "answers": {"q1": submission.q1, "q2": submission.q2, "q3": submission.q3},
            "date": {"start_date": submission.start_date, "end_date": submission.end_date},
            payload_key: route_body,
            "message": "답변완료"
        }
        return Response(out, status=status.HTTP_201_CREATED)


# 경로 결과 조회
@permission_classes([IsAuthenticated, IsTouristUser])
class RouteResultbySubmissionView(APIView):
    def get(self, request):
        # user_type 확인
        try:
            user_type = request.user.profile.user_type
        except AttributeError:
            return Response({"error": "User profile or user_type not found."}, status=status.HTTP_400_BAD_REQUEST)
        
        # (필요 시 user_type에 따라 다른 처리 가능)
        # 예를 들어, user_type == 0(관람객) 인 경우에만 진행하고 싶다면
        if user_type != 'tourist':
            return Response({"error": "You do not have permission to access this resource."}, status=status.HTTP_403_FORBIDDEN)
        
        submission_id = request.GET.get("submission_id")
        if not submission_id:
            return Response({"error": "submission_id 쿼리 파라미터가 필요합니다."}, status=status.HTTP_400_BAD_REQUEST)
        
        try:
            sid = int(submission_id)
        except (TypeError, ValueError):
            return Response({"error": "submission_id는 유효한 정수여야 합니다."}, status=status.HTTP_400_BAD_REQUEST)
        
        submission = QuestionnaireSubmission.objects.select_related("route", "user", "travel_plan").filter(id=sid).first()
        if not submission:
            return Response({"error": "해당 submission_id가 존재하지 않습니다."}, status=status.HTTP_404_NOT_FOUND)
        if submission.user_id != request.user.id:
            return Response({"error": "이 경로에 접근할 권한이 없습니다."}, status=status.HTTP_403_FORBIDDEN)
        
        route_data = RouteDetailSerializer(submission.route, context={"request": request}).data
        routes = route_data.get("routes", [])

        plan = getattr(submission, "travel_plan", None)

        def _fill_rest_from_plan(item):
            if item.get("name") == "오늘의 휴식처":
                # type이 비어있으면 숙소로 지정
                if item.get("type") is None:
                    item["type"] = REST_CODE
                # TravelPlan 기반으로 좌표/주소 보강
                if plan:
                    if not item.get("address") and plan.lodging_address:
                        item["address"] = plan.lodging_address
                    if item.get("latitude") is None and plan.lodging_latitude is not None:
                        item["latitude"] = float(plan.lodging_latitude)
                    if item.get("longitude") is None and plan.lodging_longitude is not None:
                        item["longitude"] = float(plan.lodging_longitude)
            return item

        routes = [_fill_rest_from_plan(it) for it in routes]

        # 1일/1박2일 분기 + type_label 삽입
        if submission.start_date != submission.end_date:
            rest_idx = next((i for i, it in enumerate(routes) if it.get("type") == REST_CODE), None)
            if rest_idx is not None:
                day1 = routes[:rest_idx + 1]  # 숙소 포함
                day2 = routes[rest_idx + 1:]  # 숙소 이후
            else:
                day1, day2 = routes, []

            out_routes = {
                "day1": [inject_type_label(it) for it in day1],
                "day2": [inject_type_label(it) for it in day2],
            }
        else:
            out_routes = [inject_type_label(it) for it in routes]

        route_body = {
            "id": route_data.get("id"),
            "name": route_data.get("name"),
            "routes": out_routes
        }

        payload_key = "route_overnight" if (submission.start_date != submission.end_date) else "route"

        resp = {
            "submission_id": submission.id,
            "user": {"username": getattr(submission.user, "user_name", getattr(submission.user, "username", ""))},
            "answers": {"q1": submission.q1, "q2": submission.q2, "q3": submission.q3},
            "date": {"start_date": submission.start_date, "end_date": submission.end_date},
        }
        resp[payload_key] = route_body

        return Response(resp, status=status.HTTP_200_OK)
    

# 삭제
@permission_classes([IsAuthenticated, IsTouristUser])
class TravelPlanDeleteView(APIView):
    def delete(self, request):
        submission_id = request.GET.get("submission_id")
        if not submission_id:
            return Response(
                {"error": "submission_id 쿼리 파라미터가 필요합니다."},
                status=status.HTTP_400_BAD_REQUEST
            )
        
        submission = get_object_or_404(QuestionnaireSubmission.objects.select_related("travel_plan"), id=submission_id, user=request.user)
        
        deleted_submission_id = submission.id
        deleted_plan_id = submission.travel_plan_id
        if submission.travel_plan_id:
            submission.travel_plan.delete()
            return Response(
                {
                    "message": "삭제완료",
                    "deleted_submission_id": deleted_submission_id,
                    "deleted_travel_plan_id": deleted_plan_id
                },
                status=status.HTTP_200_OK
            )
        else:
            submission.delete()
            return Response(
                {
                    "message": "삭제완료",
                    "deleted_submission_id": deleted_submission_id,
                    "deleted_travel_plan_id": None
                },
                status=status.HTTP_200_OK
            )
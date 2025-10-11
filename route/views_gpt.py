from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import status
from django.db import transaction, close_old_connections
from django.shortcuts import get_object_or_404
from django.db.models.functions import Lower
from openai import OpenAI
import json
import logging
import math
from concurrent.futures import ThreadPoolExecutor
from openai import OpenAI, APIConnectionError, APITimeoutError, APIStatusError
import httpx

from .models import Route, RouteStop, QuestionnaireSubmission, TravelPlan
from .serializers import *
from home.models import PlaceItem
from home.views import get_first_image
from django.conf import settings

from rest_framework.decorators import permission_classes
from rest_framework.permissions import AllowAny, IsAuthenticated
from home.permissions import IsTouristUser

EXECUTOR = ThreadPoolExecutor(max_workers=8)

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
        # if not base.get("image_url") and base.get("name"):
        #     base["image_url"] = get_first_image(base["name"])
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


class GPTTimeoutError(Exception):
    pass


def call_gpt(system_prompt, payload, timeout_sec=58):
    logger = logging.getLogger(__name__)

    client = OpenAI(
        api_key=settings.OPENAI_API_KEY,
        max_retries=0,
        timeout=timeout_sec # 58초 후 타임아웃
    )

    try:
        client_req = client.with_options(timeout=timeout_sec)
        resp = client_req.chat.completions.create(
            model="gpt-5",
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": json.dumps(payload, ensure_ascii=False, separators=(',', ':'))}
            ],
            response_format={"type": "json_object"},
        )
        return json.loads(resp.choices[0].message.content)
        # ---- 타임아웃만 별도로 캐치해서 우리 커스텀 예외로 변환 ----
    except (APITimeoutError, httpx.ReadTimeout, httpx.TimeoutException) as e:
        logger.warning("OpenAI 호출 타임아웃(%ss): %s", timeout_sec, str(e))
        raise GPTTimeoutError(f"openai timeout after {timeout_sec}s") from e

    # ---- 네트워크/서버 오류는 다른 예외로 ----
    except (APIConnectionError, APIStatusError, httpx.HTTPError) as e:
        logger.error("OpenAI 네트워크/서버 오류: %s", str(e))
        raise

    # ---- 그 외 예외는 실제 원인 파악 위해 한 번만 스택 출력 ----
    except Exception:
        logger.exception("OpenAI 호출 실패(기타 예외)")
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


def haversine_km(lat1, lon1, lat2, lon2):
    """Harversine distance (km) - None 좌표가 있으면 큰 값 반환하여 선택되지 않게."""
    if None in (lat1, lon1, lat2, lon2):
        return float('inf')
    R = 6371  # 지구 반경 (km)
    phi1, phi2 = math.radians(lat1), math.radians(lat2)
    dphi = math.radians(lat2 - lat1)
    dlmb = math.radians(lon2 - lon1)
    a = math.sin(dphi / 2) ** 2 + math.cos(phi1) * math.cos(phi2) * math.sin(dlmb / 2) ** 2
    return 2 * R * math.asin(math.sqrt(a))


def nearest_neighbor_order(origin, places):
    remaining = places[:]
    cur = {"latitude": origin.get("latitude"), "longitude": origin.get("longitude")}
    ordered = []
    while remaining:
        # 가장 가까운 장소 찾기
        best = None
        best_d = float('inf')
        for it in remaining:
            d = haversine_km(cur["latitude"], cur["longitude"], it.get("latitude"), it.get("longitude"))
            if d < best_d:
                best, best_d = it, d
            elif d == best_d:
                k1 = (it.get("name") or "", it.get("address") or "")
                k2 = (best.get("name") or "", best.get("address") or "")
                if k1 < k2:
                    best = it
        ordered.append(best)
        cur = {"latitude": best.get("latitude"), "longitude": best.get("longitude")}
        remaining.remove(best)
    return ordered


def split_overnight_lists(ordered_with_rest):
    rest_idx = next((i for i, it in enumerate(ordered_with_rest) if it.get("type") == REST_CODE), None)
    if rest_idx is None:
        return ordered_with_rest, []
    
    day1 = ordered_with_rest[:rest_idx + 1]  # 숙소 포함
    day2 = ordered_with_rest[rest_idx + 1:]  # 숙소 이후

    non_rest_count = sum(1 for it in ordered_with_rest if it.get("type") != REST_CODE)
    if non_rest_count >= 2 and len(day2) == 0:
        # 숙소 이후 일정이 없으면, day1의 마지막 장소를 day2로 이동
        for i in range(len(day1) -2, -1, -1):
            if day1[i].get("type") != REST_CODE:
                move = day1.pop(i)
                day2 = [move] + day2
                break

    return day1, day2


def rebuild_route_with_gpt_background(submission_id: int):
    logger = logging.getLogger(__name__)
    try:
        # 스레드 DB 연결 안정화
        close_old_connections()

        sub = (QuestionnaireSubmission.objects
               .select_related("travel_plan", "route")
               .filter(id=submission_id).first())
        if not sub or not sub.travel_plan:
            logger.warning(f"[bg] invalid submission {submission_id}")
            return

        plan = sub.travel_plan
        origin = origin_from_plan(plan)
        places = build_places_from_plan(plan)
        overnight = is_overnight_for_submission(sub, plan)
        if overnight:
            places = ensure_lodging_included(
                places, plan.lodging_address, plan.lodging_latitude, plan.lodging_longitude
            )

        payload = build_gpt_payload(origin=origin, places=places, overnight=overnight)

        # HTTP와 무관하게 넉넉한 타임아웃
        gpt_out = call_gpt(GPT_SYSTEM_PROMPT, payload, timeout_sec=300)
        routes_out = gpt_out.get("routes")
        if not routes_out:
            logger.warning(f"[bg] no routes in GPT response for submission {submission_id}")
            return

        # 기존 route 교체
        with transaction.atomic():
            route = sub.route
            if route is None:
                route = save_gpt_route_as_route(routes_out, route_name="나의 여정")
                sub.route = route
                sub.save(update_fields=["route"])
            else:
                RouteStop.objects.filter(route=route).delete()
                flat = flatten_routes_for_save(routes_out)
                names = [it.get("name") for it in flat if it.get("name")]
                place_by_name = {p.name: p for p in PlaceItem.objects.filter(name__in=names)}
                stops = []
                for it in flat:
                    name = it.get("name") or ""
                    p = place_by_name.get(name)
                    stops.append(RouteStop(
                        route=route,
                        order=it["order"],
                        place_name=name,
                        place=p if p else None
                    ))
                RouteStop.objects.bulk_create(stops)

        logger.info(f"[bg] submission {submission_id} route updated with GPT result")
    except Exception as e:
        logging.getLogger(__name__).exception(f"[bg] rebuild failed for submission {submission_id}: {e}")
    finally:
        close_old_connections()


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

        # 2) GPT 호출(58초 타임아웃)
        routes_out = None
        source = "gpt"

        try:
            payload = build_gpt_payload(origin=origin, places=places, overnight=overnight)
            gpt_out = call_gpt(GPT_SYSTEM_PROMPT, payload)
            routes_out = gpt_out.get("routes")
            if routes_out is None:
                raise ValueError("GPT 응답에 routes 필드가 없습니다.")
        except Exception:
            source = "logic_fallback"
            ordered = nearest_neighbor_order(origin, places)
            if overnight:
                day1, day2 = split_overnight_lists(ordered)
                routes_out = {
                    "day1": clean_for_response_list(day1),
                    "day2": clean_for_response_list(day2),
                }
            else:
                routes_out = clean_for_response_list(ordered)

            # 비동기 재생성 태스크 실행
            try:
                EXECUTOR.submit(rebuild_route_with_gpt_background, sub.id)
            except Exception:
                logging.getLogger(__name__).exception("재생성 비동기 태스크 실행 실패")
        
        
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
                "source": source,
                "message": "답변완료",
            },
            status=status.HTTP_201_CREATED
        )
    

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
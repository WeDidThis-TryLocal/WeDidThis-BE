from rest_framework import serializers
from .models import *
from home.pictures import get_place_images
from home.models import PlaceItem
from home.services import get_coords_from_address


def setting_routes(routes_payload):
    if not isinstance(routes_payload, list) or len(routes_payload) != 1:
        raise serializers.ValidationError("routes는 단일 객체를 담은 리스트여야 합니다.")
    route_map = routes_payload[0]

    try:
        keys = sorted(int(k) for k in route_map.keys())
    except Exception:
        raise serializers.ValidationError("routes[0]의 키는 정수 문자열이어야 합니다.")
    
    if keys[0] != 1 or keys != list(range(1, len(keys) + 1)):
        raise serializers.ValidationError("routes[0]의 키는 1부터 시작하는 연속 정수여야 합니다.")
    
    stops = []
    for i in keys:
        v = route_map[str(i)]
        if not isinstance(v, str) or not v.strip():
            raise serializers.ValidationError(f"{i}번 장소명이 비어있습니다.")
        stops.append((i, v.strip()))
    return stops


class RouteCreateSerializer(serializers.Serializer):
    name = serializers.CharField(max_length=100)
    routes = serializers.ListField(child=serializers.DictField(), min_length=1, max_length=1)

    def create(self, validated_data):
        stops = setting_routes(validated_data["routes"])
        route = Route.objects.create(name=validated_data["name"])
        RouteStop.objects.bulk_create([
            RouteStop(route=route, order=order, place_name=place)
            for order, place in stops
        ])
        return route
    

class RouteDetailSerializer(serializers.ModelSerializer):
    routes = serializers.SerializerMethodField()

    class Meta:
        model = Route
        fields = ["id", "name", "routes"]

    def first_image(self, name):
        try:
            links = get_place_images(name) or []
            return links[0] if links else None
        except Exception:
            return None

    def get_routes(self, obj):
        stops = list(obj.stops.all())
        names = [s.place_name for s in stops]

        qs = PlaceItem.objects.filter(name__in=names).prefetch_related("images")
        by_name = {p.name: p for p in qs}

        result = []
        for s in stops:
            p = by_name.get(s.place_name)
            if p:
                result.append({
                    "order": s.order,
                    "name": p.name,
                    "type": p.type,
                    "address": p.address,
                    "image_url": self.first_image(p.name),
                })
            else:
                result.append({
                    "order": s.order,
                    "name": s.place_name,
                    "type": None,
                    "address": None,
                    "image_url": self.first_image(s.place_name),
                })
        return result
    

class QuestionnaireSubmissionSerializer(serializers.Serializer):
    q1 = serializers.IntegerField(min_value=1)
    q2 = serializers.IntegerField(required=False, allow_null=True)
    q3 = serializers.IntegerField(required=False, allow_null=True)

    start_date = serializers.DateField(required=True, input_formats=["%Y-%m-%d"])
    end_date   = serializers.DateField(required=True, input_formats=["%Y-%m-%d"])

    def validate(self, attrs):
        q1 = attrs.get("q1")
        q2 = attrs.get("q2")
        q3 = attrs.get("q3")

        sd = attrs.get("start_date")
        ed = attrs.get("end_date")

        if q1 == 1 and q2 is None:
            raise serializers.ValidationError("q1=1 인 경우 q2는 필수입니다.")
        if q1 == 1 and q2 == 1 and q3 is None:
            raise serializers.ValidationError("q1=1 & q2=1 인 경우 q3는 필수입니다.")
        if ed < sd:
            raise serializers.ValidationError("도착날짜(end_date)는 출발날짜(start_date)보다 빠를 수 없습니다.")
        
        try:
            rule = RouteDecisionMap.objects.get(q1=q1, q2=q2, q3=q3)
            attrs["mapped_route"] = rule.route
        except RouteDecisionMap.DoesNotExist:
            attrs["mapped_route"] = None
        
        return attrs
    
    def create(self, validated_data):
        user = self.context.get("request").user if self.context.get("request") else None
        route = validated_data.pop("mapped_route")
        submission = QuestionnaireSubmission.objects.create(
            user=user if getattr(user, "is_authenticated", False) else None,
            route=route,
            **validated_data
        )
        return submission
    

class TravelPlanCreateSerializer(serializers.Serializer):
    origin_address = serializers.CharField(max_length=255)
    places = serializers.ListField(child=serializers.CharField(max_length=100), allow_empty=False)
    lodging_address = serializers.CharField(max_length=255, required=False, allow_blank=True, allow_null=True)

    def resolve_places(self, names):
        qs = PlaceItem.objects.filter(name__in=names)
        found = {p.name: p for p in qs}
        missing = [nm for nm in names if nm not in found]
        if missing:
            raise serializers.ValidationError({"places": f"존재하지 않는 장소명: {', '.join(missing)}"})
        return [found[nm] for nm in names]
    
    def create(self, validated_data):
        request = self.context.get("request")
        if not request or not getattr(request.user, "is_authenticated", False):
            raise serializers.ValidationError("로그인 사용자만 설정할 수 있습니다.")
        
        user = request.user

        origin_address = validated_data["origin_address"].strip()
        places_names = [nm.strip() for nm in validated_data["places"]]
        lodging_address = validated_data.get("lodging_address")
        lodging_address = lodging_address.strip() if lodging_address else None

        o_lat, o_lon = get_coords_from_address(origin_address)
        l_lat, l_lon = (None, None)
        if lodging_address:
            l_lat, l_lon = get_coords_from_address(lodging_address)

        places = self.resolve_places(places_names)

        plan = TravelPlan.objects.create(
            user=user,
            origin_address=origin_address,
            origin_latitude=o_lat,
            origin_longitude=o_lon,
            lodging_address=lodging_address or None,
            lodging_latitude=l_lat,
            lodging_longitude=l_lon,
        )

        TravelPlanStop.objects.bulk_create([
            TravelPlanStop(plan=plan, order=i + 1, place=p)
            for i, p in enumerate(places)
        ])

        return plan
    

class TravelPlanStopOutSerializer(serializers.ModelSerializer):
    place_id = serializers.IntegerField(source="place.id")
    name = serializers.CharField(source="place.name")
    type = serializers.CharField(source="place.type")
    type_label = serializers.SerializerMethodField()
    address = serializers.CharField(source="place.address")
    latitude = serializers.DecimalField(source="place.latitude", max_digits=15, decimal_places=10)
    longitude = serializers.DecimalField(source="place.longitude", max_digits=15, decimal_places=10)

    class Meta:
        model = TravelPlanStop
        fields = ["order", "place_id", "name", "type", "type_label", "address", "latitude", "longitude"]

    def get_type_label(self, obj):
        return obj.place.get_type_display()
    

class TravelPlanDetailSerializer(serializers.ModelSerializer):
    stops = TravelPlanStopOutSerializer(many=True, read_only=True)
    user_name = serializers.SerializerMethodField()

    class Meta:
        model = TravelPlan
        fields = [
            "id",
            "user_name",
            "origin_address", "origin_latitude", "origin_longitude",
            "lodging_address", "lodging_latitude", "lodging_longitude",
            "stops",
            "created_at"
        ]

    def get_user_name(self, obj):
        u = obj.user
        for attr in ("user_name", "username", "email"):
            val = getattr(u, attr, None)
            if val:
                return val
        return str(u.pk)
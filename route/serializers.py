from rest_framework import serializers
from .models import *
from home.pictures import get_place_images


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

    def validate(self, attrs):
        q1 = attrs.get("q1")
        q2 = attrs.get("q2")
        q3 = attrs.get("q3")

        if q1 == 1 and q2 is None:
            raise serializers.ValidationError("q1=1 인 경우 q2는 필수입니다.")
        if q1 == 1 and q2 == 1 and q3 is None:
            raise serializers.ValidationError("q1=1 & q2=1 인 경우 q3는 필수입니다.")
        
        try:
            rule = RouteDecisionMap.objects.get(q1=q1, q2=q2, q3=q3)
        except RouteDecisionMap.DoesNotExist:
            raise serializers.ValidationError("해당 질문 조합에 매핑된 경로가 없습니다.")
        
        attrs["mapped_route"] = rule.route
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
import requests
from django.conf import settings

KAKAO_API_KEY = getattr(settings, 'KAKAO_REST_API_KEY', None)


def get_address_from_place_name(place_name):
    # 카카오 장소 검색 API: 장소명 -> 주소
    url = "https://dapi.kakao.com/v2/local/search/keyword.json"
    headers = {"Authorization": f"KakaoAK {KAKAO_API_KEY}"}
    params = {"query": place_name}
    resp = requests.get(url, headers=headers, params=params)
    data = resp.json()
    if data['documents']:
        return data['documents'][0]['address_name']
    return None


def get_coords_from_address(address):
    # 카카오 주소 검색 API: 주소 -> 좌표
    url = "https://dapi.kakao.com/v2/local/search/address.json"
    headers = {"Authorization": f"KakaoAK {KAKAO_API_KEY}"}
    params = {"query": address}
    resp = requests.get(url, headers=headers, params=params)
    data = resp.json()
    if data['documents']:
        doc = data['documents'][0]
        # 'road_address' 또는 'address' 필드 내에 y(위도), x(경도)가 있음
        # 도로명 주소 우선
        coords = doc.get('road_address') or doc.get('address')
        if coords and coords.get('y') and coords.get('x'):
            lat = round(float(coords['y']), 10)
            lon = round(float(coords['x']), 10)
            return lat, lon
    return None, None
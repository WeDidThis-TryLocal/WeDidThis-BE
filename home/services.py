import requests
import logging
from django.conf import settings
from .pictures import get_place_images

KAKAO_API_KEY = getattr(settings, 'KAKAO_REST_API_KEY', None)
TOUR_API_KEY = getattr(settings, 'TOUR_API_KEY', None)

LOGGER = logging.getLogger(__name__)


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


def get_tour_info(name):
    # 관광 API: 장소명 -> 사진 리스트
    url = "http://apis.data.go.kr/B551011/PhotoGalleryService1/galleryDetailList1"
    params = {
        "numOfRows": 7,
        "pageNo": 1,
        "MobileOS": "IOS",
        "MobileApp": "WeDidThis",
        "title": name,
        "_type": "json",
        "serviceKey": TOUR_API_KEY
    }
    try:
        resp = requests.get(url, params=params)
        print(resp.status_code)
        print(resp.headers.get("Content-Type"))
        print(resp.text)
        data = resp.json()
        items = data.get("response", {}).get("body", {}).get("items", {}).get("item", [])
        image_urls = [item['galWebImageUrl'] for item in items if 'galWebImageUrl' in item]
        if image_urls:
            db_images = get_place_images(name)[1:]
            return image_urls + db_images
        LOGGER.info("관광공사 API에서 사진을 찾을 수 없습니다.: %s", name)
        return get_place_images(name)
    except Exception as e:
        LOGGER.warning("관광공사 API 사진 호출 실패하였습니다. (%s), 데이터베이스로 대체합니다.", e)
        return get_place_images(name)
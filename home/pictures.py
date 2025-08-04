DATA = {
    "sites": [
        {
            "name": "사우당 종택",
            "links": [
                "https://trylocalbucket.s3.ap-northeast-2.amazonaws.com/%EC%82%AC%EC%9A%B0%EB%8B%B9+%EC%A2%85%ED%83%9D/%EC%82%AC%EC%9A%B0%EB%8B%B9%EC%A2%85%ED%83%9D1.jpg",
                "https://trylocalbucket.s3.ap-northeast-2.amazonaws.com/%EC%82%AC%EC%9A%B0%EB%8B%B9+%EC%A2%85%ED%83%9D/%EC%82%AC%EC%9A%B0%EB%8B%B9%EC%A2%85%ED%83%9D2.jpg",
                "https://trylocalbucket.s3.ap-northeast-2.amazonaws.com/%EC%82%AC%EC%9A%B0%EB%8B%B9+%EC%A2%85%ED%83%9D/%EC%82%AC%EC%9A%B0%EB%8B%B9%EC%A2%85%ED%83%9D3.jpeg",
                "https://trylocalbucket.s3.ap-northeast-2.amazonaws.com/%EC%82%AC%EC%9A%B0%EB%8B%B9+%EC%A2%85%ED%83%9D/%EC%82%AC%EC%9A%B0%EB%8B%B9%EC%A2%85%ED%83%9D4.jpg",
                "https://trylocalbucket.s3.ap-northeast-2.amazonaws.com/%EC%82%AC%EC%9A%B0%EB%8B%B9+%EC%A2%85%ED%83%9D/%EC%82%AC%EC%9A%B0%EB%8B%B9%EC%A2%85%ED%83%9D5.jpg"
            ]
        }
    ]
}


def get_place_images(name: str) -> list:
    for site in DATA['sites']:
        if site.get("name") == name:
            return site.get("links", [])
    return []
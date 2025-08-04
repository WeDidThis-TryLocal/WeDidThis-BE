from django.db import models


class PlaceItem(models.Model):
    TRIP = 'trip'
    EXPERIENCE = 'experience'
    FESTIVAL = 'festival'
    CAFE = 'cafe'
    REST = 'rest'
    TYPE_CHOICES = [
        (TRIP, '관광'),
        (EXPERIENCE, '체험'),
        (FESTIVAL, '축제'),
        (CAFE, '카페'),
        (REST, '숙소')
    ]

    type = models.CharField('유형', max_length=10, choices=TYPE_CHOICES)
    name = models.CharField('이름', max_length=100)
    description = models.TextField('설명')
    
    address = models.CharField('주소', max_length=255, blank=True, null=True)
    latitude = models.DecimalField('위도', max_digits=15, decimal_places=10, null=True, blank=True)
    longitude = models.DecimalField('경도', max_digits=15, decimal_places=10, null=True, blank=True)
    contact = models.CharField('연락처', max_length=30, blank=True, null=True)
    link = models.URLField('링크', blank=True, null=True)

    # 축제 전용 필드
    period = models.CharField('기간', max_length=100, blank=True, null=True)
    place = models.CharField('장소', max_length=100, blank=True, null=True)
    organizer = models.CharField('주최자', max_length=100, blank=True, null=True)

    # 체험, 카페 공통 필드
    parking = models.CharField('주차', max_length=50, blank=True, null=True)
    sales = models.CharField('할인', max_length=50, blank=True, null=True)

    # 체험 전용 필드
    toilet = models.CharField('화장실', max_length=50, blank=True, null=True)

    # 카페 전용 필드
    coffee = models.CharField('커피 정보', max_length=50, blank=True, null=True)

    created_at = models.DateTimeField('생성일', auto_now_add=True)
    updated_at = models.DateTimeField('수정일', auto_now=True)

    def __str__(self):
        return f"[{self.get_type_display()}] {self.name}"
    

class PlaceImage(models.Model):
    place = models.ForeignKey(PlaceItem, related_name='images', on_delete=models.CASCADE)
    image_url = models.URLField('이미지 URL', max_length=500)

    def __str__(self):
        return f"{self.place.name} - {self.image_url}"
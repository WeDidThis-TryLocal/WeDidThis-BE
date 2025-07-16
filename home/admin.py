from django.contrib import admin
from home.models import PlaceItem, PlaceImage

class PlaceImageInline(admin.TabularInline):
    model = PlaceImage
    extra = 1  # 이미지 추가 입력란 개수

class PlaceItemAdmin(admin.ModelAdmin):
    list_display = ('id', 'type', 'name', 'address', 'contact', 'created_at')
    list_filter = ('type', 'created_at')
    search_fields = ('name', 'address', 'description')
    inlines = [PlaceImageInline]
    readonly_fields = ('created_at', 'updated_at')

class PlaceImageAdmin(admin.ModelAdmin):
    list_display = ('id', 'place', 'image_url')
    search_fields = ('place__name', 'image_url')

admin.site.register(PlaceItem, PlaceItemAdmin)
admin.site.register(PlaceImage, PlaceImageAdmin)  # Register PlaceImage model with admin
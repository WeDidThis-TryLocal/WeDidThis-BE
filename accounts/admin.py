from django.contrib import admin
from django.contrib.auth.admin import UserAdmin
from accounts.models import User, UserProfile


class UserCheck(UserAdmin):
    # admin 페이지에서 확인할 수 있는 필드
    list_display = ('id', 'account_id', 'user_name', 'is_active', 'is_staff', 'is_superuser', 'date_joined')
    list_filter = ('is_active', 'is_staff', 'is_superuser', 'date_joined')
    search_fields = ('account_id', 'user_name')
    ordering = ('-date_joined',)

    # admin 페이지에서 사용자 수정할 때 입력 필드
    fieldsets = (
        ('user', {'fields': ('account_id', 'password')}),
        ('Personal Info', {'fields': ('user_name', 'is_active', 'is_staff', 'is_superuser')}),
    )

    # admin 페이지에서 사용자 생성할 때 입력 필드
    add_fieldsets = (
        ('User Info', {
            'classes': ('wide',),
            'fields': ('account_id', 'password1', 'password2', 'user_name', 'is_active', 'is_staff', 'is_superuser')
        }),
    )

class UserProfileCheck(admin.ModelAdmin):
    # admin 페이지에서 확인할 수 있는 필드
    list_display = (
        'id',                # UserProfile의 PK
        'user',              # 연결된 User 객체
        'user_type',         # 가입 유형
        'farm_name',         # 농장 이름
        'farm_address',      # 농장 주소
        'representative_name', # 대표자 이름
        'open_date',       # 개업일자
        'business_reg_number', # 사업자 등록 번호
        'created_at',        # 생성일
        'updated_at',        # 수정일
    )
    list_filter = ('user_type', 'created_at')
    search_fields = ('user__account_id', 'farm_name', 'business_reg_number')

    # admin 페이지에서 사용자 수정할 때 입력 필드
    fieldsets = (
        ('User Info', {'fields': ('user', 'user_type')}),
        ('Farm Info', {'fields': ('farm_name', 'farm_address', 'business_reg_number')}),
    )

    # admin 페이지에서 사용자 생성할 때 입력 필드
    add_fieldsets = (
        ('User Info', {
            'classes': ('wide',),
            'fields': ('user', 'user_type', 'farm_name', 'farm_address', 'representative_name', 'open_date', 'business_reg_number')
        }),
    )


admin.site.register(User, UserCheck)
admin.site.register(UserProfile, UserProfileCheck)  # UserProfile 모델도 admin에 등록
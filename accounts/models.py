from django.db import models
from django.contrib.auth.models import AbstractBaseUser, BaseUserManager, PermissionsMixin
from django.utils import timezone
from django.utils.translation import gettext_lazy as _


# Create your models here.
# 헬퍼 클래스 - 유저를 생성할 때 사용
class UserManager(BaseUserManager):
    use_in_migrations = True

    def create_user(self, account_id, user_name, password, **extra_fields):
        """
        주어진 id, 닉네임(또는 농가 이름), 비밀번호 개인정보로 User 인스턴스 생성
        """
        if not account_id:
            raise ValueError('아이디는 필수 항목입니다.')
        if not user_name:
            raise ValueError('닉네임(또는 농가 이름)은 필수 항목입니다.')
        if not password:
            raise ValueError('비밀번호는 필수 항목입니다.')
        
        user = self.model(
            account_id=account_id,
            user_name=user_name,
            **extra_fields
        )
        user.set_password(password)
        user.save(using=self._db)

        return user
    
    def create_superuser(self, account_id, user_name, password):
        """
        주어진 id, 닉네임(또는 농가 이름), 비밀번호 개인정보로 User 인스턴스 생성
        """
        superuser = self.model(
            account_id=account_id,
            user_name=user_name,
        )
        superuser.set_password(password)
        superuser.is_active = True # 해당 계정이 활성인지를 결정
        superuser.is_staff = True # 참인 경우 admin 사이트에 접속 가능
        superuser.is_superuser = True # 모든 권한 부여
        superuser.save(using=self._db)
        return superuser
    

# AbstractBaseUser를 상속해서 유저 커스텀
class User(AbstractBaseUser, PermissionsMixin):
    account_id = models.CharField('아이디', max_length=30, unique=True, null=False, blank=False)
    user_name = models.CharField('닉네임(또는 농가 이름)', max_length=50, null=False)
    date_joined = models.DateTimeField('가입일', default=timezone.now)
    is_active = models.BooleanField('활성화 여부', default=True)
    is_staff = models.BooleanField('관리자 여부', default=False)
    is_superuser = models.BooleanField('최고 관리자 여부', default=False)

    USERNAME_FIELD = 'account_id' # 유저 모델의 unique=True가 옵션으로 설정된 필드 값
    REQUIRED_FIELDS = ['user_name'] # 필수로 받고 싶은 값

    # 헬퍼 클래스 사용
    objects = UserManager()

    def __str__(self):
        return self.account_id
    

class UserProfile(models.Model):
    # 가입 유형
    FARMER = 'farmer'
    TOURIST = 'tourist'
    TYPE_CHOICES = [
        (FARMER, '농부'),
        (TOURIST, '관광객'),
    ]

    user = models.OneToOneField(User, on_delete=models.CASCADE, related_name='profile')
    user_type = models.CharField('가입 유형', max_length=10, choices=TYPE_CHOICES)

    # 농부 전용 필드
    farm_name = models.CharField('농장 이름', max_length=100, null=True, blank=True)
    farm_address = models.CharField('농장 주소', max_length=255, null=True, blank=True)
    business_reg_number = models.CharField('사업자 등록 번호', max_length=20, null=True, blank=True)
    created_at = models.DateTimeField('프로필 생성일', auto_now_add=True)
    updated_at = models.DateTimeField('프로필 수정일', auto_now=True)

    def clean(self):
        """
        user_type 따라 필수값 검증
        """
        if self.user_type == self.FARMER:
            missing = []
            for field in ('farm_name', 'farm_address', 'business_reg_number'):
                if not getattr(self, field):
                    missing.append(field)
            if missing:
                raise ValueError({f: '농부 가입 시 필수 항목입니다.' for f in missing})
            
        def __str__(self):
            return f'{self.user.account_id} ({self.get_user_type_display()})'
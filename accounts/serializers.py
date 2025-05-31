from .models import UserProfile, User
from rest_framework import serializers
from django.contrib.auth import authenticate
from rest_framework_simplejwt.serializers import TokenObtainPairSerializer


# 회원가입 Serializer
class TouristSignupSerializer(serializers.Serializer):
    account_id = serializers.CharField(max_length=30, required=True)
    password = serializers.CharField(write_only=True)
    name = serializers.CharField(max_length=50, required=True)

    def validate_account_id(self, value):
        if User.objects.filter(account_id=value).exists():
            raise serializers.ValidationError("중복된 아이디가 존재합니다.")
        return value

    def create(self, validated_data):
        # user_name 자리에 name을 입력
        user = User.objects.create_user(
            account_id = validated_data['account_id'],
            user_name = validated_data['name'],
            password = validated_data['password'],
        )
        UserProfile.objects.create(
            user=user,
            user_type=UserProfile.TOURIST
        )
        return user
    

class FarmerSignupSerializer(serializers.Serializer):
    account_id = serializers.CharField(max_length=30, required=True)
    password = serializers.CharField(write_only=True)
    name = serializers.CharField(max_length=50)
    farm_address = serializers.CharField(max_length=255)
    business_reg_number = serializers.CharField(max_length=20)

    def validate_account_id(self, value):
        if User.objects.filter(account_id=value).exists():
            raise serializers.ValidationError("중복된 아이디가 존재합니다.")
        return value
    
    def validate_business_reg_number(self, value):
        if UserProfile.objects.filter(business_reg_number=value).exists():
            raise serializers.ValidationError("이미 가입된 농가입니다.")
        return value

    def create(self, validated_data):
        # user_name 자리에 name을 입력
        user = User.objects.create_user(
            account_id = validated_data['account_id'],
            user_name = validated_data['name'],
            password = validated_data['password'],
        )
        UserProfile.objects.create(
            user=user,
            user_type=UserProfile.FARMER,
            farm_name=validated_data['name'],
            farm_address=validated_data['farm_address'],
            business_reg_number=validated_data['business_reg_number'],
        )
        return user
    

# 로그인 Serializer
class UserLoginSerializer(serializers.Serializer):
    account_id = serializers.CharField(required=True)
    password = serializers.CharField(required=True, write_only=True)
    user_name = serializers.CharField(read_only=True)
    user_type = serializers.IntegerField(read_only=True)  # 0: tourist, 1: farmer
    token = serializers.CharField(max_length=255, read_only=True)

    def validate(self, data):
        account_id = data.get('account_id', None)
        password = data.get('password', None)
        user = authenticate(username=account_id, password=password)

        if user is None:
            raise serializers.ValidationError(
                "아이디 또는 비밀번호가 잘못되었습니다. 아이디와 비밀번호를 정확히 입력해주세요."
            )
        try:
            token = TokenObtainPairSerializer.get_token(user)
            access_token = str(token.access_token)
        except User.DoesNotExist:
            raise serializers.ValidationError(
                "아이디 또는 비밀번호가 잘못되었습니다. 아이디와 비밀번호를 정확히 입력해주세요."
            )
        
        prof = user.profile
        mapping = {
            UserProfile.FARMER: 1,
            UserProfile.TOURIST: 0
        }

        return {
            'account_id': user.account_id,
            'user_name': user.user_name,
            'user_type': mapping[prof.user_type],
            'token': access_token
        }
# 데이터 처리
from .serializers import *
from .models import User, UserProfile

# APIView 사용
from rest_framework.views import APIView
from rest_framework import status
from rest_framework.response import Response

# 인증
from rest_framework.decorators import permission_classes
from rest_framework.permissions import AllowAny


# 아이디 중복확인 뷰
@permission_classes([AllowAny])  # 누구나 접근 가능
class CheckAccountIDView(APIView):
    def post(self, request):
        account_id = request.data.get('account_id')
        exists = User.objects.filter(account_id=account_id).exists()
        if exists:
            return Response({
                'exists': exists,
                'message': '이미 사용 중인 아이디입니다.'
            })
        else:
            return Response({
                'exists': exists,
                'message': '사용 가능한 아이디입니다.'   
            })

# 사업자 번호 중복 확인 뷰
@permission_classes([AllowAny])  # 누구나 접근 가능
class CheckBusinessRegNumberView(APIView):
    def post(self, request):
        business_reg_number = request.data.get('business_reg_number')
        exists = UserProfile.objects.filter(business_reg_number=business_reg_number).exists()
        if exists:
            return Response({
                'exists': exists,
                'message': '이미 가입된 사업자입니다.'
            })
        else:
            return Response({
                'exists': exists, 
            })
        
# 닉네임 중복 확인 뷰
@permission_classes([AllowAny])  # 누구나 접근 가능
class CheckUserNameView(APIView):
    def post(self, request):
        user_type = request.data.get('user_type')
        user_name = request.data.get('user_name')
        
        # user_type에 따라 처리 분기
        if user_type == 0:  # 관광객
            exists = User.objects.filter(user_name=user_name).exists()
            if exists:
                return Response({
                    'exists': exists,
                    'message': '이미 사용 중인 닉네임입니다.'
                })
            else:
                return Response({
                    'exists': exists,
                    'message': '사용 가능한 닉네임입니다.'
                })
        else:  # 농부
            # 농부 등 관광객이 아닐 때는 중복체크 하지 않음
            return Response({'exists': False, 'message': '중복확인 대상이 아닙니다.'})

# 회원가입 뷰
@permission_classes([AllowAny])  # 누구나 접근 가능
class SignupView(APIView):
    """
    POST body에 'user_type': 'tourist 또는 'farmer' 를 포함시켜서 각각 다른 Serializer로 분기 처리
    """
    def post(self, request):
        user_type = int(request.data.get('user_type'))
        if user_type == 0:  # 관광객
            serializer = TouristSignupSerializer(data=request.data)
        elif user_type == 1:  # 농부
            serializer = FarmerSignupSerializer(data=request.data)
        else:
            return Response(
                {'message': "user_type은 0(관광객) 또는 1(농부)만 가능합니다."},
                status=status.HTTP_400_BAD_REQUEST
            )
        
        serializer.is_valid(raise_exception=True)
        user = serializer.save()
        return Response(
            {
                'message': '회원가입이 완료되었습니다.',
                'account_id': user.account_id,
                'user_type': user.profile.user_type,  # UserProfile에서 user_type 가져오기
                'user_name': user.user_name
            },
            status=status.HTTP_201_CREATED
        )
    

# 로그인 뷰
@permission_classes([AllowAny])  # 누구나 접근 가능
class LoginView(APIView):
    """
    POST body에 'account_id'와 'password'를 포함시켜서 로그인
    """
    def post(self, request):
        serializer = UserLoginSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        response = {
            'account_id': serializer.validated_data['account_id'],
            'user_name': serializer.validated_data['user_name'],
            'user_type': serializer.validated_data['user_type'],
            'success': True,
            'token': serializer.validated_data['token']
        }
        return Response(response, status=status.HTTP_200_OK)
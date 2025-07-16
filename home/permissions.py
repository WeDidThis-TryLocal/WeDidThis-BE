from rest_framework.permissions import BasePermission

class IsTouristUser(BasePermission):
    """
    관람객(user_type=0)만 접근 허용
    """
    def has_permission(self, request, view):
        user = request.user
        if not user or not user.is_authenticated:
            return False
        try:
            # user.profile.user_type이 'tourist'이면 관람객 (0)
            return user.profile.user_type == 0
        except AttributeError:
            return False

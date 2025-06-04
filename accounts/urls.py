from django.urls import path
from .views import *


urlpatterns = [
    path('signup', SignupView.as_view()),
    path("login", LoginView.as_view()),
    path("check_account_id", CheckAccountIDView.as_view()),
    path("check_business_reg_number", CheckBusinessRegNumberView.as_view()),
    path("check_user_name", CheckUserNameView.as_view()),
]
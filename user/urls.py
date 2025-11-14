from django.urls import path

from . import views

app_name = 'user'

urlpatterns = [
    path('', views.LoginView.as_view(), name='login'),
    path('login/', views.LoginView.as_view(), name='login-explicit'),
    path('user/', views.UserIndexView.as_view(), name='index'),
    path('user/change-password/', views.ChangePasswordView.as_view(), name='change-password'),
    path('user/forgot-password/', views.ForgotPasswordView.as_view(), name='forgot-password'),
    path('logout/', views.LogoutView.as_view(), name='logout'),
]

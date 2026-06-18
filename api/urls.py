from django.urls import path
from . import views

urlpatterns = [
    path('register/', views.register_user),
    path('login/', views.login_user),
    path('profile/', views.get_profile),
    path('update-profile/', views.update_profile),
    path('activities/', views.get_activities),
    path('rewards/', views.get_rewards),
    path('esp/get-code/', views.esp_get_code),
    path('esp/check-scan/', views.esp_check_scan),
    path('esp/end-session/', views.esp_end_session),
    path('user/scan-qr/', views.user_scan_qr),
    path('employee/update-location/', views.employee_update_location),
    path('bins/', views.get_all_bins),
]
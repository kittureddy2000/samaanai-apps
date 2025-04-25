from django.urls import path
from . import views

app_name = 'calorie_tracker'

urlpatterns = [
    path('', views.simplified_entry, name='simplified_entry'),
    path('daily/', views.daily_report, name='daily_report'),
    path('weekly/', views.weekly_report, name='weekly_report'),
    path('monthly/', views.monthly_report, name='monthly_report'),
    path('profile/', views.user_profile, name='user_profile'),
    path('weight/', views.track_weight, name='track_weight'),
]
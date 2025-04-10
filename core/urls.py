# core/urls.py

from django.urls import path, include
from . import views

app_name = 'core'  # Define the namespace

urlpatterns = [

    path('', views.dashboard, name='dashboard'),  
    path('dashboard/', views.dashboard, name='dashboard'), 
    path('login/', views.login_view, name='login'),
    path('signup/', views.signup_view, name='signup'),  
    path('logout/', views.logout_view, name='logout'),
    path('oauth/', include('social_django.urls', namespace='social')),  # Social Auth URLs
    
]
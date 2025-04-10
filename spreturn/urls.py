from django.urls import path,include

from . import views

# Add the app_name here
app_name = 'spreturn'

urlpatterns = [
    path('', views.spreturn, name='spreturn'),
    path('sp-insights/', views.spreturn_insights, name='spreturn_insights'),
    path('add-sp-info/', views.add_sp_info, name='add-sp-info'),
]
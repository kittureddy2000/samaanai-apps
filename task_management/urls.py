from django.urls import path, include
from . import views, auth_utils,sync_utils
from django.conf.urls.static import static
from pathlib import Path  # Import Path from pathlib for file system operations

app_name = 'task_management'

urlpatterns = [
    path('^task_management/attachments/(?P<path>.*)$', views.serve_attachment),
    path('', views.get_lists, name='get_lists'),
    path('add/<int:list_id>/', views.add_task, name='add_task'),
    path('get_all_tasks/', views.get_all_tasks, name='get_all_tasks'),
    path('complete_task/<int:task_id>/', views.complete_task, name='complete_task'),
    path('mark_favorite/', views.mark_favorite, name='mark_favorite'),   
    path('get_task_details/<int:task_id>/', views.get_task_details, name='get_task_details'),   
    path('completed_tasks/', views.completed_tasks, name='completed_tasks'),   
    path('undelete_task/<int:task_id>/', views.undelete_task, name='undelete_task'),   
    path('edit_task/<int:task_id>/', views.edit_task, name='edit_task'),   
    path('edit_task_in_panel/<int:task_id>/', views.edit_task_in_panel, name='edit_task_in_panel'),   
    path('search_tasks/', views.search_tasks, name='search_tasks'),   
    path('create_task_list/', views.create_task_list, name='create_task_list'),
    path('get_tasks_by_list/<int:list_id>/', views.get_tasks_by_list, name='get_tasks_by_list'),
    path('delete_tasks/', views.delete_tasks, name='delete_tasks'),

    #Google and Micrsoft Task Sync
    path('sync_google_tasks/', views.sync_google_tasks, name='sync_google_tasks'),
    path('connect_microsoft/', auth_utils.connect_microsoft, name='connect_microsoft'),
    path('microsoft_callback/', auth_utils.microsoft_callback, name='microsoft_callback'),
    path('sync_microsoft_tasks/', views.sync_microsoft_tasks, name='sync_microsoft_tasks'),    
    path('sync_tasks/', sync_utils.trigger_background_sync, name='trigger_background_sync'),
    path('process_sync_task/', sync_utils.process_sync_task, name='process_sync_task'),
    path('trigger_user_sync/', views.trigger_user_sync, name='trigger_user_sync'),
    path('get_task_counts/', views.get_task_counts, name='get_task_counts'),
    path('process_ms_task_update/', sync_utils.process_ms_task_update, name='process_ms_task_update'),
    path('process_google_task_update/', sync_utils.process_google_task_update, name='process_google_task_update'),

] 


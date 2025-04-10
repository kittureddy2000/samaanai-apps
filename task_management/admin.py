from django.contrib import admin
from .models import Task, TaskList

class TaskListAdmin(admin.ModelAdmin):
    list_display = ('list_name', 'list_code', 'list_type')  # Fields to display in admin list view
    search_fields = ('list_name', 'list_code')  # Fields to be searchable in admin
    list_filter = ('list_type',)  # Fields to filter by in admin

admin.site.register(TaskList, TaskListAdmin)

class TaskAdmin(admin.ModelAdmin):
    list_display = ('task_name', 'user', 'list_name', 'due_date', 'task_completed', 'important')
    search_fields = ('task_name', 'user__username', 'list_name__list_name')
    list_filter = ('task_completed', 'important', 'list_name', 'user')
    date_hierarchy = 'due_date'  # Allows filtering by date hierarchy
    exclude = ('creation_date', 'last_update_date')  # Exclude certain fields from the form

admin.site.register(Task, TaskAdmin)

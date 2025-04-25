from django.contrib import admin
from .models import CalorieEntry

@admin.register(CalorieEntry)
class CalorieEntryAdmin(admin.ModelAdmin):
    list_display = ['user', 'date', 'entry_type', 'description', 'calories', 'created_at']
    list_filter = ['user', 'date', 'entry_type']
    search_fields = ['user__username', 'description']
    date_hierarchy = 'date'
from django.contrib import admin

# Register your models here.
from .models import spinfo


@admin.register(spinfo)
class spinfoAdmin(admin.ModelAdmin):
    list_display = (
        'year', 
        'avg_closing_price', 
        'year_open', 
        'year_high', 
        'year_low', 
        'year_close', 
        'spreturn', 
        'return_divident', 
        'inflation'
    )
    list_filter = ('year',)
    search_fields = ['year']

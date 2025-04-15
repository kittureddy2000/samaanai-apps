from django.contrib import admin

# Register your models here.
from django.contrib import admin
from .models import Portfolio, Stock, Transaction


@admin.register(Portfolio)
class PortfolioAdmin(admin.ModelAdmin):
    list_display = ('name', 'user', 'created_at')
    list_filter = ('user',)
    search_fields = ('name', 'user__username')
    date_hierarchy = 'created_at'


@admin.register(Stock)
class StockAdmin(admin.ModelAdmin):
    list_display = ('symbol', 'name')
    search_fields = ('symbol', 'name')
    
    actions = ['refresh_stock_data']
    
    def refresh_stock_data(self, request, queryset):
        """Admin action to refresh stock data for selected stocks"""
        from .services import StockDataService
        
        stock_service = StockDataService()
        symbols = [stock.symbol for stock in queryset]
        results = stock_service.refresh_multiple_stocks(symbols)
        
        updated = sum(1 for result in results.values() if result)
        
        self.message_user(request, f"Successfully updated {updated} out of {queryset.count()} stocks.")
    
    refresh_stock_data.short_description = "Refresh stock data from API"


@admin.register(Transaction)
class TransactionAdmin(admin.ModelAdmin):
    list_display = ('stock_symbol', 'transaction_type', 'quantity', 'price_per_share', 
                   'transaction_date', 'portfolio', 'total_value')
    list_filter = ('transaction_type', 'portfolio', 'transaction_date')
    search_fields = ('stock_symbol', 'portfolio__name')
    date_hierarchy = 'transaction_date'
    
    def total_value(self, obj):
        """Calculate and display the total value of the transaction"""
        return f"${obj.total_value:.2f}"
    
    total_value.short_description = "Total Value"
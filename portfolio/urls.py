from django.urls import path
from . import views
from . import api

app_name = 'portfolio'

urlpatterns = [
    # Dashboard
    path('', views.dashboard, name='dashboard'),
    
    # Portfolio management
    path('portfolios/', views.portfolio_list, name='portfolio_list'),
    path('portfolios/<int:pk>/', views.portfolio_detail, name='portfolio_detail'),
    path('portfolios/<int:pk>/delete/', views.delete_portfolio, name='delete_portfolio'),
    
    # Transaction management
    path('portfolios/<int:portfolio_pk>/transactions/', views.transaction_list, name='transaction_list'),
    path('portfolios/<int:portfolio_pk>/transactions/add/', views.add_transaction, name='add_transaction'),
    path('transactions/<int:transaction_pk>/edit/', views.edit_transaction, name='edit_transaction'),
    path('transactions/<int:transaction_pk>/delete/', views.delete_transaction, name='delete_transaction'),
    
    # Import transactions
    path('import-transactions/', views.import_transactions, name='import_transactions'),
    path('import-transactions/<int:portfolio_pk>/', views.import_transactions, name='import_transactions_portfolio'),
    path('download-template/', views.download_template, name='download_template'),
    
    # Stock price refresh
    path('portfolios/<int:portfolio_pk>/refresh/', views.refresh_stock_prices, name='refresh_stock_prices'),
    
    # Cloud Tasks API endpoints
    path('api/refresh-stocks/', api.refresh_stocks, name='api_refresh_stocks'),
    path('api/refresh-all-stocks/', api.refresh_all_stocks, name='api_refresh_all_stocks'),
    
    # Debug view
    path('debug/api/', views.debug_api, name='debug_api'),
]
from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.utils import timezone
from django.http import JsonResponse, HttpResponse
from django.db.models import Sum
from decimal import Decimal
import pandas as pd
import io
import logging
from django.urls import reverse

from .models import Portfolio, Transaction, Stock
from .forms import PortfolioForm, TransactionForm, TransactionImportForm
from .api import update_stock_info, StockAPIError, fetch_stock_data, get_api_key
from .tasks import refresh_stock_data, update_all_stocks_daily
from .services import StockDataService

logger = logging.getLogger(__name__)


@login_required
def dashboard(request):
    """Main dashboard view showing all portfolios summary"""
    portfolios = Portfolio.objects.filter(user=request.user)
    
    # Calculate total portfolio value across all portfolios
    total_value = sum(portfolio.get_total_value() for portfolio in portfolios)
    total_cost = sum(portfolio.get_total_cost() for portfolio in portfolios)
    total_gain_loss = total_value - total_cost
    
    # Calculate total gain/loss percentage
    if total_cost > 0:
        total_gain_loss_percentage = (total_gain_loss / total_cost) * 100
    else:
        total_gain_loss_percentage = Decimal('0.00')
    
    context = {
        'portfolios': portfolios,
        'total_value': total_value,
        'total_cost': total_cost,
        'total_gain_loss': total_gain_loss,
        'total_gain_loss_percentage': total_gain_loss_percentage,
    }
    
    return render(request, 'portfolio/portfolio_dashboard.html', context)


@login_required
def portfolio_list(request):
    """View to list all portfolios belonging to the user"""
    portfolios = Portfolio.objects.filter(user=request.user)
    
    # Handle new portfolio creation
    if request.method == 'POST':
        form = PortfolioForm(request.POST)
        if form.is_valid():
            portfolio = form.save(commit=False)
            portfolio.user = request.user
            portfolio.save()
            messages.success(request, f'Portfolio "{portfolio.name}" created successfully!')
            return redirect('portfolio:portfolio_detail', pk=portfolio.pk)
    else:
        form = PortfolioForm()
    
    context = {
        'portfolios': portfolios,
        'form': form,
    }
    
    return render(request, 'portfolio/portfolio_list.html', context)


@login_required
def portfolio_detail(request, pk):
    """View to show details of a specific portfolio"""
    portfolio = get_object_or_404(Portfolio, pk=pk, user=request.user)
    
    # Get the holdings data
    holdings = portfolio.get_holdings()
    
    # Trigger refresh of stock data for all stocks in this portfolio
    # This is done asynchronously using Google Cloud Tasks
    symbols = set(holding['symbol'] for holding in holdings)
    refresh_stock_data(list(symbols))
    
    # Calculate portfolio summary
    total_value = portfolio.get_total_value()
    total_cost = portfolio.get_total_cost()
    total_gain_loss = portfolio.get_total_gain_loss()
    total_gain_loss_percentage = portfolio.get_total_gain_loss_percentage()
    
    # Get recent transactions
    recent_transactions = Transaction.objects.filter(portfolio=portfolio).order_by('-transaction_date')[:10]
    
    context = {
        'portfolio': portfolio,
        'holdings': holdings,
        'total_value': total_value,
        'total_cost': total_cost,
        'total_gain_loss': total_gain_loss,
        'total_gain_loss_percentage': total_gain_loss_percentage,
        'recent_transactions': recent_transactions,
    }
    
    return render(request, 'portfolio/portfolio_detail.html', context)


@login_required
def transaction_list(request, portfolio_pk):
    """View to list and add transactions for a specific portfolio"""
    portfolio = get_object_or_404(Portfolio, pk=portfolio_pk, user=request.user)
    transactions = Transaction.objects.filter(portfolio=portfolio).order_by('-transaction_date')
    
    context = {
        'portfolio': portfolio,
        'transactions': transactions,
    }
    
    return render(request, 'portfolio/transaction_list.html', context)


@login_required
def add_transaction(request, portfolio_pk):
    """View to add a new transaction to a portfolio"""
    portfolio = get_object_or_404(Portfolio, pk=portfolio_pk, user=request.user)
    
    if request.method == 'POST':
        form = TransactionForm(request.POST)
        if form.is_valid():
            transaction = form.save(commit=False)
            transaction.portfolio = portfolio
            transaction.save()
            
            # Create or update the Stock record
            stock, created = Stock.objects.get_or_create(symbol=transaction.stock_symbol)
            
            # If this is a new stock or the price is stale, fetch updated data
            if created or stock.is_price_stale():
                update_stock_info(stock)
            
            messages.success(request, 'Transaction added successfully!')
            return redirect('portfolio:portfolio_detail', pk=portfolio_pk)
    else:
        form = TransactionForm(initial={'transaction_date': timezone.now()})
    
    context = {
        'portfolio': portfolio,
        'form': form,
        'action': 'Add',
    }
    
    return render(request, 'portfolio/transaction_form.html', context)


@login_required
def edit_transaction(request, transaction_pk):
    """View to edit an existing transaction"""
    transaction = get_object_or_404(Transaction, pk=transaction_pk)
    portfolio = transaction.portfolio
    
    # Ensure user owns this transaction's portfolio
    if portfolio.user != request.user:
        messages.error(request, "You don't have permission to edit this transaction.")
        return redirect('portfolio:dashboard')
    
    if request.method == 'POST':
        form = TransactionForm(request.POST, instance=transaction)
        if form.is_valid():
            form.save()
            messages.success(request, 'Transaction updated successfully!')
            return redirect('portfolio:portfolio_detail', pk=portfolio.pk)
    else:
        form = TransactionForm(instance=transaction)
    
    context = {
        'portfolio': portfolio,
        'form': form,
        'transaction': transaction,
        'action': 'Edit',
    }
    
    return render(request, 'portfolio/transaction_form.html', context)


@login_required
def delete_transaction(request, transaction_pk):
    """View to delete a transaction"""
    transaction = get_object_or_404(Transaction, pk=transaction_pk)
    portfolio = transaction.portfolio
    
    # Ensure user owns this transaction's portfolio
    if portfolio.user != request.user:
        messages.error(request, "You don't have permission to delete this transaction.")
        return redirect('portfolio:dashboard')
    
    if request.method == 'POST':
        transaction.delete()
        messages.success(request, 'Transaction deleted successfully!')
        return redirect('portfolio:portfolio_detail', pk=portfolio.pk)
    
    context = {
        'portfolio': portfolio,
        'transaction': transaction,
    }
    
    return render(request, 'portfolio/transaction_confirm_delete.html', context)


@login_required
def refresh_stock_prices(request, portfolio_pk):
    """
    Refresh stock prices for a portfolio
    """
    portfolio = get_object_or_404(Portfolio, pk=portfolio_pk, user=request.user)
    
    # Get list of unique stock symbols in the portfolio
    stock_symbols = set()
    for transaction in portfolio.transactions.all():
        stock_symbols.add(transaction.stock_symbol)
    
    if not stock_symbols:
        messages.info(request, "No stocks in portfolio to refresh.")
        return redirect('portfolio:portfolio_detail', pk=portfolio_pk)
    
    # Use the stock service to refresh prices
    stock_service = StockDataService()
    results = stock_service.refresh_multiple_stocks(stock_symbols)
    
    # Count successes and failures
    success_count = sum(1 for result in results.values() if result)
    error_count = len(results) - success_count
    
    if error_count > 0:
        messages.warning(
            request, 
            f"Refreshed {success_count} stocks. Unable to refresh {error_count} stocks due to API errors."
        )
    else:
        messages.success(request, f"Successfully refreshed prices for {success_count} stocks.")
    
    return redirect('portfolio:portfolio_detail', pk=portfolio_pk)


@login_required
def delete_portfolio(request, pk):
    """View to delete a portfolio"""
    portfolio = get_object_or_404(Portfolio, pk=pk, user=request.user)
    
    if request.method == 'POST':
        portfolio.delete()
        messages.success(request, f'Portfolio "{portfolio.name}" deleted successfully!')
        return redirect('portfolio:portfolio_list')
    
    context = {
        'portfolio': portfolio,
    }
    
    return render(request, 'portfolio/portfolio_confirm_delete.html', context)


@login_required
def debug_api(request):
    """Debug view to manually test Alpha Vantage API"""
    import json
    
    # Initialize context
    context = {
        'api_key': None,
        'test_symbol': 'AAPL',
        'result': None,
        'error': None,
    }
    
    # Only superusers can access this debug view
    if not request.user.is_superuser:
        context['error'] = 'Only superusers can access this debug view'
        return render(request, 'portfolio/debug_api.html', context)
    
    try:
        # Get API key
        context['api_key'] = f"{get_api_key()[:4]}...{get_api_key()[-4:]}"
        
        # If symbol is provided in request, use it
        if 'symbol' in request.GET:
            context['test_symbol'] = request.GET.get('symbol').upper()
        
        # Fetch data for the test symbol
        price, company_name = fetch_stock_data(context['test_symbol'])
        
        context['result'] = {
            'symbol': context['test_symbol'],
            'price': str(price),
            'company_name': company_name,
            'success': True,
        }
        
    except Exception as e:
        context['error'] = str(e)
        context['result'] = {
            'symbol': context['test_symbol'],
            'success': False,
        }
    
    return render(request, 'portfolio/debug_api.html', context)


@login_required
def import_transactions(request, portfolio_pk=None):
    """View to import transactions from a CSV or Excel file"""
    initial = {}
    if portfolio_pk:
        initial['portfolio'] = portfolio_pk
    
    if request.method == 'POST':
        form = TransactionImportForm(request.user, request.POST, request.FILES)
        if form.is_valid():
            portfolio = form.cleaned_data['portfolio']
            file = request.FILES['file']
            
            # Check file size (5MB limit)
            if file.size > 5 * 1024 * 1024:
                messages.error(request, 'File too large. Maximum size is 5MB.')
                return redirect('portfolio:import_transactions')
            
            # Determine file type and parse
            try:
                if file.name.endswith('.csv'):
                    df = pd.read_csv(file)
                else:  # Excel file
                    df = pd.read_excel(file)
                
                # Validate required columns
                required_columns = ['symbol', 'quantity', 'price_per_share']
                missing_columns = [col for col in required_columns if col not in df.columns]
                
                if missing_columns:
                    messages.error(request, f"Missing required columns: {', '.join(missing_columns)}. " 
                                          f"Required columns are: {', '.join(required_columns)}.")
                    return redirect('portfolio:import_transactions')
                
                # Optional columns
                if 'transaction_date' not in df.columns:
                    df['transaction_date'] = timezone.now()
                
                if 'transaction_type' not in df.columns:
                    df['transaction_type'] = 'BUY'  # Default to BUY
                
                # Process each row and create transactions
                success_count = 0
                error_count = 0
                errors = []
                
                for index, row in df.iterrows():
                    try:
                        # Validate transaction type
                        if row['transaction_type'].upper() not in ['BUY', 'SELL']:
                            error_count += 1
                            errors.append(f"Row {index+1}: Invalid transaction type. Must be 'BUY' or 'SELL'.")
                            continue
                        
                        # Create the transaction
                        transaction = Transaction(
                            portfolio=portfolio,
                            stock_symbol=row['symbol'].upper().strip(),
                            transaction_type=row['transaction_type'].upper(),
                            quantity=row['quantity'],
                            price_per_share=row['price_per_share'],
                            transaction_date=row['transaction_date'],
                        )
                        transaction.save()
                        
                        # Update stock info
                        stock, created = Stock.objects.get_or_create(symbol=transaction.stock_symbol)
                        if created or stock.is_price_stale():
                            update_stock_info(stock)
                        
                        success_count += 1
                    except Exception as e:
                        error_count += 1
                        errors.append(f"Row {index+1}: {str(e)}")
                
                # Show results
                if success_count > 0:
                    messages.success(request, f"Successfully imported {success_count} transactions.")
                
                if error_count > 0:
                    messages.warning(request, f"Encountered {error_count} errors during import.")
                    for error in errors[:10]:  # Show first 10 errors
                        messages.warning(request, error)
                    
                    if len(errors) > 10:
                        messages.warning(request, f"... and {len(errors) - 10} more errors.")
                
                return redirect('portfolio:portfolio_detail', pk=portfolio.pk)
                
            except Exception as e:
                messages.error(request, f"Error processing file: {str(e)}")
                return redirect('portfolio:import_transactions')
    else:
        form = TransactionImportForm(request.user, initial=initial)
    
    context = {
        'form': form,
    }
    
    return render(request, 'portfolio/import_transactions.html', context)


def download_template(request):
    """View to download a CSV template for transaction import"""
    response = HttpResponse(content_type='text/csv')
    response['Content-Disposition'] = 'attachment; filename="transaction_import_template.csv"'
    
    response.write('symbol,quantity,price_per_share,transaction_type,transaction_date\n')
    response.write('AAPL,10,150.50,BUY,2023-01-15\n')
    response.write('MSFT,5,280.75,BUY,2023-01-20\n')
    response.write('GOOGL,2,2500.00,SELL,2023-02-05\n')
    
    return response
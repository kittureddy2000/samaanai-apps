from django.db import models

# Create your models here.
from django.db import models
from django.contrib.auth.models import User
from django.utils import timezone
from decimal import Decimal


class Portfolio(models.Model):
    """Model representing a user's stock portfolio"""
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='portfolios')
    name = models.CharField(max_length=100)
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"{self.name} - {self.user.username}"
    
    def get_total_value(self):
        """Calculate the current total value of the portfolio"""
        total = Decimal('0.00')
        for holding in self.get_holdings():
            total += holding['current_value']
        return total
    
    def get_total_cost(self):
        """Calculate the total cost basis of the portfolio"""
        total = Decimal('0.00')
        for holding in self.get_holdings():
            total += holding['cost_basis']
        return total
    
    def get_total_gain_loss(self):
        """Calculate the total gain/loss of the portfolio"""
        return self.get_total_value() - self.get_total_cost()
    
    def get_total_gain_loss_percentage(self):
        """Calculate the total gain/loss percentage of the portfolio"""
        cost = self.get_total_cost()
        if cost == 0:
            return Decimal('0.00')
        return (self.get_total_gain_loss() / cost) * 100
    
    def get_holdings(self):
        """
        Calculate current holdings based on transactions
        Returns a list of dictionaries with stock holdings information
        """
        from portfolio.services import StockDataService
        stock_service = StockDataService()
        
        holdings = {}
        
        for transaction in self.transactions.all():
            symbol = transaction.stock_symbol
            
            if symbol not in holdings:
                holdings[symbol] = {
                    'symbol': symbol,
                    'quantity': Decimal('0.00'),
                    'cost_basis': Decimal('0.00'),
                }
            
            if transaction.transaction_type == 'BUY':
                current_quantity = holdings[symbol]['quantity']
                current_cost = holdings[symbol]['cost_basis']
                
                # Add shares and cost
                holdings[symbol]['quantity'] += transaction.quantity
                holdings[symbol]['cost_basis'] += transaction.quantity * transaction.price_per_share
            
            elif transaction.transaction_type == 'SELL':
                # Reduce shares (cost basis will be adjusted proportionally)
                if holdings[symbol]['quantity'] > 0:
                    sell_ratio = transaction.quantity / holdings[symbol]['quantity']
                    if sell_ratio > 1:
                        sell_ratio = 1  # Can't sell more than 100% of holdings
                    
                    holdings[symbol]['cost_basis'] -= holdings[symbol]['cost_basis'] * sell_ratio
                    holdings[symbol]['quantity'] -= transaction.quantity
        
        # Filter out positions with zero shares and calculate current values
        result = []
        total_portfolio_value = Decimal('0.00')
        
        # First pass: calculate total portfolio value for percentage calculations
        for symbol, data in holdings.items():
            if data['quantity'] > 0:
                # Get stock data from cache or API
                stock_data = stock_service.get_stock_data(symbol)
                # Convert float to Decimal for calculations
                current_price = Decimal(str(stock_data.get('current_price', 0.0)))
                current_value = data['quantity'] * current_price
                total_portfolio_value += current_value
        
        # Second pass: create holding entries with all data
        for symbol, data in holdings.items():
            if data['quantity'] > 0:
                # Get stock data from cache or API
                stock_data = stock_service.get_stock_data(symbol)
                # Convert float to Decimal for calculations
                current_price = Decimal(str(stock_data.get('current_price', 0.0)))
                
                # Calculate average cost per share
                avg_cost = Decimal('0.00')
                if data['quantity'] > 0:
                    avg_cost = data['cost_basis'] / data['quantity']
                
                # Calculate current value and gain/loss
                current_value = data['quantity'] * current_price
                gain_loss = current_value - data['cost_basis']
                gain_loss_percentage = Decimal('0.00')
                
                if data['cost_basis'] > 0:
                    gain_loss_percentage = (gain_loss / data['cost_basis']) * 100
                
                # Calculate portfolio percentage
                portfolio_percentage = Decimal('0.00')
                if total_portfolio_value > 0:
                    portfolio_percentage = (current_value / total_portfolio_value) * 100
                
                # Get other stock data, converting floats to Decimals
                company_name = stock_data.get('company_name', symbol)
                day_change = Decimal(str(stock_data.get('day_change', 0.0)))
                day_change_percentage = Decimal(str(stock_data.get('day_change_percentage', 0.0)))
                
                # Convert other float values to Decimal if they exist
                fifty_two_week_high = Decimal(str(stock_data.get('fifty_two_week_high'))) if stock_data.get('fifty_two_week_high') is not None else None
                fifty_two_week_low = Decimal(str(stock_data.get('fifty_two_week_low'))) if stock_data.get('fifty_two_week_low') is not None else None
                pe_ratio = Decimal(str(stock_data.get('pe_ratio'))) if stock_data.get('pe_ratio') is not None else None
                dividend_yield = Decimal(str(stock_data.get('dividend_yield'))) if stock_data.get('dividend_yield') is not None else None
                
                # Calculate day's gain $ (day's change × quantity)
                day_gain = day_change * data['quantity']
                
                # Calculate 52-week range deltas if available
                delta_from_52w_low = None
                delta_from_52w_high = None
                
                if fifty_two_week_low and current_price > 0:
                    delta_from_52w_low = current_price - fifty_two_week_low
                
                if fifty_two_week_high and current_price > 0:
                    delta_from_52w_high = fifty_two_week_high - current_price
                
                result.append({
                    'symbol': symbol,
                    'quantity': data['quantity'],
                    'avg_cost': avg_cost,
                    'cost_basis': data['cost_basis'],
                    'current_price': current_price,
                    'current_value': current_value,
                    'gain_loss': gain_loss,
                    'gain_loss_percentage': gain_loss_percentage,
                    'company_name': company_name,
                    'day_change_percentage': day_change_percentage,
                    'day_change': day_change,
                    'day_gain': day_gain,
                    'fifty_two_week_high': fifty_two_week_high,
                    'fifty_two_week_low': fifty_two_week_low,
                    'delta_from_52w_low': delta_from_52w_low,
                    'delta_from_52w_high': delta_from_52w_high,
                    'pe_ratio': pe_ratio,
                    'dividend_yield': dividend_yield,
                    'portfolio_percentage': portfolio_percentage,
                    'total_gain': gain_loss
                })
        
        # Sort holdings by value (descending)
        result.sort(key=lambda x: x['current_value'], reverse=True)
        return result


class Stock(models.Model):
    """
    Model representing basic stock information
    Note: Dynamic data like prices are stored in Redis cache
    """
    symbol = models.CharField(max_length=10, unique=True, db_index=True)
    name = models.CharField(max_length=200, blank=True)
    
    def __str__(self):
        return f"{self.symbol} - {self.name}"
    

class Transaction(models.Model):
    """Model representing a stock transaction"""
    TRANSACTION_TYPES = [
        ('BUY', 'Buy'),
        ('SELL', 'Sell')
    ]
    
    portfolio = models.ForeignKey(Portfolio, on_delete=models.CASCADE, related_name='transactions')
    stock_symbol = models.CharField(max_length=10, db_index=True)
    transaction_type = models.CharField(max_length=4, choices=TRANSACTION_TYPES)
    quantity = models.DecimalField(max_digits=15, decimal_places=4)  # Allow fractional shares
    price_per_share = models.DecimalField(max_digits=15, decimal_places=2)
    transaction_date = models.DateTimeField()
    created_at = models.DateTimeField(auto_now_add=True)
    
    def __str__(self):
        return f"{self.transaction_type} {self.quantity} {self.stock_symbol} @ {self.price_per_share}"
    
    @property
    def total_value(self):
        """Calculate the total value of the transaction"""
        return self.quantity * self.price_per_share
    
    class Meta:
        ordering = ['-transaction_date']
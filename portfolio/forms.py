from django import forms
from django.utils import timezone
from .models import Portfolio, Transaction
from django.core.validators import FileExtensionValidator


class PortfolioForm(forms.ModelForm):
    """Form for creating and editing portfolios"""
    class Meta:
        model = Portfolio
        fields = ['name']
        widgets = {
            'name': forms.TextInput(attrs={'class': 'form-control'})
        }


class TransactionForm(forms.ModelForm):
    """Form for creating and editing transactions"""
    transaction_date = forms.DateField(
        initial=timezone.now().date(),
        widget=forms.DateInput(
            attrs={
                'class': 'form-control',
                'type': 'date'
            }
        )
    )
    
    class Meta:
        model = Transaction
        fields = ['stock_symbol', 'transaction_type', 'quantity', 'price_per_share', 'transaction_date']
        widgets = {
            'stock_symbol': forms.TextInput(attrs={
                'class': 'form-control',
                'placeholder': 'e.g., AAPL, GOOGL'
            }),
            'transaction_type': forms.Select(attrs={'class': 'form-control'}),
            'quantity': forms.NumberInput(attrs={
                'class': 'form-control',
                'step': '0.0001',
                'min': '0.0001'
            }),
            'price_per_share': forms.NumberInput(attrs={
                'class': 'form-control',
                'step': '0.01',
                'min': '0.01'
            })
        }
    
    def clean_stock_symbol(self):
        """Convert stock symbol to uppercase"""
        symbol = self.cleaned_data.get('stock_symbol')
        if symbol:
            return symbol.upper().strip()
        return symbol
    
    def clean(self):
        """Validate transaction data"""
        cleaned_data = super().clean()
        transaction_type = cleaned_data.get('transaction_type')
        quantity = cleaned_data.get('quantity')
        
        # Validate quantity is positive
        if quantity and quantity <= 0:
            self.add_error('quantity', 'Quantity must be greater than zero.')
        
        # Additional validations for SELL transactions can be added here
        # For example, checking if the user has enough shares to sell
        
        return cleaned_data


class TransactionImportForm(forms.Form):
    """Form for importing transactions from a CSV or Excel file"""
    file = forms.FileField(
        label='Select a file',
        help_text='Max. 5 megabytes - CSV or Excel (.xlsx) files only',
        validators=[
            FileExtensionValidator(allowed_extensions=['csv', 'xlsx', 'xls'])
        ]
    )
    portfolio = forms.ModelChoiceField(
        queryset=Portfolio.objects.none(),
        required=True,
        label='Select portfolio'
    )
    
    def __init__(self, user, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # Filter portfolios by user
        self.fields['portfolio'].queryset = Portfolio.objects.filter(user=user)
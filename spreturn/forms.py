from django import forms
from .models import spinfo

class SPInfoForm(forms.ModelForm):
    class Meta:
        model = spinfo
        fields = ['year', 'avg_closing_price', 'year_open', 'year_high', 'year_low', 'year_close', 'spreturn', 'return_divident', 'inflation']



class SPReturnForm(forms.Form):
    numYears = forms.IntegerField(initial=30, label="Number of Years")
    reccuringDeposit = forms.ChoiceField(
        choices=[('Yes', 'Yes'), ('No', 'No')],
        initial='No',
        label="Recurring Deposit"
    )
    startingInvest = forms.DecimalField(initial=1.0, label="Starting Investment")
    reccuringDepositAmount = forms.DecimalField(initial=1.0, label="Recurring Amount")

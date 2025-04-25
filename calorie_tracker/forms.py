from django import forms
from django.utils import timezone
from .models import CalorieEntry, UserProfile, WeightEntry

class DateSelectForm(forms.Form):
    selected_date = forms.DateField(
        widget=forms.DateInput(attrs={'type': 'date'}),
        initial=timezone.now
    )

class CalorieEntryForm(forms.ModelForm):
    class Meta:
        model = CalorieEntry
        fields = ['entry_type', 'description', 'calories']
        widgets = {
            'description': forms.Textarea(attrs={'rows': 2, 'class': 'form-control'}),
            'calories': forms.NumberInput(attrs={'class': 'form-control'}),
        }

class BreakfastEntryForm(CalorieEntryForm):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.initial['entry_type'] = 'Breakfast'
        self.fields['entry_type'].widget = forms.HiddenInput()

class LunchEntryForm(CalorieEntryForm):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.initial['entry_type'] = 'Lunch'
        self.fields['entry_type'].widget = forms.HiddenInput()

class DinnerEntryForm(CalorieEntryForm):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.initial['entry_type'] = 'Dinner'
        self.fields['entry_type'].widget = forms.HiddenInput()

class SnackEntryForm(CalorieEntryForm):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.initial['entry_type'] = 'Snack'
        self.fields['entry_type'].widget = forms.HiddenInput()

class ExerciseEntryForm(CalorieEntryForm):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.initial['entry_type'] = 'Exercise'
        self.fields['entry_type'].widget = forms.HiddenInput()
        self.fields['calories'].label = 'Calories Burned'

class UserProfileForm(forms.ModelForm):
    date_of_birth = forms.DateField(
        widget=forms.DateInput(attrs={'type': 'date'}),
        required=False
    )
    
    class Meta:
        model = UserProfile
        fields = ['date_of_birth', 'height', 'gender', 'activity_level', 'basal_metabolic_rate', 'daily_calorie_goal', 'weekly_weight_loss_goal']
        widgets = {
            'height': forms.NumberInput(attrs={'class': 'form-control', 'step': '0.01'}),
            'gender': forms.Select(attrs={'class': 'form-select'}),
            'activity_level': forms.Select(attrs={'class': 'form-select'}),
            'basal_metabolic_rate': forms.NumberInput(attrs={'class': 'form-control'}),
            'daily_calorie_goal': forms.NumberInput(attrs={'class': 'form-control'}),
            'weekly_weight_loss_goal': forms.NumberInput(attrs={'class': 'form-control', 'step': '0.1'}),
        }
        labels = {
            'date_of_birth': 'Date of Birth',
            'height': 'Height (cm)',
            'gender': 'Gender',
            'activity_level': 'Activity Level',
            'basal_metabolic_rate': 'BMR (calories/day)',
            'daily_calorie_goal': 'Daily Calorie Goal',
            'weekly_weight_loss_goal': 'Weekly Weight Loss Goal (lbs)',
        }
        help_texts = {
            'basal_metabolic_rate': 'Your Basal Metabolic Rate (calories burned at rest)',
            'daily_calorie_goal': 'Your target daily calorie intake',
            'weekly_weight_loss_goal': 'Target weight loss per week in pounds',
        }

class WeightEntryForm(forms.ModelForm):
    date = forms.DateField(
        widget=forms.DateInput(attrs={'type': 'date'}),
        initial=timezone.now
    )
    
    class Meta:
        model = WeightEntry
        fields = ['date', 'weight', 'notes']
        widgets = {
            'weight': forms.NumberInput(attrs={'class': 'form-control', 'step': '0.1'}),
            'notes': forms.Textarea(attrs={'rows': 2, 'class': 'form-control'}),
        }
        labels = {
            'weight': 'Weight (kg)',
            'notes': 'Notes (optional)',
        }
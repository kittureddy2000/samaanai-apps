from django.shortcuts import render, redirect
from django.contrib.auth.decorators import login_required
from django.db.models import Sum
from django.utils import timezone
from datetime import datetime, timedelta, date
from dateutil.relativedelta import relativedelta
from .models import CalorieEntry, WeightEntry, UserProfile
from .forms import (
    DateSelectForm, BreakfastEntryForm, LunchEntryForm, 
    DinnerEntryForm, SnackEntryForm, ExerciseEntryForm,
    UserProfileForm, WeightEntryForm
)

@login_required
def simplified_entry(request):
    # Handle date selection
    selected_date = timezone.now().date()
    if request.method == 'GET' and 'selected_date' in request.GET:
        date_form = DateSelectForm(request.GET)
        if date_form.is_valid():
            selected_date = date_form.cleaned_data['selected_date']
    else:
        date_form = DateSelectForm(initial={'selected_date': selected_date})
    
    # Calculate previous and next day for navigation
    prev_day = selected_date - timedelta(days=1)
    next_day = selected_date + timedelta(days=1)
    
    # Handle form submission
    if request.method == 'POST':
        # Check if we're dealing with the simplified form
        if 'breakfast_calories' in request.POST or 'lunch_calories' in request.POST or \
           'dinner_calories' in request.POST or 'snack_calories' in request.POST or \
           'exercise_calories' in request.POST:
            
            # Get the date from the form or use the selected date
            entry_date = selected_date
            if 'selected_date' in request.POST:
                try:
                    entry_date = datetime.strptime(request.POST.get('selected_date'), '%Y-%m-%d').date()
                    selected_date = entry_date  # Update selected_date to maintain after redirect
                except ValueError:
                    pass
            
            # Delete existing entries for this date to replace them
            CalorieEntry.objects.filter(
                user=request.user,
                date=entry_date
            ).delete()
            
            # Process breakfast calories
            breakfast_calories = request.POST.get('breakfast_calories', '')
            if breakfast_calories.strip():
                try:
                    calories = int(breakfast_calories)
                    if calories > 0:
                        CalorieEntry.objects.create(
                            user=request.user,
                            date=entry_date,
                            entry_type='Breakfast',
                            description='Breakfast',
                            calories=calories
                        )
                except ValueError:
                    pass
            
            # Process lunch calories
            lunch_calories = request.POST.get('lunch_calories', '')
            if lunch_calories.strip():
                try:
                    calories = int(lunch_calories)
                    if calories > 0:
                        CalorieEntry.objects.create(
                            user=request.user,
                            date=entry_date,
                            entry_type='Lunch',
                            description='Lunch',
                            calories=calories
                        )
                except ValueError:
                    pass
            
            # Process dinner calories
            dinner_calories = request.POST.get('dinner_calories', '')
            if dinner_calories.strip():
                try:
                    calories = int(dinner_calories)
                    if calories > 0:
                        CalorieEntry.objects.create(
                            user=request.user,
                            date=entry_date,
                            entry_type='Dinner',
                            description='Dinner',
                            calories=calories
                        )
                except ValueError:
                    pass
            
            # Process snack calories
            snack_calories = request.POST.get('snack_calories', '')
            if snack_calories.strip():
                try:
                    calories = int(snack_calories)
                    if calories > 0:
                        CalorieEntry.objects.create(
                            user=request.user,
                            date=entry_date,
                            entry_type='Snack',
                            description='Snack',
                            calories=calories
                        )
                except ValueError:
                    pass
            
            # Process exercise calories
            exercise_calories = request.POST.get('exercise_calories', '')
            if exercise_calories.strip():
                try:
                    calories = int(exercise_calories)
                    if calories > 0:
                        CalorieEntry.objects.create(
                            user=request.user,
                            date=entry_date,
                            entry_type='Exercise',
                            description='Exercise',
                            calories=calories
                        )
                except ValueError:
                    pass
            
            # Process weight entry if provided
            weight = request.POST.get('weight', '')
            if weight.strip():
                try:
                    weight_value = float(weight)
                    if weight_value > 0:
                        # Check if entry for this date already exists
                        weight_entry, created = WeightEntry.objects.get_or_create(
                            user=request.user,
                            date=entry_date,
                            defaults={'weight': weight_value}
                        )
                        if not created:
                            weight_entry.weight = weight_value
                            weight_entry.save()
                except ValueError:
                    pass
            
            # Redirect to the same date after saving
            return redirect(f"{request.path}?selected_date={entry_date.strftime('%Y-%m-%d')}")
        
        # Handle the original form submission with entry_type
        elif 'entry_type' in request.POST:
            entry_type = request.POST.get('entry_type')
            
            # Select the appropriate form
            if entry_type == 'Breakfast':
                form = BreakfastEntryForm(request.POST)
                form_submitted = 'breakfast'
            elif entry_type == 'Lunch':
                form = LunchEntryForm(request.POST)
                form_submitted = 'lunch'
            elif entry_type == 'Dinner':
                form = DinnerEntryForm(request.POST)
                form_submitted = 'dinner'
            elif entry_type == 'Snack':
                form = SnackEntryForm(request.POST)
                form_submitted = 'snack'
            elif entry_type == 'Exercise':
                form = ExerciseEntryForm(request.POST)
                form_submitted = 'exercise'
            
            # Process the form
            if form.is_valid():
                entry = form.save(commit=False)
                entry.user = request.user
                entry.date = selected_date
                entry.save()
                # Redirect to avoid form resubmission
                return redirect('calorie_tracker:simplified_entry')
    
    # Get existing entries for this date
    entries = CalorieEntry.objects.filter(
        user=request.user,
        date=selected_date
    ).order_by('entry_type', '-created_at')
    
    # Group entries by type
    breakfast_entries = entries.filter(entry_type='Breakfast')
    lunch_entries = entries.filter(entry_type='Lunch')
    dinner_entries = entries.filter(entry_type='Dinner')
    snack_entries = entries.filter(entry_type='Snack')
    exercise_entries = entries.filter(entry_type='Exercise')
    
    # Calculate totals
    food_calories = entries.exclude(entry_type='Exercise').aggregate(Sum('calories'))['calories__sum'] or 0
    exercise_calories = entries.filter(entry_type='Exercise').aggregate(Sum('calories'))['calories__sum'] or 0
    net_calories = food_calories - exercise_calories
    
    # Get user's target calories
    user_profile = request.user.profile
    target_calories = user_profile.calculate_target_calories() or 0
    
    # Get weight entry for this date
    weight_entry = WeightEntry.objects.filter(user=request.user, date=selected_date).first()
    
    # Get existing calorie totals by type for prefilling the form
    breakfast_calories = breakfast_entries.aggregate(Sum('calories'))['calories__sum'] or ''
    lunch_calories = lunch_entries.aggregate(Sum('calories'))['calories__sum'] or ''
    dinner_calories = dinner_entries.aggregate(Sum('calories'))['calories__sum'] or ''
    snack_calories = snack_entries.aggregate(Sum('calories'))['calories__sum'] or ''
    exercise_calories = exercise_entries.aggregate(Sum('calories'))['calories__sum'] or ''
    
    context = {
        'date_form': date_form,
        'selected_date': selected_date,
        'prev_day': prev_day,
        'next_day': next_day,
        'breakfast_entries': breakfast_entries,
        'lunch_entries': lunch_entries,
        'dinner_entries': dinner_entries,
        'snack_entries': snack_entries,
        'exercise_entries': exercise_entries,
        'food_calories': food_calories,
        'exercise_calories': exercise_calories,
        'net_calories': net_calories,
        'target_calories': target_calories,
        'weight_entry': weight_entry,
        'breakfast_calories': breakfast_calories,
        'lunch_calories': lunch_calories,
        'dinner_calories': dinner_calories,
        'snack_calories': snack_calories,
        'exercise_calories': exercise_calories,
    }
    
    return render(request, 'calorie_tracker/simplified_entry.html', context)

@login_required
def daily_report(request):
    # Handle date selection
    selected_date = timezone.now().date()
    if request.method == 'GET' and 'selected_date' in request.GET:
        date_form = DateSelectForm(request.GET)
        if date_form.is_valid():
            selected_date = date_form.cleaned_data['selected_date']
    else:
        date_form = DateSelectForm(initial={'selected_date': selected_date})
    
    # Get previous and next day
    prev_day = selected_date - timedelta(days=1)
    next_day = selected_date + timedelta(days=1)
    
    # Get entries for the selected date
    entries = CalorieEntry.objects.filter(
        user=request.user,
        date=selected_date
    ).order_by('entry_type')
    
    # Calculate totals
    food_entries = entries.exclude(entry_type='Exercise')
    exercise_entries = entries.filter(entry_type='Exercise')
    
    food_calories = food_entries.aggregate(Sum('calories'))['calories__sum'] or 0
    exercise_calories = exercise_entries.aggregate(Sum('calories'))['calories__sum'] or 0
    net_calories = food_calories - exercise_calories
    
    context = {
        'date_form': date_form,
        'selected_date': selected_date,
        'prev_day': prev_day,
        'next_day': next_day,
        'entries': entries,
        'food_entries': food_entries,
        'exercise_entries': exercise_entries,
        'food_calories': food_calories,
        'exercise_calories': exercise_calories,
        'net_calories': net_calories,
    }
    
    return render(request, 'calorie_tracker/daily_report.html', context)

@login_required
def weekly_report(request):
    """
    Display weekly caloric data from Wednesday to Tuesday
    """
    today = timezone.now().date()
    
    # Determine the current week's Wednesday and Tuesday
    # If today is Tuesday, use previous Wednesday
    # If today is Wednesday or later, use current Wednesday
    if today.weekday() == 1:  # Tuesday is 1
        end_date = today
        start_date = end_date - timedelta(days=6)
    else:
        # Find the Wednesday of this week
        days_since_wednesday = (today.weekday() - 2) % 7
        current_wednesday = today - timedelta(days=days_since_wednesday)
        
        # If today is before Wednesday, use previous week
        if today.weekday() < 2:  # Monday (0), Tuesday (1)
            start_date = current_wednesday - timedelta(days=7)
            end_date = start_date + timedelta(days=6)
        else:  # Wednesday to Sunday
            start_date = current_wednesday
            end_date = start_date + timedelta(days=6)
    
    # Handle week navigation
    if 'direction' in request.GET:
        direction = request.GET.get('direction')
        weeks = int(request.GET.get('weeks', 1))
        
        if direction == 'prev':
            start_date = start_date - timedelta(weeks=weeks)
            end_date = end_date - timedelta(weeks=weeks)
        elif direction == 'next':
            start_date = start_date + timedelta(weeks=weeks)
            end_date = end_date + timedelta(weeks=weeks)
    
    # Get previous and next week
    prev_week_start = start_date - timedelta(weeks=1)
    next_week_start = start_date + timedelta(weeks=1)
    
    # Get entries for the selected week
    entries = CalorieEntry.objects.filter(
        user=request.user,
        date__gte=start_date,
        date__lte=end_date
    ).order_by('date', 'entry_type')
    
    # Get user's profile data
    user_profile = request.user.profile
    bmr = user_profile.basal_metabolic_rate or 0
    target_calories = user_profile.calculate_target_calories() or 0
    
    # Calculate daily totals for the week
    daily_totals = []
    chart_dates = []
    food_calories_data = []
    exercise_calories_data = []
    net_calories_data = []
    target_calories_data = []
    
    # For calories remaining calculation from last Wednesday to today
    consumed_calories_until_today = 0
    target_calories_until_today = 0
    
    for day_offset in range(7):
        current_date = start_date + timedelta(days=day_offset)
        day_entries = entries.filter(date=current_date)
        
        food_cals = day_entries.exclude(entry_type='Exercise').aggregate(Sum('calories'))['calories__sum'] or 0
        exercise_cals = day_entries.filter(entry_type='Exercise').aggregate(Sum('calories'))['calories__sum'] or 0
        net_cals = food_cals - exercise_cals
        
        daily_totals.append({
            'date': current_date,
            'food_calories': food_cals,
            'exercise_calories': exercise_cals,
            'net_calories': net_cals,
            'target_calories': target_calories,
        })
        
        # Prepare chart data
        chart_dates.append(current_date.strftime('%a'))
        food_calories_data.append(food_cals)
        exercise_calories_data.append(exercise_cals)
        net_calories_data.append(net_cals)
        target_calories_data.append(target_calories)
        
        # Calculate totals for days up to today
        if current_date <= today:
            consumed_calories_until_today += net_cals
            target_calories_until_today += target_calories
    
    # Calculate weekly totals
    weekly_food_calories = sum(day['food_calories'] for day in daily_totals)
    weekly_exercise_calories = sum(day['exercise_calories'] for day in daily_totals)
    weekly_net_calories = weekly_food_calories - weekly_exercise_calories
    weekly_target_calories = target_calories * 7
    
    # Calculate weekly calories remaining for the entire week
    weekly_calories_remaining = weekly_target_calories - weekly_net_calories
    
    # Calculate calories remaining until today (target - consumed)
    calories_remaining_until_today = target_calories_until_today - consumed_calories_until_today
    
    context = {
        'start_date': start_date,
        'end_date': end_date,
        'prev_week_start': prev_week_start,
        'next_week_start': next_week_start,
        'entries': entries,
        'daily_totals': daily_totals,
        'weekly_food_calories': weekly_food_calories,
        'weekly_exercise_calories': weekly_exercise_calories,
        'weekly_net_calories': weekly_net_calories,
        'weekly_target_calories': weekly_target_calories,
        'weekly_calories_remaining': weekly_calories_remaining,
        'calories_remaining_until_today': calories_remaining_until_today,
        'chart_dates': chart_dates,
        'food_calories_data': food_calories_data,
        'exercise_calories_data': exercise_calories_data,
        'net_calories_data': net_calories_data,
        'target_calories_data': target_calories_data,
    }
    
    return render(request, 'calorie_tracker/weekly_report.html', context)

@login_required
def monthly_report(request):
    today = timezone.now().date()
    
    # Default to current month
    year = today.year
    month = today.month
    
    # Handle month selection
    if 'month' in request.GET and 'year' in request.GET:
        try:
            year = int(request.GET.get('year'))
            month = int(request.GET.get('month'))
        except ValueError:
            pass
    
    # Calculate first and last day of the month
    first_day = date(year, month, 1)
    if month == 12:
        last_day = date(year+1, 1, 1) - timedelta(days=1)
    else:
        last_day = date(year, month+1, 1) - timedelta(days=1)
    
    # Get previous and next month
    if month == 1:
        prev_month = 12
        prev_year = year - 1
    else:
        prev_month = month - 1
        prev_year = year
    
    if month == 12:
        next_month = 1
        next_year = year + 1
    else:
        next_month = month + 1
        next_year = year
    
    # Get entries for the selected month
    entries = CalorieEntry.objects.filter(
        user=request.user,
        date__gte=first_day,
        date__lte=last_day
    ).order_by('date', 'entry_type')
    
    # Calculate daily totals
    days_in_month = (last_day - first_day).days + 1
    daily_totals = []
    
    for day in range(1, days_in_month + 1):
        current_date = date(year, month, day)
        day_entries = entries.filter(date=current_date)
        
        food_cals = day_entries.exclude(entry_type='Exercise').aggregate(Sum('calories'))['calories__sum'] or 0
        exercise_cals = day_entries.filter(entry_type='Exercise').aggregate(Sum('calories'))['calories__sum'] or 0
        net_cals = food_cals - exercise_cals
        
        daily_totals.append({
            'date': current_date,
            'food_calories': food_cals,
            'exercise_calories': exercise_cals,
            'net_calories': net_cals,
        })
    
    # Calculate monthly totals
    monthly_food_calories = sum(day['food_calories'] for day in daily_totals)
    monthly_exercise_calories = sum(day['exercise_calories'] for day in daily_totals)
    monthly_net_calories = monthly_food_calories - monthly_exercise_calories
    
    # Get month name
    month_name = first_day.strftime('%B')
    
    context = {
        'year': year,
        'month': month,
        'month_name': month_name,
        'first_day': first_day,
        'last_day': last_day,
        'prev_month': prev_month,
        'prev_year': prev_year,
        'next_month': next_month,
        'next_year': next_year,
        'entries': entries,
        'daily_totals': daily_totals,
        'monthly_food_calories': monthly_food_calories,
        'monthly_exercise_calories': monthly_exercise_calories,
        'monthly_net_calories': monthly_net_calories,
    }
    
    return render(request, 'calorie_tracker/monthly_report.html', context)

@login_required
def user_profile(request):
    """View and edit user profile information"""
    # Get or create user profile
    try:
        profile = request.user.profile
    except:
        # Create a profile for existing users if they don't have one
        profile = UserProfile.objects.create(user=request.user)
    
    if request.method == 'POST':
        form = UserProfileForm(request.POST, instance=profile)
        if form.is_valid():
            profile_instance = form.save(commit=False)
            
            # Only auto-calculate BMR if the field is empty and we have all required data
            if not profile_instance.basal_metabolic_rate:
                calculated_bmr = profile_instance.calculate_bmr()
                if calculated_bmr:
                    profile_instance.basal_metabolic_rate = calculated_bmr
            
            # Always update daily calorie goal based on BMR and weight loss goal
            if profile_instance.basal_metabolic_rate and profile_instance.weekly_weight_loss_goal:
                profile_instance.daily_calorie_goal = profile_instance.calculate_target_calories()
                    
            profile_instance.save()
            return redirect('calorie_tracker:user_profile')
    else:
        form = UserProfileForm(instance=profile)
    
    # Get weight entries
    weight_entries = WeightEntry.objects.filter(user=request.user).order_by('-date')[:10]
    
    context = {
        'form': form,
        'profile': profile,
        'weight_entries': weight_entries,
    }
    
    return render(request, 'calorie_tracker/user_profile.html', context)

@login_required
def track_weight(request):
    """Add or edit weight entries"""
    today = timezone.now().date()
    
    # Check if there's an entry for today
    today_entry = WeightEntry.objects.filter(user=request.user, date=today).first()
    
    if request.method == 'POST':
        form = WeightEntryForm(request.POST, instance=today_entry)
        if form.is_valid():
            entry = form.save(commit=False)
            entry.user = request.user
            entry.save()
            
            # Update BMR if profile has sufficient data
            request.user.profile.save()
            
            # Redirect to avoid form resubmission
            return redirect('calorie_tracker:track_weight')
    else:
        form = WeightEntryForm(instance=today_entry)
    
    # Get weight history for chart
    weight_entries = WeightEntry.objects.filter(user=request.user).order_by('-date')[:30]
    
    context = {
        'form': form,
        'weight_entries': weight_entries,
    }
    
    return render(request, 'calorie_tracker/track_weight.html', context)
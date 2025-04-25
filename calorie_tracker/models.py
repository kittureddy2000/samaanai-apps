from django.db import models
from django.contrib.auth.models import User
from django.utils import timezone
from django.core.validators import MinValueValidator
from django.db.models.signals import post_save
from django.dispatch import receiver

class CalorieEntry(models.Model):
    ENTRY_TYPE_CHOICES = [
        ('Breakfast', 'Breakfast'),
        ('Lunch', 'Lunch'),
        ('Dinner', 'Dinner'),
        ('Snack', 'Snack'),
        ('Exercise', 'Exercise'),
    ]
    
    user = models.ForeignKey(User, on_delete=models.CASCADE)
    date = models.DateField(default=timezone.now)
    entry_type = models.CharField(max_length=10, choices=ENTRY_TYPE_CHOICES)
    description = models.TextField(blank=True)
    calories = models.IntegerField(default=0, 
                                  help_text="Use positive values for food, negative for exercise")
    
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    class Meta:
        ordering = ['-date', 'entry_type']
        verbose_name_plural = "Calorie Entries"
    
    def __str__(self):
        return f"{self.user.username} - {self.entry_type} on {self.date}: {self.calories} calories"
    
    @property
    def is_exercise(self):
        return self.entry_type == 'Exercise'

class UserProfile(models.Model):
    GENDER_CHOICES = [
        ('M', 'Male'),
        ('F', 'Female'),
        ('O', 'Other'),
    ]
    
    ACTIVITY_LEVEL_CHOICES = [
        ('S', 'Sedentary (little or no exercise)'),
        ('L', 'Lightly active (light exercise/sports 1-3 days/week)'),
        ('M', 'Moderately active (moderate exercise/sports 3-5 days/week)'),
        ('V', 'Very active (hard exercise/sports 6-7 days a week)'),
        ('E', 'Extra active (very hard exercise, physical job or training twice a day)'),
    ]
    
    user = models.OneToOneField(User, on_delete=models.CASCADE, related_name='profile')
    date_of_birth = models.DateField(null=True, blank=True)
    height = models.DecimalField(max_digits=5, decimal_places=2, null=True, blank=True, help_text="Height in cm")
    gender = models.CharField(max_length=1, choices=GENDER_CHOICES, null=True, blank=True)
    activity_level = models.CharField(max_length=1, choices=ACTIVITY_LEVEL_CHOICES, default='S')
    basal_metabolic_rate = models.IntegerField(null=True, blank=True, help_text="BMR in calories/day")
    daily_calorie_goal = models.IntegerField(default=2000, help_text="Daily calorie goal")
    weekly_weight_loss_goal = models.DecimalField(max_digits=3, decimal_places=1, default=0.0, help_text="Weekly weight loss goal in pounds")
    
    def __str__(self):
        return f"{self.user.username}'s Profile"
    
    def calculate_bmr(self):
        """Calculate Basal Metabolic Rate based on user's profile data"""
        # Need weight, height, age and gender
        # Get the most recent weight entry
        latest_weight = WeightEntry.objects.filter(user=self.user).order_by('-date').first()
        
        if not latest_weight or not self.height or not self.date_of_birth or not self.gender:
            return None
            
        # Calculate age
        from datetime import date
        today = date.today()
        age = today.year - self.date_of_birth.year - ((today.month, today.day) < (self.date_of_birth.month, self.date_of_birth.day))
        
        # Convert weight to kg (already in kg)
        weight_kg = float(latest_weight.weight)
        
        # Convert height to cm (already in cm)
        height_cm = float(self.height)
        
        # Mifflin-St Jeor Equation
        if self.gender == 'M':  # Male
            bmr = 10 * weight_kg + 6.25 * height_cm - 5 * age + 5
        else:  # Female or Other
            bmr = 10 * weight_kg + 6.25 * height_cm - 5 * age - 161
            
        # Apply activity level multiplier
        activity_multipliers = {
            'S': 1.2,  # Sedentary
            'L': 1.375,  # Lightly active
            'M': 1.55,  # Moderately active
            'V': 1.725,  # Very active
            'E': 1.9  # Extra active
        }
        
        bmr *= activity_multipliers.get(self.activity_level, 1.2)
        
        return int(bmr)
    
    def calculate_target_calories(self):
        """Calculate target calories based on BMR and weight loss goal"""
        if not self.basal_metabolic_rate or not self.weekly_weight_loss_goal:
            return None
            
        # Convert weekly weight loss goal to daily calorie deficit
        # 1 pound = 3500 calories
        daily_deficit = (self.weekly_weight_loss_goal * 3500) / 7
        
        return int(self.basal_metabolic_rate - daily_deficit)
    
    def save(self, *args, **kwargs):
        # Update daily calorie goal based on BMR and weight loss goal if both are set
        if self.basal_metabolic_rate and self.weekly_weight_loss_goal:
            self.daily_calorie_goal = self.calculate_target_calories()
        
        super().save(*args, **kwargs)

class WeightEntry(models.Model):
    user = models.ForeignKey(User, on_delete=models.CASCADE)
    date = models.DateField(default=timezone.now)
    weight = models.DecimalField(max_digits=5, decimal_places=2, validators=[MinValueValidator(0)], help_text="Weight in kg")
    notes = models.TextField(blank=True)
    
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    class Meta:
        ordering = ['-date']
        verbose_name_plural = "Weight Entries"
        unique_together = ['user', 'date']
        
    def __str__(self):
        return f"{self.user.username}'s weight on {self.date}: {self.weight} kg"

@receiver(post_save, sender=User)
def create_user_profile(sender, instance, created, **kwargs):
    """Create a user profile when a new user is created"""
    if created:
        UserProfile.objects.create(user=instance)

@receiver(post_save, sender=User)
def save_user_profile(sender, instance, **kwargs):
    """Save the user profile when the user is saved"""
    # Check if profile exists first to avoid RelatedObjectDoesNotExist error
    try:
        if hasattr(instance, 'profile'):
            instance.profile.save()
    except Exception:
        # If there's any error, create the profile
        UserProfile.objects.get_or_create(user=instance)
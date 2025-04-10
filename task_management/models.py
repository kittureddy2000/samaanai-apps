from django.db import models
from django.utils import timezone
from django.contrib.auth.models import User
from django.conf import settings

class TaskList(models.Model):
    LIST_TYPE_CHOICES = (
        ('special', 'Special'),  # For dynamic lists like "Important," "Past Due," "All Tasks"
        ('google_primary', 'Google Primary'),  # For "G My Tasks"
        ('microsoft_primary', 'Microsoft Primary'),  # For "MS Tasks"
        ('normal', 'Normal'),  # For all other lists (e.g., "G Mobile List," "MS Books")
    )

    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='task_lists', null=True)
    list_name = models.CharField(max_length=200)
    list_code = models.CharField(max_length=500, null=True)
    list_type = models.CharField(max_length=20, choices=LIST_TYPE_CHOICES, default='normal')  # Replace special_list
    list_source = models.CharField(max_length=50, null=True, blank=True)

    def __str__(self):
        return self.list_name

    class Meta:
        ordering = ['list_name']  # Optional, for consistency

class Task(models.Model):
    NO_RECURRENCE = 'NO_RECURRENCE'
    DAILY = 'DAILY'
    WEEKLY = 'WEEKLY'
    MONTHLY = 'MONTHLY'
    YEARLY = 'YEARLY'

    RECURRENCE_CHOICES = [
        (NO_RECURRENCE, 'No Recurrence'),
        (DAILY, 'Daily'),
        (WEEKLY, 'Weekly'),
        (MONTHLY, 'Monthly'),
        (YEARLY, 'Yearly'),
    ]
    SOURCE_CHOICES = [
        ('google', 'Google'),
        ('microsoft', 'Microsoft'),
    ]
    
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE)
    task_name = models.CharField(max_length=2000)
    list_name = models.ForeignKey(TaskList, on_delete=models.SET_DEFAULT, default=1, blank=True)
    task_description = models.TextField(null=True, blank=True)
    due_date = models.DateTimeField(null=True, blank=True)
    reminder_time = models.DateTimeField(blank = True, null=True)
    recurrence = models.CharField(max_length=100, choices=RECURRENCE_CHOICES, blank=True)
    task_completed = models.BooleanField(default=False)
    important = models.BooleanField(default=False)
    assigned_to = models.CharField(max_length=100, null=True, blank=True)
    source = models.CharField(max_length=30, choices=SOURCE_CHOICES, blank=True, null=True)
    source_id = models.CharField(max_length=255, null=True, blank=True)
    creation_date = models.DateTimeField(auto_now_add=True)
    last_update_date = models.DateTimeField(auto_now=True)

    def __str__(self):
        return self.task_name

    class Meta:
        ordering = ['-creation_date']
        unique_together = ('source', 'source_id')
        indexes = [
            models.Index(fields=['user', 'task_completed', 'due_date']),
        ]
        
class Image(models.Model):
    task = models.ForeignKey(Task, on_delete=models.CASCADE, related_name='images')
    image_url = models.URLField(max_length=500)
    image_name = models.CharField(max_length=255,default='imageblank.png')        


class TaskHistory(models.Model):
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE)
    task_name = models.CharField(max_length=200)
    list_name = models.ForeignKey(TaskList, on_delete=models.SET_DEFAULT, default=1, blank=True)
    task_description = models.CharField(max_length=2000, null=True, blank=True)  # Remove the comma here
    due_date = models.DateTimeField(null=True, blank=True)
    reminder_time = models.DateTimeField(default=timezone.now, null=True, blank=True)
    recurrence = models.CharField(max_length=100, blank=True)
    task_completed = models.BooleanField(default=False)
    important = models.BooleanField(default=False)
    assigned_to = models.CharField(max_length=100, null=True, blank=True)
    creation_date = models.DateTimeField(auto_now_add=True)
    last_update_date = models.DateTimeField(auto_now=True)
    source_id = models.CharField(max_length=255, unique=True)   
    source = models.CharField(max_length=255, null=True, blank=True)  # Add this

    def __str__(self):
        return self.task_name

    class Meta:
        ordering = ['-creation_date']
        unique_together = ('source', 'source_id')

class TaskSyncStatus(models.Model):
    user = models.ForeignKey(User, on_delete=models.CASCADE)
    provider = models.CharField(max_length=20, choices=[('google', 'Google'), ('microsoft', 'Microsoft')])
    is_complete = models.BooleanField(default=False)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        unique_together = ('user', 'provider')

    def __str__(self):
        return f"{self.user.username} - {self.provider} Sync Status: {self.is_complete}"
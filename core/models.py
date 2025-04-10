from django.db import models
from django.contrib.auth.models import User
from django.utils import timezone
from datetime import timedelta

class UserToken(models.Model):
    PROVIDER_CHOICES = [
        ('google', 'Google'),
        ('microsoft', 'Microsoft'),
    ]

    user = models.ForeignKey(User, on_delete=models.CASCADE)  # Changed from OneToOneField
    provider = models.CharField(max_length=20, choices=PROVIDER_CHOICES)
    access_token = models.TextField()
    refresh_token = models.TextField(null=True, blank=True)
    token_type = models.CharField(max_length=50, null=True, blank=True)
    expires_in = models.IntegerField(null=True, blank=True)  # Duration in seconds
    token_expires_at = models.DateTimeField(null=True, blank=True)  
    last_synced_at = models.DateTimeField(null=True, blank=True)
    
    class Meta:
        indexes = [
            models.Index(fields=['user', 'provider']),
        ]

    def __str__(self):
        return f"{self.user.username} - {self.provider.capitalize()}"

    def set_token_expiry(self):
        if self.expires_in:
            self.token_expires_at = timezone.now() + timedelta(seconds=self.expires_in)
        else:
            self.token_expires_at = None

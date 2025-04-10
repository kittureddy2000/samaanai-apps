# core/pipeline.py

from core.models import UserToken
from django.utils import timezone
from datetime import timedelta

def save_tokens(strategy, details, backend, user, response, *args, **kwargs):
    """
    Saves access and refresh tokens to UserToken model.
    Handles both Google and Microsoft providers.
    """
    provider = backend.name  # 'google-oauth2' or 'microsoft'
    access_token = response.get('access_token')
    refresh_token = response.get('refresh_token')
    expires_in = response.get('expires_in')  # Duration in seconds

    if provider == 'google-oauth2':
        provider_name = 'google'
    elif provider == 'microsoft':
        provider_name = 'microsoft'
    else:
        provider_name = None  # Handle other providers if any

    if provider_name and access_token:
        try:
            user_token = UserToken.objects.get(user=user, provider=provider_name)
            user_token.access_token = access_token
            if refresh_token:
                user_token.refresh_token = refresh_token
            user_token.expires_in = expires_in
            user_token.set_token_expiry()
            user_token.save()
        except UserToken.DoesNotExist:
            user_token = UserToken.objects.create(
                user=user,
                provider=provider_name,
                access_token=access_token,
                refresh_token=refresh_token,
                expires_in=expires_in,
            )
            user_token.set_token_expiry()
            user_token.save()
    """
    Saves access and refresh tokens to UserToken model.
    Handles both Google and Microsoft providers.
    """
    provider = backend.name  # 'google-oauth2' or 'microsoft'
    access_token = response.get('access_token')
    refresh_token = response.get('refresh_token')
    expires_in = response.get('expires_in')  # Duration in seconds

    if provider == 'google-oauth2':
        provider_name = 'google'
    elif provider == 'microsoft':
        provider_name = 'microsoft'
    else:
        provider_name = None  # Handle other providers if any

    if provider_name and access_token:
        try:
            user_token = UserToken.objects.get(user=user, provider=provider_name)
            user_token.access_token = access_token
            if refresh_token:
                user_token.refresh_token = refresh_token
            user_token.expires_in = expires_in
            user_token.set_token_expiry()
            user_token.save()
        except UserToken.DoesNotExist:
            user_token = UserToken.objects.create(
                user=user,
                provider=provider_name,
                access_token=access_token,
                refresh_token=refresh_token,
                expires_in=expires_in,
            )
            user_token.set_token_expiry()
            user_token.save()
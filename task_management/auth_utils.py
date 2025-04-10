# auth_utils.py
import msal
from django.conf import settings
from django.shortcuts import redirect, HttpResponse
from django.utils import timezone
from core.models import UserToken
import logging
from django.contrib.auth.decorators import login_required

logger = logging.getLogger(__name__)

# Microsoft OAuth handlers (unchanged)
@login_required
def connect_microsoft(request):
    msal_app = msal.ConfidentialClientApplication(
        client_id=settings.MICROSOFT_AUTH['CLIENT_ID'],
        client_credential=settings.MICROSOFT_AUTH['CLIENT_SECRET'],
        authority=settings.MICROSOFT_AUTH['AUTHORITY']
    )
    auth_url = msal_app.get_authorization_request_url(
        scopes=settings.MICROSOFT_AUTH['SCOPE'],
        redirect_uri=settings.MICROSOFT_AUTH['REDIRECT_URI'],
        state=request.get_full_path()
    )
    return redirect(auth_url)

@login_required
def microsoft_callback(request):
    code = request.GET.get('code')
    if not code:
        error = request.GET.get('error', 'Unknown error')
        error_description = request.GET.get('error_description', 'No description provided.')
        logger.error(f"Microsoft callback error: {error} - {error_description}")
        return HttpResponse(f"Authentication failed: {error_description}", status=400)

    msal_app = msal.ConfidentialClientApplication(
        client_id=settings.MICROSOFT_AUTH['CLIENT_ID'],
        client_credential=settings.MICROSOFT_AUTH['CLIENT_SECRET'],
        authority=settings.MICROSOFT_AUTH['AUTHORITY']
    )
    result = msal_app.acquire_token_by_authorization_code(
        code=code, scopes=settings.MICROSOFT_AUTH["SCOPE"],
        redirect_uri=settings.MICROSOFT_AUTH["REDIRECT_URI"]
    )
    if "access_token" in result:
        user = request.user
        defaults = {
            'access_token': result["access_token"],
            'token_type': result.get("token_type"),
            'expires_in': result.get("expires_in"),
        }
        if "refresh_token" in result:
            defaults['refresh_token'] = result["refresh_token"]
        user_token, _ = UserToken.objects.update_or_create(
            user=user, provider='microsoft', defaults=defaults
        )
        user_token.set_token_expiry()
        user_token.save()
        return redirect('/dashboard/')
    error = result.get("error", "Unknown error")
    error_description = result.get("error_description", "No description provided.")
    return HttpResponse(f"Could not retrieve access token: {error_description}", status=400)

def refresh_microsoft_token(user_token):
    """
    Refreshes the Microsoft access token using the refresh token.
    Updates the UserToken model with the new access token and expiry.
    Returns the new access token or None if refresh fails.
    """
    msal_app = msal.ConfidentialClientApplication(
        client_id=settings.MICROSOFT_AUTH['CLIENT_ID'],
        client_credential=settings.MICROSOFT_AUTH['CLIENT_SECRET'],
        authority=settings.MICROSOFT_AUTH['AUTHORITY']
    )

    result = msal_app.acquire_token_by_refresh_token(
        refresh_token=user_token.refresh_token,
        scopes=settings.MICROSOFT_AUTH["SCOPE"]
    )

    if "access_token" in result:
        user_token.access_token = result["access_token"]
        user_token.expires_in = result.get("expires_in")
        user_token.token_type = result.get("token_type")
        if "refresh_token" in result:
            user_token.refresh_token = result["refresh_token"]
        user_token.set_token_expiry()
        user_token.save()
        logger.info(f"Refreshed Microsoft token for user: {user_token.user.username}")
        return result["access_token"]
    else:
        logger.error(f"Failed to refresh Microsoft token for user {user_token.user.username}: {result.get('error_description')}")
        return None

def is_token_expired(user_token):
    """
    Checks if the access token is expired.
    Returns True if expired, False otherwise.
    """
    if user_token.token_expires_at:
        return timezone.now() >= user_token.token_expires_at
    return False  # If no expiry info, assume not expired (adjust as needed)

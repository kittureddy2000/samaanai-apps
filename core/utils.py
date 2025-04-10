# core/utils.py
import logging
from django.conf import settings

logger = logging.getLogger(__name__)

# In core/utils.py
from django.core.mail import EmailMessage

def send_email(subject, message, recipient_list, html_message=None, from_email=None):
    if html_message:
        email = EmailMessage(
            subject=subject,
            body=message,  # Plain text fallback
            from_email=from_email or settings.DEFAULT_FROM_EMAIL,
            to=recipient_list,
            cc=None,
            bcc=None,
            reply_to=None,
        )
        email.content_subtype = "html"  # Set content type to HTML
        email.send()
    else:
        from django.core.mail import send_mail
        send_mail(
            subject=subject,
            message=message,
            from_email=from_email or settings.DEFAULT_FROM_EMAIL,
            recipient_list=recipient_list,
            fail_silently=True,
        )
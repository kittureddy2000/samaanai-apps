from django.utils.html import format_html
from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build
from google.auth.transport.requests import Request
from django.conf import settings
from .models import Task, Image
from core.models import UserToken
from google.cloud import storage
from pathlib import Path
import uuid
import logging
from .auth_utils import is_token_expired, refresh_microsoft_token    

logger = logging.getLogger(__name__)

def get_google_service(user):
    token = UserToken.objects.get(user=user, provider='google')
    creds = Credentials(
        token=token.access_token,
        refresh_token=token.refresh_token,
        token_uri='https://oauth2.googleapis.com/token',
        client_id=settings.SOCIAL_AUTH_GOOGLE_OAUTH2_KEY,
        client_secret=settings.SOCIAL_AUTH_GOOGLE_OAUTH2_SECRET,
        scopes=['https://www.googleapis.com/auth/tasks'],
    )
    if creds.expired and creds.refresh_token:
        creds.refresh(Request())
        token.access_token = creds.token
        token.save()
    return build('tasks', 'v1', credentials=creds)

def get_ms_access_token(user):
    token = UserToken.objects.get(user=user, provider='microsoft')
    if is_token_expired(token):
        access_token = refresh_microsoft_token(token)
    else:
        access_token = token.access_token
    return access_token

def handle_image_upload(task, images):
    task_management_attachments_dir = Path(__file__).resolve().parent / 'attachments'
    task_management_attachments_dir.mkdir(exist_ok=True)

    for image in images:
        if settings.ENVIRONMENT == 'development':
            file_name = f"{uuid.uuid4()}_{image.name}"
            file_path = task_management_attachments_dir / file_name
            with open(file_path, 'wb+') as destination:
                for chunk in image.chunks():
                    destination.write(chunk)
            Image.objects.create(
                task=task,
                image_url=f"/task_management/attachments/{file_name}",
                image_name=image.name
            )
        else:
            client = storage.Client()
            bucket = client.get_bucket(settings.GS_BUCKET_NAME)
            blob = bucket.blob(str(uuid.uuid4()))
            blob.upload_from_file(image, content_type=image.content_type)
            blob.make_public()
            Image.objects.create(task=task, image_url=blob.public_url, image_name=image.name)

def generate_sync_report(updates):
    if not updates:
        return "<p>No updates were made during this sync.</p>"
    html = """
    <table border="1" style="border-collapse: collapse; width: 100%;">
        <thead>
            <tr style="background-color: #f2f2f2;">
                <th style="padding: 8px;">Source</th>
                <th style="padding: 8px;">Task Name</th>
                <th style="padding: 8px;">Action</th>
                <th style="padding: 8px;">Timestamp</th>
                <th style="padding: 8px;">List Name</th>
                <th style="padding: 8px;">Key Fields Updated</th>
            </tr>
        </thead>
        <tbody>
    """
    for update in updates:
        fields_updated = ", ".join([f"{k}: {v}" for k, v in update.get('updated_fields', {}).items()]) if update.get('updated_fields') else "-"
        html += format_html(
            """
            <tr>
                <td style="padding: 8px;">{}</td>
                <td style="padding: 8px;">{}</td>
                <td style="padding: 8px;">{}</td>
                <td style="padding: 8px;">{}</td>
                <td style="padding: 8px;">{}</td>
                <td style="padding: 8px;">{}</td>
            </tr>
            """,
            update['provider'],
            update['task_name'],
            update['action'],
            update['timestamp'].strftime('%Y-%m-%d %H:%M:%S UTC'),
            update['list_name'] if update['list_name'] else "N/A",
            fields_updated
        )
    html += "</tbody></table>"
    return html
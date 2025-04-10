# In task_management/signals.py
from django.db.models.signals import post_save
from django.dispatch import receiver
from .models import Task
import logging
import json
import os
from google.cloud import tasks_v2
from django.conf import settings

logger = logging.getLogger(__name__)

@receiver(post_save, sender=Task)
def sync_task_update(sender, instance, created, **kwargs):
    """
    When a task is updated, sync it with external services asynchronously using Google Cloud Tasks.
    """
    # Skip if this is a sync-triggered save to prevent infinite recursion
    if hasattr(instance, '_skip_signal') and instance._skip_signal:
        logger.debug(f"Skipping signal for task {instance.task_name} to prevent recursion")
        return
    
    # Skip automatic updates for external tasks when they're loaded
    # Only trigger updates when they are specifically updated by the user
    if instance.source in ['microsoft', 'google'] and hasattr(instance, 'user'):
        # If this is just a page load or a task that was automatically modified
        # by the system (and not explicitly by a user), don't trigger sync
        if not created and not kwargs.get('update_fields'):
            logger.debug(f"Skipping auto-sync for {instance.source.capitalize()} task {instance.task_name} - not user-initiated")
            return
        
        logger.info(f"Scheduling Cloud Task for {instance.source.capitalize()} task update: {instance.task_name}")
        
        # Determine which endpoint to use based on the source
        endpoint = 'process_ms_task_update' if instance.source == 'microsoft' else 'process_google_task_update'
        queue_name = 'ms-task-update-queue' if instance.source == 'microsoft' else 'google-task-update-queue'
        
        # Create a Cloud Task
        try:
            # If in development, call the function directly 
            # (or use a local tasks emulator if available)
            if settings.ENVIRONMENT == 'development':
                from django.test import Client
                client_http = Client()
                task_body = json.dumps({"user_id": instance.user.id, "task_id": instance.id}).encode()
                client_http.post(f'/task_management/{endpoint}/',
                                task_body,
                                content_type='application/json')
            else:
                # Create and queue the Cloud Task
                client = tasks_v2.CloudTasksClient()
                project = os.environ.get('PROJECT_ID', 'your-project-id')
                location = 'us-west1'  # Your Cloud Tasks queue location
                
                parent = client.queue_path(project, location, queue_name)
                
                task_body = json.dumps({
                    "user_id": instance.user.id,
                    "task_id": instance.id
                }).encode()
                
                task = {
                    'http_request': {
                        'http_method': tasks_v2.HttpMethod.POST,
                        'url': f'{settings.BASE_URL}/task_management/{endpoint}/',
                        'body': task_body,
                        'headers': {'Content-Type': 'application/json'},
                    }
                }
                
                client.create_task(request={'parent': parent, 'task': task})
                logger.info(f"Enqueued Cloud Task for {instance.source.capitalize()} task update: {instance.task_name}")
        
        except Exception as e:
            logger.error(f"Error creating Cloud Task for {instance.source.capitalize()} task update: {e}", exc_info=True)
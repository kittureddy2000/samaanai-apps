# sync_utils.py
from django.conf import settings
from django.utils import timezone
from .models import Task, TaskList,  TaskSyncStatus
from core.models import UserToken
from .utils import get_google_service, get_ms_access_token, generate_sync_report
from googleapiclient.discovery import build
from google.oauth2.credentials import Credentials
from google.auth.transport.requests import Request
from dateutil import parser as date_parser
import requests
import json
import logging
import os
from google.cloud import tasks_v2
from django.http import HttpResponse, JsonResponse
from django.views.decorators.csrf import csrf_exempt
from django.contrib.auth.models import User
from datetime import datetime
from core.utils import send_email
from .auth_utils import is_token_expired, refresh_microsoft_token    




logger = logging.getLogger(__name__)


# Fetch and save Google Tasks
def fetch_google_tasks_and_save(user, creds):
    updates = []
    logger.info(f"Starting Google Tasks sync for user: {user.username}")
    
    try:
        service = build('tasks', 'v1', credentials=creds, cache=None)    
        token_record = UserToken.objects.get(user=user, provider='google')
        last_synced_at = token_record.last_synced_at
        logger.info(f"Last sync time: {last_synced_at}")
        
        # Step 1: Get all Google task lists
        logger.info("Fetching Google Tasks lists")
        try:
            tasklists_results = service.tasklists().list().execute()
            task_lists = tasklists_results.get('items', [])
            logger.info(f"Found {len(task_lists)} Google task lists")
        except Exception as e:
            logger.error(f"Error fetching Google task lists: {e}")
            return [{'provider': 'Google Tasks', 'error': str(e), 'action': 'Error', 'timestamp': timezone.now()}]
        
        # Track all task IDs processed in this sync
        all_synced_task_ids = set()
        
        for task_list in task_lists:
            list_title = task_list.get('title', 'Unnamed List')
            list_id = task_list.get('id')
            
            logger.info(f"Processing Google list: '{list_title}' (ID: {list_id})")
            
            # Create or get a TaskList for each Google task list
            if list_title == "My Tasks":
                # Create or get "G My Tasks" as a google_primary list
                google_task_list, created = TaskList.objects.get_or_create(
                    user=user,
                    list_code=list_id,
                    defaults={
                        'list_name': "G My Tasks",
                        'list_type': 'google_primary',
                        'list_source': 'Google'
                    }
                )
                if created:
                    logger.info(f"Created primary Google list 'G My Tasks' for list '{list_title}'")
                else:
                    logger.info(f"Using existing primary Google list 'G My Tasks'")
            else:
                # Create or get other Google lists as normal lists with "G" prefix
                google_task_list, created = TaskList.objects.get_or_create(
                    user=user,
                    list_code=list_id,
                    defaults={
                        'list_name': f"G {list_title}",
                        'list_type': 'normal',
                        'list_source': 'Google'
                    }
                )
                if created:
                    logger.info(f"Created new Google list 'G {list_title}'")
                else:
                    logger.info(f"Using existing Google list '{google_task_list.list_name}'")
            
            # Build the request parameters
            request_params = {
                'tasklist': list_id,
                'showCompleted': True,
                'showHidden': True,
                'maxResults': 100
            }
            
            # Add updatedMin parameter if we have a last sync time
            if last_synced_at:
                updated_min = last_synced_at.isoformat()
                request_params['updatedMin'] = updated_min
                logger.info(f"Fetching tasks updated since: {updated_min}")
            
            # Get tasks that have been updated since last sync
            all_tasks = []
            
            # Handle pagination for tasks
            page_token = None
            page_count = 0
            
            while True:
                page_count += 1
                if page_token:
                    request_params['pageToken'] = page_token
                
                try:
                    tasks_results = service.tasks().list(**request_params).execute()
                    items = tasks_results.get('items', [])
                    all_tasks.extend(items)
                    
                    logger.info(f"Retrieved page {page_count} with {len(items)} tasks from '{list_title}'")
                    
                    # Debug each task status
                    for task in items:
                        logger.debug(f"Task '{task.get('title', 'No Title')}' status: {task.get('status')}")
                    
                    # Check if there are more pages
                    page_token = tasks_results.get('nextPageToken')
                    if not page_token:
                        break
                except Exception as e:
                    logger.error(f"Error fetching tasks from list '{list_title}': {e}")
                    break
            
            logger.info(f"Total updated tasks found in '{list_title}': {len(all_tasks)}")
            
            # Process the tasks
            for task in all_tasks:
                if not task.get('title'):
                    logger.warning("Skipping task without title")
                    continue
                    
                google_task_id = task.get('id')
                all_synced_task_ids.add(google_task_id)
                
                task_title = task.get('title', 'No Title')
                
                # Google uses 'status' field with values 'needsAction' or 'completed'
                raw_status = task.get('status', 'needsAction')
                is_completed = raw_status == 'completed'
                logger.debug(f"Task '{task_title}' status from Google: {raw_status}, interpreted as completed={is_completed}")
                
                task_notes = task.get('notes', '')
                
                due_date_raw = task.get('due')
                due_date = None
                if due_date_raw:
                    try:
                        due_date = datetime.fromisoformat(due_date_raw.replace('Z', '+00:00'))
                    except Exception as e:
                        logger.warning(f"Failed to parse due date for task '{task_title}': {e}")
                
                existing_task = Task.objects.filter(user=user, source_id=google_task_id, source='google').first()
                if existing_task:
                    # Update existing task
                    updated = False
                    updated_fields = {}
                    
                    if existing_task.task_name != task_title:
                        updated_fields['task_name'] = task_title
                        existing_task.task_name = task_title
                        updated = True
                    
                    if existing_task.task_description != task_notes:
                        updated_fields['task_description'] = task_notes
                        existing_task.task_description = task_notes
                        updated = True
                    
                    # Explicitly log the completion status comparison
                    logger.debug(f"Task '{task_title}': DB status={existing_task.task_completed}, Google status={is_completed}")
                    if existing_task.task_completed != is_completed:
                        updated_fields['task_completed'] = is_completed
                        existing_task.task_completed = is_completed
                        updated = True
                        logger.info(f"Updating completion status for '{task_title}' to {is_completed}")
                    
                    if existing_task.due_date != due_date:
                        updated_fields['due_date'] = due_date.strftime('%Y-%m-%d') if due_date else None
                        existing_task.due_date = due_date
                        updated = True
                    
                    if updated:
                        existing_task.last_update_date = timezone.now()
                        existing_task.save()
                        logger.info(f"Updated Google task '{task_title}' with changes: {', '.join(updated_fields.keys())}")
                        updates.append({
                            'provider': 'Google Tasks',
                            'task_name': task_title,
                            'action': 'Updated',
                            'timestamp': timezone.now(),
                            'list_name': existing_task.list_name.list_name,
                            'updated_fields': updated_fields
                        })
                else:
                    # Create new task
                    logger.info(f"Creating new Google task '{task_title}' with completed={is_completed}")
                    new_task = Task.objects.create(
                        user=user, 
                        task_name=task_title, 
                        task_completed=is_completed,
                        task_description=task_notes,
                        due_date=due_date,
                        list_name=google_task_list, 
                        source_id=google_task_id, 
                        source='google',
                        creation_date=timezone.now(), 
                        last_update_date=timezone.now()
                    )
                    updates.append({
                        'provider': 'Google Tasks',
                        'task_name': task_title,
                        'action': 'Created',
                        'timestamp': timezone.now(),
                        'list_name': google_task_list.list_name
                    })
            
            # If this is the first sync (no last_synced_at), we need to get a complete picture
            # to properly handle deletions
            if not last_synced_at:
                logger.info("First sync detected - getting all task IDs to establish baseline")
                
                # Get all task IDs from this list to establish a baseline
                all_task_ids_request = {
                    'tasklist': list_id,
                    'showCompleted': True,
                    'showHidden': True,
                    'maxResults': 100,
                    'fields': 'items(id)'  # Only request ID field to minimize data transfer
                }
                
                # Handle pagination
                all_google_task_ids = set()
                next_page_token = None
                
                while True:
                    if next_page_token:
                        all_task_ids_request['pageToken'] = next_page_token
                    
                    try:
                        result = service.tasks().list(**all_task_ids_request).execute()
                        for task in result.get('items', []):
                            all_google_task_ids.add(task['id'])
                        
                        next_page_token = result.get('nextPageToken')
                        if not next_page_token:
                            break
                    except Exception as e:
                        logger.error(f"Error fetching all task IDs from list '{list_title}': {e}")
                        break
                
                # Update our tracking set with ALL task IDs from this list
                all_synced_task_ids.update(all_google_task_ids)
                logger.info(f"Total task IDs found in list '{list_title}': {len(all_google_task_ids)}")
        
        # Only check for deletions if this is the first sync or explicitly requested
        # Otherwise, we can skip the deletion check as we're only processing modifications
        if not last_synced_at:
            # Now detect deletions - find tasks in DB that weren't in the API response
            deleted_tasks = Task.objects.filter(
                user=user, source='google'
            ).exclude(source_id__in=all_synced_task_ids)
            
            logger.info(f"Found {deleted_tasks.count()} tasks to mark as deleted (completed)")
            
            # Handle the deleted tasks
            for deleted_task in deleted_tasks:
                # Only mark as completed if not already completed
                if not deleted_task.task_completed:
                    deleted_task.task_completed = True
                    deleted_task.save()
                    logger.info(f"Marked task '{deleted_task.task_name}' as completed (deleted from Google)")
                    updates.append({
                        'provider': 'Google Tasks',
                        'task_name': deleted_task.task_name,
                        'action': 'Marked as Completed (deleted from Google)',
                        'timestamp': timezone.now(),
                        'list_name': deleted_task.list_name.list_name
                    })
        
        # Update last_synced_at timestamp
        token_record.last_synced_at = datetime.now(timezone.utc)
        token_record.save()
        logger.info(f"Google sync completed successfully with {len(updates)} updates")
        
        return updates
    
    except UserToken.DoesNotExist:
        logger.error(f"Google token not found for user {user.username}")
        return [{'provider': 'Google Tasks', 'error': 'Token not found', 'action': 'Error', 'timestamp': timezone.now()}]
    except Exception as e:
        logger.error(f"Unexpected error during Google sync for user {user.username}: {e}", exc_info=True)
        return [{'provider': 'Google Tasks', 'error': str(e), 'action': 'Error', 'timestamp': timezone.now()}]

# Fetch and save Microsoft Tasks
def fetch_microsoft_tasks_and_save(user, access_token):
    updates = []
    logger.info(f"Starting Microsoft Tasks sync for user: {user.username}")
    
    try:
        token_record = UserToken.objects.get(user=user, provider='microsoft')
        last_synced_at = token_record.last_synced_at
        logger.info(f"Last sync time: {last_synced_at}")
        
        headers = {'Authorization': f'Bearer {access_token}', 'Content-Type': 'application/json'}
        
        # Step 1: Get all Microsoft task lists
        logger.info("Fetching Microsoft To Do lists")
        todo_lists_url = "https://graph.microsoft.com/v1.0/me/todo/lists"
        
        try:
            response = requests.get(todo_lists_url, headers=headers, timeout=30)
            response.raise_for_status()
            microsoft_lists = response.json().get("value", [])
            logger.info(f"Found {len(microsoft_lists)} Microsoft To Do lists")
        except requests.exceptions.RequestException as e:
            logger.error(f"Error fetching Microsoft To Do lists: {e}")
            return [{'provider': 'Microsoft To Do', 'error': str(e), 'action': 'Error', 'timestamp': timezone.now()}]
        
        # Track all task IDs processed in this sync
        all_synced_task_ids = set()
        
        # Process each task list
        for ms_list in microsoft_lists:
            list_display_name = ms_list.get("displayName", "Unnamed List")
            list_id = str(ms_list["id"])
            
            logger.info(f"Processing Microsoft list: '{list_display_name}' (ID: {list_id})")
            
            # Create or get the appropriate TaskList in the database
            if list_display_name == "Tasks":
                ms_task_list, created = TaskList.objects.get_or_create(
                    user=user,
                    list_code=list_id,
                    defaults={
                        'list_name': "MS Tasks",
                        'list_type': 'microsoft_primary',
                        'list_source': 'Microsoft'
                    }
                )
            else:
                ms_task_list, created = TaskList.objects.get_or_create(
                    user=user,
                    list_code=list_id,
                    defaults={
                        'list_name': f"MS {list_display_name}",
                        'list_type': 'normal',
                        'list_source': 'Microsoft'
                    }
                )
            
            # Build the filter query using last_synced_at
            filter_query = ""
            if last_synced_at:
                # Format the date according to Microsoft Graph API requirements
                last_sync_str = last_synced_at.replace(microsecond=0).isoformat().replace('+00:00', 'Z')
                filter_query = f"?$filter=lastModifiedDateTime ge {last_sync_str}"
                logger.info(f"Filtering tasks modified since: {last_sync_str}")
            
            # Fetch tasks that have been changed since last sync
            tasks_url = f"https://graph.microsoft.com/v1.0/me/todo/lists/{list_id}/tasks{filter_query}"
            
            # Use pagination to get all modified tasks, with page limit
            all_ms_tasks = []
            next_link = tasks_url
            page_count = 0
            max_pages = getattr(settings, 'MS_SYNC_MAX_PAGES', 30)
            
            while next_link and page_count < max_pages:
                page_count += 1
                try:
                    tasks_response = requests.get(next_link, headers=headers, timeout=30)
                    tasks_response.raise_for_status()
                    tasks_data = tasks_response.json()
                    
                    page_tasks = tasks_data.get("value", [])
                    all_ms_tasks.extend(page_tasks)
                    logger.info(f"Retrieved page {page_count} with {len(page_tasks)} tasks from '{list_display_name}'")
                    
                    next_link = tasks_data.get("@odata.nextLink")
                except requests.exceptions.RequestException as e:
                    logger.error(f"Error fetching tasks from list '{list_display_name}': {e}")
                    break
            
            if next_link and page_count >= max_pages:
                logger.warning(f"Reached maximum page limit ({max_pages}) when fetching MS tasks. Some tasks may not be synced.")
                
            logger.info(f"Total modified tasks found in '{list_display_name}': {len(all_ms_tasks)}")
            
            # Process tasks with more controlled error handling
            for task_item in all_ms_tasks:
                try:
                    ms_task_id = task_item["id"]
                    all_synced_task_ids.add(ms_task_id)
                    
                    title = task_item.get("title", "Untitled")
                    
                    # Microsoft uses 'status' field with 'completed' for completed tasks
                    raw_status = task_item.get("status", "notStarted")
                    is_completed = raw_status == 'completed'
                    
                    # Handle due date
                    due_date_raw = task_item.get("dueDateTime")
                    due_date = None
                    if due_date_raw and "dateTime" in due_date_raw:
                        try:
                            naive_due_date = date_parser.parse(due_date_raw["dateTime"])
                            due_date = timezone.make_aware(naive_due_date, timezone.get_default_timezone())
                        except Exception as e:
                            logger.warning(f"Failed to parse due date for task '{title}': {e}")
                    
                    # Get task notes/description (ensure it's not too long)
                    task_notes = ""
                    if task_item.get("body") and task_item["body"].get("content"):
                        task_notes = task_item["body"]["content"]
                    
                    # Check if task already exists
                    existing_task = Task.objects.filter(user=user, source_id=ms_task_id, source='microsoft').first()
                    
                    if existing_task:
                        # Update existing task logic
                        updated = False
                        updated_fields = {}
                        
                        if existing_task.task_name != title:
                            existing_task.task_name = title
                            updated_fields['task_name'] = title
                            updated = True
                        
                        if existing_task.task_description != task_notes:
                            existing_task.task_description = task_notes
                            updated_fields['task_description'] = task_notes
                            updated = True
                        
                        if existing_task.task_completed != is_completed:
                            existing_task.task_completed = is_completed
                            updated_fields['task_completed'] = is_completed
                            updated = True
                            logger.info(f"Updating completion status for '{title}' to: {is_completed}")
                        
                        if existing_task.due_date != due_date:
                            existing_task.due_date = due_date
                            updated_fields['due_date'] = due_date.strftime('%Y-%m-%d') if due_date else None
                            updated = True
                        
                        if updated:
                            existing_task.last_update_date = timezone.now()
                            existing_task.save()
                            logger.info(f"Updated Microsoft task '{title}' with changes: {', '.join(updated_fields.keys())}")
                            updates.append({
                                'provider': 'Microsoft To Do',
                                'task_name': title,
                                'action': 'Updated',
                                'timestamp': timezone.now(),
                                'list_name': ms_task_list.list_name,
                                'updated_fields': updated_fields
                            })
                    else:
                        # Create new task individually
                        logger.info(f"Creating new Microsoft task '{title}' with completed={is_completed}")
                        new_task = Task(
                            user=user, 
                            task_name=title, 
                            task_completed=is_completed, 
                            task_description=task_notes,
                            due_date=due_date,
                            list_name=ms_task_list, 
                            source='microsoft', 
                            source_id=ms_task_id,
                            creation_date=timezone.now(), 
                            last_update_date=timezone.now()
                        )
                        new_task.save()
                        logger.info(f"Successfully created Microsoft task: {title} with ID: {ms_task_id}")
                        updates.append({
                            'provider': 'Microsoft To Do',
                            'task_name': title,
                            'action': 'Created',
                            'timestamp': timezone.now(),
                            'list_name': ms_task_list.list_name
                        })
                except Exception as e:
                    logger.error(f"Error processing Microsoft task '{title if 'title' in locals() else 'unknown'}': {e}", exc_info=True)
                    # Continue with next task
        
        # End of sync process - update timestamp
        old_timestamp = token_record.last_synced_at if token_record.last_synced_at else "None"
        token_record.last_synced_at = datetime.now(timezone.utc)
        token_record.save()
        logger.info(f"Updated last_synced_at from {old_timestamp} to {token_record.last_synced_at}")
        
        logger.info(f"Microsoft sync completed successfully with {len(updates)} updates")
        return updates
        
    except UserToken.DoesNotExist:
        logger.error(f"Microsoft token not found for user {user.username}")
        return [{'provider': 'Microsoft To Do', 'error': 'Token not found', 'action': 'Error', 'timestamp': timezone.now()}]
    except Exception as e:
        logger.error(f"Unexpected error during Microsoft sync for user {user.username}: {e}", exc_info=True)
        return [{'provider': 'Microsoft To Do', 'error': str(e), 'action': 'Error', 'timestamp': timezone.now()}]

def process_ms_tasks(user, ms_task_list, ms_tasks, headers):
    updates = []
    new_tasks = []
    existing_tasks_to_update = []
    task_ids = set()
    
    logger.info(f"Processing {len(ms_tasks)} Microsoft tasks for list '{ms_task_list.list_name}'")
    
    for task_item in ms_tasks:
        ms_task_id = task_item["id"]
        task_ids.add(ms_task_id)
        
        title = task_item.get("title", "Untitled")
        
        # Microsoft uses 'status' field with 'completed' for completed tasks
        raw_status = task_item.get("status", "notStarted")
        is_completed = raw_status == 'completed'
        logger.debug(f"Task '{title}' status from Microsoft: {raw_status}, interpreted as completed={is_completed}")
        
        # Handle due date
        due_date_raw = task_item.get("dueDateTime")
        due_date = None
        if due_date_raw and "dateTime" in due_date_raw:
            try:
                naive_due_date = date_parser.parse(due_date_raw["dateTime"])
                due_date = timezone.make_aware(naive_due_date, timezone.get_default_timezone())
            except Exception as e:
                logger.warning(f"Failed to parse due date for task '{title}': {e}")
        
        # Get task notes/description
        task_notes = ""
        if task_item.get("body") and task_item["body"].get("content"):
            task_notes = task_item["body"]["content"]
        
        # Check if task already exists in database
        existing_task = Task.objects.filter(user=user, source_id=ms_task_id, source='microsoft').first()
        
        if existing_task:
            # Update existing task
            updated = False
            updated_fields = {}
            
            if existing_task.task_name != title:
                existing_task.task_name = title
                updated_fields['task_name'] = title
                updated = True
            
            if existing_task.task_description != task_notes:
                existing_task.task_description = task_notes
                updated_fields['task_description'] = task_notes
                updated = True
            
            # Explicitly log the completion status comparison
            logger.debug(f"Task '{title}': DB status={existing_task.task_completed}, MS status={is_completed}")
            if existing_task.task_completed != is_completed:
                existing_task.task_completed = is_completed
                updated_fields['task_completed'] = is_completed
                updated = True
                logger.info(f"Updating completion status for '{title}' to: {is_completed}")
            
            if existing_task.due_date != due_date:
                existing_task.due_date = due_date
                updated_fields['due_date'] = due_date.strftime('%Y-%m-%d') if due_date else None
                updated = True
            
            if updated:
                existing_task.last_update_date = timezone.now()
                existing_tasks_to_update.append(existing_task)
                logger.info(f"Updated Microsoft task '{title}' with changes: {', '.join(updated_fields.keys())}")
                updates.append({
                    'provider': 'Microsoft To Do',
                    'task_name': title,
                    'action': 'Updated',
                    'timestamp': timezone.now(),
                    'list_name': ms_task_list.list_name,
                    'updated_fields': updated_fields
                })
        else:
            # Create new task
            logger.info(f"Creating new Microsoft task '{title}' with completed={is_completed}")
            new_task = Task(
                user=user, 
                task_name=title, 
                task_completed=is_completed, 
                task_description=task_notes,
                due_date=due_date,
                list_name=ms_task_list, 
                source='microsoft', 
                source_id=ms_task_id,
                creation_date=timezone.now(), 
                last_update_date=timezone.now()
            )
            new_tasks.append(new_task)
            updates.append({
                'provider': 'Microsoft To Do',
                'task_name': title,
                'action': 'Created',
                'timestamp': timezone.now(),
                'list_name': ms_task_list.list_name
            })
    
    # Bulk create and update operations for efficiency
    if new_tasks:
        for task in new_tasks:
            try:
                task.save()
                logger.info(f"Successfully created Microsoft task: {task.task_name}")
            except Exception as e:
                logger.error(f"Failed to create Microsoft task '{task.task_name}': {e}")
    
    if existing_tasks_to_update:
        logger.info(f"Bulk updating {len(existing_tasks_to_update)} existing Microsoft tasks")
        Task.objects.bulk_update(
            existing_tasks_to_update, 
            ['task_name', 'task_description', 'task_completed', 'due_date', 'last_update_date']
        )
    
    return updates, task_ids

# Reusable sync function for both UI and background tasks
def sync_user_tasks(user, provider):
    try:
        logger.info(f"Starting sync for user: {user.username} with provider: {provider}")
        updates = []
        if provider == 'google':
            google_token = UserToken.objects.get(user=user, provider='google')
            creds = Credentials(
                token=google_token.access_token, refresh_token=google_token.refresh_token,
                token_uri='https://oauth2.googleapis.com/token', client_id=settings.SOCIAL_AUTH_GOOGLE_OAUTH2_KEY,
                client_secret=settings.SOCIAL_AUTH_GOOGLE_OAUTH2_SECRET,
                scopes=['https://www.googleapis.com/auth/tasks'],
            )
            if creds.expired and creds.refresh_token:
                creds.refresh(Request())
                google_token.access_token = creds.token
                google_token.save()
            updates = fetch_google_tasks_and_save(user, creds)
        elif provider == 'microsoft':
            ms_token = UserToken.objects.get(user=user, provider='microsoft')
            access_token = ms_token.access_token if not is_token_expired(ms_token) else refresh_microsoft_token(ms_token)
            if not access_token:
                raise Exception("Microsoft token refresh failed - please re-authenticate")
            updates = fetch_microsoft_tasks_and_save(user, access_token)
        
        TaskSyncStatus.objects.update_or_create(
            user=user, provider=provider, defaults={'is_complete': True}
        )

        # Send email with report only in production
        if updates:  # Remove development check for testing
            report_html = generate_sync_report(updates)
            subject = f"Task Sync Report for {provider.capitalize()} - {timezone.now().strftime('%Y-%m-%d %H:%M UTC')}"
            message = f"""
            <h2>Task Sync Report for {provider.capitalize()}</h2>
            <p>Below is the summary of updates applied during the latest sync operation:</p>
            {report_html}
            """
            send_email(
                subject=subject,
                message=message,  # Plain text fallback
                recipient_list=[user.email],
                html_message=message  # HTML version
            )
            logger.info(f"Sync report email sent to {user.username} for {provider}")
        elif not updates:
            logger.info(f"No updates to report for {user.username} and {provider}")
        else:
            logger.info(f"Skipping email in development for {user.username} and {provider}")

    except Exception as e:
        logger.error(f"Error syncing {provider} tasks for user {user.username}: {e}")
        raise

@csrf_exempt
def trigger_background_sync(request):
    """Endpoint triggered by Cloud Scheduler to enqueue sync tasks."""
    logger.info("Triggering background sync")
    if request.method != 'POST':
        logger.warning("Method not allowed: %s", request.method)
        return HttpResponse("Method not allowed", status=405)
    
    # Local testing override
    if settings.ENVIRONMENT == 'development':
        from django.test import Client
        client_http = Client()
        logger.info("Using local test client for Cloud Tasks")
    else:
        # Only initialize Cloud Tasks client in production
        client = tasks_v2.CloudTasksClient()
        project = os.environ.get('PROJECT_ID')  # e.g., 'my-project'
        location = 'us-west1'  # Adjust as needed
        queue = 'task-sync-queue'
        parent = client.queue_path(project, location, queue)

    users = UserToken.objects.values('user').distinct()
    for user_dict in users:
        user_id = user_dict['user']
        logger.info("Processing user ID: %s", user_id)
        for provider in ['google', 'microsoft']:
            if UserToken.objects.filter(user_id=user_id, provider=provider).exists():
                logger.info("User ID %s has provider %s", user_id, provider)
                if settings.ENVIRONMENT == 'development':
                    # Simulate Cloud Tasks locally
                    logger.info("Simulating Cloud Tasks locally for user ID %s and provider %s", user_id, provider)
                    client_http.post('/task_management/process_sync_task/',
                                     f'{{"user_id": {user_id}, "provider": "{provider}"}}',
                                     content_type='application/json')
                else:
                    # Enqueue task in production
                    task = {
                        'http_request': {
                            'http_method': tasks_v2.HttpMethod.POST,
                            'url': f'{settings.BASE_URL}/task_management/process_sync_task/',
                            'body': f'{{"user_id": {user_id}, "provider": "{provider}"}}'.encode(),
                            'headers': {'Content-Type': 'application/json'},
                        }
                    }
                    client.create_task(request={'parent': parent, 'task': task})
                    logger.info("Enqueued %s sync task for user %s", provider, user_id)
    
    logger.info("Sync tasks enqueued successfully")
    return HttpResponse("Sync tasks enqueued", status=200)

@csrf_exempt
def process_sync_task(request):
    """Endpoint to process an individual sync task."""
    logger.info("Processing sync task")
    if request.method != 'POST':
        logger.warning("Method not allowed: %s", request.method)
        return HttpResponse("Method not allowed", status=405)
    
    try:
        data = json.loads(request.body.decode('utf-8'))
        user_id = data.get('user_id')
        provider = data.get('provider')
        
        if not user_id or not provider:
            return JsonResponse({'error': 'user_id and provider are required'}, status=400)

        user = User.objects.get(id=user_id)
        sync_user_tasks(user, provider)
        
        # Update sync status
        TaskSyncStatus.objects.update_or_create(
            user=user, provider=provider, defaults={'is_complete': True}
        )
        logger.info(f"{provider.capitalize()} sync completed for user ID: {user_id}")
        return HttpResponse(f"{provider.capitalize()} sync completed for user {user_id}", status=200)
    except User.DoesNotExist:
        logger.error(f"User not found for ID: {user_id}")
        return HttpResponse(f"User not found: {user_id}", status=404)
    except Exception as e:
        logger.error(f"Error processing sync task for user ID: {user_id}, provider: {provider}, Error: {e}", exc_info=True)
        return HttpResponse(f"Error processing sync task: {e}", status=500)


def update_google_task(user, task):
    try:
        logger.info(f"Updating Google task: {task.task_name} (ID: {task.source_id})")
        service = get_google_service(user)
        tasklist_id = task.list_name.list_code
        
        # Get the current task from Google
        try:
            external_task = service.tasks().get(tasklist=tasklist_id, task=task.source_id).execute()
        except Exception as e:
            logger.error(f"Error retrieving Google task: {e}")
            return {"status": "error", "message": f"Error retrieving task: {str(e)}"}
        
        # Parse the updated date
        try:
            external_updated = datetime.fromisoformat(external_task['updated'].replace('Z', '+00:00'))
        except Exception as e:
            logger.warning(f"Error parsing updated date: {e}. Using current time instead.")
            external_updated = timezone.now()
        
        # Check if the external task is newer
        if external_updated > task.last_update_date:
            logger.warning(f"External task {task.task_name} is newer; skipping update")
            return None

        # Ensure due_date is timezone-aware
        due_date = None
        if task.due_date:
            due_date = task.due_date
            if timezone.is_naive(due_date):
                due_date = timezone.make_aware(due_date, timezone.get_default_timezone())
        
        # Check if task description is too large and truncate if necessary
        task_description = task.task_description or ''
        if len(task_description) > 10000:
            logger.warning(f"Task description too large ({len(task_description)} chars), truncating to 10000 chars")
            task_description = task_description[:10000] + "... (truncated)"
        
        # Prepare the task update
        google_task = {
            'id': task.source_id,
            'title': task.task_name,
            'notes': task_description,
            'due': due_date.isoformat() + 'Z' if due_date else None,
            'status': 'completed' if task.task_completed else 'needsAction',
        }
        
        # Update the task in Google
        logger.info(f"Sending update to Google for task: {task.task_name}")
        result = service.tasks().update(tasklist=tasklist_id, task=task.source_id, body=google_task).execute()
        
        # Set _skip_signal flag to prevent infinite recursion
        task._skip_signal = True
        task.save()
        logger.info(f"Successfully updated Google task: {task.task_name}")
        return result
    
    except Exception as e:
        logger.error(f"Error updating Google task: {task.task_name}, Error: {e}", exc_info=True)
        return {"status": "error", "message": str(e)}

@csrf_exempt
def process_google_task_update(request):
    """Endpoint to process Google task updates asynchronously."""
    try:
        if request.method != 'POST':
            return HttpResponse("Method not allowed", status=405)
        
        # Parse the request body
        data = json.loads(request.body.decode('utf-8'))
        user_id = data.get('user_id')
        task_id = data.get('task_id')
        
        # Validate the data
        if not user_id or not task_id:
            logger.error("Missing required fields in Google task update request")
            return JsonResponse({'error': 'Missing required fields'}, status=400)
        
        # Get the user and task
        try:
            user = User.objects.get(id=user_id)
            task = Task.objects.get(id=task_id, user=user)
            logger.info(f"Processing Google task update for task: {task.task_name} (ID: {task_id})")
        except User.DoesNotExist:
            logger.error(f"User not found for ID: {user_id}")
            return JsonResponse({'error': f'User not found for ID: {user_id}'}, status=404)
        except Task.DoesNotExist:
            logger.error(f"Task not found for ID: {task_id} and user ID: {user_id}")
            return JsonResponse({'error': f'Task not found for ID: {task_id}'}, status=404)
        
        # Update the Google task
        try:
            # Use the same module's function to avoid circular import
            result = update_google_task(user, task)
            if result:
                logger.info(f"Successfully processed Google task update for: {task.task_name}")
                return JsonResponse({'status': 'success', 'task_name': task.task_name})
            else:
                logger.warning(f"Google task update skipped for: {task.task_name} (likely due to newer external version)")
                return JsonResponse({'status': 'skipped', 'reason': 'External task is newer'})
        except Exception as e:
            logger.error(f"Error updating Google task {task.task_name}: {e}", exc_info=True)
            return JsonResponse({'error': f'Update error: {str(e)}'}, status=500)
    
    except json.JSONDecodeError:
        logger.error("Invalid JSON in request body")
        return JsonResponse({'error': 'Invalid JSON in request body'}, status=400)
    except Exception as e:
        logger.error(f"Unexpected error processing Google task update: {e}", exc_info=True)
        return JsonResponse({'error': str(e)}, status=500)

def update_ms_task(user, task):
    access_token = get_ms_access_token(user)
    headers = {'Authorization': f'Bearer {access_token}', 'Content-Type': 'application/json'}
    list_id = task.list_name.list_code
    
    logger.info(f"Updating Microsoft task: {task.task_name} (ID: {task.source_id})")
    
    try:
        response = requests.get(
            f'https://graph.microsoft.com/v1.0/me/todo/lists/{list_id}/tasks/{task.source_id}',
            headers=headers,
            timeout=10
        )
        response.raise_for_status()
        external_task = response.json()
        
        # Handle Microsoft's unusual datetime format more robustly
        try:
            # First try to directly parse the string
            last_modified = external_task.get('lastModifiedDateTime', '')
            
            # If the datetime string contains too many fractional digits, truncate it
            if '.' in last_modified:
                date_part, fraction = last_modified.split('.')
                if '+' in fraction:
                    fraction_part, timezone_part = fraction.split('+')
                    # Truncate to 6 digits if longer
                    if len(fraction_part) > 6:
                        fraction_part = fraction_part[:6]
                    last_modified = f"{date_part}.{fraction_part}+{timezone_part}"
                elif 'Z' in fraction:
                    fraction_part = fraction.split('Z')[0]
                    # Truncate to 6 digits if longer
                    if len(fraction_part) > 6:
                        fraction_part = fraction_part[:6]
                    last_modified = f"{date_part}.{fraction_part}Z"
                
            # Use dateutil parser which is more forgiving
            external_updated = date_parser.parse(last_modified)
        except Exception as e:
            logger.warning(f"Error parsing lastModifiedDateTime: {e}. Using current time instead.")
            external_updated = timezone.now()

        if external_updated > task.last_update_date:
            logger.warning(f"External task {task.task_name} is newer; skipping update")
            return None

        # Ensure dueDateTime is timezone-aware
        due_date_time = None
        if task.due_date:
            due_date_time = task.due_date
            if timezone.is_naive(due_date_time):
                due_date_time = timezone.make_aware(due_date_time, timezone.get_default_timezone())

        # Check if task description is too large and truncate if necessary
        task_description = task.task_description or ''
        if len(task_description) > 10000:
            logger.warning(f"Task description too large ({len(task_description)} chars), truncating to 10000 chars")
            task_description = task_description[:10000] + "... (truncated)"

        ms_task = {
            'title': task.task_name,
            'body': {'content': task_description, 'contentType': 'text'},
            'dueDateTime': {
                'dateTime': due_date_time.isoformat() if due_date_time else None,
                'timeZone': 'UTC'
            } if due_date_time else {},
            'status': 'completed' if task.task_completed else 'notStarted',
        }
        
        # Update the Microsoft task
        logger.info(f"Sending PATCH request to Microsoft for task: {task.task_name}")
        response = requests.patch(
            f'https://graph.microsoft.com/v1.0/me/todo/lists/{list_id}/tasks/{task.source_id}',
            headers=headers,
            json=ms_task,
            timeout=10  # Add a reasonable timeout
        )
        response.raise_for_status()
        
        # Set _skip_signal flag to prevent infinite recursion
        task._skip_signal = True
        task.save()
        logger.info(f"Successfully updated Microsoft task: {task.task_name}")
        return response.json()
    except requests.exceptions.Timeout:
        # Handle timeout separately from other errors
        logger.warning(f"Timeout while updating Microsoft task: {task.task_name}. Task will be marked for retry.")
        return {"status": "timeout", "message": "Request timed out, will retry"}
    except Exception as e:
        logger.error(f"Error updating Microsoft task: {task.task_name}, Error: {e}", exc_info=True)
        return {"status": "error", "message": str(e)}

@csrf_exempt
def process_ms_task_update(request):
    """Endpoint to process Microsoft task updates asynchronously."""
    try:
        if request.method != 'POST':
            return HttpResponse("Method not allowed", status=405)
        
        # Parse the request body
        data = json.loads(request.body.decode('utf-8'))
        user_id = data.get('user_id')
        task_id = data.get('task_id')
        
        # Validate the data
        if not user_id or not task_id:
            logger.error("Missing required fields in task update request")
            return JsonResponse({'error': 'Missing required fields'}, status=400)
        
        # Get the user and task
        try:
            user = User.objects.get(id=user_id)
            task = Task.objects.get(id=task_id, user=user)
            logger.info(f"Processing MS task update for task: {task.task_name} (ID: {task_id})")
        except User.DoesNotExist:
            logger.error(f"User not found for ID: {user_id}")
            return JsonResponse({'error': f'User not found for ID: {user_id}'}, status=404)
        except Task.DoesNotExist:
            logger.error(f"Task not found for ID: {task_id} and user ID: {user_id}")
            return JsonResponse({'error': f'Task not found for ID: {task_id}'}, status=404)
        
        # Update the Microsoft task
        try:
            # Use the same module's function to avoid circular import
            result = update_ms_task(user, task)
            if result:
                logger.info(f"Successfully processed task update for: {task.task_name}")
                return JsonResponse({'status': 'success', 'task_name': task.task_name})
            else:
                logger.warning(f"Task update skipped for: {task.task_name} (likely due to newer external version)")
                return JsonResponse({'status': 'skipped', 'reason': 'External task is newer'})
        except Exception as e:
            logger.error(f"Error updating task {task.task_name}: {e}", exc_info=True)
            return JsonResponse({'error': f'Update error: {str(e)}'}, status=500)
    
    except json.JSONDecodeError:
        logger.error("Invalid JSON in request body")
        return JsonResponse({'error': 'Invalid JSON in request body'}, status=400)
    except Exception as e:
        logger.error(f"Unexpected error processing Microsoft task update: {e}", exc_info=True)
        return JsonResponse({'error': str(e)}, status=500)
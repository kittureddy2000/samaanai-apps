from django.shortcuts import render, get_object_or_404, redirect
from .models import Task, TaskList, TaskHistory
from .forms import TaskForm, TaskListForm
from django.shortcuts import render
from django.db.models import Q,Count
from django.contrib.auth.decorators import login_required
from django.http import FileResponse, Http404
from dateutil.relativedelta import relativedelta
from datetime import timedelta
import os
import logging
from django.conf import settings
from django.utils import timezone
from django.contrib import messages
from django.http import JsonResponse, HttpResponse
import logging
from pathlib import Path
from datetime import datetime, time as dt_time
from django.shortcuts import redirect
from django.conf import settings
from core.models import UserToken
import json
from django.contrib.auth.models import User
from google.cloud import tasks_v2
from django.views.decorators.csrf import csrf_exempt
from .models import TaskSyncStatus  # You'll need to create this model
from .utils import handle_image_upload
from .sync_utils import sync_user_tasks


logger = logging.getLogger(__name__)

# Ensure predefined lists exist for the user
def ensure_predefined_lists(user):
    predefined_lists = [
        {"name": "Samaan List", "listcode": "SAMAAN_TASKS"},
        {"name": "Past Due", "listcode": "PAST_DUE"},
        {"name": "Important", "listcode": "IMPORTANT"},
        {"name": "All Tasks", "listcode": "ALL_TASKS"},

    ]
    logger.info("Inside ensure_predefined_lists")
    logger.info(predefined_lists)

    # Get existing predefined lists for the user
    existing_names = TaskList.objects.filter(
        user=user,
        list_name__in=[predefined["name"] for predefined in predefined_lists],
        list_type='special'
    ).values_list('list_name', flat=True)

    logger.info([field.name for field in TaskList._meta.get_fields()])

    # Create any missing predefined lists
    for predefined in predefined_lists:
        if predefined["name"] not in existing_names:
            logger.info("Creating Predefined List : " + predefined["name"])
            TaskList.objects.create(
                user=user,
                list_name=predefined["name"],
                list_code=predefined["listcode"],
                list_type='special'  # Use list_type instead of special_list
            )


# Get all Taks triggered at the start of page load
@login_required
def get_all_tasks(request):
    logger.info("Getting All Tasks called as main function")

    #tasks = Task.objects.filter(user=request.user, task_completed=False).order_by('due_date')
    tasks = Task.objects.filter(user=request.user, task_completed=False).order_by('due_date').select_related('list_name')

    tasks_data = list(tasks.values(
        'id', 'task_name', 'list_name', 'due_date', 'task_description', 'due_date', 'reminder_time', 'recurrence',
        'task_completed','important', 'assigned_to', 'creation_date', 'last_update_date'))

    return JsonResponse({'tasks': tasks_data})

# Get All tasks for the given list
@login_required
def get_tasks_by_list(request, list_id):
    logger.info("Function: Get Tasks with list id : " + str(list_id))

    sort_by = request.GET.get('sort', 'due_date')
    order = request.GET.get('order', 'asc')
    if order == 'desc':
        sort_by = '-' + sort_by

    logger.info("Sort By : " + sort_by)
    if sort_by == 'important':
        sort_by = '-important'
    elif sort_by not in ['due_date']:
        sort_by = 'due_date'

    tasklist = TaskList.objects.get(id=list_id, user=request.user)
    logger.info("List Name : " + tasklist.list_name)

    if tasklist.list_type == 'special':
        if tasklist.list_code == "IMPORTANT":
            tasks = Task.objects.filter(user=request.user, important=True, task_completed=False).order_by(sort_by)
        elif tasklist.list_code == "PAST_DUE":
            tasks = Task.objects.filter(user=request.user, due_date__lt=timezone.now(), task_completed=False).order_by(sort_by)
        elif tasklist.list_code == "ALL_TASKS":
            tasks = Task.objects.filter(user=request.user, task_completed=False).order_by(sort_by)
        elif tasklist.list_code == "SAMAAN_TASKS":
            tasks = Task.objects.filter(user=request.user, list_name=tasklist, task_completed=False).order_by(sort_by)
    else:
        tasks = Task.objects.filter(user=request.user, list_name=tasklist, task_completed=False).order_by(sort_by)

    tasks_data = list(tasks.values(
        'id', 'task_name', 'list_name', 'due_date', 'task_description', 'due_date', 'reminder_time', 'recurrence',
        'task_completed', 'important', 'assigned_to', 'creation_date', 'last_update_date'))
    return JsonResponse({'tasks': tasks_data})

# Live Search Tasks
def search_tasks(request):
    # Get the query and filter parameters from GET
    query = request.GET.get('q', '')
    filter_param = request.GET.get('filter')

    # Choose the base queryset based on the filter.
    # By default, we show only active (not completed) tasks.
    if filter_param == 'completed':
        tasks = Task.objects.filter(user=request.user, task_completed=True)
    elif filter_param == 'all':
        tasks = Task.objects.filter(user=request.user)
    elif filter_param == 'past_due':
        # Show past-due tasks that are not completed.
        tasks = Task.objects.filter(user=request.user, task_completed=False, due_date__lt=timezone.now())
    else:
        # Default: active tasks only (not completed)
        tasks = Task.objects.filter(user=request.user, task_completed=False)

    # If a search query is provided, filter by task name or description.
    if query:
        tasks = tasks.filter(Q(task_name__icontains=query) | Q(task_description__icontains=query))

    # Sorting
    sort_by = request.GET.get('sort_by')
    if sort_by == 'important':
        tasks = tasks.order_by('-important')
    elif sort_by in ['due_date']:
        tasks = tasks.order_by(sort_by)

    try:
        tasks_data = list(
            tasks.values(
                'id',
                'task_name',
                'list_name',
                'due_date',
                'task_description',
                'reminder_time',
                'recurrence',
                'task_completed',
                'important',
                'assigned_to',
                'creation_date',
                'last_update_date'
            )
        )
        return JsonResponse({'tasks': tasks_data})
    except Exception as e:
        logger.error(f"Error in search_tasks: {e}")
        return JsonResponse({'error': 'An error occurred'}, status=500)

# Get All Task Lists that renders the sidebar:
@login_required
def get_lists(request):
    # Ensure predefined lists are created
    ensure_predefined_lists(request.user)
    
    # Get all task lists, annotated with counts for regular lists
    task_lists = TaskList.objects.filter(user=request.user).annotate(
        task_count=Count('task', filter=Q(task__task_completed=False))
    ).order_by('-list_type', 'list_name')  # Sort by list_type first, then name

    # Split into special, semi-special, and normal lists
    special_lists = task_lists.filter(list_type='special')
    semi_special_lists = task_lists.filter(list_type__in=['google_primary', 'microsoft_primary']).order_by('list_name')
    normal_lists = task_lists.filter(list_type='normal').order_by('list_name')  # Sort alphabetically by list_name

    # Calculate counts for special lists dynamically
    special_counts = {
        "IMPORTANT": Task.objects.filter(user=request.user, important=True, task_completed=False).count(),
        "PAST_DUE": Task.objects.filter(user=request.user, due_date__lt=timezone.now(), task_completed=False).count(),
        "ALL_TASKS": Task.objects.filter(user=request.user, task_completed=False).count(),
    }

    # Calculate counts for semi-special lists
    semi_special_counts = {
        "G My Tasks": Task.objects.filter(user=request.user, source="google", list_name__list_name="G My Tasks", task_completed=False).count(),
        "MS Tasks": Task.objects.filter(user=request.user, source="microsoft", list_name__list_name="MS Tasks", task_completed=False).count(),
    }

    # Attach counts to special lists
    for task_list in special_lists:
        if task_list.list_code in special_counts:
            task_list.task_count = special_counts[task_list.list_code]

    # Attach counts to semi-special lists (manually, since they're normal lists but treated specially)
    for task_list in semi_special_lists:
        if task_list.list_name in semi_special_counts:
            task_list.task_count = semi_special_counts[task_list.list_name]

    # --- Debugging Log --- 
    logger.info(f"[get_lists] Special: {[l.list_name for l in special_lists]}")
    logger.info(f"[get_lists] Semi-Special: {[l.list_name for l in semi_special_lists]}")
    logger.info(f"[get_lists] Normal: {[l.list_name for l in normal_lists]} (Count: {len(normal_lists)})")
    # --- End Debugging Log --- 
    
    context = {
        'special_lists': special_lists,
        'semi_special_lists': semi_special_lists,
        'normal_lists': normal_lists,
    }
    return render(request, 'task_management/task_dashboard.html', context)

# Create a new task list
def create_task_list(request):
    if request.method == 'POST':
        logger.info(f"create_task_list: Received POST request from user {request.user.username}")
        form = TaskListForm(request.POST)
        if form.is_valid():
            logger.info(f"create_task_list: Form is valid - list_name: {form.cleaned_data.get('list_name')}")
            task_list = form.save(commit=False)
            task_list.user = request.user
            task_list.list_type = form.cleaned_data.get('list_type', 'normal') 
            task_list.list_code = form.cleaned_data.get('list_code', f"custom_{task_list.list_name.lower().replace(' ', '_')}") 
            task_list.save()
            
            logger.info(f"create_task_list: List saved successfully - ID: {task_list.id}, Name: {task_list.list_name}")
            
            # Create a more comprehensive response
            response_data = {
                'success': True,
                'list': {
                    'id': task_list.id,
                    'name': task_list.list_name,
                    'list_type': task_list.list_type,
                    'list_code': task_list.list_code,
                    'icon': 'far fa-list',  # Using outline icon for consistency
                    'created_at': timezone.now().isoformat()
                }
            }
            logger.info(f"create_task_list: Returning success response: {response_data}")
            return JsonResponse(response_data)
        else:
            # Log the specific validation errors
            logger.error(f"create_task_list: Form validation failed: {form.errors.as_json()}") 
            # Return form errors as JSON for AJAX
            return JsonResponse({'success': False, 'errors': form.errors}, status=400)
    else:
        # GET request: Render only the form template for loading into modal
        logger.info(f"create_task_list: Received GET request from user {request.user.username}")
        form = TaskListForm()
        # Exclude fields we don't want user to set directly in the simple modal
        form.fields.pop('list_code', None)
        form.fields.pop('list_type', None)
        return render(request, 'task_management/create_list_form.html', {'form': form})

def complete_task(request, task_id):
    """Mark a task as complete or incomplete"""
    logger.info(f"complete_task view called with task_id: {task_id}, method: {request.method}")
    
    try:
        task = Task.objects.get(id=task_id)
        logger.info(f"Found task: ID={task.id}, Name='{task.task_name}', Current completed status={task.task_completed}")
        
        # Toggle the completion status
        task.task_completed = not task.task_completed
        task.save()
        
        logger.info(f"Toggled task completion. New status={task.task_completed}")
        
        # Return the updated task information
        response_data = {
            'success': True,
            'id': task.id,
            'task_name': task.task_name,
            'task_completed': task.task_completed
        }
        logger.info(f"Returning success response: {response_data}")
        return JsonResponse(response_data)
    except Task.DoesNotExist:
        logger.error(f"Task with ID {task_id} not found")
        return JsonResponse({'success': False, 'error': 'Task not found'}, status=404)
    except Exception as e:
        logger.error(f"Error in complete_task: {str(e)}", exc_info=True)
        return JsonResponse({'success': False, 'error': str(e)}, status=500)

def mark_favorite(request):
    task_id = request.POST.get('id')
    task = Task.objects.get(id=task_id, user=request.user)
    task_name = task.task_name
    print("Marking Task as Favorite : " + task_name)

    if task.important:
        task.important = False
    else:
        task.important = True
    task.save()

    print("Task Saved in Mark_Favorite : ")
    if task.important:
        print("Task is important True ")
    else:
        print("Task important : False ")

    return JsonResponse({'Important': task.important, 'task_name': task_name, 'task_id': task_id})

def get_task_details(request, task_id):
    print("Function: Get Tasks Details " + str(task_id))

    # Use get_object_or_404 to get the task or return a 404 response if not found
    task = get_object_or_404(Task, id=task_id, user=request.user)
    print("Task Name : " + task.task_name)
    print("Task Description : " + task.task_description)
    print("Task Due Date : " + task.due_date.strftime("%m/%d/%Y"))  # Corrected date format

    # Construct the task data dictionary manually
    task_data = {
        'id': task.id,
        'task_name': task.task_name,
        # 'list_name': task.list_name.name if task.list_name else None,  # Assuming list_name is a ForeignKey
        'due_date': task.due_date.strftime("%m/%d/%Y"),
        'task_description': task.task_description,
        'reminder_time': task.reminder_time.strftime("%m/%d/%Y, %H:%M") if task.reminder_time else None,
        'recurrence': task.recurrence,
        'task_completed': task.task_completed,
        'important': task.important,
        'assigned_to': task.assigned_to,
        'creation_date': task.creation_date.strftime("%m/%d/%Y, %H:%M"),
        'last_update_date': task.last_update_date.strftime("%m/%d/%Y, %H:%M"),
    }

    return JsonResponse(task_data)


@login_required
def add_task(request, list_id):
    print("Add Task Function request method: " + request.method)

    # Fetch the task list or use default SAMAAN_TASKS if list_id is None
    if list_id:
        task_list = get_object_or_404(TaskList, id=list_id, user=request.user)
    else:
        # Default to SAMAAN_TASKS list if no list is specified
        task_list = TaskList.objects.get(user=request.user, list_code="SAMAAN_TASKS", list_type='special')
    image_data = []

    if request.method == "POST":
        add_task_form = TaskForm(request.POST, request.FILES)
        print("Inside POST Request for Add Task")

        if add_task_form.is_valid():
            print("Add Task form is Valid")
            try:
                task = Task(
                    user=request.user,
                    task_name=add_task_form.cleaned_data['task_name'],
                    task_description=add_task_form.cleaned_data['task_description'],
                    due_date=add_task_form.cleaned_data['due_date'],
                    list_name=task_list,
                    reminder_time=add_task_form.cleaned_data['reminder_time'],
                    task_completed=False,
                    assigned_to=request.user.username,
                    creation_date=timezone.now(),
                    last_update_date=timezone.now(),
                )
                task.save()
                print("Task Saved")
                # Image Handling
                images = request.FILES.getlist('images')
                handle_image_upload(task, images)


                logger.info("Returning success response for Create task id : %s", task.task_name)
                return JsonResponse({
                    'id': task.id,
                    'task_name': task.task_name,
                    'task_description': task.task_description,
                    'due_date': task.due_date.strftime('%Y-%m-%d') if task.due_date else None,
                    'important': task.important,
                    'task_completed': task.task_completed,
                    'images': image_data
                })


            except Exception as e:
                print(f"Error occurred: {e}")
                return HttpResponse(f"Error occurred: {e}", status=500)
        else:
            print("Add Task form is not valid")
            print(add_task_form.errors)  # Debugging purpose
            return HttpResponse("Invalid form submission.", status=400)

    # Handle GET request or other methods
    else:
        print("This is a GET Request for Add Task")
        form = TaskForm(initial={'list_name': list_id})
        return render(request, "task_management/add_task.html", {"add_task_form": form})

    # Fallback response to ensure all code paths return a response
    return HttpResponse("Unexpected error occurred.", status=500)

def edit_task(request, task_id):
    logger.info("Edit task Function Task id : %s", task_id)

    task = get_object_or_404(Task, id=task_id, user=request.user)
    images = task.images.all()
    image_data = []

    if request.method == 'POST':
        try:
            form = TaskForm(request.POST, request.FILES, instance=task)
            logger.info("Received POST request, Task id: %s", task_id)

            if form.is_valid():
                logger.info("Task form is valid, Task id: %s", task_id)
                task = form.save(commit=False)

                # Make due_date and reminder_time timezone-aware
                if form.cleaned_data.get('due_date'):
                    due_date = form.cleaned_data['due_date']
                    task.due_date = timezone.make_aware(datetime.combine(due_date, dt_time(6, 0)), timezone.get_default_timezone())

                if form.cleaned_data.get('reminder_time'):
                    reminder_time = form.cleaned_data['reminder_time']
                    task.reminder_time = timezone.make_aware(datetime.combine(reminder_time, dt_time(6, 0)), timezone.get_default_timezone())

                # Set last_update_date to current time
                task.last_update_date = timezone.now()
                
                # Save task with update_fields to signal this is a user-initiated update
                # This helps our signal handler distinguish between automatic and user updates
                update_fields = ['task_name', 'task_description', 'due_date', 'reminder_time', 'last_update_date']
                if 'task_completed' in form.cleaned_data:
                    task.task_completed = form.cleaned_data['task_completed']
                    update_fields.append('task_completed')
                if 'important' in form.cleaned_data:
                    task.important = form.cleaned_data['important']
                    update_fields.append('important')
                
                task.save(update_fields=update_fields)

                logger.info("Task saved successfully, Task id: %s", task_id)

                # Image Handling
                uploaded_images = request.FILES.getlist('images')
                handle_image_upload(task, uploaded_images)

                logger.info("Returning success response for edit task id : %s", task_id)
                return JsonResponse({
                    'id': task.id,
                    'task_name': task.task_name,
                    'task_description': task.task_description,
                    'due_date': task.due_date.strftime('%Y-%m-%d') if task.due_date else None,
                    'important': task.important,
                    'task_completed': task.task_completed,
                    'images': image_data
                })
            else:
                logger.warning("Task form is invalid, Task id: %s", task_id)
                for field, errors in form.errors.items():
                    logger.warning("Form Field: %s,  Errors: %s", field, errors)
                return JsonResponse({'errors': form.errors}, status=400)

        except Exception as e:
            logger.error("An unexpected error occurred while processing task id : %s, Error: %s", task_id, e, exc_info=True)
            return HttpResponse(f"An error occurred: {e}", status=500)

    elif request.method == 'GET':
        try:
            form = TaskForm(instance=task)
            logger.info("Edit Task in Get method id : %s ", task_id)
            image_data = []

            for image in images:
                logger.info("Image URL: %s ; Image ID: %s", image.image_url, image.id)
                image_data.append({'url': image.image_url, 'image_name': image.image_name, 'id': image.id})

            return render(request, 'task_management/edit_task.html', {'edit_task_form': form, 'images': images, 'task_id': task_id})
        except Exception as e:
            logger.error("An unexpected error occurred in GET method for task id %s : Error %s", task_id, e,
                         exc_info=True)
            return HttpResponse(f"An error occurred: {e}", status=500)

def edit_task_in_panel(request, task_id):
    task = get_object_or_404(Task, id=task_id, user=request.user)
    form = TaskForm(instance=task)
    print("Add Task Method :  " + request.method + " ; Task id : " + str(task_id))
    # Render your form template with the form context, and return as HTML
    return render(request, 'task_management/edit_task.html', {'edit_task_form': form})

def completed_tasks(request):
    print("In Completed Tasks : ")
    # Get all completed tasks and render them in the "completed_tasks.html"
    completed_tasks = Task.objects.filter(user=request.user, task_completed=True)
    return render(request, 'task_management/completed_tasks.html', {'completed_tasks': completed_tasks})

def delete_tasks(request):
    tasks = Task.objects.filter(user=request.user)

    if request.method == 'POST':
        print("In Delete Tasks Function")
        task_ids = request.POST.getlist('selected_tasks')
        Task.objects.filter(user=request.user, id__in=task_ids).delete()
        messages.success(request, 'Selected tasks have been deleted.')

        return redirect('task_management:delete_tasks')

    return render(request, 'task_management/delete_tasks.html', {'tasks': tasks})

def undelete_task(request, task_id):
    if request.method == 'POST':
        task = get_object_or_404(Task, id=task_id, user=request.user, task_completed=True)
        task.task_completed = False
        task.save()
        return JsonResponse({'status': 'success', 'message': 'Task reactivated successfully.'})
    else:
        return JsonResponse({'status': 'error', 'message': 'Invalid request'}, status=400)

def serve_attachment(request, path):
    logger.info("Request to serve attachment at path : %s", path)
    task_management_attachments_dir = Path(__file__).resolve().parent / 'attachments'
    file_path = task_management_attachments_dir / path
    logger.info("File Path: %s", file_path)
    if not file_path.exists():
        logger.warning("File does not exist at: %s", file_path)
        raise Http404("File not found.")
    try:
        response = FileResponse(open(file_path, 'rb'))
        return response
    except Exception as e:
        logger.error("Error loading file : %s ; Error : %s", file_path, e, exc_info=True)
        raise Http404(f"Error loading file")

@login_required
def sync_google_tasks(request):
    sync_user_tasks(request.user, 'google')
    return JsonResponse({'message': 'Google Tasks synced successfully!'})

@login_required
def sync_microsoft_tasks(request):
    sync_user_tasks(request.user, 'microsoft')
    return JsonResponse({'message': 'Microsoft Tasks synced successfully!'})

# Background task endpoint triggered by Cloud Scheduler
# This api is called from Google Cloud Tasks



@csrf_exempt
@login_required
def trigger_user_sync(request):
    """Endpoint triggered from UI to enqueue sync tasks for the current user."""
    logger.info(f"Triggering user sync for user: {request.user.username}")
    if request.method != 'POST':
        return HttpResponse("Method not allowed", status=405)

    try:
        for provider in ['google', 'microsoft']:
            if UserToken.objects.filter(user=request.user, provider=provider).exists():
                logger.info(f"Enqueuing sync for user {request.user.username} and provider {provider}")
                task_body = json.dumps({"user_id": request.user.id, "provider": provider}).encode()
                if settings.ENVIRONMENT == 'development':
                    from django.test import Client
                    client_http = Client()
                    client_http.post('/task_management/process_sync_task/',
                                     task_body,
                                     content_type='application/json')
                else:
                    client = tasks_v2.CloudTasksClient()
                    project = os.environ.get('PROJECT_ID', 'using-ai-405105')
                    location = 'us-west1'
                    queue = 'task-sync-queue'
                    parent = client.queue_path(project, location, queue)
                    task = {
                        'http_request': {
                            'http_method': tasks_v2.HttpMethod.POST,
                            'url': f'{settings.BASE_URL}/task_management/process_sync_task/',
                            'body': task_body,
                            'headers': {'Content-Type': 'application/json'},
                        }
                    }
                    client.create_task(request={'parent': parent, 'task': task})
                    logger.info(f"Enqueued {provider} sync task for user {request.user.username}")

        return JsonResponse({'message': 'Sync tasks enqueued for user'})
    except Exception as e:
        logger.error(f"Error triggering user sync for {request.user.username}: {e}", exc_info=True)
        return JsonResponse({'error': f'Error enqueuing sync tasks: {e}'}, status=500)
# View to check sync status
@csrf_exempt  # Optional, depending on your needs; remove if UI uses CSRF
def check_sync_status(request):
    """
    Check the status of a sync operation for a user and provider.
    Returns JSON: {'completed': bool}.
    """
    logger.info("Checking sync status for request")
    if request.method != 'GET':
        return HttpResponse("Method not allowed", status=405)

    provider = request.GET.get('provider')
    user_id = request.GET.get('user_id')

    if not provider or not user_id:
        return JsonResponse({'error': 'Provider and user_id are required'}, status=400)

    try:
        user = User.objects.get(id=user_id)
    except User.DoesNotExist:
        return JsonResponse({'error': 'User not found'}, status=404)

    # Check if sync is complete for this user/provider
    sync_status, created = TaskSyncStatus.objects.get_or_create(
        user=user, provider=provider, defaults={'is_complete': False}
    )

    # Simulate checking if sync is complete (you can modify this logic)
    # In practice, update TaskSyncStatus in sync_user_tasks when sync completes
    is_complete = sync_status.is_complete

    return JsonResponse({'completed': is_complete})

@login_required
def get_task_counts(request):
    # Counts for regular (normal) lists
    task_lists = TaskList.objects.filter(user=request.user, list_type='normal').annotate(
        task_count=Count('task', filter=Q(task__task_completed=False))
    ).values('id', 'task_count')

    # Convert to a dictionary for easier lookup
    counts = {str(tl['id']): tl['task_count'] for tl in task_lists}

    # Special list counts (dynamic special lists: Important, Past Due, All Tasks)
    special_counts = {
        "IMPORTANT": Task.objects.filter(user=request.user, important=True, task_completed=False).count(),
        "PAST_DUE": Task.objects.filter(user=request.user, due_date__lt=timezone.now(), task_completed=False).count(),
        "ALL_TASKS": Task.objects.filter(user=request.user, task_completed=False).count(),
    }

    # Semi-special list counts (G My Tasks and MS Tasks)
    semi_special_counts = {
        "G My Tasks": Task.objects.filter(user=request.user, source="google", list_name__list_name="G My Tasks", task_completed=False).count(),
        "MS Tasks": Task.objects.filter(user=request.user, source="microsoft", list_name__list_name="MS Tasks", task_completed=False).count(),
    }

    # Add special counts to the response using list IDs
    for task_list in TaskList.objects.filter(user=request.user, list_type='special'):
        if task_list.list_code in special_counts:
            counts[str(task_list.id)] = special_counts[task_list.list_code]

    # Add semi-special counts to the response using list IDs
    for task_list in TaskList.objects.filter(user=request.user, list_type__in=['google_primary', 'microsoft_primary']):
        if task_list.list_name == "G My Tasks":
            counts[str(task_list.id)] = semi_special_counts["G My Tasks"]
        elif task_list.list_name == "MS Tasks":
            counts[str(task_list.id)] = semi_special_counts["MS Tasks"]

    return JsonResponse({'counts': counts})
    


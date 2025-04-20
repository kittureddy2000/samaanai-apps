from django.shortcuts import render, get_object_or_404, redirect
from .models import Task, TaskList, TaskHistory
from .forms import TaskForm, TaskListForm, TaskEditForm
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
        {"name": "Samaan Tasks", "listcode": "SAMAAN_TASKS"},
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
        tasks = Task.objects.filter(user=request.user, task_completed=False)
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
        "SAMAAN_TASKS": Task.objects.filter(user=request.user, list_name__list_name="Samaan Tasks"  , task_completed=False).count(),
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
        task = Task.objects.get(id=task_id, user=request.user)
        logger.info(f"Found task: {task.task_name} (ID: {task.id}, Source: {task.source}, List: {task.list_name.list_name if task.list_name else 'None'})")
        
        # Create history record of this completion
        TaskHistory.objects.create(
            user=request.user,
            task_name=task.task_name,
            list_name=task.list_name,
            task_description=task.task_description,
            due_date=task.due_date,
            recurrence=task.recurrence,
            important=task.important,
            assigned_to=task.assigned_to,
            task_completed=True,  # Always true for history of completed instance
            source_id=f"{task.id}-{timezone.now().strftime('%Y%m%d%H%M%S%f')}",  # Unique source_id
            source='internal'  # Internal source for tracking
        )
        logger.info(f"Created task history record for task completion: {task.task_name}")
        
        # Handle based on recurrence pattern
        if task.recurrence != Task.NO_RECURRENCE and task.recurrence and task.due_date:
            # For recurring tasks, we'll update the due date instead of marking complete
            new_due_date = None
            
            if task.recurrence == Task.DAILY:
                new_due_date = task.due_date + timedelta(days=1)
            elif task.recurrence == Task.WEEKLY:
                new_due_date = task.due_date + timedelta(weeks=1)
            elif task.recurrence == Task.MONTHLY:
                new_due_date = task.due_date + relativedelta(months=1)
            elif task.recurrence == Task.YEARLY:
                new_due_date = task.due_date + relativedelta(years=1)
            
            task.due_date = new_due_date
            # Reset completion status as this is now the next instance
            task.task_completed = False
            task.last_update_date = timezone.now()  # Ensure last_update_date is set
            
            # Save with specific update_fields to trigger signal properly
            logger.info(f"Saving recurring task with new due date: {new_due_date}")
            task.save(update_fields=['due_date', 'task_completed', 'last_update_date'])
            
            logger.info(f"Updated recurring task: {task.task_name} with new due date: {new_due_date}")
            
            return JsonResponse({
                'status': 'success',
                'task_id': task.id,
                'task_name': task.task_name,
                'recurring': True,
                'next_due_date': task.due_date.isoformat() if task.due_date else None,
                'completed': False  # The task itself isn't complete, just this instance
            })
        else:
            # For non-recurring tasks, toggle completion as before
            previous_state = task.task_completed
            task.task_completed = not task.task_completed
            task.last_update_date = timezone.now()  # Ensure last_update_date is set
            
            # Log the task's source and external sync eligibility
            if task.source in ['microsoft', 'google']:
                logger.info(f"Task {task.task_name} has source '{task.source}' - will be synced to external service")
            else:
                logger.info(f"Task {task.task_name} has no external source (source: '{task.source}') - no external sync needed")
            
            # Save with specific update_fields to trigger signal properly
            logger.info(f"Saving task with completion toggled from {previous_state} to {task.task_completed}")
            task.save(update_fields=['task_completed', 'last_update_date'])
            
            logger.info(f"Toggled completion status for task: {task.task_name} to {task.task_completed}")
            
            return JsonResponse({
                'status': 'success',
                'task_id': task.id, 
                'task_name': task.task_name,
                'completed': task.task_completed,
                'recurring': False
            })

    except Task.DoesNotExist:
        logger.error(f"Task with ID {task_id} not found")
        return JsonResponse({'status': 'error', 'message': 'Task not found'}, status=404)
    except Exception as e:
        logger.error(f"Error in complete_task: {str(e)}", exc_info=True)
        return JsonResponse({'status': 'error', 'message': str(e)}, status=500)

def mark_favorite(request):
    task_id = request.POST.get('id')
    try:
        task = Task.objects.get(id=task_id, user=request.user)
        task_name = task.task_name
        logger.info(f"Toggling favorite status for task: {task_name} (ID: {task_id})")

        task.important = not task.important # Toggle the important status
        task.last_update_date = timezone.now() # Update timestamp
        
        # Save the change, specifying update_fields for signal handler
        task.save(update_fields=['important', 'last_update_date'])

        logger.info(f"Task {task_name} important status set to: {task.important}")

        # Return the full task data needed by updateTaskCardUI
        return JsonResponse({
            'status': 'success', # Added for consistency
            'task_id': task.id, 
            'id': task.id, # Include 'id' as well for safety
            'task_name': task.task_name,
            'completed': task.task_completed,
            'important': task.important,
            'due_date': task.due_date.isoformat() if task.due_date else None,
            # Add recurring fields if your UI needs them after marking favorite
            # 'recurring': task.recurrence != Task.NO_RECURRENCE and task.recurrence,
            # 'next_due_date': None # Usually not relevant here, but include if needed
        })
        
    except Task.DoesNotExist:
        logger.error(f"Task with ID {task_id} not found for mark_favorite")
        return JsonResponse({'status': 'error', 'message': 'Task not found'}, status=404)
    except Exception as e:
        logger.error(f"Error in mark_favorite: {str(e)}", exc_info=True)
        return JsonResponse({'status': 'error', 'message': str(e)}, status=500)

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
def add_task(request):
    # Removed list_id parameter as it's not needed in the URL anymore
    logger.debug(f"add_task view called. Method: {request.method}")
    if request.method == 'POST':
        logger.info(f"Received POST request for add_task from user {request.user.username}")
        # Log POST data carefully - avoid logging sensitive info if applicable
        # logger.debug(f"POST data: {request.POST}") 
        # Log file data separately if needed
        # logger.debug(f"FILES data: {request.FILES}") 
        
        # Get or create the Samaan Tasks list
        try:
            samaan_list, created = TaskList.objects.get_or_create(
                user=request.user, # Ensure list is associated with the user
                list_name="Samaan Tasks",
                defaults={'list_type': 'normal'} # Provide default type if needed
            )
            logger.info(f"Using TaskList: {samaan_list.list_name} (ID: {samaan_list.id}), Created: {created}")
        except Exception as e:
            logger.error(f"Error getting/creating Samaan Tasks list for user {request.user.username}: {e}", exc_info=True)
            return JsonResponse({'success': False, 'error': 'Could not retrieve task list.'}, status=500)
            
        form = TaskForm(request.POST, request.FILES) # Include request.FILES for image uploads
        
        if form.is_valid():
            logger.info("Add task form is valid.")
            try:
                task = form.save(commit=False)
                task.user = request.user  # Explicitly set the user
                task.list_name = samaan_list
                
                # Default reminder time to due date if due date exists
                if task.due_date:
                    task.reminder_time = task.due_date
                    logger.debug(f"Setting reminder_time to due_date: {task.reminder_time}")
                else:
                    # If due_date is null, set it to tomorrow
                    task.due_date = timezone.now() + timezone.timedelta(days=1)
                    task.reminder_time = task.due_date
                    logger.debug(f"Due date was null, setting to tomorrow: {task.due_date}")
                    logger.debug(f"Setting reminder_time to new due_date: {task.reminder_time}")
                
                logger.info(f"Attempting to save task '{task.task_name}' for user {request.user.username}")
                task.save()
                logger.info(f"Task saved successfully with ID: {task.id}")

                # Image Handling after task is saved
                uploaded_images = request.FILES.getlist('images')
                if uploaded_images:
                    logger.info(f"Handling {len(uploaded_images)} uploaded images for task {task.id}")
                    handle_image_upload(task, uploaded_images) # Assuming handle_image_upload exists and works
                else:
                    logger.info(f"No images uploaded for task {task.id}")
                
                response_data = {
                    'success': True,
                    'task': {
                        'id': task.id,
                        'task_name': task.task_name,
                        'task_description': task.task_description,
                        'completed': task.task_completed,
                        'important': task.important,
                        'due_date': task.due_date.isoformat() if task.due_date else None,
                        'reminder_time': task.reminder_time.isoformat() if task.reminder_time else None,
                        'recurrence': task.recurrence,
                        'list_name': {'id': task.list_name.id, 'name': task.list_name.list_name} # Include list info
                        # Add image info if needed
                    }
                }
                logger.info(f"Returning success JSON response for task {task.id}")
                # logger.debug(f"Success JSON data: {response_data}")
                return JsonResponse(response_data)
            except Exception as e:
                logger.error(f"Error saving task or handling images for user {request.user.username}: {e}", exc_info=True)
                return JsonResponse({'success': False, 'error': 'Error saving task data.'}, status=500)
        else:
            logger.warning(f"Add task form is invalid for user {request.user.username}. Errors: {form.errors.as_json()}")
            # Return validation errors in the JSON response
            return JsonResponse({'success': False, 'errors': form.errors}, status=400)
    
    # Handle GET request (loading the form initially)
    elif request.method == 'GET':
        logger.debug("Received GET request for add_task form.")
        form = TaskForm()
        return render(request, 'task_management/add_task.html', {'add_task_form': form})
    
    else:
        logger.warning(f"Received unsupported method {request.method} for add_task.")
        return JsonResponse({'error': 'Method not allowed'}, status=405)

def edit_task(request, task_id):
    logger.info("Edit task Function Task id : %s", task_id)

    task = get_object_or_404(Task, id=task_id, user=request.user)
    images = task.images.all()
    image_data = []

    if request.method == 'POST':
        logger.info(f"Received POST request for edit_task, Task id: {task_id}")
        # logger.debug(f"POST data: {request.POST}") 

        try:
            # Keep form instance for reference if needed, but process POST directly
            form = TaskEditForm(request.POST, request.FILES, instance=task) 
            
            update_fields = ['last_update_date']
            task.last_update_date = timezone.now()

            # --- Process fields directly from request.POST ---

            # Text fields
            if 'task_name' in request.POST:
                task.task_name = request.POST['task_name'].strip()
                update_fields.append('task_name')
            if 'task_description' in request.POST:
                task.task_description = request.POST.get('task_description', '').strip()
                update_fields.append('task_description')

            # Date fields 
            if 'due_date' in request.POST:
                if request.POST['due_date']: # If date string is present
                    try:
                        parsed_date = datetime.strptime(request.POST['due_date'], '%Y-%m-%d').date()
                        naive_datetime = datetime.combine(parsed_date, dt_time.min) 
                        task.due_date = timezone.make_aware(naive_datetime, timezone.get_default_timezone())
                        logger.debug(f"Processed due_date: {task.due_date}")
                    except ValueError:
                        logger.warning(f"Invalid due_date format received: {request.POST['due_date']}")
                else: # Empty string means clear the date
                    task.due_date = None
                    logger.debug("Processed empty due_date (cleared)")
                update_fields.append('due_date')

            if 'reminder_time' in request.POST:
                if request.POST['reminder_time']:
                    try:
                        parsed_date = datetime.strptime(request.POST['reminder_time'], '%Y-%m-%d').date()
                        naive_datetime = datetime.combine(parsed_date, dt_time(9, 0)) # Default time 9 AM
                        task.reminder_time = timezone.make_aware(naive_datetime, timezone.get_default_timezone())
                        logger.debug(f"Processed reminder_time: {task.reminder_time}")
                    except ValueError:
                        logger.warning(f"Invalid reminder_time format received: {request.POST['reminder_time']}")
                else: # Empty string means clear the date
                    task.reminder_time = None
                    logger.debug("Processed empty reminder_time (cleared)")
                update_fields.append('reminder_time')

            # Choice field (Recurrence)
            if 'recurrence' in request.POST:
                recurrence_value = request.POST['recurrence']
                valid_choices = [choice[0] for choice in Task.RECURRENCE_CHOICES]
                if recurrence_value in valid_choices:
                    task.recurrence = recurrence_value
                    update_fields.append('recurrence')
                    logger.debug(f"Processed recurrence: {task.recurrence}")
                else:
                     logger.warning(f"Invalid recurrence value received: {recurrence_value}")

            # Boolean fields - More robust check
            if 'task_completed' in request.POST:
                # Checkbox sends 'on' or specific value when checked. Absence means False.
                task.task_completed = request.POST.get('task_completed') == 'on' # Adjust 'on' if your checkbox sends a different value
                logger.debug(f"Processing task_completed: Found in POST, Value='{request.POST.get('task_completed')}', Set={task.task_completed}")
            else:
                task.task_completed = False
                logger.debug(f"Processing task_completed: Not in POST, Set=False")
            update_fields.append('task_completed')

            if 'important' in request.POST:
                task.important = request.POST.get('important') == 'on' # Adjust 'on' if value differs
                logger.debug(f"Processing important: Found in POST, Value='{request.POST.get('important')}', Set={task.important}")
            else:
                task.important = False
                logger.debug(f"Processing important: Not in POST, Set=False")
            update_fields.append('important')
            
            # List Name (if editable)
            if 'list_name' in request.POST:
                 try:
                      list_id = int(request.POST['list_name'])
                      task.list_name = TaskList.objects.get(id=list_id, user=request.user)
                      update_fields.append('list_name')
                      logger.debug(f"Processed list_name: ID={list_id}")
                 except (ValueError, TaskList.DoesNotExist, TypeError): # Added TypeError for safety
                      logger.warning(f"Invalid or non-existent list_name ID received: {request.POST.get('list_name')}")

            # --- Log final values before saving ---
            final_update_fields = sorted(list(set(update_fields))) # Ensure uniqueness and sort for clarity
            logger.info(f"--- FINAL CHECK BEFORE SAVE (Task ID: {task_id}) ---")
            logger.info(f"  Fields to update: {final_update_fields}")
            logger.info(f"  task.due_date: {task.due_date} (Type: {type(task.due_date)})")
            logger.info(f"  task.reminder_time: {task.reminder_time} (Type: {type(task.reminder_time)})")
            logger.info(f"  task.recurrence: {task.recurrence}")
            logger.info(f"  task.task_completed: {task.task_completed}")
            logger.info(f"  task.important: {task.important}")
            logger.info(f"  task.task_name: {task.task_name}")
            # Add other fields as needed for debugging

            # --- Save the changes ---
            if len(final_update_fields) > 1: 
                task.save(update_fields=final_update_fields) 
                logger.info(f"Task {task_id} save executed.")
            else:
                logger.info(f"No effective changes detected for task {task_id}; skipping save.")

            # --- Image Handling ---
            uploaded_images = request.FILES.getlist('images')
            if uploaded_images:
                logger.info(f"Handling {len(uploaded_images)} uploaded images for task {task.id}")
                handle_image_upload(task, uploaded_images)
            
            # --- Return success response ---
            image_data = [{'url': img.image_url, 'image_name': img.image_name, 'id': img.id} for img in task.images.all()] # Refresh image data
            logger.info(f"Returning success response for edit task id : {task_id}")
            return JsonResponse({
                'id': task.id,
                'task_name': task.task_name,
                'task_description': task.task_description,
                'due_date': task.due_date.isoformat() if task.due_date else None,
                'reminder_time': task.reminder_time.isoformat() if task.reminder_time else None,
                'recurrence': task.recurrence,
                'important': task.important,
                'task_completed': task.task_completed,
                'images': image_data,
                'list_name': {'id': task.list_name.id, 'name': task.list_name.list_name}
            })

        except Exception as e:
            logger.error(f"An unexpected error occurred while processing POST for edit task id: {task_id}, Error: {e}", exc_info=True)
            return JsonResponse({'success': False, 'error': f"An server error occurred: {e}"}, status=500)

    elif request.method == 'GET':
        try:
            # Use TaskEditForm for GET if it exists and is different, otherwise TaskForm is fine
            form = TaskEditForm(instance=task) if 'TaskEditForm' in locals() else TaskForm(instance=task) 
            logger.info(f"Edit Task - GET method - Using form: {type(form).__name__} for task {task_id}")
            image_data = []
            for image in images:
                image_data.append({'url': image.image_url, 'image_name': image.image_name, 'id': image.id})

            return render(request, 'task_management/edit_task.html', {'edit_task_form': form, 'images': images, 'task_id': task_id})
        except Exception as e:
            logger.error(f"An unexpected error occurred in GET method for edit task id {task_id} : Error {e}", exc_info=True)
            return HttpResponse(f"An error occurred loading the edit form: {e}", status=500)

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


# Background task endpoint triggered by Cloud Scheduler

@csrf_exempt
@login_required
def trigger_user_sync(request):
    """Endpoint triggered from UI both when page loads and when user clicks on sync button to enqueue sync tasks for the current user."""
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

    # Special list counts (dynamic special lists: Important, Past Due, All Tasks, Samaan Tasks)
    special_counts = {
        "IMPORTANT": Task.objects.filter(user=request.user, important=True, task_completed=False).count(),
        "PAST_DUE": Task.objects.filter(user=request.user, due_date__lt=timezone.now(), task_completed=False).count(),
        "ALL_TASKS": Task.objects.filter(user=request.user, task_completed=False).count(),
        "SAMAAN_TASKS": Task.objects.filter(user=request.user, list_name__list_name="Samaan Tasks", task_completed=False).count(),
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
    


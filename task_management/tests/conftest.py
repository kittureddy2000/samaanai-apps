import pytest
import json
from django.contrib.auth.models import User
from django.utils import timezone
from pytest_django.asserts import assertRedirects, assertContains
from unittest.mock import patch, MagicMock
from task_management.models import Task, TaskList, TaskSyncStatus
from core.models import UserToken
import datetime
import os
from dateutil.relativedelta import relativedelta
from django.core.management import call_command

@pytest.fixture
def user():
    """Create a test user."""
    user = User.objects.create_user(
        username='testuser',
        email='test@example.com',
        password='securepassword123'
    )
    return user

@pytest.fixture
def authenticated_client(client, user):
    """Create an authenticated client."""
    client.login(username='testuser', password='securepassword123')
    return client

@pytest.fixture
def task_list(user):
    """Create a sample task list."""
    return TaskList.objects.create(
        user=user,
        list_name="Samaan Tasks",
        list_code="SAMAAN_TASKS",
        list_type="special"
    )

@pytest.fixture
def task(user, task_list):
    """Create a sample task."""
    return Task.objects.create(
        user=user,
        task_name="Test Task",
        task_description="Test Description",
        list_name=task_list,
        due_date=timezone.now() + datetime.timedelta(days=1),
        reminder_time=timezone.now() + datetime.timedelta(hours=2),
        task_completed=False,
        important=False
    )

@pytest.fixture
def google_token(user):
    """Create a Google token for the user."""
    return UserToken.objects.create(
        user=user,
        provider='google',
        access_token='fake-access-token',
        refresh_token='fake-refresh-token',
        token_expires_at=timezone.now() + datetime.timedelta(hours=1)
    )

@pytest.fixture
def microsoft_token(user):
    """Create a Microsoft token for the user."""
    return UserToken.objects.create(
        user=user,
        provider='microsoft',
        access_token='fake-access-token',
        refresh_token='fake-refresh-token',
        token_expires_at=timezone.now() + datetime.timedelta(hours=1)
    )

@pytest.fixture
def mock_google_service():
    """Mock the Google Tasks API service."""
    with patch('task_management.sync_utils.build') as mock_build:
        service_mock = MagicMock()
        tasks_mock = MagicMock()
        tasklists_mock = MagicMock()
        
        # Structure the mock to match how the Google Tasks API is used
        service_mock.tasks.return_value = tasks_mock
        service_mock.tasklists.return_value = tasklists_mock
        
        # Mock responses for various API methods
        tasklists_mock.list.return_value.execute.return_value = {
            'items': [{'id': 'list1', 'title': 'My Tasks'}]
        }
        
        tasks_mock.list.return_value.execute.return_value = {
            'items': [
                {
                    'id': 'task1',
                    'title': 'Google Task 1',
                    'notes': 'Task notes',
                    'due': (timezone.now() + datetime.timedelta(days=1)).isoformat() + 'Z',
                    'status': 'needsAction'
                }
            ]
        }
        
        mock_build.return_value = service_mock
        yield service_mock

@pytest.fixture
def mock_ms_requests():
    """Mock requests for Microsoft API calls."""
    with patch('task_management.sync_utils.requests.get') as mock_get, \
         patch('task_management.sync_utils.requests.patch') as mock_patch, \
         patch('task_management.sync_utils.requests.post') as mock_post:
        
        # Mock GET responses
        mock_get.return_value = MagicMock()
        mock_get.return_value.status_code = 200
        mock_get.return_value.json.return_value = {
            'value': [
                {
                    'id': 'list1',
                    'displayName': 'Tasks'
                }
            ]
        }
        
        # Mock PATCH responses
        mock_patch.return_value = MagicMock()
        mock_patch.return_value.status_code = 200
        
        # Mock POST responses
        mock_post.return_value = MagicMock()
        mock_post.return_value.status_code = 200
        
        yield (mock_get, mock_patch, mock_post)

# Parallel testing support
@pytest.fixture(scope="session")
def django_db_setup(django_db_setup, django_db_blocker):
    with django_db_blocker.unblock():
        # Force migrations to run before any tests
        call_command('migrate')

# Extended task fixtures
@pytest.fixture
def completed_task(user, task_list):
    """Create a sample completed task."""
    return Task.objects.create(
        user=user,
        task_name="Completed Test Task",
        task_description="Already completed task",
        list_name=task_list,
        due_date=timezone.now() - datetime.timedelta(days=1),
        task_completed=True,
        important=False
    )

@pytest.fixture
def important_task(user, task_list):
    """Create a sample important task."""
    return Task.objects.create(
        user=user,
        task_name="Important Test Task",
        task_description="Flagged as important",
        list_name=task_list,
        due_date=timezone.now() + datetime.timedelta(days=1),
        task_completed=False,
        important=True
    )

@pytest.fixture
def recurring_task(user, task_list, request):
    """Create a recurring task with specified pattern."""
    recurrence = getattr(request, "param", Task.DAILY)
    
    return Task.objects.create(
        user=user,
        task_name=f"Recurring {recurrence} Task",
        task_description="This task repeats",
        list_name=task_list,
        due_date=timezone.now() + datetime.timedelta(days=1),
        recurrence=recurrence,
        task_completed=False,
        important=False
    )
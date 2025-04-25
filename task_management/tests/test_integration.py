import pytest
from unittest.mock import patch, MagicMock
from django.urls import reverse
import json
from task_management.models import Task, TaskList, TaskSyncStatus
from core.models import UserToken
from django.utils import timezone
import datetime

@pytest.mark.django_db
class TestTaskLifecycle:
    def test_complete_task_integration(self, authenticated_client, task, mock_google_service):
        """Test the complete lifecycle of a task including completion and sync."""
        # Setup - Link task to Google
        task.source = 'google'
        task.source_id = 'google-task-id-123'
        task.save()
        
        # 1. Mark task as complete
        complete_url = reverse('task_management:complete_task', args=[task.id])
        with patch('task_management.views.TaskSyncStatus.objects.update_or_create'):
            with patch('task_management.signals.trigger_google_task_update') as mock_trigger:
                response = authenticated_client.get(complete_url)
                assert response.status_code == 200
                
                # Verify task was marked as complete
                task.refresh_from_db()
                assert task.task_completed is True
                
                # Verify sync was triggered
                mock_trigger.assert_called_once()
    
    def test_task_creation_to_sync(self, authenticated_client, task_list, google_token, mock_google_service):
        """Test the full process: create task, verify it's synced to Google Tasks."""
        # 1. Create a new task
        add_url = reverse('task_management:add_task')
        task_data = {
            'task_name': 'Integration Test Task',
            'task_description': 'This task should be synced',
            'due_date': '2023-12-31'
        }
        
        # Create task and expect no sync (no source yet)
        with patch('task_management.signals.trigger_google_task_update') as mock_trigger:
            response = authenticated_client.post(add_url, task_data)
            assert response.status_code == 200
            
            # Verify task was created
            content = json.loads(response.content)
            assert content['success'] is True
            task_id = content['task']['id']
            
            # Verify sync was not triggered (not linked to Google yet)
            mock_trigger.assert_not_called()
        
        # 2. Now set up the task to be synced with Google
        task = Task.objects.get(id=task_id)
        task.source = 'google'
        task.source_id = 'new-google-task-id'
        task.save()
        
        # 3. Edit the task and verify sync is triggered
        edit_url = reverse('task_management:edit_task', args=[task.id])
        edit_data = {
            'task_name': 'Updated Integration Test Task',
            'task_description': 'Updated description',
            'due_date': '2023-12-15',
            'important': True
        }
        
        with patch('task_management.signals.trigger_google_task_update') as mock_trigger:
            response = authenticated_client.post(edit_url, edit_data)
            assert response.status_code == 200
            
            # Verify task was updated
            task.refresh_from_db()
            assert task.task_name == 'Updated Integration Test Task'
            assert task.important is True
            
            # Verify sync was triggered
            mock_trigger.assert_called_once()

    def test_cross_service_sync_resolution(self, user, google_token, microsoft_token):
        """Test conflict resolution when a task is updated in multiple services."""
        # Create a task that exists in both Google and Microsoft
        task = Task.objects.create(
            user=user,
            task_name="Sync Conflict Task",
            task_description="This task exists in both services",
            due_date=timezone.now() + datetime.timedelta(days=1),
            source="google",  # Primary source is Google
            source_id="conflict-task-id",
            last_update_date=timezone.now() - datetime.timedelta(minutes=30)
        )
        
        # Create sync status records for this user
        TaskSyncStatus.objects.create(
            user=user, provider="google", is_complete=True,
            last_sync=timezone.now() - datetime.timedelta(hours=1)
        )
        TaskSyncStatus.objects.create(
            user=user, provider="microsoft", is_complete=True,
            last_sync=timezone.now() - datetime.timedelta(hours=1)
        )
        
        # Mock the Google API to indicate the task was updated more recently there
        with patch('task_management.sync_utils.build') as mock_google_build:
            google_service_mock = MagicMock()
            google_tasks_mock = MagicMock()
            
            # Mock a more recent update in Google
            google_task_data = {
                'id': 'conflict-task-id',
                'title': 'Updated in Google',
                'notes': 'This was changed in Google',
                'updated': (timezone.now() - datetime.timedelta(minutes=15)).isoformat() + 'Z'
            }
            google_tasks_mock.get.return_value.execute.return_value = google_task_data
            google_service_mock.tasks.return_value = google_tasks_mock
            mock_google_build.return_value = google_service_mock
            
            # Mock the Microsoft API to indicate an older update
            with patch('task_management.sync_utils.requests.get') as mock_ms_get:
                ms_response_mock = MagicMock()
                ms_response_mock.status_code = 200
                ms_response_mock.json.return_value = {
                    'id': 'conflict-task-id',
                    'title': 'Updated in Microsoft',
                    'body': {'content': 'This was changed in Microsoft'},
                    'lastModifiedDateTime': (timezone.now() - datetime.timedelta(minutes=20)).isoformat()
                }
                mock_ms_get.return_value = ms_response_mock
                
                # Trigger the sync for both services
                from task_management.sync_utils import sync_user_tasks
                
                # Mock credentials
                with patch('task_management.sync_utils.Credentials'):
                    with patch('task_management.sync_utils.get_ms_access_token'):
                        # Execute Google sync first
                        sync_user_tasks(user, 'google')
                        
                        # Then Microsoft sync
                        sync_user_tasks(user, 'microsoft')
                        
                        # The task should have the Google version (more recent)
                        task.refresh_from_db()
                        assert task.task_name == 'Updated in Google'
                        assert task.task_description == 'This was changed in Google'
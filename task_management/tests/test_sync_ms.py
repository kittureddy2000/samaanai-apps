import pytest
from unittest.mock import patch, MagicMock
from django.utils import timezone
import datetime
from task_management.sync_utils import fetch_microsoft_tasks_and_save, update_ms_task

@pytest.mark.django_db
class TestMicrosoftTasksSync:
    def test_fetch_microsoft_tasks(self, user, microsoft_token, mock_ms_requests):
        """Test fetching tasks from Microsoft and saving them locally."""
        mock_get, mock_patch, mock_post = mock_ms_requests
        
        # Configure mock response for tasks
        mock_get.return_value.json.side_effect = [
            # First call - get task lists
            {
                'value': [
                    {'id': 'list1', 'displayName': 'Tasks'}
                ]
            },
            # Second call - get tasks
            {
                'value': [
                    {
                        'id': 'task1',
                        'title': 'MS Task 1',
                        'body': {'content': 'Task notes', 'contentType': 'text'},
                        'status': 'notStarted',
                        'lastModifiedDateTime': timezone.now().isoformat()
                    }
                ]
            }
        ]
        
        with patch('task_management.sync_utils.get_ms_access_token') as mock_get_token:
            mock_get_token.return_value = 'fake-ms-access-token'
            updates = fetch_microsoft_tasks_and_save(user, 'fake-ms-access-token')
            
            # Assert updates were processed
            assert len(updates) >= 1
            assert updates[0]['provider'] == 'Microsoft To Do'
            
            # Verify database state
            from task_management.models import Task
            assert Task.objects.filter(user=user, source='microsoft').exists()
    
    def test_update_microsoft_task(self, user, microsoft_token, task, mock_ms_requests):
        """Test updating a task in Microsoft To Do."""
        mock_get, mock_patch, mock_post = mock_ms_requests
        
        # Setup the task to be linked to Microsoft
        task.source = 'microsoft'
        task.source_id = 'ms-task-id-123'
        task.save()
        
        # Configure mock response for getting task
        mock_get.return_value.json.return_value = {
            'id': 'ms-task-id-123',
            'title': 'Original Title',
            'lastModifiedDateTime': (timezone.now() - datetime.timedelta(hours=1)).isoformat()
        }
        
        # Configure mock response for updating task
        mock_patch.return_value.json.return_value = {
            'id': 'ms-task-id-123',
            'title': 'Updated Title'
        }
        
        # Test updating the task
        with patch('task_management.sync_utils.get_ms_access_token') as mock_get_token:
            mock_get_token.return_value = 'fake-ms-access-token'
            result = update_ms_task(user, task)
            
            # Verify PATCH request was made
            mock_patch.assert_called_once()
            assert 'tasks/ms-task-id-123' in mock_patch.call_args[0][0]
            
            # Verify result
            assert result is not None
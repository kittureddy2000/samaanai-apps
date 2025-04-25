import pytest
from unittest.mock import patch, MagicMock
from django.utils import timezone
import datetime
from task_management.sync_utils import fetch_google_tasks_and_save, update_google_task

@pytest.mark.django_db
class TestGoogleTasksSync:
    def test_fetch_google_tasks(self, user, google_token, mock_google_service):
        """Test fetching tasks from Google and saving them locally."""
        with patch('task_management.sync_utils.Credentials') as mock_credentials:
            # Set up the mock credentials
            mock_creds = MagicMock()
            mock_creds.expired = False
            mock_credentials.return_value = mock_creds
            
            updates = fetch_google_tasks_and_save(user, mock_creds)
            
            # Assert updates were processed
            assert len(updates) >= 1
            assert 'task_name' in updates[0]
            assert 'action' in updates[0]
            
            # Verify database state - we should have a task created
            from task_management.models import Task
            assert Task.objects.filter(user=user, source='google').exists()
            
    def test_update_google_task(self, user, google_token, task, mock_google_service):
        """Test updating a task in Google."""
        # Setup the task to be linked to Google
        task.source = 'google'
        task.source_id = 'google-task-id-123'
        # Set last_update_date to a specific time
        task.last_update_date = timezone.now()
        task.save()
        
        # Setup the mock service
        tasks_mock = mock_google_service.tasks.return_value
        get_mock = tasks_mock.get.return_value.execute
        update_mock = tasks_mock.update.return_value.execute
        
        # Mock the get response with a properly formatted date string
        # Make sure this date is OLDER than task.last_update_date
        one_hour_ago = (timezone.now() - datetime.timedelta(hours=1)).strftime('%Y-%m-%dT%H:%M:%SZ')
        get_mock.return_value = {
            'id': 'google-task-id-123',
            'title': 'Original Title',
            'updated': one_hour_ago  # This is the key change - use a proper date format that's in the past
        }
        
        # Mock the update response
        update_mock.return_value = {
            'id': 'google-task-id-123',
            'title': 'Updated Title'
        }
        
        # Test updating the task
        with patch('task_management.sync_utils.get_google_service') as mock_get_service:
            mock_get_service.return_value = mock_google_service
            result = update_google_task(user, task)
            
            # Verify the update was called with correct parameters
            tasks_mock.update.assert_called_once()
            call_args = tasks_mock.update.call_args[1]
            assert call_args['task'] == 'google-task-id-123'
            assert call_args['body']['title'] == task.task_name
            
            # Verify result
            assert result is not None
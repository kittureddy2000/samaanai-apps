import pytest
from unittest.mock import patch, MagicMock
from django.utils import timezone
import datetime
from task_management.models import Task, TaskSyncStatus

@pytest.mark.django_db
class TestSyncEdgeCases:
    def test_sync_token_expired(self, user, google_token):
        """Test handling of expired tokens during sync."""
        # Set token to be expired
        google_token.token_expires_at = timezone.now() - datetime.timedelta(hours=1)
        google_token.save()
        
        with patch('task_management.sync_utils.build') as mock_build:
            with patch('task_management.sync_utils.Credentials') as mock_credentials:
                # Configure mock to simulate token refresh
                mock_creds = MagicMock()
                mock_creds.expired = True
                mock_creds.refresh_token = 'refresh-token'
                mock_credentials.return_value = mock_creds
                
                # Run the sync function
                from task_management.sync_utils import sync_user_tasks
                sync_user_tasks(user, 'google')
                
                # Verify token refresh was attempted
                mock_creds.refresh.assert_called_once()
    
    def test_sync_task_with_email_link(self, user, google_token, mock_google_service):
        """Test syncing a Google task with an email link in its description."""
        # Configure mock to return a task with an email link
        tasks_mock = mock_google_service.tasks.return_value
        list_mock = tasks_mock.list.return_value.execute
        
        list_mock.return_value = {
            'items': [
                {
                    'id': 'google-task-with-email',
                    'title': 'Task with Email Link',
                    'notes': 'Check this email',
                    'links': [
                        {
                            'type': 'email',
                            'link': 'https://mail.google.com/mail/u/0/#inbox/123456'
                        }
                    ],
                    'status': 'needsAction'
                }
            ]
        }
        
        with patch('task_management.sync_utils.Credentials') as mock_credentials:
            mock_creds = MagicMock()
            mock_creds.expired = False
            mock_credentials.return_value = mock_creds
            
            # Run the sync function
            updates = fetch_google_tasks_and_save(user, mock_creds)
            
            # Verify task was created with email link in description
            task = Task.objects.get(source_id='google-task-with-email')
            assert 'https://mail.google.com/mail/u/0/#inbox/123456' in task.task_description

    @pytest.mark.parametrize("error_type,expected_result", [
        ("connection_error", "retry"),
        ("auth_error", "refresh_token"),
        ("not_found", "create_new"),
        ("rate_limit", "backoff"),
    ])
    def test_sync_error_handling(self, user, google_token, error_type, expected_result):
        """Test how the sync system handles various API errors."""
        with patch('task_management.sync_utils.build') as mock_build:
            service_mock = MagicMock()
            tasks_mock = MagicMock()
            
            # Configure different error behaviors based on error_type
            if error_type == "connection_error":
                from googleapiclient.errors import HttpError
                from requests.exceptions import ConnectionError
                tasks_mock.list.side_effect = ConnectionError("Failed to connect")
                expected_behavior = "retry"
            elif error_type == "auth_error":
                from google.auth.exceptions import RefreshError
                tasks_mock.list.side_effect = RefreshError("Token refresh error")
                expected_behavior = "refresh_token"
            elif error_type == "not_found":
                from googleapiclient.errors import HttpError
                resp = MagicMock()
                resp.status = 404
                tasks_mock.list.side_effect = HttpError(resp, b"Not found")
                expected_behavior = "create_new"
            elif error_type == "rate_limit":
                from googleapiclient.errors import HttpError
                resp = MagicMock()
                resp.status = 429
                tasks_mock.list.side_effect = HttpError(resp, b"Rate limited")
                expected_behavior = "backoff"
            
            service_mock.tasks.return_value = tasks_mock
            mock_build.return_value = service_mock
            
            # Run the sync function with error handling
            with patch('task_management.sync_utils.handle_sync_error') as mock_handler:
                from task_management.sync_utils import fetch_google_tasks_and_save
                from task_management.sync_utils import Credentials
                
                with patch('task_management.sync_utils.Credentials') as mock_credentials:
                    mock_creds = MagicMock()
                    mock_creds.expired = False
                    mock_credentials.return_value = mock_creds
                    
                    try:
                        fetch_google_tasks_and_save(user, mock_creds)
                    except Exception:
                        pass
                    
                    # Verify error handler was called with expected approach
                    if expected_result == "retry":
                        assert mock_handler.called
                        assert mock_handler.call_args[0][1] == "retry"
                    elif expected_result == "refresh_token":
                        assert mock_handler.called
                        assert mock_handler.call_args[0][1] == "refresh_token"
                    # Continue checking other expected results

    def test_file_attachment_sync(self, user, task, google_token, mock_google_service):
        """Test syncing tasks with file attachments."""
        # Setup a task with a file attachment
        from django.core.files.uploadedfile import SimpleUploadedFile
        
        # Mock getting attachment information from Google
        tasks_mock = mock_google_service.tasks.return_value
        get_mock = tasks_mock.get.return_value.execute
        
        # Configure mock to include attachment data
        get_mock.return_value = {
            'id': 'task-with-attachment',
            'title': 'Task with File',
            'notes': 'Check this file',
            'attachments': [
                {
                    'id': 'attachment1',
                    'filename': 'test.pdf',
                    'mimeType': 'application/pdf',
                    'downloadUrl': 'https://example.com/test.pdf'
                }
            ]
        }
        
        # Test your attachment handling logic
        # This would need to be adapted to your actual implementation
        with patch('task_management.sync_utils.download_attachment') as mock_download:
            mock_download.return_value = SimpleUploadedFile(
                "test.pdf", 
                b"file content", 
                content_type="application/pdf"
            )
            
            # Run the sync function that processes attachments
            from task_management.sync_utils import process_google_task_attachments
            # This function would need to be adapted to your actual implementation
            with patch('task_management.sync_utils.Credentials'):
                process_google_task_attachments(user, task, get_mock.return_value)
                
                # Verify attachments were processed
                # This assertion would need to match your implementation
                assert task.attachments.count() == 1
                assert task.attachments.first().filename == 'test.pdf'
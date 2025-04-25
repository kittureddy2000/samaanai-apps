import pytest
from django.urls import reverse
import json
from task_management.models import Task, TaskList

@pytest.mark.django_db
class TestTaskViews:
    def test_add_task(self, authenticated_client, task_list):
        """Test adding a new task via the add_task view."""
        url = reverse('task_management:add_task')
        data = {
            'task_name': 'New Task',
            'task_description': 'Task Description',
            'due_date': '2023-12-31',
            'recurrence': 'NO_RECURRENCE',
            'important': False
        }
        
        response = authenticated_client.post(url, data)
        assert response.status_code == 200
        assert Task.objects.filter(task_name='New Task').exists()
        
        # Check JSON response
        content = json.loads(response.content)
        assert content['success'] is True
        assert 'task' in content
        
    def test_edit_task(self, authenticated_client, task):
        """Test editing an existing task."""
        url = reverse('task_management:edit_task', args=[task.id])
        data = {
            'task_name': 'Updated Task Name',
            'task_description': 'Updated Description',
            'due_date': '2023-12-31',
            'recurrence': 'WEEKLY',
            'important': 'on'  # HTML checkbox sends 'on' when checked
        }
        
        response = authenticated_client.post(url, data)
        assert response.status_code == 200
        
        # Refresh task from database
        task.refresh_from_db()
        assert task.task_name == 'Updated Task Name'
        assert task.task_description == 'Updated Description'
        assert task.recurrence == 'WEEKLY'
        assert task.important is True
        
    def test_complete_task(self, authenticated_client, task):
        """Test marking a task as complete."""
        url = reverse('task_management:complete_task', args=[task.id])
        response = authenticated_client.get(url)
        assert response.status_code == 200
        
        # Refresh task from database
        task.refresh_from_db()
        assert task.task_completed is True
        
        # Check response content
        content = json.loads(response.content)
        assert content['status'] == 'success'
        assert content['completed'] is True
        
    def test_mark_favorite(self, authenticated_client, task):
        """Test marking a task as important/favorite."""
        url = reverse('task_management:mark_favorite')
        data = {'id': task.id}
        
        response = authenticated_client.post(url, data)
        assert response.status_code == 200
        
        # Refresh task from database
        task.refresh_from_db()
        assert task.important is True
        
        # Check response content
        content = json.loads(response.content)
        assert 'important' in content or 'Important' in content
        
    def test_get_all_tasks(self, authenticated_client, task):
        """Test retrieving all tasks."""
        url = reverse('task_management:get_all_tasks')
        response = authenticated_client.get(url)
        assert response.status_code == 200
        
        # Check response content
        content = json.loads(response.content)
        assert 'tasks' in content
        assert len(content['tasks']) >= 1
        
    def test_get_tasks_by_list(self, authenticated_client, task_list, task):
        """Test retrieving tasks by list."""
        url = reverse('task_management:get_tasks_by_list', args=[task_list.id])
        response = authenticated_client.get(url)
        assert response.status_code == 200
        
        # Check response content
        content = json.loads(response.content)
        assert 'tasks' in content
        assert len(content['tasks']) >= 1
        
    def test_search_tasks(self, authenticated_client, task):
        """Test searching for tasks."""
        url = reverse('task_management:search_tasks')
        query_params = {'q': 'Test'}
        
        response = authenticated_client.get(url, query_params)
        assert response.status_code == 200
        
        # Check response content
        content = json.loads(response.content)
        assert 'tasks' in content
        assert len(content['tasks']) >= 1
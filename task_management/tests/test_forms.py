import pytest
from django.utils import timezone
from task_management.forms import TaskForm, TaskEditForm

@pytest.mark.django_db
class TestTaskForm:
    def test_valid_task_form(self):
        """Test creating a valid task form."""
        form_data = {
            'task_name': 'Test Task',
            'task_description': 'Task Description',
            'due_date': timezone.now() + timezone.timedelta(days=1),
            'recurrence': 'NO_RECURRENCE',
            'task_completed': False,
            'important': False
        }
        
        form = TaskForm(data=form_data)
        assert form.is_valid()
        
    def test_blank_task_name(self):
        """Test that a blank task name is invalid."""
        form_data = {
            'task_name': '',
            'task_description': 'Task Description',
            'due_date': timezone.now() + timezone.timedelta(days=1)
        }
        
        form = TaskForm(data=form_data)
        assert not form.is_valid()
        assert 'task_name' in form.errors
        
    def test_task_edit_form(self, task):
        """Test editing a task through the form."""
        form_data = {
            'task_name': 'Updated Task',
            'task_description': 'Updated Description',
            'due_date': timezone.now() + timezone.timedelta(days=2),
            'reminder_time': timezone.now() + timezone.timedelta(hours=1),
            'recurrence': 'WEEKLY',
            'task_completed': True,
            'important': True
        }
        
        form = TaskEditForm(data=form_data, instance=task)
        assert form.is_valid()
        
        # Save form and check if task was updated
        updated_task = form.save()
        assert updated_task.task_name == 'Updated Task'
        assert updated_task.recurrence == 'WEEKLY'
        assert updated_task.task_completed is True
        assert updated_task.important is True
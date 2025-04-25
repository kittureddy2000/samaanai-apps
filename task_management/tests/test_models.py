import pytest
from django.utils import timezone
import datetime
from task_management.models import Task, TaskList
from dateutil.relativedelta import relativedelta

@pytest.mark.django_db
class TestTaskModel:
    def test_task_creation(self, task):
        """Test that a task can be created with all its fields."""
        assert task.id is not None
        assert task.task_name == "Test Task"
        assert task.task_description == "Test Description"
        assert not task.task_completed
        assert not task.important
        
    def test_task_completion(self, task):
        """Test toggling task completion."""
        assert not task.task_completed
        task.task_completed = True
        task.save()
        refreshed_task = Task.objects.get(id=task.id)
        assert refreshed_task.task_completed
        
    def test_task_importance(self, task):
        """Test toggling task importance."""
        assert not task.important
        task.important = True
        task.save()
        refreshed_task = Task.objects.get(id=task.id)
        assert refreshed_task.important
        
    def test_task_due_date(self, task):
        """Test setting and retrieving task due date."""
        future_date = timezone.now() + datetime.timedelta(days=5)
        task.due_date = future_date
        task.save()
        refreshed_task = Task.objects.get(id=task.id)
        # Compare dates by truncating microseconds
        assert refreshed_task.due_date.replace(microsecond=0) == future_date.replace(microsecond=0)
        
    def test_recurring_task_constant_values(self):
        """Test recurrence type constants."""
        assert Task.NO_RECURRENCE == 'NO_RECURRENCE'
        assert Task.DAILY == 'DAILY'
        assert Task.WEEKLY == 'WEEKLY'
        assert Task.MONTHLY == 'MONTHLY'
        assert Task.YEARLY == 'YEARLY'

@pytest.mark.django_db
class TestTaskListModel:
    def test_tasklist_creation(self, task_list):
        """Test that a task list can be created."""
        assert task_list.id is not None
        assert task_list.list_name == "Samaan Tasks"
        assert task_list.list_code == "SAMAAN_TASKS"
        assert task_list.list_type == "special"
        
    def test_tasklist_string_representation(self, task_list):
        """Test the string representation of a task list."""
        assert str(task_list) == "Samaan Tasks"
        
    def test_tasklist_task_association(self, task_list, task):
        """Test association between task and task list."""
        assert task.list_name == task_list

@pytest.mark.django_db
class TestRecurringTaskModel:
    @pytest.mark.parametrize("recurrence_type,expected_delta", [
        (Task.DAILY, datetime.timedelta(days=1)),
        (Task.WEEKLY, datetime.timedelta(weeks=1)),
        (Task.MONTHLY, relativedelta(months=1)),
        (Task.YEARLY, relativedelta(years=1)),
    ])
    def test_recurring_task_next_date(self, task, recurrence_type, expected_delta):
        """Test next due date calculation for different recurrence patterns."""
        original_due_date = timezone.now() + datetime.timedelta(days=1)
        task.due_date = original_due_date
        task.recurrence = recurrence_type
        task.save()
        
        # Simulate the complete_task view's behavior for recurring tasks
        expected_next_date = original_due_date + expected_delta
            
        # Test the logic for calculating next date
        from task_management.views import complete_task
        from django.test import RequestFactory
        
        factory = RequestFactory()
        request = factory.get('/')
        request.user = task.user
        response = complete_task(request, task.id)
        
        # Get the updated task
        updated_task = Task.objects.get(id=task.id)
        
        # Compare dates by truncating microseconds
        assert updated_task.due_date.replace(microsecond=0) == expected_next_date.replace(microsecond=0)
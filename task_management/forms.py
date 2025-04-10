from django import forms
from .models import Task, TaskList
from .widget import DatePickerInput, TimePickerInput, DateTimePickerInput
from django.contrib.auth.forms import UserCreationForm
from django.contrib.auth.models import User
from django.utils import timezone


class TaskListForm(forms.ModelForm):
    class Meta:
        model = TaskList
        fields = ['list_name', 'list_code', 'list_type']
        widgets = {
            'list_name': forms.TextInput(attrs={'class': 'form-control'}),
            'list_code': forms.HiddenInput(),
            'list_type': forms.HiddenInput(),
        }
        required = {
            'list_code': False,
            'list_type': False,
        }

    def __init__(self, *args, **kwargs):
        super(TaskListForm, self).__init__(*args, **kwargs)
        self.fields['list_code'].required = False
        self.fields['list_type'].required = False

class TaskForm(forms.ModelForm):
    class Meta:
        model = Task
        fields = ['task_name', 'task_description', 'list_name', 'due_date', 'reminder_time', 'recurrence', 'task_completed', 'important']
        widgets = {
            'task_name': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'Task name'}),
            'task_description': forms.Textarea(attrs={'class': 'form-control', 'placeholder': 'Task description'}),
            'list_name': forms.Select(attrs={'class': 'form-control'}),
            'reminder_time': forms.DateTimeInput(attrs={'type':'datetime-local'}),
            'due_date': forms.DateTimeInput(attrs={'type':'datetime-local'}),
            'recurrence': forms.Select(attrs={'class': 'd-none'}) # removed the default select element and hid this.
        }

    def __init__(self, *args, **kwargs):
        super(TaskForm, self).__init__(*args, **kwargs)
        self.fields['list_name'].queryset = TaskList.objects.all()
        



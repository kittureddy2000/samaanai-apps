from django.apps import AppConfig


class TaskManagementConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'task_management'

    def ready(self):
        import task_management.signals  # Import signals to register them
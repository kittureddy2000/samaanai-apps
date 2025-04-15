import logging
from django.core.management.base import BaseCommand
from google.cloud import tasks_v2
from google.api_core.exceptions import AlreadyExists, GoogleAPICallError
import os
from django.conf import settings

logger = logging.getLogger(__name__)

class Command(BaseCommand):
    help = 'Setup Cloud Tasks queue for stock data updates'

    def handle(self, *args, **options):
        self.stdout.write("Starting Cloud Tasks queue setup...")
        
        # Get configuration values
        project_id = os.environ.get('PROJECT_ID', settings.PROJECT_ID if hasattr(settings, 'PROJECT_ID') else None)
        location = os.environ.get('CLOUD_TASKS_LOCATION', 'us-central1')
        queue_name = os.environ.get('CLOUD_TASKS_QUEUE', 'stock-updates')
        
        if not project_id:
            self.stdout.write(self.style.ERROR("❌ PROJECT_ID not found in environment variables or settings"))
            self.stdout.write(self.style.WARNING("Set PROJECT_ID in environment or settings.py before running this command"))
            return
        
        self.stdout.write(f"Using project: {project_id}")
        self.stdout.write(f"Location: {location}")
        self.stdout.write(f"Queue name: {queue_name}")
        
        try:
            # Initialize the Cloud Tasks client
            client = tasks_v2.CloudTasksClient()
            parent = f"projects/{project_id}/locations/{location}"
            queue_path = client.queue_path(project_id, location, queue_name)
            
            # Check if queue already exists
            try:
                existing_queue = client.get_queue(request={"name": queue_path})
                self.stdout.write(self.style.SUCCESS(f"✅ Queue '{queue_name}' already exists"))
                self.stdout.write("Queue configuration:")
                self.stdout.write(f"  Rate: {existing_queue.rate_limits.max_dispatches_per_second} dispatches/second")
                self.stdout.write(f"  Max concurrent: {existing_queue.rate_limits.max_concurrent_dispatches}")
                return
            except GoogleAPICallError:
                self.stdout.write(f"Queue '{queue_name}' doesn't exist. Creating it...")
            
            # Create a queue with rate limiting appropriate for stock API calls
            # AlphaVantage has limitations of about 5 calls per minute for free tier
            queue = {
                "name": queue_path,
                "rate_limits": {
                    "max_dispatches_per_second": 0.2,  # ~12 tasks per minute (< API limits)
                    "max_concurrent_dispatches": 5,    # Max 5 concurrent requests
                },
                "retry_config": {
                    "max_attempts": 5,
                    "min_backoff": {"seconds": 60},    # 1 minute initial backoff
                    "max_backoff": {"seconds": 3600},  # 1 hour max backoff
                    "max_retry_duration": {"seconds": 86400},  # Retry for up to 1 day
                    "max_doublings": 3,
                },
            }
            
            # Create the queue
            response = client.create_queue(request={"parent": parent, "queue": queue})
            self.stdout.write(self.style.SUCCESS(f"✅ Created queue: {response.name}"))
            
            # Set up Cloud Scheduler job to refresh all stocks daily
            self.stdout.write("Setting up daily stock refresh job...")
            
            from portfolio.tasks import schedule_daily_stock_refresh
            job_name = schedule_daily_stock_refresh()
            
            if job_name:
                self.stdout.write(self.style.SUCCESS(f"✅ Created/updated Cloud Scheduler job: {job_name}"))
            else:
                self.stdout.write(self.style.ERROR("❌ Failed to create/update Cloud Scheduler job"))
            
        except AlreadyExists:
            self.stdout.write(self.style.SUCCESS(f"✅ Queue '{queue_name}' already exists"))
        
        except Exception as e:
            self.stdout.write(self.style.ERROR(f"❌ Error: {str(e)}"))
            import traceback
            traceback.print_exc()
            
        self.stdout.write(self.style.SUCCESS("\nCloud Tasks setup completed!")) 
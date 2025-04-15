import logging
import json
import os
from google.cloud import tasks_v2
from google.protobuf import timestamp_pb2
import datetime

from django.conf import settings
from django.urls import reverse

logger = logging.getLogger(__name__)

# Configuration for Cloud Tasks
CLOUD_TASKS_LOCATION = os.environ.get('CLOUD_TASKS_LOCATION', 'us-central1')
CLOUD_TASKS_QUEUE = os.environ.get('CLOUD_TASKS_QUEUE', 'stock-updates')
CLOUD_TASKS_PROJECT = os.environ.get('PROJECT_ID', settings.PROJECT_ID if hasattr(settings, 'PROJECT_ID') else None)
SERVICE_URL = os.environ.get('CLOUDRUN_SERVICE_URL', settings.CLOUDRUN_SERVICE_URL if hasattr(settings, 'CLOUDRUN_SERVICE_URL') else 'http://localhost:8000')


def create_cloud_task(relative_uri, payload, delay_seconds=0, task_name=None):
    """
    Create a Cloud Task to execute the given function
    """
    if not CLOUD_TASKS_PROJECT:
        logger.error("No PROJECT_ID configured for Cloud Tasks")
        return None

    client = tasks_v2.CloudTasksClient()
    parent = client.queue_path(CLOUD_TASKS_PROJECT, CLOUD_TASKS_LOCATION, CLOUD_TASKS_QUEUE)
    
    # Construct the request body
    task = {
        'http_request': {  # Specify the type of request
            'http_method': tasks_v2.HttpMethod.POST,
            'url': f"{SERVICE_URL.rstrip('/')}/{relative_uri.lstrip('/')}",  # URL to call
            'headers': {
                'Content-Type': 'application/json',
            },
            'body': json.dumps(payload).encode(),  # Task body
        }
    }
    
    # Add a name if provided
    if task_name:
        task['name'] = client.task_path(
            CLOUD_TASKS_PROJECT, 
            CLOUD_TASKS_LOCATION, 
            CLOUD_TASKS_QUEUE, 
            task_name
        )
    
    # Add scheduling time if delay is specified
    if delay_seconds > 0:
        d = datetime.datetime.utcnow() + datetime.timedelta(seconds=delay_seconds)
        timestamp = timestamp_pb2.Timestamp()
        timestamp.FromDatetime(d)
        task['schedule_time'] = timestamp
    
    # Create the task
    try:
        response = client.create_task(request={"parent": parent, "task": task})
        logger.info(f"Created task: {response.name}")
        return response.name
    except Exception as e:
        logger.error(f"Error creating Cloud Task: {str(e)}")
        return None


def refresh_stock_data(symbols, delay_seconds=0):
    """
    Create a Cloud Task to refresh stock data for the given symbols
    """
    if not symbols:
        logger.warning("No symbols provided to refresh_stock_data")
        return None
    
    logger.info(f"Scheduling refresh for {len(symbols)} stocks: {', '.join(symbols[:5])}{' and more' if len(symbols) > 5 else ''}")
    
    # Create a task to refresh these specific stocks
    payload = {
        "symbols": symbols
    }
    
    # Create a task with a unique name based on symbols
    symbols_hash = hash(''.join(sorted(symbols))) % 10000000
    task_name = f"refresh-stocks-{symbols_hash}-{int(datetime.datetime.utcnow().timestamp())}"
    
    return create_cloud_task(
        relative_uri="portfolio/api/refresh-stocks/",
        payload=payload,
        delay_seconds=delay_seconds,
        task_name=task_name
    )


def update_all_stocks_daily():
    """
    Create a Cloud Task to update all stocks in the database
    This can be called by a Cloud Scheduler job once daily
    """
    logger.info("Scheduling daily update for all stocks")
    
    # Create a task for refreshing all stocks
    payload = {}  # Empty payload means "refresh all"
    task_name = f"refresh-all-stocks-{int(datetime.datetime.utcnow().timestamp())}"
    
    return create_cloud_task(
        relative_uri="portfolio/api/refresh-all-stocks/",
        payload=payload,
        task_name=task_name
    )


def schedule_daily_stock_refresh():
    """
    Create a Cloud Scheduler job to refresh all stocks daily at market close (4:30 PM ET)
    This should be run once during application deployment or setup
    """
    from google.cloud import scheduler_v1
    
    client = scheduler_v1.CloudSchedulerClient()
    parent = f"projects/{CLOUD_TASKS_PROJECT}/locations/{CLOUD_TASKS_LOCATION}"
    job_name = f"{parent}/jobs/daily-stock-refresh"
    
    # Define the Cloud Scheduler job
    job = {
        'name': job_name,
        'schedule': '30 16 * * 1-5',  # 4:30 PM ET, Monday-Friday
        'time_zone': 'America/New_York',
        'http_target': {
            'uri': f"{SERVICE_URL.rstrip('/')}/portfolio/api/trigger-daily-refresh/",
            'http_method': scheduler_v1.HttpMethod.POST,
            'headers': {
                'Content-Type': 'application/json',
            },
        }
    }
    
    # Check if the job already exists
    try:
        client.get_job(request={"name": job_name})
        # If we get here, job exists, so update it
        response = client.update_job(request={"job": job})
        logger.info(f"Updated daily stock refresh scheduler job: {response.name}")
    except Exception:
        # Job doesn't exist, create it
        response = client.create_job(request={"parent": parent, "job": job})
        logger.info(f"Created daily stock refresh scheduler job: {response.name}")
    
    return response.name
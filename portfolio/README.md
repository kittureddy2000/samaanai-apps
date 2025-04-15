# Portfolio Management Application

A Django application for tracking stock portfolios, transactions, and market data.

## Redis Caching Implementation

This application now uses Redis for caching stock data instead of storing it directly in the database. This provides several advantages:

1. **Reduced Database Load**: Only essential data (transactions, portfolio structure) is stored in the database
2. **Better Performance**: Redis provides faster data access than database queries
3. **Configurable Freshness**: Different cache timeouts for different types of data (15 minutes for prices, 24 hours for company info)
4. **API Rate Limit Management**: Reduces the number of API calls to AlphaVantage, respecting their rate limits

### Key Components:

1. **StockDataService**: Service layer that handles retrieving stock data from Redis or the API
2. **Redis Cache Configuration**: Settings for connecting to Redis and configuring cache parameters
3. **Cloud Tasks Integration**: Background tasks for refreshing stock data through Google Cloud Tasks
4. **Management Commands**: For setup and administration

## Deployment Instructions

### 1. Update Database Schema

```bash
python manage.py makemigrations portfolio --name simplify_stock_model
python manage.py migrate
```

### 2. Setup Redis Cache

For local development:
```bash
# Install Redis locally
brew install redis  # Mac
sudo apt-get install redis-server  # Ubuntu/Debian

# Start Redis
redis-server
```

For production in Google Cloud:
```bash
# Create a Redis instance in Cloud Memorystore
gcloud redis instances create stock-cache \
    --size=1 \
    --region=us-central1 \
    --redis-version=redis_6_x
```

After creating the Redis instance, set the environment variables:
```
REDIS_HOST=<redis-ip-address>
REDIS_PORT=6379
REDIS_PASSWORD=<optional-password>
REDIS_SSL=True  # If using SSL
```

### 3. Setup Cloud Tasks Queue

```bash
# Make sure the commands directory structure is in place
mkdir -p portfolio/management/commands

# Set required environment variables
export PROJECT_ID=your-google-cloud-project-id
export CLOUD_TASKS_LOCATION=us-central1
export CLOUD_TASKS_QUEUE=stock-updates
export CLOUDRUN_SERVICE_URL=https://your-service-url.run.app

# Run the setup command
python manage.py setup_cloud_tasks
```

### 4. Initialize Stock Data Cache

After deployment, run the cache initialization command:

```bash
python manage.py setup_redis_cache
```

## Environment Variables

Add these to your `.env` file for local development or your Cloud Run configuration for production:

```
# Redis Configuration
REDIS_HOST=localhost  # or IP address of Cloud Memorystore instance
REDIS_PORT=6379
REDIS_DB=0
REDIS_PASSWORD=  # Leave empty for no password
REDIS_SSL=False  # Set to True for Cloud Memorystore with SSL

# Cloud Tasks Configuration  
PROJECT_ID=your-google-cloud-project-id
CLOUD_TASKS_LOCATION=us-central1
CLOUD_TASKS_QUEUE=stock-updates
CLOUDRUN_SERVICE_URL=https://your-service-url.run.app

# API Keys
ALPHA_VANTAGE_API_KEY=your-alpha-vantage-api-key
```

## Maintenance and Monitoring

- Check Redis cache status: `python manage.py setup_redis_cache`
- Monitor Cloud Tasks queue in Google Cloud Console
- Verify scheduled job status in Cloud Scheduler

## Architecture Diagram

```
┌─────────────────┐      ┌─────────────────┐      ┌─────────────────┐
│   Django App    │◄────►│  Redis Cache    │      │ AlphaVantage    │
│  (Cloud Run)    │      │ (Memorystore)   │      │      API        │
└────────┬────────┘      └─────────────────┘      └────────▲────────┘
         │                                                  │
         │                                                  │
         │                                                  │
         │                      Cache Miss                  │
         └──────────────────────────────────────────────────┘
                              
┌─────────────────┐      ┌─────────────────┐
│  Cloud Tasks    │◄────►│Cloud Scheduler  │
│    Queue        │      │                 │
└─────────────────┘      └─────────────────┘
```

## Features

- Create and manage multiple stock portfolios
- Track buy and sell transactions
- Real-time stock price updates via Alpha Vantage API
- Performance metrics (total value, gain/loss, etc.)
- Background stock updates using Google Cloud Tasks

## Google Cloud Tasks Integration

This application uses Google Cloud Tasks for background stock data updates. The Celery implementation has been replaced with Cloud Tasks for improved scalability and reliability.

### Setup Instructions

1. **Set up Google Cloud Project**:
   - Create a Google Cloud project
   - Enable Cloud Tasks API
   - Set up service account with necessary permissions

2. **Configure Environment Variables**:
   ```
   PROJECT_ID=your-gcp-project-id
   BASE_URL=https://your-app-url.com
   ```

3. **Create Cloud Tasks Queue**:
   ```
   python portfolio/setup_cloud_tasks.py --project-id=your-gcp-project-id
   ```

4. **Schedule Daily Updates** (Optional):
   - Set up a Cloud Scheduler job to trigger the management command
   ```
   python manage.py schedule_stock_updates
   ```

### Cloud Tasks Architecture

- **Task Creation**: The `tasks.py` module contains functions to create Cloud Tasks
- **Task Handlers**: API endpoints in `api.py` process tasks triggered by Cloud Tasks
- **Stock Updates**: Both on-demand updates and scheduled daily refreshes are supported

## Deployment

When deploying to Google Cloud Run:

1. Ensure the service account has Cloud Tasks permissions
2. Set the BASE_URL environment variable to your Cloud Run service URL
3. Configure the Cloud Tasks queue in the same region as your Cloud Run service

## Development

For local development, the application will send tasks to Cloud Tasks, but you can easily mock this behavior for testing. 

##TODO
Performnace management
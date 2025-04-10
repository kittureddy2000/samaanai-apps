#!/bin/sh

# Exit immediately if a command exits with a non-zero status.
set -e

# Function to wait for the database to be ready
wait_for_db() {
    echo "Waiting for database..."
    # Use environment variables for database connection
    # Assumes PostgreSQL is on localhost:5432 via Cloud SQL Proxy or similar
    while ! pg_isready -h ${DB_HOST:-localhost} -p ${DB_PORT:-5432} -U ${DB_USER:-postgres} -q -t 1; do
        echo "Database is unavailable - sleeping"
        sleep 1
    done
    echo "Database is up!"
}

# Optional: Wait for DB if needed, uncomment if DB startup is slow
# wait_for_db 

# Collect static files
echo "Collecting static files..."
python manage.py collectstatic --noinput

# Run database migrations  <-- REMOVE/COMMENT THESE OUT
# echo "python manage.py Before Running Make Migrations"
# python manage.py makemigrations
# 
# echo "python manage.py Before Running migrate"
# python manage.py migrate
# 
# echo "python manage.py migrate - Complete..."

# Start Gunicorn server
# Use PORT environment variable provided by Cloud Run
# Use environment variables for Gunicorn configuration where possible
WORKERS=${GUNICORN_WORKERS:-1} # Default to 1 worker if not set
THREADS=${GUNICORN_THREADS:-8} # Default to 8 threads if not set
TIMEOUT=${GUNICORN_TIMEOUT:-0} # Default to 0 (infinite) if not set

echo "Starting Gunicorn server on port $PORT with $WORKERS workers and $THREADS threads..."
exec gunicorn samaanai.wsgi:application \
    --bind :$PORT \
    --workers $WORKERS \
    --threads $THREADS \
    --timeout $TIMEOUT
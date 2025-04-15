#!/bin/sh

# Exit immediately if a command exits with a non-zero status.
set -e

# Function to wait for the database to be ready
wait_for_db() {
    echo "Waiting for database..."
    
    # Try to connect using Python instead of pg_isready
    until python -c "
import sys
import psycopg2
try:
    psycopg2.connect(
        dbname='$DB_NAME',
        user='$DB_USER',
        password='$DB_PASSWORD',
        host='$DB_HOST'
    )
except psycopg2.OperationalError:
    sys.exit(1)
sys.exit(0)
    "; do
        echo "Database is unavailable - sleeping"
        sleep 1
    done
    
    echo "Database is up - continuing..."
}

# Optional: Wait for DB if needed, uncomment if DB startup is slow
wait_for_db 

# Collect static files
echo "Collecting static files..."
python manage.py collectstatic --noinput

echo "python manage.py Before Running Make Migrations"
python manage.py makemigrations

echo "python manage.py Before Running migrate"
python manage.py migrate

echo "python manage.py migrate - Complete..."

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
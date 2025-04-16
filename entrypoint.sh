#!/bin/sh

# Exit immediately if a command exits with a non-zero status.
set -e

# Function to wait for the database to be ready
wait_for_db() {
    echo "Waiting for database..."
    
    # Check if we're connecting to a Cloud SQL instance via Unix socket
    if [[ "$DB_HOST" == /cloudsql/* ]]; then
        echo "Detected Cloud SQL socket connection at $DB_HOST"
        
        # Try to connect using Python and Unix socket
        until python -c "
import sys
import psycopg2
try:
    conn_params = {
        'dbname': '$DB_NAME',
        'user': '$DB_USER',
        'password': '$DB_PASSWORD',
    }
    
    # Use Unix socket for Cloud SQL
    conn_params['host'] = '/cloudsql/$DB_INSTANCE_CONNECTION_NAME'
    
    conn = psycopg2.connect(**conn_params)
    conn.close()
    print('Database connection successful')
except psycopg2.OperationalError as e:
    print(f'Database connection error: {e}')
    sys.exit(1)
sys.exit(0)
        "; do
            echo "Database is unavailable - sleeping"
            sleep 1
        done
    else
        # Regular TCP connection for non-Cloud SQL or local development
        echo "Using TCP connection to database at $DB_HOST"
        
        # Try to connect using Python with TCP connection
        until python -c "
import sys
import psycopg2
try:
    conn = psycopg2.connect(
        dbname='$DB_NAME',
        user='$DB_USER',
        password='$DB_PASSWORD',
        host='$DB_HOST'
    )
    conn.close()
    print('Database connection successful')
except psycopg2.OperationalError as e:
    print(f'Database connection error: {e}')
    sys.exit(1)
sys.exit(0)
        "; do
            echo "Database is unavailable - sleeping"
            sleep 1
        done
    fi
    
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
PORT=${PORT:-8080} # Default to 8080 if not set

echo "Starting Gunicorn server on port $PORT with $WORKERS workers and $THREADS threads..."
exec gunicorn samaanai.wsgi:application \
    --bind 0.0.0.0:$PORT \
    --workers $WORKERS \
    --threads $THREADS \
    --timeout $TIMEOUT
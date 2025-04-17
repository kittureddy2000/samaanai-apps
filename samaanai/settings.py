#sammanaiapps/settings.py
"""Django settings for samaanai project."""

from pathlib import Path
import os
import environ
import google.auth
import json
from google.oauth2 import service_account
import google.cloud.logging
from google.cloud.logging.handlers import CloudLoggingHandler
from django.contrib.messages import constants as messages
import logging

# --- Setup logger ---
logger = logging.getLogger(__name__)
logger.setLevel(logging.DEBUG)  # Set the minimum log level

# Console handler
console_handler = logging.StreamHandler()
console_handler.setLevel(logging.DEBUG)  # Set the minimum log level for the console handler

# Formatter
formatter = logging.Formatter('[%(asctime)s] %(levelname)s %(name)s: %(message)s')
console_handler.setFormatter(formatter)

# Add the console handler to the logger
logger.addHandler(console_handler)

logger.info("settings.py loaded")

# Build paths inside the project like this: BASE_DIR / 'subdir'.
BASE_DIR = Path(__file__).resolve().parent.parent

# Initialize the environment object
env = environ.Env()

# Load the .env file
env_file = os.path.join(BASE_DIR, '.env')
if os.path.isfile(env_file):
    env.read_env(env_file)  # Load the environment variables from the .env file
    logger.info(".env file loaded successfully")
else:
    logger.warning("No .env file found")

# Print environment variable values for debugging
logger.info(f"ENVIRONMENT: {env('ENVIRONMENT', default='Not Set')}")
logger.info(f"SECRET_KEY: {env('SECRET_KEY', default='Not Set')}")
logger.info(f"PROJECT_ID: {env('PROJECT_ID', default='Not Set')}")
logger.info(f"DEBUG: {env.bool('DJANGO_DEBUG', default=False)}")
logger.info(f"HOST: {env('DB_HOST', default='Not Set')}")
logger.info(f"DB_NAME: {env('DB_NAME', default='Not Set')}")
logger.info(f"DB_USER: {env('DB_USER', default='Not Set')}")

# Redis settings for caching
REDIS_HOST = env('REDIS_HOST', default='localhost')
REDIS_PORT = env('REDIS_PORT', default='6379')
REDIS_DB = env('REDIS_DB', default='0')
REDIS_PASSWORD = env('REDIS_PASSWORD', default=None)
REDIS_SSL = env.bool('REDIS_SSL', default=False)

# Configure Django Redis Cache
CACHES = {
    "default": {
        "BACKEND": "django_redis.cache.RedisCache",
        "LOCATION": f"{'rediss' if REDIS_SSL else 'redis'}://{REDIS_HOST}:{REDIS_PORT}/{REDIS_DB}",
        "OPTIONS": {
            "CLIENT_CLASS": "django_redis.client.DefaultClient",
            "PASSWORD": REDIS_PASSWORD,
            "SOCKET_CONNECT_TIMEOUT": 5,  # seconds
            "SOCKET_TIMEOUT": 5,  # seconds
            "CONNECTION_POOL_KWARGS": {"max_connections": 100},
        },
        "KEY_PREFIX": "samaanai"
    }
}

# Stock data cache timeouts (in seconds)
STOCK_PRICE_CACHE_TIMEOUT = 60 * 15  # 15 minutes
STOCK_DETAILS_CACHE_TIMEOUT = 60 * 60 * 24  # 24 hours

try:
    credentials, project = google.auth.default()
    logger.info(f"Google Cloud project: {project}")
except google.auth.exceptions.DefaultCredentialsError as e:
    logger.error(f"Error: {str(e)}")

# Determine the environment ('development' or 'production')
ENVIRONMENT = env('ENVIRONMENT', default='development')
logger.info(f"Environment: {ENVIRONMENT}")

SECRET_KEY = None
DB_PASSWORD = None
EMAIL_HOST_PASSWORD = None

if ENVIRONMENT == 'development':
    logger.info('Entering Development Environment settings')
    ALLOWED_HOSTS = ['localhost','testserver','127.0.0.1']
    
    SECRET_KEY = env('SECRET_KEY', default='your-default-secret-key')
    DB_PASSWORD = env('DB_PASSWORD')
    EMAIL_HOST_USER = env('EMAIL_HOST_USER')
    EMAIL_HOST_PASSWORD = env('EMAIL_HOST_PASSWORD')
    PROJECT_ID = env('PROJECT_ID')

    logger.info("Setting CSS storage in local environment")
    STATIC_URL = '/static/'
    STATIC_ROOT = BASE_DIR / 'staticfiles'
    STATICFILES_DIRS = [BASE_DIR / 'core' / 'static']
    MEDIA_URL = '/media/'
    MEDIA_ROOT = BASE_DIR / 'media'

else:
    logger.info('Entering PRODUCTION Environment settings')

    # Function to get secret from Google Secret Manager
    def get_secret(secret_name):
        """Retrieves the value of a secret from Google Secret Manager."""
        from google.cloud import secretmanager

        project_id = os.environ.get('PROJECT_ID')
        if not project_id:
            raise Exception('PROJECT_ID environment variable not set.')

        client = secretmanager.SecretManagerServiceClient()
        name = f"projects/{project_id}/secrets/{secret_name}/versions/latest"
        response = client.access_secret_version(request={"name": name})
        secret_value = response.payload.data.decode('UTF-8')
        return secret_value

    # Fetch the service account JSON from the environment variable
    try:
        service_account_info = json.loads(get_secret('GOOGLE_APPLICATION_CREDENTIALS'))
        GS_CREDENTIALS = service_account.Credentials.from_service_account_info(service_account_info)
        logger.info("Successfully loaded service account credentials from Secret Manager.")
    except Exception as e:
        logger.error(f"Failed to load service account credentials: {e}")
        GS_CREDENTIALS = None  # Or handle the error as appropriate for your application

    # Fetch secrets from Google Secret Manager
    SECRET_KEY = get_secret('SECRET_KEY')
    DB_PASSWORD = get_secret('DB_PASSWORD')
    EMAIL_HOST_USER = os.environ.get('EMAIL_HOST_USER')
    EMAIL_HOST_PASSWORD = get_secret('EMAIL_HOST_PASSWORD')
    BASE_URL = env('BASE_URL', default='https://www.samaanai.com')

    logger.info("Setting up CSS storage in Google Cloud Storage")
    logger.info("EMAIL_HOST_USER: {EMAIL_HOST_USER}")
    logger.info("EMAIL_HOST_PASSWORD: {EMAIL_HOST_PASSWORD}")

    # In production, use Google Cloud Storage
    DEFAULT_FILE_STORAGE = 'storages.backends.gcloud.GoogleCloudStorage'
    STATICFILES_STORAGE = 'storages.backends.gcloud.GoogleCloudStorage'

    print(f"GS_BUCKET_NAME (raw): {os.environ.get('GS_BUCKET_NAME')}")
    print(f"REDIRECT_URI (raw): {os.environ.get('REDIRECT_URI')}")

    # # REDIRECT_URI = env('REDIRECT_URI', default='local_default_url')
    # # print(f"REDIRECT_URI (after): {REDIRECT_URI}")

    # # REDIRECT_URI1 = env('REDIRECT_URI')
    # # logger.info(f"REDIRECT_URI1: {REDIRECT_URI1}")  
    

    REDIRECT_URI = env('REDIRECT_URI', default='https://www.samaanai.com/task_management/microsoft_callback/')
    logger.info(f"REDIRECT_URI: {REDIRECT_URI}")


    GS_BUCKET_NAME = env('GS_BUCKET_NAME', default='using-ai-samaan')
    logger.info(f"GS_BUCKET_NAME: {GS_BUCKET_NAME}")

    STATIC_URL = f'https://storage.googleapis.com/{GS_BUCKET_NAME}/'
    MEDIA_URL = f'https://storage.googleapis.com/{GS_BUCKET_NAME}/media/'

    CLOUDRUN_SERVICE_URL = env("CLOUDRUN_SERVICE_URL", default=None)
    logger.info(f"CLOUDRUN_SERVICE_URL: {CLOUDRUN_SERVICE_URL}")
    
    allowed_hosts_str = env("DJANGO_ALLOWED_HOSTS", default=CLOUDRUN_SERVICE_URL)
    ALLOWED_HOSTS = allowed_hosts_str.split(',')
    logger.info(f"ALLOWED_HOSTS: {ALLOWED_HOSTS}")
    SECURE_SSL_REDIRECT = True
    SESSION_COOKIE_SECURE = True 
    CSRF_COOKIE_SECURE = True
    SECURE_PROXY_SSL_HEADER = ('HTTP_X_FORWARDED_PROTO', 'https')



    if CLOUDRUN_SERVICE_URL:
        CSRF_TRUSTED_ORIGINS = [CLOUDRUN_SERVICE_URL]
    else:
        CSRF_TRUSTED_ORIGINS = env.list('CSRF_TRUSTED_ORIGINS', default=[])
    logger.info(f"ALLOWED_HOSTS: {ALLOWED_HOSTS}")
    
    # Setup Google Cloud Logging
    try:
        client = google.cloud.logging.Client(credentials=GS_CREDENTIALS)
        client.setup_logging()
        logger.info("Successfully set up Google Cloud Logging.")
    except Exception as e:
        logger.error(f"Failed to set up Google Cloud Logging: {e}")

# General settings
DEBUG = env.bool('DEBUG', default=(ENVIRONMENT == 'development'))

logger.info("Setting up database configuration")

# Check if we're using Cloud SQL socket connection
DB_HOST = env('DB_HOST', default='db')
DB_NAME = env('DB_NAME')
DB_USER = env('DB_USER')
DB_PORT = env('DB_PORT', default='5432')
DB_INSTANCE_CONNECTION_NAME = env('DB_INSTANCE_CONNECTION_NAME', default=None)

# Get the password based on environment
if ENVIRONMENT == 'production':
    logger.info("Using Secret Manager password for database in production")
    
    try:
        # Check if we already have a password from Secret Manager
        if DB_PASSWORD:
            logger.info("Password already loaded from Secret Manager")
            logger.info(f"Password length: {len(DB_PASSWORD)}")
        else:
            logger.error("DB_PASSWORD is None from Secret Manager!")
    except Exception as e:
        logger.error(f"Error checking DB_PASSWORD: {e}")
else:
    logger.info("Using .env password for database in development")
    DB_PASSWORD = env('DB_PASSWORD')
    logger.info(f"Development password length: {len(DB_PASSWORD) if DB_PASSWORD else 0}")

logger.info("Password check complete")

# Database configuration
if DB_HOST.startswith('/cloudsql/'):
    logger.info(f"Using Cloud SQL socket connection at {DB_HOST}")
    # Log database connection details (without the password)
    logger.info(f"Database connection details - NAME: {DB_NAME}, USER: {DB_USER}, HOST: {DB_HOST}")
    
    # When connecting to Cloud SQL using Unix socket, the format is different
    # We should specify the socket directory as HOST
    DATABASES = {
        'default': {
            'ENGINE': 'django.db.backends.postgresql',
            'NAME': DB_NAME,
            'USER': DB_USER,
            'PASSWORD': DB_PASSWORD,
            'HOST': DB_HOST,  # /cloudsql/<PROJECT-ID>:<REGION>:<INSTANCE-NAME>
            'PORT': '',
            'OPTIONS': {'sslmode': 'disable'},
        }
    }
    logger.info("Using PostgreSQL with Cloud SQL Unix socket")
else:
    logger.info(f"Using standard TCP connection to database at {DB_HOST}")
    # Log database connection details (without the password)
    logger.info(f"Database connection details - NAME: {DB_NAME}, USER: {DB_USER}, HOST: {DB_HOST}, PORT: {DB_PORT}")
    
    DATABASES = {
        'default': {
            'ENGINE': 'django.db.backends.postgresql',
            'NAME': DB_NAME,
            'USER': DB_USER,
            'PASSWORD': DB_PASSWORD,
            'HOST': DB_HOST,
            'PORT': DB_PORT,
        }
    }
    logger.info("Using standard PostgreSQL TCP connection")

# Log that database configuration is complete (but don't log the actual config with password)
logger.info("Database configuration complete")


logger.info("Configuring installed apps and middleware")
INSTALLED_APPS = [
    'django.contrib.admin',
    'django.contrib.auth',
    'django.contrib.contenttypes',
    'django.contrib.sessions',
    'django.contrib.messages',
    'django.contrib.staticfiles',
    'core',
    'social_django',  # Added social-auth-app-django
    'spreturn',
    # 'task_management',
    'task_management.apps.TaskManagementConfig',  # Update this line
    'widget_tweaks',
    'crispy_forms',
    'crispy_bootstrap5', 
    'portfolio',
]

MIDDLEWARE = [
    'django.middleware.security.SecurityMiddleware',
    'django.contrib.sessions.middleware.SessionMiddleware',
    'django.middleware.common.CommonMiddleware',
    'django.middleware.csrf.CsrfViewMiddleware',
    'django.contrib.auth.middleware.AuthenticationMiddleware',
    'django.contrib.messages.middleware.MessageMiddleware',
    'django.middleware.clickjacking.XFrameOptionsMiddleware',
    'social_django.middleware.SocialAuthExceptionMiddleware',  # Added middleware for social-auth-app-django
]

# Authentication backends
AUTHENTICATION_BACKENDS = (
    'django.contrib.auth.backends.ModelBackend',
    'social_core.backends.google.GoogleOAuth2',  # Added Google OAuth2 backend
)


ROOT_URLCONF = 'samaanai.urls'

logger.info("Setting up template configuration")
TEMPLATES = [
    {
        'BACKEND': 'django.template.backends.django.DjangoTemplates',
        'DIRS': [os.path.join(BASE_DIR, 'core', 'templates')],
        'APP_DIRS': True,
        'OPTIONS': {
            'context_processors': [
                'django.template.context_processors.debug',
                'django.template.context_processors.request', 
                'django.contrib.auth.context_processors.auth',
                'django.contrib.messages.context_processors.messages',
                'social_django.context_processors.backends',  # Added for social-auth-app-django
                'social_django.context_processors.login_redirect',  # Added for social-auth-app-django
            ],
        },
    },
]

WSGI_APPLICATION = 'samaanai.wsgi.application'

# Password validation
AUTH_PASSWORD_VALIDATORS = [
    {'NAME': 'django.contrib.auth.password_validation.UserAttributeSimilarityValidator'},
    {'NAME': 'django.contrib.auth.password_validation.MinimumLengthValidator'},
    {'NAME': 'django.contrib.auth.password_validation.CommonPasswordValidator'},
    {'NAME': 'django.contrib.auth.password_validation.NumericPasswordValidator'},
]


# social-auth-app-django settings
SOCIAL_AUTH_GOOGLE_OAUTH2_KEY = env('GOOGLE_CLIENT_ID', default=None)
SOCIAL_AUTH_GOOGLE_OAUTH2_SECRET = env('GOOGLE_CLIENT_SECRET', default=None)
SOCIAL_AUTH_GOOGLE_OAUTH2_SCOPE = [
    'https://www.googleapis.com/auth/userinfo.email',
    'https://www.googleapis.com/auth/userinfo.profile',
    'https://www.googleapis.com/auth/gmail.readonly',       # Extended scope for Gmail
    'https://www.googleapis.com/auth/tasks'           # Extended scope for Google Tasks
]

# Alpha Vantage API key for stock data
ALPHA_VANTAGE_API_KEY = env('ALPHA_VANTAGE_API_KEY', default=None)

SOCIAL_AUTH_GOOGLE_OAUTH2_AUTH_EXTRA_ARGUMENTS = {
    'access_type': 'offline',
    'prompt': 'consent',  # or 'consent' or 'select_account' 
}
logger.info("setting up social-auth-app-django pipeline")   
# social-auth-app-django pipeline
SOCIAL_AUTH_PIPELINE = (
    'social_core.pipeline.social_auth.social_details',
    'social_core.pipeline.social_auth.social_uid',
    'social_core.pipeline.social_auth.auth_allowed',
    'social_core.pipeline.social_auth.social_user',
    'social_core.pipeline.user.get_username',
    'social_core.pipeline.user.create_user',        # Creates the user if missing
    'social_core.pipeline.social_auth.associate_user',
    'social_core.pipeline.social_auth.load_extra_data',
    'social_core.pipeline.user.user_details',
    'core.pipeline.save_tokens',
)
SOCIAL_AUTH_LOGIN_REDIRECT_URL = '/dashboard/'
SOCIAL_AUTH_LOGOUT_REDIRECT_URL = '/login/'
LOGIN_URL = '/login/'
LOGIN_REDIRECT_URL = '/dashboard/'
LOGOUT_REDIRECT_URL = '/login/'

logger.info("setting up Microsoft OAuth2 configuration")
MICROSOFT_AUTH = {
    "CLIENT_ID": env('MS_CLIENT_ID'),
    "CLIENT_SECRET": env('MS_CLIENT_SECRET'),
    "TENANT_ID": env('MS_TENANT_ID', default='common'),  
    "REDIRECT_URI": env('REDIRECT_URI'),
    "AUTHORITY": "https://login.microsoftonline.com/common", 
    'SCOPE': ['Tasks.Read']
}


# Default primary key field type
DEFAULT_AUTO_FIELD = 'django.db.models.BigAutoField'
CRISPY_TEMPLATE_PACK = 'bootstrap5'

CACHE_TIMEOUT = 300

# ... (rest of the settings.py from the previous response)

MESSAGE_TAGS = {
    messages.DEBUG: 'debug',
    messages.INFO: 'info',
    messages.SUCCESS: 'success',
    messages.WARNING: 'warning',
    messages.ERROR: 'danger',  # Bootstrap uses 'danger' instead of 'error'
}


# Email Backend Configuration
EMAIL_BACKEND = 'django.core.mail.backends.smtp.EmailBackend'
EMAIL_HOST = 'smtp.gmail.com'
EMAIL_PORT = 587  # Use 465 for SSL
EMAIL_USE_TLS = True  # Use EMAIL_USE_SSL=True if using port 465
DEFAULT_FROM_EMAIL = env('DEFAULT_FROM_EMAIL', default='samaanapps@gmail.com')
SERVER_EMAIL = env('DEFAULT_FROM_EMAIL', default='samaanapps@gmail.com')


LANGUAGE_CODE = 'en-us'
TIME_ZONE = 'UTC'
USE_I18N = True
USE_L10N = True
USE_TZ = True

logger.info(f"EMAIL_BACKEND: {EMAIL_BACKEND}")
logger.info(f"EMAIL_HOST: {EMAIL_HOST}")
logger.info(f"EMAIL_USE_TLS: {EMAIL_USE_TLS}")
logger.info(f"EMAIL_PORT: {EMAIL_PORT}")
logger.info(f"EMAIL_HOST_USER: {EMAIL_HOST_USER}")
logger.info(f"EMAIL_HOST_PASSWORD: {EMAIL_HOST_PASSWORD}")
logger.info(f"DEFAULT_FROM_EMAIL: {DEFAULT_FROM_EMAIL}")
logger.info(f"Static URL: {STATIC_URL}")
logger.info(f"Media URL: {MEDIA_URL}")

if ENVIRONMENT == 'development':
    # Development LOGGING configuration
    LOGGING = {
        'version': 1,
        'disable_existing_loggers': False,
        'formatters': {
            'standard': {
                'format': '[%(asctime)s] %(levelname)s %(name)s: %(message)s'
            },
            'verbose': {
                'format': '[%(asctime)s] %(levelname)s %(name)s %(pathname)s:%(lineno)d - %(message)s'
            },
        },
        'handlers': {
            'console': {
                'level': 'INFO',  # This handler logs DEBUG and above.
                'class': 'logging.StreamHandler',
                'formatter': 'standard',
            },
            'file': {
                'level': 'INFO',  # This handler logs DEBUG and above.
                'class': 'logging.FileHandler',
                'filename': os.path.join(BASE_DIR, 'logs/django_app.log'),
                'formatter': 'verbose',
            },
        },
        'loggers': {
            'django': {
                'handlers': ['console', 'file'],
                'level': 'INFO',
                'propagate': True,
            },
            'task_management': {  # Now correctly nested under "loggers"
                'handlers': ['console', 'file'],
                'level': 'INFO',
                'propagate': False,
            },

            'core': {  # Now correctly nested under "loggers"
                'handlers': ['console', 'file'],
                'level': 'INFO',
                'propagate': False,
            },
            # Optionally, add a root logger if needed:
            '': {
                'handlers': ['console', 'file'],
                'level': 'INFO',
            },
        },
    }

else:
    # Production LOGGING configuration
    LOGGING = {
        'version': 1,
        'disable_existing_loggers': False,
        'formatters': {
            'standard': {
                'format': '[%(asctime)s] %(levelname)s %(name)s: %(message)s'
            },
        },
        'handlers': {
            'cloud': {
                'class': 'google.cloud.logging.handlers.CloudLoggingHandler',
                'client': client,
                'formatter': 'standard',
            },
        },
        'root': {
            'handlers': ['cloud'],
            'level': 'INFO',
        },
    }

logger.info('settings.py file loaded successfully')
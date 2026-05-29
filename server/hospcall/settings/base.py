import logging
import os
from pathlib import Path

import structlog

from hospcall.settings import IS_DEPLOYED

BASE_DIR = Path(__file__).resolve().parent.parent.parent

SECRET_KEY = os.environ.get('SECRET_KEY', 'local-dev-secret-key-not-for-production')
DEBUG = os.environ.get('DEBUG', 'False').lower() == 'true'
ALLOWED_HOSTS = [h for h in os.environ.get('ALLOWED_HOSTS', '*').split(',') if h]

SECURE_PROXY_SSL_HEADER = ('HTTP_X_FORWARDED_PROTO', 'https')

INSTALLED_APPS = [
    'django.contrib.admin',
    'django.contrib.auth',
    'django.contrib.contenttypes',
    'django.contrib.sessions',
    'django.contrib.messages',
    'django.contrib.staticfiles',
    'corsheaders',
    'rest_framework',
    'django_extensions',
    'django_celery_results',
    'django_celery_beat',
    'health',
    'hospital.apps.HospitalConfig',
    'prompt.apps.PromptConfig',
    'calling.apps.CallingConfig',
    'schedule.apps.ScheduleConfig',
    'sourcing.apps.SourcingConfig',
]

MIDDLEWARE = [
    'django.middleware.security.SecurityMiddleware',
    'corsheaders.middleware.CorsMiddleware',
    'django.contrib.sessions.middleware.SessionMiddleware',
    'django.middleware.common.CommonMiddleware',
    'django.middleware.csrf.CsrfViewMiddleware',
    'django.contrib.auth.middleware.AuthenticationMiddleware',
    'django.contrib.messages.middleware.MessageMiddleware',
    'django.middleware.clickjacking.XFrameOptionsMiddleware',
]

ROOT_URLCONF = 'hospcall.urls'

TEMPLATES = [
    {
        'BACKEND': 'django.template.backends.django.DjangoTemplates',
        'DIRS': [],
        'APP_DIRS': True,
        'OPTIONS': {
            'context_processors': [
                'django.template.context_processors.request',
                'django.contrib.auth.context_processors.auth',
                'django.contrib.messages.context_processors.messages',
            ],
        },
    },
]

ASGI_APPLICATION = 'hospcall.asgi.application'

DATABASES = {
    'default': {
        'ENGINE': 'django.db.backends.postgresql',
        'NAME': os.environ.get('DB_NAME', 'hospcall'),
        'USER': os.environ.get('DB_USER', 'hospcall'),
        'PASSWORD': os.environ.get('DB_PASSWORD', ''),
        'HOST': os.environ.get('DB_HOST', 'localhost'),
        'PORT': os.environ.get('DB_PORT', '5432'),
        'CONN_HEALTH_CHECKS': True,
        'CONN_MAX_AGE': 600,
        'OPTIONS': {
            'connect_timeout': 5,
            'keepalives': 1,
            'keepalives_idle': 30,
            'keepalives_interval': 10,
            'keepalives_count': 5,
        },
    }
}

REDIS_URL = os.environ.get('REDIS_URL', 'redis://localhost:6379/0')

CACHES = {
    'default': {
        'BACKEND': 'django.core.cache.backends.redis.RedisCache',
        'LOCATION': REDIS_URL,
    }
}

# Celery
CELERY_BROKER_URL = REDIS_URL
if REDIS_URL.startswith('rediss://'):
    import ssl

    CELERY_BROKER_USE_SSL = {'ssl_cert_reqs': ssl.CERT_NONE}
    CELERY_REDIS_BACKEND_USE_SSL = {'ssl_cert_reqs': ssl.CERT_NONE}
CELERY_RESULT_BACKEND = 'django-db'
CELERY_RESULT_EXTENDED = True
CELERY_ACCEPT_CONTENT = ['json']
CELERY_TASK_SERIALIZER = 'json'
CELERY_RESULT_SERIALIZER = 'json'
CELERY_TIMEZONE = 'UTC'
CELERY_TASK_ACKS_LATE = True
CELERY_TASK_REJECT_ON_WORKER_LOST = True
CELERY_WORKER_PREFETCH_MULTIPLIER = 1

# DRT-5265 — dedicated queue for the sourcing tile search tasks. Google
# searchText calls go on `sourcing_search` so a concurrency-limited worker
# bounds their rate; LLM classify / persist stay on the default `celery`
# queue.
CELERY_TASK_ROUTES = {
    'sourcing.resolve_viewport': {'queue': 'sourcing_search'},
    'sourcing.fetch_tile': {'queue': 'sourcing_search'},
}

# DRT-5265 sourcing tile guardrails.
SOURCING_MAX_DEPTH = 6            # job-parameter overridable
SOURCING_CALL_LIMIT = 300         # job-parameter overridable (~$0.035/call → ~$10.5)
SOURCING_SPLIT_THRESHOLD = 55     # cumulative results >= this + no nextPageToken → split
SOURCING_MIN_TILE_METERS = 300    # edge length; stop splitting once a tile is this small
SOURCING_MAX_PAGES = 3            # API hard limit (60 results)
SOURCING_TILE_MAX_RETRIES = 3     # OVER_QUERY_LIMIT / transient network
SOURCING_SSE_MAX_SECONDS = 60 * 30  # SSE connection lifetime cap

# DRF
REST_FRAMEWORK = {
    'DEFAULT_RENDERER_CLASSES': ['rest_framework.renderers.JSONRenderer'],
    'DEFAULT_PARSER_CLASSES': ['rest_framework.parsers.JSONParser'],
    'DEFAULT_PERMISSION_CLASSES': ['rest_framework.permissions.AllowAny'],
}

# CORS — backoffice (Vercel + localhost dev)
CORS_ALLOWED_ORIGINS = [
    'http://localhost:3000',
    'http://localhost:3001',
    'https://hospcall.drtail.us',  # backoffice custom domain (Vercel)
]
CORS_ALLOWED_ORIGIN_REGEXES = [
    r'^https://hospcall-backoffice-[\w-]+-drtail-frontend\.vercel\.app$',
    r'^https://hospcall-backoffice(-[\w-]+)?\.vercel\.app$',
]
CORS_ALLOW_CREDENTIALS = False
CORS_ALLOW_HEADERS = [
    'authorization',
    'content-type',
    'accept',
    'origin',
]

# BlandAI
BLANDAI_API_KEY = os.environ.get('BLANDAI_API_KEY', '')
BLANDAI_BASE_URL = os.environ.get('BLANDAI_BASE_URL', 'https://api.bland.ai/v1')
BLANDAI_DEFAULT_VOICE = os.environ.get('BLANDAI_DEFAULT_VOICE', 'maya')
BLANDAI_DEFAULT_MODEL = os.environ.get('BLANDAI_DEFAULT_MODEL', 'base')
BLANDAI_DEFAULT_LANGUAGE = os.environ.get('BLANDAI_DEFAULT_LANGUAGE', 'en')
BLANDAI_MAX_DURATION = int(os.environ.get('BLANDAI_MAX_DURATION', '5'))  # minutes
BLANDAI_WEBHOOK_URL = os.environ.get('BLANDAI_WEBHOOK_URL', '')
BLANDAI_WEBHOOK_SECRET = os.environ.get('BLANDAI_WEBHOOK_SECRET', '')

# Google Places (target hospital sourcing)
GOOGLE_PLACES_API_KEY = os.environ.get('GOOGLE_PLACES_API_KEY', '')

# Anthropic — sourcing classifier (DRT-5204 §2.3).
# Loaded from SSM `/hospcall/ANTHROPIC_API_KEY` in prod; empty in local/test
# where the classifier is mocked at the boundary. This is the app key —
# distinct from the GitHub Actions `ANTHROPIC_API_KEY` repo secret the
# claude-review CI uses (different system, no collision).
ANTHROPIC_API_KEY = os.environ.get('ANTHROPIC_API_KEY', '')
ANTHROPIC_BASE_URL = os.environ.get('ANTHROPIC_BASE_URL', 'https://api.anthropic.com')

# AWS / S3
AWS_REGION = os.environ.get('AWS_REGION', 'us-west-2')
# Bucket for archived BlandAI call recordings. Empty in local/test where the
# archive helper short-circuits with a clear error instead of a silent skip.
RECORDINGS_BUCKET_NAME = os.environ.get('RECORDINGS_BUCKET_NAME', '')

# Backoffice mutating endpoints — clients send this token in X-Backoffice-Token.
# Empty value blocks every write request (fail closed in misconfigured env).
BACKOFFICE_API_TOKEN = os.environ.get('BACKOFFICE_API_TOKEN', '')

# Calling defaults
CALLING_TIMEZONE = os.environ.get('CALLING_TIMEZONE', 'America/Los_Angeles')

# i18n
LANGUAGE_CODE = 'en-us'
TIME_ZONE = 'UTC'
USE_I18N = True
USE_TZ = True

# Static
STATIC_URL = 'static/'
STATIC_ROOT = BASE_DIR / 'staticfiles'

DEFAULT_AUTO_FIELD = 'django.db.models.BigAutoField'

# Logging
LOGGING = {
    'version': 1,
    'disable_existing_loggers': False,
    'formatters': {
        'json': {'format': '%(message)s %(asctime)s %(levelname)s %(name)s'},
    },
    'handlers': {
        'console': {'class': 'logging.StreamHandler'},
        'json_console': {
            'level': 'INFO',
            'class': 'logging.StreamHandler',
            'formatter': 'json',
        },
        'null': {'class': 'logging.NullHandler'},
    },
    'loggers': {
        '': {
            'handlers': ['console'] if not IS_DEPLOYED else ['json_console'],
            'level': 'DEBUG' if DEBUG else 'INFO',
        },
        'django': {
            'handlers': ['console'] if not IS_DEPLOYED else ['json_console'],
            'level': 'INFO' if not IS_DEPLOYED else 'WARNING',
        },
        'django.request': {
            'handlers': ['console'] if not IS_DEPLOYED else ['json_console'],
            'level': 'WARNING',
            'propagate': False,
        },
        **{
            name: {'handlers': ['null'], 'level': 'DEBUG', 'propagate': False}
            for name in ['botocore', 'boto3', 'urllib3', 'celery']
        },
    },
}

structlog.configure(
    processors=[
        structlog.contextvars.merge_contextvars,
        structlog.processors.add_log_level,
        structlog.processors.StackInfoRenderer(),
        structlog.dev.set_exc_info,
        structlog.processors.format_exc_info,
        structlog.processors.UnicodeDecoder(),
        (
            structlog.processors.JSONRenderer()
            if IS_DEPLOYED
            else structlog.dev.ConsoleRenderer()
        ),
    ],
    wrapper_class=structlog.make_filtering_bound_logger(
        logging.INFO if not DEBUG else logging.DEBUG
    ),
    logger_factory=structlog.WriteLoggerFactory(),
    cache_logger_on_first_use=True,
)

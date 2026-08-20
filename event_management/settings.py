"""
Django settings for the Eventra project.
"""

import os
from pathlib import Path

from dotenv import load_dotenv

BASE_DIR = Path(__file__).resolve().parent.parent

# Loads values from the local .env file.
load_dotenv(BASE_DIR / '.env.example')


# ---------------------------------------------------------------------------
# Core Configuration
# ---------------------------------------------------------------------------

# Django secret key is loaded from .env.
# Never hardcode the real secret key in source code.
SECRET_KEY = os.environ.get('SECRET_KEY')

if not SECRET_KEY:
    raise RuntimeError(
        "SECRET_KEY is not configured. "
        "Please add SECRET_KEY to your .env file."
    )


# DEBUG is controlled through .env.
# Local development:
# DEBUG=True
#
# Production:
# DEBUG=False
DEBUG = os.environ.get('DEBUG', 'True').strip().lower() == 'true'


# ALLOWED_HOSTS is controlled through .env.
#
# Local development:
# ALLOWED_HOSTS=127.0.0.1,localhost
#
# Production:
# ALLOWED_HOSTS=your-domain.com,www.your-domain.com
ALLOWED_HOSTS = [
    host.strip()
    for host in os.environ.get(
        'ALLOWED_HOSTS',
        '127.0.0.1,localhost'
    ).split(',')
    if host.strip()
]


# ---------------------------------------------------------------------------
# CSRF Trusted Origins
# ---------------------------------------------------------------------------

# Optional.
# For local development this can normally remain empty.
#
# Example production:
# CSRF_TRUSTED_ORIGINS=https://example.com,https://www.example.com
CSRF_TRUSTED_ORIGINS = [
    origin.strip()
    for origin in os.environ.get(
        'CSRF_TRUSTED_ORIGINS',
        ''
    ).split(',')
    if origin.strip()
]


# ---------------------------------------------------------------------------
# Production Security
# ---------------------------------------------------------------------------

# HSTS is enabled only when explicitly configured through environment
# variables. This prevents accidentally enabling HSTS during local
# development.

SECURE_HSTS_SECONDS = int(
    os.environ.get('SECURE_HSTS_SECONDS', '0')
)

SECURE_HSTS_INCLUDE_SUBDOMAINS = (
    os.environ.get(
        'SECURE_HSTS_INCLUDE_SUBDOMAINS',
        'False'
    ).strip().lower() == 'true'
)

SECURE_HSTS_PRELOAD = (
    os.environ.get(
        'SECURE_HSTS_PRELOAD',
        'False'
    ).strip().lower() == 'true'
)

# These are only enabled when DEBUG=False.
SECURE_SSL_REDIRECT = (
    os.environ.get(
        'SECURE_SSL_REDIRECT',
        'False'
    ).strip().lower() == 'true'
) if not DEBUG else False

SESSION_COOKIE_SECURE = (
    os.environ.get(
        'SESSION_COOKIE_SECURE',
        'False'
    ).strip().lower() == 'true'
) if not DEBUG else False

CSRF_COOKIE_SECURE = (
    os.environ.get(
        'CSRF_COOKIE_SECURE',
        'False'
    ).strip().lower() == 'true'
) if not DEBUG else False

SECURE_CONTENT_TYPE_NOSNIFF = True
SECURE_REFERRER_POLICY = 'same-origin'


# ---------------------------------------------------------------------------
# AI Chatbot
# ---------------------------------------------------------------------------

# Never hardcode the Gemini API key.
# Put it in the local .env file.
GEMINI_API_KEY = os.environ.get('GEMINI_API_KEY', '')

GEMINI_MODEL = os.environ.get(
    'GEMINI_MODEL',
    'gemini-2.0-flash'
)


# ---------------------------------------------------------------------------
# Application Definition
# ---------------------------------------------------------------------------

INSTALLED_APPS = [
    'django.contrib.admin',
    'django.contrib.auth',
    'django.contrib.contenttypes',
    'django.contrib.sessions',
    'django.contrib.messages',
    'django.contrib.staticfiles',

    # Local Apps
    'users',
    'events',
    'categories',
    'dashboard',
    'venues',
    'resources',
    'vendors',
    'staff',
    'budget',
    'tickets',
    'payments',
    'reviews',
    'chatbot',
    'reports',
    'workflow',
    'sponsors',
    'wishlist',
    'tasks',
    'certificates',
    'surveys',
    'chat',
    'gallery',
    'support',
    'currency',
    'ops',
    'organizations',
    'platform_settings',
]


# ---------------------------------------------------------------------------
# Middleware
# ---------------------------------------------------------------------------

MIDDLEWARE = [
    'django.middleware.security.SecurityMiddleware',
    'django.contrib.sessions.middleware.SessionMiddleware',
    'django.middleware.locale.LocaleMiddleware',
    'django.middleware.common.CommonMiddleware',
    'django.middleware.csrf.CsrfViewMiddleware',
    'django.contrib.auth.middleware.AuthenticationMiddleware',
    'platform_settings.middleware.MaintenanceModeMiddleware',
    'django.contrib.messages.middleware.MessageMiddleware',
    'django.middleware.clickjacking.XFrameOptionsMiddleware',
]


# ---------------------------------------------------------------------------
# URL Configuration
# ---------------------------------------------------------------------------

ROOT_URLCONF = 'event_management.urls'


# ---------------------------------------------------------------------------
# Templates
# ---------------------------------------------------------------------------

TEMPLATES = [
    {
        'BACKEND': 'django.template.backends.django.DjangoTemplates',
        'DIRS': [BASE_DIR / 'templates'],
        'APP_DIRS': True,
        'OPTIONS': {
            'context_processors': [
                'django.template.context_processors.request',
                'django.template.context_processors.media',
                'django.contrib.auth.context_processors.auth',
                'django.contrib.messages.context_processors.messages',
                'django.template.context_processors.i18n',
                'workflow.context_processors.notifications',
                'currency.context_processors.active_currency',
            ],
        },
    },
]


# ---------------------------------------------------------------------------
# WSGI
# ---------------------------------------------------------------------------

WSGI_APPLICATION = 'event_management.wsgi.application'


# ---------------------------------------------------------------------------
# Database
# ---------------------------------------------------------------------------

DATABASES = {
    'default': {
        'ENGINE': 'django.db.backends.sqlite3',
        'NAME': BASE_DIR / 'db.sqlite3',

        # SQLite waits for another transaction instead of immediately
        # raising "database is locked".
        'OPTIONS': {
            'timeout': 20,
        },

        # Test database configuration.
        # A real file is used so concurrency tests can exercise SQLite
        # locking behavior correctly.
        'TEST': {
            'NAME': str(BASE_DIR / 'test_db.sqlite3'),
        },
    }
}


# ---------------------------------------------------------------------------
# Custom User Model
# ---------------------------------------------------------------------------

AUTH_USER_MODEL = 'users.User'


# ---------------------------------------------------------------------------
# Password Validation
# ---------------------------------------------------------------------------

AUTH_PASSWORD_VALIDATORS = [
    {
        'NAME':
            'django.contrib.auth.password_validation.'
            'UserAttributeSimilarityValidator'
    },
    {
        'NAME':
            'django.contrib.auth.password_validation.'
            'MinimumLengthValidator'
    },
    {
        'NAME':
            'django.contrib.auth.password_validation.'
            'CommonPasswordValidator'
    },
    {
        'NAME':
            'django.contrib.auth.password_validation.'
            'NumericPasswordValidator'
    },
]


# ---------------------------------------------------------------------------
# Internationalization
# ---------------------------------------------------------------------------

LANGUAGE_CODE = 'en-us'

TIME_ZONE = 'Asia/Kolkata'

USE_I18N = True

USE_TZ = True

LANGUAGES = [
    ('en', 'English'),
    ('hi', 'हिन्दी (Hindi)'),
]

LOCALE_PATHS = [
    BASE_DIR / 'locale'
]


# ---------------------------------------------------------------------------
# Static Files
# ---------------------------------------------------------------------------

STATIC_URL = 'static/'

STATICFILES_DIRS = [
    BASE_DIR / 'static'
]

STATIC_ROOT = BASE_DIR / 'staticfiles'


# ---------------------------------------------------------------------------
# Media Files
# ---------------------------------------------------------------------------

MEDIA_URL = '/media/'

MEDIA_ROOT = BASE_DIR / 'media'


# ---------------------------------------------------------------------------
# Default Primary Key
# ---------------------------------------------------------------------------

DEFAULT_AUTO_FIELD = 'django.db.models.BigAutoField'


# ---------------------------------------------------------------------------
# Authentication Redirects
# ---------------------------------------------------------------------------

LOGIN_URL = 'users:login'

LOGIN_REDIRECT_URL = 'dashboard:dashboard'

LOGOUT_REDIRECT_URL = 'pages:home'


# ---------------------------------------------------------------------------
# Django Message Tags
# ---------------------------------------------------------------------------

MESSAGE_TAGS = {
    10: 'debug',
    20: 'info',
    25: 'success',
    30: 'warning',
    40: 'danger',
}


# ---------------------------------------------------------------------------
# Email
# ---------------------------------------------------------------------------

# Console backend is appropriate for local development.
# Configure SMTP through environment variables before production deployment.
EMAIL_BACKEND = 'django.core.mail.backends.console.EmailBackend'
"""
Django settings for the Eventra project.
"""

import os
from pathlib import Path

from dotenv import load_dotenv

BASE_DIR = Path(__file__).resolve().parent.parent

# Loads a local .env file if present (see .env.example). Safe to call
# even when no .env exists — load_dotenv() just no-ops in that case, so
# this doesn't break anyone's existing setup.
load_dotenv(BASE_DIR / '.env')

SECRET_KEY = 'django-insecure-l9s(v-a=lu(vk#b+3ng)w0z!uwund2&4&(frux9r(0ckji57_2'

DEBUG = True

ALLOWED_HOSTS = ['*']

# --- AI Chatbot (Phase 9) ---------------------------------------------
# Never hardcode this. Get a free key at https://aistudio.google.com/apikey
# and put it in a local .env file (see .env.example) — never commit it.
GEMINI_API_KEY = os.environ.get('GEMINI_API_KEY', '')
GEMINI_MODEL = os.environ.get('GEMINI_MODEL', 'gemini-2.0-flash')


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

ROOT_URLCONF = 'event_management.urls'

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

WSGI_APPLICATION = 'event_management.wsgi.application'


DATABASES = {
    'default': {
        'ENGINE': 'django.db.backends.sqlite3',
        'NAME': BASE_DIR / 'db.sqlite3',
    }
}


AUTH_USER_MODEL = 'users.User'


AUTH_PASSWORD_VALIDATORS = [
    {'NAME': 'django.contrib.auth.password_validation.UserAttributeSimilarityValidator'},
    {'NAME': 'django.contrib.auth.password_validation.MinimumLengthValidator'},
    {'NAME': 'django.contrib.auth.password_validation.CommonPasswordValidator'},
    {'NAME': 'django.contrib.auth.password_validation.NumericPasswordValidator'},
]


LANGUAGE_CODE = 'en-us'
TIME_ZONE = 'Asia/Kolkata'
USE_I18N = True
USE_TZ = True

LANGUAGES = [
    ('en', 'English'),
    ('hi', 'हिन्दी (Hindi)'),
]
LOCALE_PATHS = [BASE_DIR / 'locale']


STATIC_URL = 'static/'
STATICFILES_DIRS = [BASE_DIR / 'static']
STATIC_ROOT = BASE_DIR / 'staticfiles'

MEDIA_URL = '/media/'
MEDIA_ROOT = BASE_DIR / 'media'

DEFAULT_AUTO_FIELD = 'django.db.models.BigAutoField'

LOGIN_URL = 'users:login'
LOGIN_REDIRECT_URL = 'dashboard:dashboard'
LOGOUT_REDIRECT_URL = 'pages:home'

MESSAGE_TAGS = {
    10: 'debug',
    20: 'info',
    25: 'success',
    30: 'warning',
    40: 'danger',
}

EMAIL_BACKEND = 'django.core.mail.backends.console.EmailBackend'

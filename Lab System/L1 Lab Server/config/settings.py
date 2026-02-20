"""
Lab Server settings — IIIT Bangalore Water Meter Test Bench.
Runs on L3 RPi5 in Lab Building. Port 8080.
No hardware control. HTMX polling. LoRa via L1/L2.
"""

from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent

SECRET_KEY = 'django-insecure-lab-4u%fy)lnwl6xw(bde+99a&3$@-h&z+1%qd)yd1a755o'

DEBUG = True

ALLOWED_HOSTS = ['*']

# --- Installed Apps (no channels, no controller, no bench_ui) ---
INSTALLED_APPS = [
    'django.contrib.admin',
    'django.contrib.auth',
    'django.contrib.contenttypes',
    'django.contrib.sessions',
    'django.contrib.messages',
    'django.contrib.staticfiles',
    # Shared apps
    'accounts',
    'meters',
    'testing',
    'comms',
    'reports',
    'audit',
    # Lab-specific
    # 'lab_ui',  # will be added when lab_ui app is built
]

MIDDLEWARE = [
    'django.middleware.security.SecurityMiddleware',
    'whitenoise.middleware.WhiteNoiseMiddleware',
    'django.contrib.sessions.middleware.SessionMiddleware',
    'django.middleware.common.CommonMiddleware',
    'django.middleware.csrf.CsrfViewMiddleware',
    'django.contrib.auth.middleware.AuthenticationMiddleware',
    'django.contrib.messages.middleware.MessageMiddleware',
    'django.middleware.clickjacking.XFrameOptionsMiddleware',
]

ROOT_URLCONF = 'config.urls'

TEMPLATES = [
    {
        'BACKEND': 'django.template.backends.django.DjangoTemplates',
        'DIRS': [BASE_DIR / 'templates'],
        'APP_DIRS': True,
        'OPTIONS': {
            'context_processors': [
                'django.template.context_processors.debug',
                'django.template.context_processors.request',
                'django.contrib.auth.context_processors.auth',
                'django.contrib.messages.context_processors.messages',
                'config.context_processors.deployment_context',
            ],
        },
    },
]

WSGI_APPLICATION = 'config.wsgi.application'

# --- Database: Lab's own SQLite ---
DATABASES = {
    'default': {
        'ENGINE': 'django.db.backends.sqlite3',
        'NAME': BASE_DIR / 'db_lab.sqlite3',
    }
}

AUTH_PASSWORD_VALIDATORS = [
    {'NAME': 'django.contrib.auth.password_validation.UserAttributeSimilarityValidator'},
    {'NAME': 'django.contrib.auth.password_validation.MinimumLengthValidator'},
    {'NAME': 'django.contrib.auth.password_validation.CommonPasswordValidator'},
    {'NAME': 'django.contrib.auth.password_validation.NumericPasswordValidator'},
]

# --- Internationalization ---
LANGUAGE_CODE = 'en-us'
TIME_ZONE = 'Asia/Kolkata'
USE_I18N = True
USE_TZ = True

# --- Static files ---
STATIC_URL = '/static/'
STATICFILES_DIRS = [BASE_DIR / 'static']
STATIC_ROOT = BASE_DIR / 'staticfiles'
STORAGES = {
    'staticfiles': {
        'BACKEND': 'whitenoise.storage.CompressedManifestStaticFilesStorage',
    },
}

# --- Auth ---
AUTH_USER_MODEL = 'accounts.CustomUser'
LOGIN_URL = '/accounts/login/'
LOGIN_REDIRECT_URL = '/'
LOGOUT_REDIRECT_URL = '/accounts/login/'

DEFAULT_AUTO_FIELD = 'django.db.models.BigAutoField'

# --- Hardware backend ---
HARDWARE_BACKEND = 'simulator'

# --- ACMIS Protocol ---
ASP_AES_KEY = 'a' * 64  # Must match bench side
ASP_HMAC_KEY = 'b' * 64  # Must match bench side

# --- Lab-specific ---
ASP_DEVICE_ID = 0x0001  # Lab = 0x0001
LAB_SERIAL_PORT = '/dev/ttyUSB0'

# --- Deployment Type ---
DEPLOYMENT_TYPE = 'lab'

# --- Session: 30 min timeout for lab (security) ---
SESSION_COOKIE_AGE = 1800

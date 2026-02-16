"""
Lab-side settings. Django web portal on Lab RPi5.
Usage: DJANGO_SETTINGS_MODULE=config.settings_lab
"""

from config.settings_base import *  # noqa: F401,F403

# --- Deployment Type ---
DEPLOYMENT_TYPE = 'lab'

# --- Context processor for template switching ---
TEMPLATES[0]['OPTIONS']['context_processors'].append(
    'config.context_processors.deployment_context',
)

# --- Database: SQLite is sufficient for single-user lab ---
DATABASES = {
    'default': {
        'ENGINE': 'django.db.backends.sqlite3',
        'NAME': BASE_DIR / 'db_lab.sqlite3',
    }
}

# --- No WebSocket needed on lab side ---
# Lab uses HTMX polling (2s intervals) instead

# --- Serial port to L2 bridge ---
LAB_SERIAL_PORT = '/dev/ttyUSB0'
LAB_SERIAL_BAUD = 115200

# --- ASP Device ID ---
ASP_DEVICE_ID = 0x0001  # Lab = 0x0001

# --- Session ---
SESSION_COOKIE_AGE = 1800  # 30 min timeout

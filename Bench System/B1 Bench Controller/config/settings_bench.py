"""
Bench-side settings. Test bench controller on Bench RPi5.
Usage: DJANGO_SETTINGS_MODULE=config.settings_bench
"""

from config.settings_base import *  # noqa: F401,F403

# --- Bench-specific apps ---
INSTALLED_APPS += [
    'channels',
    'controller',
    'bench_ui',
]

# --- Database: PostgreSQL for concurrent access (prod) ---
# SQLite for development
DATABASES = {
    'default': {
        'ENGINE': 'django.db.backends.sqlite3',
        'NAME': BASE_DIR / 'db_bench.sqlite3',
    }
}

# PostgreSQL config for production (uncomment when ready):
# DATABASES = {
#     'default': {
#         'ENGINE': 'django.db.backends.postgresql',
#         'NAME': 'testbench',
#         'USER': 'testbench',
#         'PASSWORD': 'testbench',
#         'HOST': 'localhost',
#         'PORT': '5432',
#     }
# }

# --- Redis ---
REDIS_URL = 'redis://localhost:6379/0'
CHANNEL_LAYERS = {
    'default': {
        'BACKEND': 'channels.layers.InMemoryChannelLayer',
        # Production: use channels_redis.core.RedisChannelLayer
    },
}

# --- Serial ports ---
BENCH_SERIAL_PORT_BUS1 = '/dev/ttyBENCH_BUS'  # B2 sensor bridge
BENCH_SERIAL_PORT_BUS2 = '/dev/ttyVFD_BUS'    # B3 VFD bridge
BENCH_SERIAL_BAUD = 115200
MODBUS_BAUD = 9600

# --- PID defaults ---
PID_KP = 0.5
PID_KI = 0.1
PID_KD = 0.05
PID_OUTPUT_MIN = 5.0   # Hz
PID_OUTPUT_MAX = 50.0  # Hz
PID_SAMPLE_RATE = 0.2  # seconds (200ms)

# --- Safety limits ---
SAFETY_PRESSURE_MAX = 8.0      # bar
SAFETY_RESERVOIR_MIN = 20.0    # percent
SAFETY_SCALE_MAX = 180.0       # kg
SAFETY_TEMP_MIN = 5.0          # Celsius
SAFETY_TEMP_MAX = 40.0         # Celsius
SAFETY_VALVE_TIMEOUT = 5.0     # seconds
SAFETY_FLOW_STABILITY = 2.0    # percent tolerance
SAFETY_STABILITY_COUNT = 5     # consecutive readings

# --- ASP Device ID ---
ASP_DEVICE_ID = 0x0002  # Bench = 0x0002

# --- Session: no timeout on bench (always logged in as system) ---
SESSION_COOKIE_AGE = 86400 * 365  # 1 year

# --- Deployment Type ---
DEPLOYMENT_TYPE = 'bench'

# --- Context processor for template switching ---
TEMPLATES[0]['OPTIONS']['context_processors'].append(
    'config.context_processors.deployment_context',
)

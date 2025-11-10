import os
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent

DEBUG = False

# You can set ALLOWED_HOSTS as env variable in Render; for now allow all:
ALLOWED_HOSTS = os.environ.get("ALLOWED_HOSTS", "*").split(",")
# Later set ALLOWED_HOSTS = "your-app.onrender.com" in Render env

# Static files
STATIC_URL = '/static/'
STATIC_ROOT = BASE_DIR / 'staticfiles'

DATABASE_URL = os.environ.get("DATABASE_URL")

if DATABASE_URL:
    # Optional: dj-database-url if you want to parse DATABASE_URL properly.
    # If you don't yet have dj-database-url, the fallback below will still work for many URLs.
    try:
        import dj_database_url

        DATABASES = {
            "default": dj_database_url.parse(DATABASE_URL, conn_max_age=600)
        }
    except Exception:
        # Minimal parse for common postgres URLs (works in many cases)
        DATABASES = {
            "default": {
                "ENGINE": "django.db.backends.postgresql",
                "NAME": os.environ.get("PGDATABASE", ""),
                "USER": os.environ.get("PGUSER", ""),
                "PASSWORD": os.environ.get("PGPASSWORD", ""),
                "HOST": os.environ.get("PGHOST", ""),
                "PORT": os.environ.get("PGPORT", ""),
            }
        }
else:
    # Local development default: SQLite (no extra packages required)
    DATABASES = {
        "default": {
            "ENGINE": "django.db.backends.sqlite3",
            "NAME": BASE_DIR / "db.sqlite3",
        }
    }

INSTALLED_APPS = [
    'django.contrib.admin',
    'django.contrib.auth',
    'django.contrib.contenttypes',
    'django.contrib.sessions',
    'django.contrib.messages',
    'django.contrib.staticfiles',  # <- THIS IS REQUIRED for collectstatic
    # ... your apps here
]
# Optional: use whitenoise to serve static files
MIDDLEWARE = [
    # Security middleware usually first
    "django.middleware.security.SecurityMiddleware",

    # Session middleware must come before Auth middleware
    "django.contrib.sessions.middleware.SessionMiddleware",

    # Common middleware
    "django.middleware.common.CommonMiddleware",

    # CSRF protection
    "django.middleware.csrf.CsrfViewMiddleware",

    # Authentication must come after SessionMiddleware
    "django.contrib.auth.middleware.AuthenticationMiddleware",

    # Messages
    "django.contrib.messages.middleware.MessageMiddleware",

    # Clickjacking protection
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
]
STATICFILES_STORAGE = "whitenoise.storage.CompressedManifestStaticFilesStorage"

SECRET_KEY = os.environ.get("SECRET_KEY", "<temporary-secret-for-local>")

TEMPLATES = [
    {
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        # include a 'templates' directory in your project root (optional)
        "DIRS": [BASE_DIR / "templates"],
        "APP_DIRS": True,
        "OPTIONS": {
            "context_processors": [
                "django.template.context_processors.debug",
                "django.template.context_processors.request",  # required by admin
                "django.contrib.auth.context_processors.auth",
                "django.contrib.messages.context_processors.messages",
            ],
        },
    },
]

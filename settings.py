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

# Optional: use whitenoise to serve static files
MIDDLEWARE = [
    'django.middleware.security.SecurityMiddleware',
    'whitenoise.middleware.WhiteNoiseMiddleware',  
]
STATICFILES_STORAGE = "whitenoise.storage.CompressedManifestStaticFilesStorage"

SECRET_KEY = os.environ.get("SECRET_KEY", "<temporary-secret-for-local>")

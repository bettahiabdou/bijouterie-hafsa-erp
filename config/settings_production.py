from .settings import *

DEBUG = False
ALLOWED_HOSTS = ['89.167.27.57', 'localhost', 'hafsa-erp.com', 'hafsaerp.duckdns.org']

# PostgreSQL Database
DATABASES = {
    'default': {
        'ENGINE': 'django.db.backends.postgresql',
        'NAME': 'hafsa_erp',
        'USER': 'hafsa_user',
        'PASSWORD': 'Kimolove@1998',
        'HOST': 'localhost',
        'PORT': '5432',
    }
}

# Static files
STATIC_ROOT = '/var/www/bijouterie-hafsa-erp/staticfiles'
STATIC_URL = '/static/'

# Security settings
CSRF_TRUSTED_ORIGINS = ['http://89.167.27.57', 'https://89.167.27.57', 'https://hafsaerp.duckdns.org']
SECRET_KEY = 'your-production-secret-key-change-this-to-something-random'

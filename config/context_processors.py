"""
Custom context processors for the project.
"""
from django.conf import settings


def amana_settings(request):
    """
    Add AMANA proxy URL to template context.
    """
    return {
        'settings': {
            'AMANA_PROXY_URL': getattr(settings, 'AMANA_PROXY_URL', ''),
        }
    }

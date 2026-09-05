from django.shortcuts import redirect
from django.urls import reverse


# Path prefixes a 'delivery' role user is allowed to reach. Everything else
# redirects to the Poste Livraison workspace.
_ALLOWED_PREFIXES = (
    '/sales/poste-livraison',
    '/logout',
    '/login',
    '/static',
    '/media',
    '/sw.js',
    '/manifest',
)


class DeliveryRoleRestrictionMiddleware:
    """Confine users with the 'Responsable livraison' role to the Poste
    Livraison workspace. They keep no access to sales, prices or stock."""

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        user = getattr(request, 'user', None)
        if user is not None and user.is_authenticated and getattr(user, 'role', None) == 'delivery':
            path = request.path
            if not any(path.startswith(p) for p in _ALLOWED_PREFIXES):
                return redirect('sales:delivery_desk')
        return self.get_response(request)

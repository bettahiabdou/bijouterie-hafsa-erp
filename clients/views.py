from django.shortcuts import render
from django.http import JsonResponse
from django.views.decorators.http import require_http_methods
from django.contrib.auth.decorators import login_required
from .models import Client
import json


@login_required(login_url='login')
@require_http_methods(["POST"])
def quick_create_client(request):
    """Quickly create a client from invoice form popup"""
    try:
        # Get data from POST
        first_name = request.POST.get('first_name', '').strip()
        last_name = request.POST.get('last_name', '').strip()
        phone = request.POST.get('phone', '').strip()
        email = request.POST.get('email', '').strip()
        city = request.POST.get('city', '').strip()

        # Validate required fields
        if not first_name or not last_name or not phone:
            return JsonResponse({
                'success': False,
                'error': 'Prénom, nom et téléphone sont obligatoires'
            })

        # Create client
        client = Client.objects.create(
            first_name=first_name,
            last_name=last_name,
            phone=phone,
            email=email or '',
            city=city or '',
            is_active=True
        )

        return JsonResponse({
            'success': True,
            'client_id': client.id,
            'client_name': f"{client.first_name} {client.last_name}",
            'client_email': client.email or 'N/A'
        })

    except Exception as e:
        return JsonResponse({
            'success': False,
            'error': f'Erreur: {str(e)}'
        }, status=400)

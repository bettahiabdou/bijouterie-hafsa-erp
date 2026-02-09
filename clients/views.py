"""
Client views for Bijouterie Hafsa ERP
"""
from django.shortcuts import render, redirect, get_object_or_404
from django.http import JsonResponse
from django.views.decorators.http import require_http_methods
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.core.paginator import Paginator
from django.db.models import Q, Sum, Count
from .models import Client
from sales.models import SaleInvoice
from users.models import ActivityLog
import json


def get_client_ip(request):
    """Get client IP address from request"""
    x_forwarded_for = request.META.get('HTTP_X_FORWARDED_FOR')
    if x_forwarded_for:
        ip = x_forwarded_for.split(',')[0]
    else:
        ip = request.META.get('REMOTE_ADDR')
    return ip


@login_required(login_url='login')
def client_list(request):
    """List all clients with filtering and search"""
    clients = Client.objects.all()

    # Search
    search_query = request.GET.get('search', '')
    if search_query:
        clients = clients.filter(
            Q(code__icontains=search_query) |
            Q(first_name__icontains=search_query) |
            Q(last_name__icontains=search_query) |
            Q(phone__icontains=search_query) |
            Q(email__icontains=search_query) |
            Q(cin__icontains=search_query)
        )

    # Filter by type
    type_filter = request.GET.get('type', '')
    if type_filter:
        clients = clients.filter(client_type=type_filter)

    # Filter by status
    status_filter = request.GET.get('status', '')
    if status_filter == 'active':
        clients = clients.filter(is_active=True)
    elif status_filter == 'inactive':
        clients = clients.filter(is_active=False)

    # Sort
    sort_by = request.GET.get('sort', '-created_at')
    allowed_sorts = {
        'name': 'last_name',
        '-name': '-last_name',
        'code': 'code',
        '-code': '-code',
        'created': 'created_at',
        '-created': '-created_at',
    }
    sort_field = allowed_sorts.get(sort_by, '-created_at')
    clients = clients.order_by(sort_field)

    # Statistics
    total_clients = Client.objects.count()
    active_clients = Client.objects.filter(is_active=True).count()
    vip_clients = Client.objects.filter(client_type='vip').count()

    # Pagination
    paginator = Paginator(clients, 20)
    page_number = request.GET.get('page', 1)
    page_obj = paginator.get_page(page_number)

    context = {
        'clients': page_obj,
        'page_obj': page_obj,
        'search_query': search_query,
        'type_filter': type_filter,
        'status_filter': status_filter,
        'sort_by': sort_by,
        'total_clients': total_clients,
        'active_clients': active_clients,
        'vip_clients': vip_clients,
        'client_types': Client.ClientType.choices,
    }

    return render(request, 'clients/client_list.html', context)


@login_required(login_url='login')
def client_detail(request, pk):
    """Display client details with purchase history"""
    client = get_object_or_404(Client, pk=pk)

    # Get client's invoices (excluding soft-deleted)
    invoices = SaleInvoice.objects.filter(
        client=client,
        is_deleted=False
    ).select_related('seller').order_by('-date', '-created_at')

    # Calculate statistics
    total_purchases = invoices.aggregate(total=Sum('total_amount'))['total'] or 0
    total_invoices = invoices.count()
    paid_invoices = invoices.filter(status='paid').count()

    # Log activity
    ActivityLog.objects.create(
        user=request.user,
        action=ActivityLog.ActionType.VIEW,
        model_name='Client',
        object_id=str(client.id),
        object_repr=client.full_name,
        ip_address=get_client_ip(request)
    )

    context = {
        'client': client,
        'invoices': invoices[:20],  # Show last 20 invoices
        'total_invoices': total_invoices,
        'total_purchases': total_purchases,
        'paid_invoices': paid_invoices,
    }

    return render(request, 'clients/client_detail.html', context)


@login_required(login_url='login')
@require_http_methods(["GET", "POST"])
def client_create(request):
    """Create a new client"""
    if request.method == 'POST':
        try:
            # Get form data
            first_name = request.POST.get('first_name', '').strip()
            last_name = request.POST.get('last_name', '').strip()
            phone = request.POST.get('phone', '').strip()

            # Validate required fields
            if not first_name or not last_name or not phone:
                messages.error(request, 'Prénom, nom et téléphone sont obligatoires.')
                return render(request, 'clients/client_form.html', {
                    'client_types': Client.ClientType.choices,
                })

            # Create client
            client = Client.objects.create(
                first_name=first_name,
                last_name=last_name,
                first_name_ar=request.POST.get('first_name_ar', '').strip(),
                last_name_ar=request.POST.get('last_name_ar', '').strip(),
                client_type=request.POST.get('client_type', 'regular'),
                phone=phone,
                phone_2=request.POST.get('phone_2', '').strip(),
                email=request.POST.get('email', '').strip(),
                address=request.POST.get('address', '').strip(),
                city=request.POST.get('city', '').strip(),
                cin=request.POST.get('cin', '').strip(),
                preferences=request.POST.get('preferences', '').strip(),
                credit_limit=request.POST.get('credit_limit', 0) or 0,
                notes=request.POST.get('notes', '').strip(),
                is_active=True
            )

            # Log activity
            ActivityLog.objects.create(
                user=request.user,
                action=ActivityLog.ActionType.CREATE,
                model_name='Client',
                object_id=str(client.id),
                object_repr=client.full_name,
                ip_address=get_client_ip(request)
            )

            messages.success(request, f'Client "{client.full_name}" créé avec succès.')
            return redirect('clients:detail', pk=client.pk)

        except Exception as e:
            messages.error(request, f'Erreur lors de la création: {str(e)}')

    context = {
        'client_types': Client.ClientType.choices,
    }
    return render(request, 'clients/client_form.html', context)


@login_required(login_url='login')
@require_http_methods(["GET", "POST"])
def client_edit(request, pk):
    """Edit an existing client"""
    client = get_object_or_404(Client, pk=pk)

    if request.method == 'POST':
        try:
            # Get form data
            first_name = request.POST.get('first_name', '').strip()
            last_name = request.POST.get('last_name', '').strip()
            phone = request.POST.get('phone', '').strip()

            # Validate required fields
            if not first_name or not last_name or not phone:
                messages.error(request, 'Prénom, nom et téléphone sont obligatoires.')
                return render(request, 'clients/client_form.html', {
                    'client': client,
                    'client_types': Client.ClientType.choices,
                    'edit_mode': True,
                })

            # Update client
            client.first_name = first_name
            client.last_name = last_name
            client.first_name_ar = request.POST.get('first_name_ar', '').strip()
            client.last_name_ar = request.POST.get('last_name_ar', '').strip()
            client.client_type = request.POST.get('client_type', 'regular')
            client.phone = phone
            client.phone_2 = request.POST.get('phone_2', '').strip()
            client.email = request.POST.get('email', '').strip()
            client.address = request.POST.get('address', '').strip()
            client.city = request.POST.get('city', '').strip()
            client.cin = request.POST.get('cin', '').strip()
            client.preferences = request.POST.get('preferences', '').strip()
            client.credit_limit = request.POST.get('credit_limit', 0) or 0
            client.notes = request.POST.get('notes', '').strip()
            client.is_active = request.POST.get('is_active') == 'on'
            client.save()

            # Log activity
            ActivityLog.objects.create(
                user=request.user,
                action=ActivityLog.ActionType.UPDATE,
                model_name='Client',
                object_id=str(client.id),
                object_repr=client.full_name,
                ip_address=get_client_ip(request)
            )

            messages.success(request, f'Client "{client.full_name}" modifié avec succès.')
            return redirect('clients:detail', pk=client.pk)

        except Exception as e:
            messages.error(request, f'Erreur lors de la modification: {str(e)}')

    context = {
        'client': client,
        'client_types': Client.ClientType.choices,
        'edit_mode': True,
    }
    return render(request, 'clients/client_form.html', context)


@login_required(login_url='login')
@require_http_methods(["POST"])
def client_delete(request, pk):
    """Delete a client (soft delete by setting inactive)"""
    client = get_object_or_404(Client, pk=pk)

    # Check if client has invoices
    invoice_count = SaleInvoice.objects.filter(client=client, is_deleted=False).count()
    if invoice_count > 0:
        messages.warning(
            request,
            f'Impossible de supprimer ce client car il a {invoice_count} facture(s). '
            f'Le client a été désactivé à la place.'
        )
        client.is_active = False
        client.save()
    else:
        # Log activity before delete
        ActivityLog.objects.create(
            user=request.user,
            action=ActivityLog.ActionType.DELETE,
            model_name='Client',
            object_id=str(client.id),
            object_repr=client.full_name,
            ip_address=get_client_ip(request)
        )
        client.delete()
        messages.success(request, f'Client supprimé avec succès.')

    return redirect('clients:list')


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

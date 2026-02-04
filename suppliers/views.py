"""
Supplier management views for Bijouterie Hafsa ERP
Includes supplier listing, creation, editing, deletion, and detail views
"""
from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required, permission_required
from django.contrib import messages
from django.db.models import Q, Count, Sum
from django.core.paginator import Paginator
from django.views.decorators.http import require_http_methods
from .models import Supplier
from purchases.models import PurchaseInvoice, Consignment
from payments.models import SupplierPayment
from users.models import ActivityLog
from utils import get_client_ip


@login_required(login_url='login')
@require_http_methods(["GET"])
def supplier_list(request):
    """List all suppliers with filtering and search"""
    suppliers = Supplier.objects.all()

    # Search by name or code
    search_query = request.GET.get('search', '')
    if search_query:
        suppliers = suppliers.filter(
            Q(code__icontains=search_query) |
            Q(name__icontains=search_query) |
            Q(name_ar__icontains=search_query) |
            Q(email__icontains=search_query) |
            Q(phone__icontains=search_query)
        )

    # Filter by type
    supplier_type_filter = request.GET.get('type', '')
    if supplier_type_filter:
        suppliers = suppliers.filter(supplier_type=supplier_type_filter)

    # Filter by city
    city_filter = request.GET.get('city', '')
    if city_filter:
        suppliers = suppliers.filter(city=city_filter)

    # Filter by active status
    active_filter = request.GET.get('active', '')
    if active_filter == 'true':
        suppliers = suppliers.filter(is_active=True)
    elif active_filter == 'false':
        suppliers = suppliers.filter(is_active=False)

    # Add related data count
    suppliers = suppliers.annotate(
        purchase_count=Count('purchaseinvoice'),
        payment_count=Count('supplierpayment')
    )

    # Pagination
    paginator = Paginator(suppliers, 20)
    page_number = request.GET.get('page', 1)
    page_obj = paginator.get_page(page_number)

    # Get unique values for filters
    supplier_types = Supplier.SupplierType.choices
    cities = Supplier.objects.values_list('city', flat=True).distinct().exclude(city='')

    context = {
        'page_obj': page_obj,
        'suppliers': page_obj.object_list,
        'search_query': search_query,
        'supplier_types': supplier_types,
        'cities': sorted(cities),
        'current_type': supplier_type_filter,
        'current_city': city_filter,
        'current_active': active_filter,
    }

    return render(request, 'suppliers/supplier_list.html', context)


@login_required(login_url='login')
@require_http_methods(["GET", "POST"])
def supplier_create(request):
    """Create a new supplier"""
    if not request.user.is_staff:
        messages.error(request, 'Vous n\'avez pas la permission d\'ajouter des fournisseurs.')
        return redirect('suppliers:list')

    if request.method == 'POST':
        try:
            # Extract data from form
            name = request.POST.get('name', '').strip()
            name_ar = request.POST.get('name_ar', '').strip()
            supplier_type = request.POST.get('supplier_type', 'other')
            contact_person = request.POST.get('contact_person', '').strip()
            phone = request.POST.get('phone', '').strip()
            phone_2 = request.POST.get('phone_2', '').strip()
            email = request.POST.get('email', '').strip()
            address = request.POST.get('address', '').strip()
            city = request.POST.get('city', '').strip()
            ice = request.POST.get('ice', '').strip()
            rc = request.POST.get('rc', '').strip()
            specialty = request.POST.get('specialty', '').strip()
            credit_limit = request.POST.get('credit_limit', 0)
            payment_terms = request.POST.get('payment_terms', '').strip()
            notes = request.POST.get('notes', '').strip()

            # Validate required fields
            if not name:
                messages.error(request, 'Le nom du fournisseur est obligatoire.')
                return render(request, 'suppliers/supplier_form.html', {
                    'supplier_types': Supplier.SupplierType.choices,
                    'form_data': request.POST,
                })

            # Create supplier - code is auto-generated in save()
            supplier = Supplier(
                name=name,
                name_ar=name_ar,
                supplier_type=supplier_type,
                contact_person=contact_person,
                phone=phone,
                phone_2=phone_2,
                email=email,
                address=address,
                city=city,
                ice=ice,
                rc=rc,
                specialty=specialty,
                credit_limit=float(credit_limit) if credit_limit else 0,
                payment_terms=payment_terms,
                notes=notes,
                is_active=True,
            )
            supplier.save()

            # Log activity
            ActivityLog.objects.create(
                user=request.user,
                action=ActivityLog.ActionType.CREATE,
                model_name='Supplier',
                object_id=str(supplier.id),
                object_repr=supplier.name,
                ip_address=get_client_ip(request)
            )

            messages.success(request, f'Fournisseur "{supplier.name}" créé avec succès.')
            return redirect('suppliers:detail', code=supplier.code)

        except Exception as e:
            messages.error(request, f'Erreur lors de la création: {str(e)}')
            return render(request, 'suppliers/supplier_form.html', {
                'supplier_types': Supplier.SupplierType.choices,
                'form_data': request.POST,
            })

    context = {
        'supplier_types': Supplier.SupplierType.choices,
    }
    return render(request, 'suppliers/supplier_form.html', context)


@login_required(login_url='login')
@require_http_methods(["GET"])
def supplier_detail(request, code):
    """Display supplier details with related transactions"""
    supplier = get_object_or_404(Supplier, code=code)

    # Get related data
    purchases = PurchaseInvoice.objects.filter(supplier=supplier).order_by('-created_at')[:10]
    consignments = Consignment.objects.filter(supplier=supplier).order_by('-created_at')[:5]
    payments = SupplierPayment.objects.filter(supplier=supplier).order_by('-created_at')[:5]

    # Calculate balance
    total_purchases = PurchaseInvoice.objects.filter(supplier=supplier).aggregate(total=Sum('total_amount'))['total'] or 0
    total_payments = SupplierPayment.objects.filter(supplier=supplier).aggregate(total=Sum('amount'))['total'] or 0
    balance = total_purchases - total_payments

    context = {
        'supplier': supplier,
        'purchases': purchases,
        'consignments': consignments,
        'payments': payments,
        'total_purchases': total_purchases,
        'total_payments': total_payments,
        'balance': balance,
        'bank_accounts': supplier.bank_accounts.all(),
    }

    return render(request, 'suppliers/supplier_detail.html', context)


@login_required(login_url='login')
@require_http_methods(["GET", "POST"])
def supplier_edit(request, code):
    """Edit supplier information"""
    supplier = get_object_or_404(Supplier, code=code)

    if not request.user.is_staff:
        messages.error(request, 'Vous n\'avez pas la permission d\'éditer les fournisseurs.')
        return redirect('suppliers:detail', code=code)

    if request.method == 'POST':
        try:
            # Extract data from form
            supplier.name = request.POST.get('name', '').strip()
            supplier.name_ar = request.POST.get('name_ar', '').strip()
            supplier.supplier_type = request.POST.get('supplier_type', 'other')
            supplier.contact_person = request.POST.get('contact_person', '').strip()
            supplier.phone = request.POST.get('phone', '').strip()
            supplier.phone_2 = request.POST.get('phone_2', '').strip()
            supplier.email = request.POST.get('email', '').strip()
            supplier.address = request.POST.get('address', '').strip()
            supplier.city = request.POST.get('city', '').strip()
            supplier.ice = request.POST.get('ice', '').strip()
            supplier.rc = request.POST.get('rc', '').strip()
            supplier.specialty = request.POST.get('specialty', '').strip()
            supplier.credit_limit = float(request.POST.get('credit_limit', 0)) if request.POST.get('credit_limit') else 0
            supplier.payment_terms = request.POST.get('payment_terms', '').strip()
            supplier.notes = request.POST.get('notes', '').strip()
            supplier.is_active = request.POST.get('is_active') == 'on'

            # Validate required fields
            if not supplier.name:
                messages.error(request, 'Le nom du fournisseur est obligatoire.')
                return render(request, 'suppliers/supplier_form.html', {
                    'supplier': supplier,
                    'supplier_types': Supplier.SupplierType.choices,
                })

            supplier.save()

            # Log activity
            ActivityLog.objects.create(
                user=request.user,
                action=ActivityLog.ActionType.UPDATE,
                model_name='Supplier',
                object_id=str(supplier.id),
                object_repr=supplier.name,
                ip_address=get_client_ip(request)
            )

            messages.success(request, f'Fournisseur "{supplier.name}" mis à jour avec succès.')
            return redirect('suppliers:detail', code=code)

        except Exception as e:
            messages.error(request, f'Erreur lors de la mise à jour: {str(e)}')
            return render(request, 'suppliers/supplier_form.html', {
                'supplier': supplier,
                'supplier_types': Supplier.SupplierType.choices,
            })

    context = {
        'supplier': supplier,
        'supplier_types': Supplier.SupplierType.choices,
    }
    return render(request, 'suppliers/supplier_form.html', context)


@login_required(login_url='login')
@require_http_methods(["GET", "POST"])
def supplier_delete(request, code):
    """Delete (soft delete) a supplier"""
    supplier = get_object_or_404(Supplier, code=code)

    if not request.user.is_staff:
        messages.error(request, 'Vous n\'avez pas la permission de supprimer les fournisseurs.')
        return redirect('suppliers:detail', code=code)

    if request.method == 'POST':
        try:
            # Soft delete - just mark as inactive
            supplier.is_active = False
            supplier.save()

            # Log activity
            ActivityLog.objects.create(
                user=request.user,
                action=ActivityLog.ActionType.DELETE,
                model_name='Supplier',
                object_id=str(supplier.id),
                object_repr=supplier.name,
                ip_address=get_client_ip(request)
            )

            messages.success(request, f'Fournisseur "{supplier.name}" désactivé.')
            return redirect('suppliers:list')

        except Exception as e:
            messages.error(request, f'Erreur lors de la suppression: {str(e)}')
            return redirect('suppliers:detail', code=code)

    # GET request - show confirmation
    context = {
        'supplier': supplier,
    }
    return render(request, 'suppliers/supplier_delete.html', context)

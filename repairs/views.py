"""
Repair management views for Bijouterie Hafsa ERP
Handles jewelry repair orders and tracking
"""

from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required, permission_required
from django.utils.timezone import now
from django.db.models import Q, Sum, Count, F, DecimalField, Value
from django.db.models.functions import Coalesce
from datetime import timedelta

from .models import Repair
from users.models import ActivityLog


def get_client_ip(request):
    """Extract client IP from request"""
    x_forwarded_for = request.META.get('HTTP_X_FORWARDED_FOR')
    if x_forwarded_for:
        ip = x_forwarded_for.split(',')[0]
    else:
        ip = request.META.get('REMOTE_ADDR')
    return ip


@login_required
def repair_list(request):
    """List all repairs with filtering"""
    repairs = Repair.objects.select_related(
        'client', 'product', 'repair_type', 'assigned_to'
    ).all()

    # Search by reference or client
    search = request.GET.get('search', '')
    if search:
        repairs = repairs.filter(
            Q(reference__icontains=search) |
            Q(client__first_name__icontains=search) |
            Q(client__last_name__icontains=search)
        )

    # Filter by status
    status = request.GET.get('status', '')
    if status:
        repairs = repairs.filter(status=status)

    # Filter by priority
    priority = request.GET.get('priority', '')
    if priority:
        repairs = repairs.filter(priority=priority)

    # Filter by date range
    date_from = request.GET.get('date_from', '')
    date_to = request.GET.get('date_to', '')
    if date_from:
        repairs = repairs.filter(received_date__gte=date_from)
    if date_to:
        repairs = repairs.filter(received_date__lte=date_to)

    # Statistics
    today = now().date()
    stats = {
        'total': repairs.count(),
        'received': repairs.filter(status='received').count(),
        'in_progress': repairs.filter(status='in_progress').count(),
        'completed': repairs.filter(status='completed').count(),
        'total_cost': repairs.aggregate(
            total=Coalesce(Sum('total_cost_dh'), Value(0), output_field=DecimalField())
        )['total'],
        'overdue': repairs.filter(
            Q(status__in=['received', 'assessing', 'approved', 'in_progress']) &
            Q(estimated_completion_date__lt=today)
        ).count(),
    }

    # Pagination
    from django.core.paginator import Paginator
    paginator = Paginator(repairs.order_by('-received_date', '-created_at'), 20)
    page = request.GET.get('page', 1)
    repairs_page = paginator.get_page(page)

    context = {
        'repairs': repairs_page,
        'search': search,
        'status': status,
        'priority': priority,
        'date_from': date_from,
        'date_to': date_to,
        'stats': stats,
        'status_choices': Repair.Status.choices,
        'priority_choices': Repair.Priority.choices,
    }
    return render(request, 'repairs/repair_list.html', context)


@login_required
@permission_required('repairs.add_repair', raise_exception=True)
def repair_create(request):
    """Create new repair"""
    if request.method == 'POST':
        # Generate reference
        from django.utils import timezone
        today = timezone.now().date()
        today_str = today.strftime('%Y%m%d')
        last_repair = Repair.objects.filter(
            reference__startswith=f'REP-{today_str}'
        ).last()

        if last_repair:
            seq = int(last_repair.reference.split('-')[-1]) + 1
        else:
            seq = 1

        reference = f'REP-{today_str}-{seq:04d}'

        repair = Repair.objects.create(
            reference=reference,
            client_id=request.POST.get('client'),
            product_id=request.POST.get('product') or None,
            item_description=request.POST.get('item_description', ''),
            repair_type_id=request.POST.get('repair_type'),
            issue_description=request.POST.get('issue_description', ''),
            estimated_completion_date=request.POST.get('estimated_completion_date'),
            priority=request.POST.get('priority', 'medium'),
            assigned_to_id=request.POST.get('assigned_to') or None,
        )

        # Log activity
        ActivityLog.objects.create(
            user=request.user,
            action_type=ActivityLog.ActionType.CREATE,
            object_type='Repair',
            object_id=repair.id,
            description=f'Created repair {repair.reference}',
            ip_address=get_client_ip(request)
        )

        return redirect('repairs:repair_detail', reference=repair.reference)

    from clients.models import Client
    from settings_app.models import RepairType
    from suppliers.models import Supplier

    context = {
        'clients': Client.objects.all(),
        'repair_types': RepairType.objects.all(),
        'suppliers': Supplier.objects.all(),
        'priority_choices': Repair.Priority.choices,
    }
    return render(request, 'repairs/repair_form.html', context)


@login_required
def repair_detail(request, reference):
    """View repair details"""
    repair = get_object_or_404(
        Repair.objects.select_related(
            'client', 'product', 'repair_type', 'assigned_to'
        ),
        reference=reference
    )

    # Log view
    ActivityLog.objects.create(
        user=request.user,
        action_type=ActivityLog.ActionType.VIEW,
        object_type='Repair',
        object_id=repair.id,
        description=f'Viewed repair {repair.reference}',
        ip_address=get_client_ip(request)
    )

    # Handle status updates
    if request.method == 'POST' and request.POST.get('action'):
        if request.user.has_perm('repairs.change_repair'):
            action = request.POST.get('action')

            if action == 'approve':
                repair.status = 'approved'
            elif action == 'start':
                repair.status = 'in_progress'
            elif action == 'complete':
                repair.status = 'completed'
                repair.completion_date = now().date()
            elif action == 'deliver':
                repair.status = 'delivered'
                repair.delivery_date = now().date()

            repair.save()

            ActivityLog.objects.create(
                user=request.user,
                action_type=ActivityLog.ActionType.UPDATE,
                object_type='Repair',
                object_id=repair.id,
                description=f'Updated repair {repair.reference} status to {repair.get_status_display()}',
                ip_address=get_client_ip(request)
            )

    # Calculate days overdue
    today = now().date()
    days_overdue = (today - repair.estimated_completion_date).days if repair.estimated_completion_date < today else 0

    context = {
        'repair': repair,
        'days_overdue': max(0, days_overdue),
        'is_overdue': repair.estimated_completion_date < today and repair.status not in ['completed', 'delivered', 'cancelled'],
    }
    return render(request, 'repairs/repair_detail.html', context)


@login_required
def repair_dashboard(request):
    """Repair management dashboard"""
    repairs = Repair.objects.select_related(
        'client', 'repair_type', 'assigned_to'
    ).all()

    today = now().date()
    thirty_days_ago = today - timedelta(days=30)

    # Statistics
    stats = {
        'total': repairs.count(),
        'received': repairs.filter(status='received').count(),
        'assessing': repairs.filter(status='assessing').count(),
        'approved': repairs.filter(status='approved').count(),
        'in_progress': repairs.filter(status='in_progress').count(),
        'completed': repairs.filter(status='completed').count(),
        'delivered': repairs.filter(status='delivered').count(),
        'overdue': repairs.filter(
            Q(status__in=['received', 'assessing', 'approved', 'in_progress']) &
            Q(estimated_completion_date__lt=today)
        ).count(),
        'total_cost': repairs.aggregate(
            total=Coalesce(Sum('total_cost_dh'), Value(0), output_field=DecimalField())
        )['total'],
        'avg_cost': repairs.aggregate(
            avg=Coalesce(
                (Sum('total_cost_dh') * 1.0) / Count('id'),
                Value(0),
                output_field=DecimalField()
            )
        )['avg'],
    }

    # By repair type
    by_type = repairs.values('repair_type__name').annotate(
        count=Count('id'),
        total_cost=Sum('total_cost_dh')
    ).order_by('-count')[:10]

    # By priority
    by_priority = repairs.values('priority').annotate(
        count=Count('id')
    ).order_by('-count')

    # Recent repairs
    recent_repairs = repairs.order_by('-received_date')[:10]

    # Overdue repairs
    overdue_repairs = repairs.filter(
        Q(status__in=['received', 'assessing', 'approved', 'in_progress']) &
        Q(estimated_completion_date__lt=today)
    ).order_by('estimated_completion_date')[:5]

    context = {
        'stats': stats,
        'by_type': by_type,
        'by_priority': by_priority,
        'recent_repairs': recent_repairs,
        'overdue_repairs': overdue_repairs,
    }
    return render(request, 'repairs/repair_dashboard.html', context)

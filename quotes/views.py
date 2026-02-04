"""
Quote management views for Bijouterie Hafsa ERP
Handles customer quotes/estimates
"""

from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required, permission_required
from django.utils.timezone import now
from django.db.models import Q, Sum, Count, F, DecimalField, Value
from django.db.models.functions import Coalesce
from datetime import timedelta

from .models import Quote, QuoteItem
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
def quote_list(request):
    """List all quotes with filtering"""
    quotes = Quote.objects.select_related(
        'client', 'created_by'
    ).prefetch_related('items').all()

    # Search by reference or client
    search = request.GET.get('search', '')
    if search:
        quotes = quotes.filter(
            Q(reference__icontains=search) |
            Q(client__first_name__icontains=search) |
            Q(client__last_name__icontains=search)
        )

    # Filter by status
    status = request.GET.get('status', '')
    if status:
        quotes = quotes.filter(status=status)

    # Filter by date range
    date_from = request.GET.get('date_from', '')
    date_to = request.GET.get('date_to', '')
    if date_from:
        quotes = quotes.filter(issued_date__gte=date_from)
    if date_to:
        quotes = quotes.filter(issued_date__lte=date_to)

    # Statistics
    today = now().date()
    stats = {
        'total': quotes.count(),
        'draft': quotes.filter(status='draft').count(),
        'sent': quotes.filter(status='sent').count(),
        'accepted': quotes.filter(status='accepted').count(),
        'converted': quotes.filter(status='converted').count(),
        'total_amount': quotes.aggregate(
            total=Coalesce(Sum('total_amount_dh'), Value(0), output_field=DecimalField())
        )['total'],
        'pending_response': quotes.filter(
            Q(status__in=['sent', 'accepted']) & Q(valid_until_date__gte=today)
        ).count(),
        'expired': quotes.filter(
            Q(status__in=['sent', 'draft']) & Q(valid_until_date__lt=today)
        ).count(),
    }

    # Pagination
    from django.core.paginator import Paginator
    paginator = Paginator(quotes.order_by('-issued_date', '-created_at'), 20)
    page = request.GET.get('page', 1)
    quotes_page = paginator.get_page(page)

    context = {
        'quotes': quotes_page,
        'search': search,
        'status': status,
        'date_from': date_from,
        'date_to': date_to,
        'stats': stats,
        'status_choices': Quote.Status.choices,
    }
    return render(request, 'quotes/quote_list.html', context)


@login_required
@permission_required('quotes.add_quote', raise_exception=True)
def quote_create(request):
    """Create new quote"""
    if request.method == 'POST':
        # Generate reference
        from django.utils import timezone
        today = timezone.now().date()
        today_str = today.strftime('%Y%m%d')
        last_quote = Quote.objects.filter(
            reference__startswith=f'QT-{today_str}'
        ).last()

        if last_quote:
            seq = int(last_quote.reference.split('-')[-1]) + 1
        else:
            seq = 1

        reference = f'QT-{today_str}-{seq:04d}'

        quote = Quote.objects.create(
            reference=reference,
            client_id=request.POST.get('client'),
            contact_person=request.POST.get('contact_person', ''),
            description=request.POST.get('description', ''),
            subtotal_dh=request.POST.get('subtotal_dh', 0),
            discount_percent=request.POST.get('discount_percent', 0),
            tax_amount_dh=request.POST.get('tax_amount_dh', 0),
            total_amount_dh=request.POST.get('total_amount_dh', 0),
            valid_until_date=request.POST.get('valid_until_date'),
            notes=request.POST.get('notes', ''),
            terms_conditions=request.POST.get('terms_conditions', ''),
            created_by=request.user,
        )

        # Log activity
        ActivityLog.objects.create(
            user=request.user,
            action_type=ActivityLog.ActionType.CREATE,
            object_type='Quote',
            object_id=quote.id,
            description=f'Created quote {quote.reference}',
            ip_address=get_client_ip(request)
        )

        return redirect('quotes:quote_detail', reference=quote.reference)

    from clients.models import Client

    context = {
        'clients': Client.objects.all(),
    }
    return render(request, 'quotes/quote_form.html', context)


@login_required
def quote_detail(request, reference):
    """View quote details"""
    quote = get_object_or_404(
        Quote.objects.select_related(
            'client', 'created_by'
        ).prefetch_related('items'),
        reference=reference
    )

    # Log view
    ActivityLog.objects.create(
        user=request.user,
        action_type=ActivityLog.ActionType.VIEW,
        object_type='Quote',
        object_id=quote.id,
        description=f'Viewed quote {quote.reference}',
        ip_address=get_client_ip(request)
    )

    # Handle status updates
    if request.method == 'POST' and request.POST.get('action'):
        if request.user.has_perm('quotes.change_quote'):
            action = request.POST.get('action')

            if action == 'send':
                quote.status = 'sent'
            elif action == 'accept':
                quote.status = 'accepted'
            elif action == 'reject':
                quote.status = 'rejected'

            quote.save()

            ActivityLog.objects.create(
                user=request.user,
                action_type=ActivityLog.ActionType.UPDATE,
                object_type='Quote',
                object_id=quote.id,
                description=f'Updated quote {quote.reference} status to {quote.get_status_display()}',
                ip_address=get_client_ip(request)
            )

    # Calculate if expired
    today = now().date()
    is_expired = quote.valid_until_date < today

    context = {
        'quote': quote,
        'items': quote.items.all(),
        'is_expired': is_expired,
        'days_until_expiry': (quote.valid_until_date - today).days if not is_expired else 0,
    }
    return render(request, 'quotes/quote_detail.html', context)


@login_required
def quote_dashboard(request):
    """Quote management dashboard"""
    quotes = Quote.objects.select_related(
        'client', 'created_by'
    ).all()

    today = now().date()

    # Statistics
    stats = {
        'total': quotes.count(),
        'draft': quotes.filter(status='draft').count(),
        'sent': quotes.filter(status='sent').count(),
        'accepted': quotes.filter(status='accepted').count(),
        'rejected': quotes.filter(status='rejected').count(),
        'converted': quotes.filter(status='converted').count(),
        'expired': quotes.filter(
            Q(status__in=['sent', 'draft']) & Q(valid_until_date__lt=today)
        ).count(),
        'total_amount': quotes.aggregate(
            total=Coalesce(Sum('total_amount_dh'), Value(0), output_field=DecimalField())
        )['total'],
        'accepted_amount': quotes.filter(status='accepted').aggregate(
            total=Coalesce(Sum('total_amount_dh'), Value(0), output_field=DecimalField())
        )['total'],
        'pending_response': quotes.filter(
            Q(status='sent') & Q(valid_until_date__gte=today)
        ).count(),
    }

    # By status
    by_status = quotes.values('status').annotate(
        count=Count('id'),
        total=Sum('total_amount_dh')
    ).order_by('-count')

    # Recent quotes
    recent_quotes = quotes.order_by('-issued_date')[:10]

    # Expiring soon
    expiring_soon = quotes.filter(
        Q(status__in=['sent', 'draft']) &
        Q(valid_until_date__gte=today) &
        Q(valid_until_date__lte=today + timedelta(days=7))
    ).order_by('valid_until_date')[:5]

    context = {
        'stats': stats,
        'by_status': by_status,
        'recent_quotes': recent_quotes,
        'expiring_soon': expiring_soon,
    }
    return render(request, 'quotes/quote_dashboard.html', context)

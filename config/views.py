"""
Main views for Bijouterie Hafsa ERP
"""
from django.shortcuts import render, redirect
from django.contrib.auth.decorators import login_required
from django.contrib.auth import authenticate, login, logout
from django.views.decorators.http import require_http_methods
from django.contrib import messages
from django.utils import timezone
from django.db.models import Sum, Count
from datetime import timedelta
from decimal import Decimal
from users.models import ActivityLog
from sales.models import SaleInvoice
from products.models import Product
from suppliers.models import Supplier
from repairs.models import Repair
from clients.models import Client


@require_http_methods(["GET", "POST"])
def login_view(request):
    """User login view"""
    if request.user.is_authenticated:
        return redirect('dashboard')

    if request.method == 'POST':
        username = request.POST.get('username')
        password = request.POST.get('password')

        user = authenticate(request, username=username, password=password)
        if user is not None:
            login(request, user)

            # Log activity
            ActivityLog.objects.create(
                user=user,
                action='login',
                ip_address=get_client_ip(request)
            )

            next_url = request.GET.get('next', 'dashboard')
            return redirect(next_url)
        else:
            messages.error(request, 'Nom d\'utilisateur ou mot de passe invalide.')

    return render(request, 'login.html')


@login_required(login_url='login')
def logout_view(request):
    """User logout view"""
    user = request.user
    logout(request)

    # Log activity
    ActivityLog.objects.create(
        user=user,
        action='logout',
        ip_address=get_client_ip(request)
    )

    messages.success(request, 'Vous avez été déconnecté avec succès.')
    return redirect('login')


@login_required(login_url='login')
def dashboard(request):
    """Main dashboard view"""
    today = timezone.now().date()
    this_month_start = today.replace(day=1)

    # Get today's sales
    today_sales = SaleInvoice.objects.filter(date=today)
    today_sales_amount = today_sales.aggregate(total=Sum('total_amount'))['total'] or Decimal('0')
    today_sales_count = today_sales.count()

    # Get this month's revenue
    month_sales = SaleInvoice.objects.filter(date__gte=this_month_start)
    month_revenue = month_sales.aggregate(total=Sum('total_amount'))['total'] or Decimal('0')

    # Get stock data
    total_products = Product.objects.count()

    # Get clients
    total_clients = Client.objects.count()

    # Get suppliers
    total_suppliers = Supplier.objects.count()

    # Get repairs in progress
    repairs_in_progress = Repair.objects.exclude(
        status__in=['completed', 'delivered', 'cancelled']
    ).count()

    # Get recent sales
    recent_sales = SaleInvoice.objects.select_related('client').order_by('-created_at')[:5]

    # Get recent activities
    recent_activities = ActivityLog.objects.select_related('user').order_by('-created_at')[:10]

    # Get live gold price in MAD (lazy import to avoid startup issues)
    gold_prices = None
    try:
        from utils import get_gold_price_mad
        gold_prices = get_gold_price_mad()
    except Exception:
        pass  # Gold prices will be None if fetch fails

    context = {
        'page_title': 'Tableau de Bord',
        # KPI Cards
        'today_sales_amount': today_sales_amount,
        'today_sales_count': today_sales_count,
        'total_stock': total_products,
        'total_clients': total_clients,
        'month_revenue': month_revenue,
        # Statistics
        'total_products': total_products,
        'total_suppliers': total_suppliers,
        'repairs_in_progress': repairs_in_progress,
        # Recent data
        'recent_sales': recent_sales,
        'activities': recent_activities,
        # Gold prices
        'gold_prices': gold_prices,
    }
    return render(request, 'dashboard.html', context)


def get_client_ip(request):
    """Get client IP address from request"""
    x_forwarded_for = request.META.get('HTTP_X_FORWARDED_FOR')
    if x_forwarded_for:
        ip = x_forwarded_for.split(',')[0]
    else:
        ip = request.META.get('REMOTE_ADDR')
    return ip

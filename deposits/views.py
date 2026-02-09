"""
Views for Client Deposit Fund management
"""
from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.db import transaction
from django.db.models import Q, Sum
from django.core.paginator import Paginator
from django.http import JsonResponse
from decimal import Decimal, InvalidOperation

from .models import DepositAccount, DepositTransaction
from clients.models import Client
from settings_app.models import PaymentMethod, BankAccount
from products.models import Product
from sales.models import SaleInvoice, SaleInvoiceItem


@login_required
def deposit_list(request):
    """List all deposit accounts with search and filters"""
    accounts = DepositAccount.objects.select_related('client').all()

    # Search
    search_query = request.GET.get('search', '')
    if search_query:
        accounts = accounts.filter(
            Q(client__first_name__icontains=search_query) |
            Q(client__last_name__icontains=search_query) |
            Q(client__phone__icontains=search_query) |
            Q(client__code__icontains=search_query)
        )

    # Status filter
    status_filter = request.GET.get('status', '')
    if status_filter == 'active':
        accounts = accounts.filter(is_active=True)
    elif status_filter == 'inactive':
        accounts = accounts.filter(is_active=False)

    # Balance filter
    balance_filter = request.GET.get('balance', '')

    # Get all accounts first, then filter by balance in Python
    # (since balance is a property, not a database field)
    accounts_list = list(accounts)

    if balance_filter == 'positive':
        accounts_list = [a for a in accounts_list if a.balance > 0]
    elif balance_filter == 'zero':
        accounts_list = [a for a in accounts_list if a.balance == 0]

    # Statistics
    total_accounts = len(accounts_list)
    active_accounts = len([a for a in accounts_list if a.is_active])
    total_balance = sum(a.balance for a in accounts_list)

    # Pagination
    paginator = Paginator(accounts_list, 20)
    page_number = request.GET.get('page', 1)
    page_obj = paginator.get_page(page_number)

    context = {
        'accounts': page_obj,
        'page_obj': page_obj,
        'search_query': search_query,
        'status_filter': status_filter,
        'balance_filter': balance_filter,
        'total_accounts': total_accounts,
        'active_accounts': active_accounts,
        'total_balance': total_balance,
    }
    return render(request, 'deposits/deposit_list.html', context)


@login_required
def deposit_detail(request, pk):
    """View deposit account details and transaction history"""
    account = get_object_or_404(
        DepositAccount.objects.select_related('client', 'created_by'),
        pk=pk
    )

    # Get transactions with pagination
    transactions = account.transactions.select_related(
        'created_by', 'payment_method', 'invoice', 'product'
    ).order_by('-created_at')

    # Filter transactions
    trans_type = request.GET.get('type', '')
    if trans_type:
        transactions = transactions.filter(transaction_type=trans_type)

    paginator = Paginator(transactions, 20)
    page_number = request.GET.get('page', 1)
    page_obj = paginator.get_page(page_number)

    # Get payment methods for add fund form
    payment_methods = PaymentMethod.objects.filter(is_active=True)
    bank_accounts = BankAccount.objects.filter(is_active=True)

    context = {
        'account': account,
        'transactions': page_obj,
        'page_obj': page_obj,
        'trans_type': trans_type,
        'transaction_types': DepositTransaction.TransactionType.choices,
        'payment_methods': payment_methods,
        'bank_accounts': bank_accounts,
    }
    return render(request, 'deposits/deposit_detail.html', context)


@login_required
def deposit_create(request):
    """Create a new deposit account for a client"""
    if request.method == 'POST':
        client_id = request.POST.get('client')
        notes = request.POST.get('notes', '')
        initial_amount = request.POST.get('initial_amount', '0')
        payment_method_id = request.POST.get('payment_method')
        bank_account_id = request.POST.get('bank_account')
        payment_reference = request.POST.get('payment_reference', '')

        try:
            client = Client.objects.get(pk=client_id)
        except Client.DoesNotExist:
            messages.error(request, 'Client non trouvé.')
            return redirect('deposits:create')

        # Check if client already has a deposit account
        if hasattr(client, 'deposit_account'):
            messages.warning(request, f'{client.full_name} a déjà un compte dépôt.')
            return redirect('deposits:detail', pk=client.deposit_account.pk)

        try:
            initial_amount = Decimal(initial_amount) if initial_amount else Decimal('0')
        except InvalidOperation:
            initial_amount = Decimal('0')

        with transaction.atomic():
            # Create deposit account
            account = DepositAccount.objects.create(
                client=client,
                notes=notes,
                created_by=request.user
            )

            # Create initial deposit transaction if amount > 0
            if initial_amount > 0:
                payment_method = None
                bank_account = None

                if payment_method_id:
                    try:
                        payment_method = PaymentMethod.objects.get(pk=payment_method_id)
                    except PaymentMethod.DoesNotExist:
                        pass

                if bank_account_id:
                    try:
                        bank_account = BankAccount.objects.get(pk=bank_account_id)
                    except BankAccount.DoesNotExist:
                        pass

                DepositTransaction.objects.create(
                    account=account,
                    transaction_type=DepositTransaction.TransactionType.DEPOSIT,
                    amount=initial_amount,
                    payment_method=payment_method,
                    bank_account=bank_account,
                    payment_reference=payment_reference,
                    description='Dépôt initial',
                    created_by=request.user
                )

        messages.success(request, f'Compte dépôt créé pour {client.full_name}.')
        return redirect('deposits:detail', pk=account.pk)

    # GET request
    # Get clients without deposit accounts
    clients_with_deposits = DepositAccount.objects.values_list('client_id', flat=True)
    clients = Client.objects.filter(is_active=True).exclude(pk__in=clients_with_deposits)
    payment_methods = PaymentMethod.objects.filter(is_active=True)
    bank_accounts = BankAccount.objects.filter(is_active=True)

    context = {
        'clients': clients,
        'payment_methods': payment_methods,
        'bank_accounts': bank_accounts,
    }
    return render(request, 'deposits/deposit_form.html', context)


@login_required
def add_fund(request, pk):
    """Add funds to a deposit account"""
    account = get_object_or_404(DepositAccount, pk=pk)

    if request.method == 'POST':
        amount = request.POST.get('amount', '0')
        payment_method_id = request.POST.get('payment_method')
        bank_account_id = request.POST.get('bank_account')
        payment_reference = request.POST.get('payment_reference', '')
        description = request.POST.get('description', '')
        notes = request.POST.get('notes', '')

        try:
            amount = Decimal(amount)
            if amount <= 0:
                messages.error(request, 'Le montant doit être positif.')
                return redirect('deposits:detail', pk=pk)
        except InvalidOperation:
            messages.error(request, 'Montant invalide.')
            return redirect('deposits:detail', pk=pk)

        payment_method = None
        bank_account = None

        if payment_method_id:
            try:
                payment_method = PaymentMethod.objects.get(pk=payment_method_id)
            except PaymentMethod.DoesNotExist:
                pass

        if bank_account_id:
            try:
                bank_account = BankAccount.objects.get(pk=bank_account_id)
            except BankAccount.DoesNotExist:
                pass

        DepositTransaction.objects.create(
            account=account,
            transaction_type=DepositTransaction.TransactionType.DEPOSIT,
            amount=amount,
            payment_method=payment_method,
            bank_account=bank_account,
            payment_reference=payment_reference,
            description=description or 'Dépôt de fonds',
            notes=notes,
            created_by=request.user
        )

        messages.success(request, f'{amount} DH ajouté au compte de {account.client.full_name}.')
        return redirect('deposits:detail', pk=pk)

    return redirect('deposits:detail', pk=pk)


@login_required
def withdrawal(request, pk):
    """Withdraw funds from a deposit account (refund to client)"""
    account = get_object_or_404(DepositAccount, pk=pk)

    if request.method == 'POST':
        amount = request.POST.get('amount', '0')
        description = request.POST.get('description', '')
        notes = request.POST.get('notes', '')

        try:
            amount = Decimal(amount)
            if amount <= 0:
                messages.error(request, 'Le montant doit être positif.')
                return redirect('deposits:detail', pk=pk)
        except InvalidOperation:
            messages.error(request, 'Montant invalide.')
            return redirect('deposits:detail', pk=pk)

        if amount > account.balance:
            messages.error(request, f'Solde insuffisant. Solde actuel: {account.balance} DH')
            return redirect('deposits:detail', pk=pk)

        DepositTransaction.objects.create(
            account=account,
            transaction_type=DepositTransaction.TransactionType.WITHDRAWAL,
            amount=-amount,  # Negative for withdrawal
            description=description or 'Retrait de fonds',
            notes=notes,
            created_by=request.user
        )

        messages.success(request, f'{amount} DH retiré du compte de {account.client.full_name}.')
        return redirect('deposits:detail', pk=pk)

    return redirect('deposits:detail', pk=pk)


@login_required
def purchase_page(request, pk):
    """Page for making a purchase using deposit funds"""
    account = get_object_or_404(
        DepositAccount.objects.select_related('client'),
        pk=pk
    )

    # Get available products
    products = Product.objects.filter(status='available').order_by('-created_at')

    # Search products
    search_query = request.GET.get('search', '')
    if search_query:
        products = products.filter(
            Q(reference__icontains=search_query) |
            Q(description__icontains=search_query) |
            Q(category__name__icontains=search_query)
        )

    # Category filter
    category_id = request.GET.get('category', '')
    if category_id:
        products = products.filter(category_id=category_id)

    # Pagination
    paginator = Paginator(products, 20)
    page_number = request.GET.get('page', 1)
    page_obj = paginator.get_page(page_number)

    # Get categories for filter
    from settings_app.models import ProductCategory
    categories = ProductCategory.objects.filter(is_active=True)

    # Payment methods for additional payment
    payment_methods = PaymentMethod.objects.filter(is_active=True)
    bank_accounts = BankAccount.objects.filter(is_active=True)

    context = {
        'account': account,
        'products': page_obj,
        'page_obj': page_obj,
        'search_query': search_query,
        'category_id': category_id,
        'categories': categories,
        'payment_methods': payment_methods,
        'bank_accounts': bank_accounts,
    }
    return render(request, 'deposits/purchase_page.html', context)


@login_required
def make_purchase(request, pk):
    """Process a purchase using deposit funds (and optionally additional payment)"""
    account = get_object_or_404(DepositAccount, pk=pk)

    if request.method != 'POST':
        return redirect('deposits:purchase', pk=pk)

    # Get selected products
    product_ids = request.POST.getlist('products')
    if not product_ids:
        messages.error(request, 'Veuillez sélectionner au moins un produit.')
        return redirect('deposits:purchase', pk=pk)

    # Get payment details
    use_deposit = request.POST.get('use_deposit', '0')
    additional_payment = request.POST.get('additional_payment', '0')
    payment_method_id = request.POST.get('payment_method')
    bank_account_id = request.POST.get('bank_account')
    payment_reference = request.POST.get('payment_reference', '')
    notes = request.POST.get('notes', '')

    try:
        use_deposit = Decimal(use_deposit)
        additional_payment = Decimal(additional_payment)
    except InvalidOperation:
        messages.error(request, 'Montant invalide.')
        return redirect('deposits:purchase', pk=pk)

    # Get products
    products = Product.objects.filter(pk__in=product_ids, status='available')
    if not products.exists():
        messages.error(request, 'Produits non disponibles.')
        return redirect('deposits:purchase', pk=pk)

    # Calculate total with custom prices
    total_amount = Decimal('0')
    product_prices = {}  # Store custom prices for each product

    for product in products:
        # Check if custom selling price was provided
        custom_price_key = f'selling_price_{product.pk}'
        custom_price = request.POST.get(custom_price_key)

        if custom_price:
            try:
                price = Decimal(custom_price)
            except InvalidOperation:
                price = product.selling_price
        else:
            price = product.selling_price

        product_prices[product.pk] = price
        total_amount += price

    # Validate amounts
    if use_deposit > account.balance:
        messages.error(request, f'Montant dépôt supérieur au solde. Solde: {account.balance} DH')
        return redirect('deposits:purchase', pk=pk)

    total_payment = use_deposit + additional_payment
    if total_payment < total_amount:
        messages.error(request, f'Paiement insuffisant. Total: {total_amount} DH, Paiement: {total_payment} DH')
        return redirect('deposits:purchase', pk=pk)

    # Get payment method for additional payment
    payment_method = None
    bank_account = None

    if payment_method_id and additional_payment > 0:
        try:
            payment_method = PaymentMethod.objects.get(pk=payment_method_id)
        except PaymentMethod.DoesNotExist:
            pass

    if bank_account_id and additional_payment > 0:
        try:
            bank_account = BankAccount.objects.get(pk=bank_account_id)
        except BankAccount.DoesNotExist:
            pass

    with transaction.atomic():
        # Create invoice
        invoice = SaleInvoice.objects.create(
            client=account.client,
            total_amount=total_amount,
            paid_amount=total_payment,
            status='paid' if total_payment >= total_amount else 'partial',
            notes=f'Achat via dépôt client. {notes}',
            created_by=request.user
        )

        # Add invoice items
        for product in products:
            # Use custom price if available, otherwise use product's selling price
            item_price = product_prices.get(product.pk, product.selling_price)

            SaleInvoiceItem.objects.create(
                invoice=invoice,
                product=product,
                quantity=1,
                unit_price=item_price,
                total_price=item_price
            )
            # Mark product as sold
            product.status = 'sold'
            product.save()

        # Create deposit transaction (purchase deduction)
        if use_deposit > 0:
            DepositTransaction.objects.create(
                account=account,
                transaction_type=DepositTransaction.TransactionType.PURCHASE,
                amount=-use_deposit,  # Negative for purchase
                invoice=invoice,
                description=f'Achat facture {invoice.reference}',
                notes=notes,
                created_by=request.user
            )

        # Record additional payment in invoice payments if any
        if additional_payment > 0 and payment_method:
            from sales.models import InvoicePayment
            InvoicePayment.objects.create(
                invoice=invoice,
                amount=additional_payment,
                payment_method=payment_method,
                bank_account=bank_account,
                reference=payment_reference,
                notes='Paiement complémentaire (achat via dépôt)',
                created_by=request.user
            )

    messages.success(request, f'Achat effectué. Facture: {invoice.reference}')
    return redirect('deposits:detail', pk=pk)


@login_required
def adjustment(request, pk):
    """Make an adjustment to the deposit account (admin correction)"""
    account = get_object_or_404(DepositAccount, pk=pk)

    if request.method == 'POST':
        amount = request.POST.get('amount', '0')
        adjustment_type = request.POST.get('adjustment_type', 'add')  # 'add' or 'subtract'
        description = request.POST.get('description', '')
        notes = request.POST.get('notes', '')

        try:
            amount = Decimal(amount)
            if amount <= 0:
                messages.error(request, 'Le montant doit être positif.')
                return redirect('deposits:detail', pk=pk)
        except InvalidOperation:
            messages.error(request, 'Montant invalide.')
            return redirect('deposits:detail', pk=pk)

        # Make negative if subtracting
        if adjustment_type == 'subtract':
            if amount > account.balance:
                messages.error(request, f'Solde insuffisant pour cette correction. Solde: {account.balance} DH')
                return redirect('deposits:detail', pk=pk)
            amount = -amount

        DepositTransaction.objects.create(
            account=account,
            transaction_type=DepositTransaction.TransactionType.ADJUSTMENT,
            amount=amount,
            description=description or 'Ajustement manuel',
            notes=notes,
            created_by=request.user
        )

        messages.success(request, f'Ajustement effectué sur le compte de {account.client.full_name}.')
        return redirect('deposits:detail', pk=pk)

    return redirect('deposits:detail', pk=pk)


# API endpoints for AJAX
@login_required
def api_client_balance(request, client_id):
    """API endpoint to get client deposit balance"""
    try:
        client = Client.objects.get(pk=client_id)
        if hasattr(client, 'deposit_account'):
            return JsonResponse({
                'has_account': True,
                'account_id': client.deposit_account.pk,
                'balance': float(client.deposit_account.balance),
                'is_active': client.deposit_account.is_active
            })
        else:
            return JsonResponse({
                'has_account': False,
                'balance': 0
            })
    except Client.DoesNotExist:
        return JsonResponse({'error': 'Client not found'}, status=404)


@login_required
def api_product_info(request, product_id):
    """API endpoint to get product info"""
    try:
        product = Product.objects.get(pk=product_id)
        return JsonResponse({
            'id': product.pk,
            'reference': product.reference,
            'description': product.description or '',
            'selling_price': float(product.selling_price),
            'status': product.status,
            'category': product.category.name if product.category else ''
        })
    except Product.DoesNotExist:
        return JsonResponse({'error': 'Product not found'}, status=404)

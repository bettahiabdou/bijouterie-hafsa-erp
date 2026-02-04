# 📋 SALES APPLICATION - REMAINING WORK PLAN

**Current Status:** Phase 1 Complete (Models & Forms) ✅
**Next Phases:** 2-5 (Endpoints, Logic, Config, Testing)

---

## PHASE 2: MISSING ENDPOINTS & VIEWS

### Priority: HIGH

#### 2.1 Invoice Edit Endpoint
**File:** `sales/views.py` (new function)
**URL:** `invoices/<str:reference>/edit/`

```python
@login_required
@require_http_methods(["GET", "POST"])
def invoice_edit(request, reference):
    """Edit existing invoice"""
    # Only allow editing of DRAFT invoices
    invoice = get_object_or_404(SaleInvoice, reference=reference)

    # Check status - only draft can be edited
    if invoice.status != SaleInvoice.Status.DRAFT:
        messages.error(request, 'Seuls les brouillons peuvent être édités.')
        return redirect('sales:invoice_detail', reference=reference)

    # Check permissions
    if request.user != invoice.created_by and not request.user.is_staff:
        messages.error(request, 'Vous n\'avez pas la permission d\'éditer cette facture.')
        return redirect('sales:invoice_detail', reference=reference)

    if request.method == 'POST':
        form = SaleInvoiceForm(request.POST, instance=invoice)
        if form.is_valid():
            form.save()
            invoice.calculate_totals()

            ActivityLog.objects.create(
                user=request.user,
                action=ActivityLog.ActionType.UPDATE,
                model_name='SaleInvoice',
                object_id=str(invoice.id),
                object_repr=invoice.reference,
                ip_address=get_client_ip(request)
            )

            messages.success(request, 'Facture mise à jour avec succès.')
            return redirect('sales:invoice_detail', reference=reference)
    else:
        form = SaleInvoiceForm(instance=invoice)

    context = {
        'invoice': invoice,
        'form': form,
    }
    return render(request, 'sales/invoice_edit.html', context)
```

---

#### 2.2 Invoice Delete Endpoint
**File:** `sales/views.py` (new function)
**URL:** `invoices/<str:reference>/delete/`

```python
@login_required
@require_http_methods(["GET", "POST"])
def invoice_delete(request, reference):
    """Delete (soft delete) invoice"""
    invoice = get_object_or_404(SaleInvoice, reference=reference)

    # Only allow deleting DRAFT invoices
    if invoice.status != SaleInvoice.Status.DRAFT:
        messages.error(request, 'Seules les factures brouillons peuvent être supprimées.')
        return redirect('sales:invoice_detail', reference=reference)

    if request.method == 'POST':
        # Soft delete - mark items as draft and reset product status
        for item in invoice.items.all():
            item.product.status = 'available'
            item.product.save(update_fields=['status'])

        invoice.status = SaleInvoice.Status.CANCELLED
        invoice.save(update_fields=['status'])

        ActivityLog.objects.create(
            user=request.user,
            action=ActivityLog.ActionType.DELETE,
            model_name='SaleInvoice',
            object_id=str(invoice.id),
            object_repr=invoice.reference,
            ip_address=get_client_ip(request)
        )

        messages.success(request, 'Facture supprimée.')
        return redirect('sales:invoice_list')

    context = {'invoice': invoice}
    return render(request, 'sales/invoice_delete.html', context)
```

---

#### 2.3 Payment Recording Endpoint
**File:** `sales/views.py` (new function)
**URL:** `invoices/<str:reference>/payment/`

```python
@login_required
@require_http_methods(["GET", "POST"])
def invoice_payment(request, reference):
    """Record payment for invoice"""
    from .forms import PaymentForm
    from payments.models import ClientPayment

    invoice = get_object_or_404(SaleInvoice, reference=reference)

    if request.method == 'POST':
        form = PaymentForm(request.POST)
        if form.is_valid():
            amount = form.cleaned_data['amount']

            # Validate amount doesn't exceed balance
            if amount > invoice.balance_due:
                messages.error(request, f'Le paiement ne peut pas dépasser le solde dû ({invoice.balance_due} DH)')
            else:
                # Create payment record
                payment = ClientPayment.objects.create(
                    client=invoice.client,
                    invoice=invoice,
                    amount=amount,
                    payment_method=form.cleaned_data['payment_method'],
                    bank_account=form.cleaned_data.get('bank_account'),
                    notes=form.cleaned_data.get('notes', ''),
                    created_by=request.user
                )

                # Update invoice
                invoice.update_payment(amount)

                # Log activity
                ActivityLog.objects.create(
                    user=request.user,
                    action=ActivityLog.ActionType.CREATE,
                    model_name='ClientPayment',
                    object_id=str(payment.id),
                    object_repr=f'{invoice.reference} - {amount} DH',
                    ip_address=get_client_ip(request)
                )

                messages.success(request, f'Paiement de {amount} DH enregistré.')
                return redirect('sales:invoice_detail', reference=reference)
    else:
        form = PaymentForm()

    context = {
        'invoice': invoice,
        'form': form,
        'remaining': invoice.balance_due,
    }
    return render(request, 'sales/invoice_payment.html', context)
```

---

#### 2.4 Delivery Update Endpoint
**File:** `sales/views.py` (new function)
**URL:** `invoices/<str:reference>/delivery/`

```python
@login_required
@require_http_methods(["GET", "POST"])
def invoice_delivery(request, reference):
    """Update delivery information"""
    from .forms import DeliveryForm

    invoice = get_object_or_404(SaleInvoice, reference=reference)

    if request.method == 'POST':
        form = DeliveryForm(request.POST, instance=invoice)
        if form.is_valid():
            form.save()

            # Update status if delivered
            if form.cleaned_data['delivery_status'] == 'delivered':
                invoice.delivery_date = timezone.now().date()
                invoice.update_status()

            ActivityLog.objects.create(
                user=request.user,
                action=ActivityLog.ActionType.UPDATE,
                model_name='SaleInvoice',
                object_id=str(invoice.id),
                object_repr=f'{invoice.reference} - Livraison',
                ip_address=get_client_ip(request)
            )

            messages.success(request, 'Informations de livraison mises à jour.')
            return redirect('sales:invoice_detail', reference=reference)
    else:
        form = DeliveryForm(instance=invoice)

    context = {
        'invoice': invoice,
        'form': form,
    }
    return render(request, 'sales/invoice_delivery.html', context)
```

---

#### 2.5 Invoice Export Endpoints
**File:** `sales/views.py` (new functions)
**URLs:**
- `invoices/<str:reference>/export-pdf/`
- `invoices/<str:reference>/print/`

Requires: `reportlab`, `weasyprint` or similar PDF library

```python
@login_required
def invoice_export_pdf(request, reference):
    """Export invoice as PDF"""
    invoice = get_object_or_404(SaleInvoice, reference=reference)

    # Generate PDF using reportlab or weasyprint
    # Return as downloadable PDF file
    # Format: Invoice_<reference>_<date>.pdf
    pass

@login_required
def invoice_print(request, reference):
    """Print-friendly invoice view"""
    invoice = get_object_or_404(SaleInvoice, reference=reference)
    # Render invoice_print.html template
    # CSS optimized for printing
    pass
```

---

#### 2.6 Loan Management Endpoints
**File:** `sales/views.py` (new functions)
**URLs:**
- `loans/` - List loans
- `loans/create/` - Create new loan
- `loans/<id>/detail/` - View loan
- `loans/<id>/return/` - Return loaned items

Needs: ClientLoanForm template and workflow

---

#### 2.7 Layaway Management Endpoints
**File:** `sales/views.py` (new functions)
**URLs:**
- `layaways/` - List layaways
- `layaways/create/` - Create layaway
- `layaways/<id>/detail/` - View layaway
- `layaways/<id>/payment/` - Record payment
- `layaways/<id>/complete/` - Complete and convert to sale

---

## PHASE 3: BUSINESS LOGIC & VALIDATION

### Priority: HIGH

#### 3.1 Implement Soft Delete for SaleInvoice
**File:** `sales/models.py`

Add field:
```python
is_deleted = models.BooleanField(_('Supprimé'), default=False)

class Meta:
    ordering = ['-date']
    indexes = [
        models.Index(fields=['is_deleted', '-date']),
    ]
```

Update queries:
```python
# In all views, add filter:
invoices = SaleInvoice.objects.filter(is_deleted=False)
```

---

#### 3.2 Status Transition Validation
**File:** `sales/models.py`

Add method:
```python
def can_transition_to(self, new_status):
    """Validate status transition"""
    valid_transitions = {
        'draft': ['confirmed', 'cancelled'],
        'confirmed': ['partial', 'paid', 'delivered', 'cancelled'],
        'partial': ['paid', 'delivered', 'cancelled'],
        'paid': ['delivered'],
        'delivered': [],
        'cancelled': [],
    }
    return new_status in valid_transitions.get(self.status, [])

def transition_to(self, new_status):
    """Change status with validation"""
    if not self.can_transition_to(new_status):
        raise ValidationError(f'Cannot transition from {self.status} to {new_status}')
    self.status = new_status
    self.save(update_fields=['status'])
```

---

#### 3.3 Optimize Client.current_balance Property
**File:** `clients/models.py`

Problem: Property calculates from scratch every time

Solution: Add caching
```python
from django.core.cache import cache

@property
def current_balance(self):
    """Get cached current balance"""
    cache_key = f'client_balance_{self.id}'
    balance = cache.get(cache_key)

    if balance is None:
        total_sales = SaleInvoice.objects.filter(
            client=self, is_deleted=False
        ).aggregate(total=Sum('total_amount'))['total'] or 0

        total_payments = ClientPayment.objects.filter(
            client=self
        ).aggregate(total=Sum('amount'))['total'] or 0

        balance = total_sales - total_payments
        cache.set(cache_key, balance, 3600)  # Cache 1 hour

    return balance

# Add invalidation on payment creation:
# In ClientPayment.save():
cache.delete(f'client_balance_{self.client.id}')
```

---

## PHASE 4: CONFIGURATION MANAGEMENT

### Priority: MEDIUM

#### 4.1 Update CompanySettings Model
**File:** `settings_app/models.py`

Add fields:
```python
# In CompanySettings class:

# Tax configuration
default_tax_rate = models.DecimalField(
    _('Taux TVA par défaut (%)'),
    max_digits=5,
    decimal_places=2,
    default=20  # Morocco default
)

tax_method = models.CharField(
    _('Mode de calcul TVA'),
    max_length=20,
    choices=[('percentage', 'Pourcentage'), ('fixed', 'Montant fixe')],
    default='percentage'
)

tax_apply_on_delivery = models.BooleanField(
    _('Appliquer TVA sur livraison'),
    default=True
)

# Payment configuration
default_payment_method = models.ForeignKey(
    PaymentMethod,
    on_delete=models.SET_NULL,
    null=True,
    blank=True,
    related_name='default_for_company',
    verbose_name=_('Méthode de paiement par défaut')
)

default_bank_account = models.ForeignKey(
    BankAccount,
    on_delete=models.SET_NULL,
    null=True,
    blank=True,
    related_name='default_for_company',
    verbose_name=_('Compte bancaire par défaut')
)

# Delivery configuration
default_delivery_method = models.ForeignKey(
    DeliveryMethod,
    on_delete=models.SET_NULL,
    null=True,
    blank=True,
    related_name='default_for_company',
    verbose_name=_('Mode de livraison par défaut')
)
```

#### 4.2 Use Settings in Views

Replace hardcoded values:
```python
# OLD:
invoice.tax_rate = 20

# NEW:
from settings_app.models import CompanySettings
settings = CompanySettings.objects.first()
invoice.tax_rate = settings.default_tax_rate if settings else 20
```

---

## PHASE 5: TEMPLATES

### Required Templates

#### 5.1 `invoice_edit.html`
- Similar to invoice_form.html
- Only show for DRAFT invoices
- Allow modifying all fields except items (edit separately)

#### 5.2 `invoice_delete.html`
- Confirmation page
- Show invoice details
- List items to be deleted
- Warn about product status reset

#### 5.3 `invoice_payment.html`
- Show invoice details
- Display remaining balance
- Payment form with amount/method/date
- Payment history table

#### 5.4 `invoice_delivery.html`
- Delivery address form
- Method/person selection
- Delivery status tracker
- Expected delivery date

#### 5.5 `invoice_print.html`
- Professional print layout
- No navigation/sidebars
- Optimized for A4 paper
- Include company logo
- QR code for reference

#### 5.6 Loan & Layaway Templates
- `loan_list.html` - List all client loans
- `loan_detail.html` - View specific loan with return tracking
- `layaway_list.html` - List all layaways
- `layaway_detail.html` - View with payment schedule

---

## PHASE 6: TESTING

### Test Coverage Needed

#### Unit Tests
```python
# tests/test_models.py
class SaleInvoiceItemTestCase(TestCase):
    def test_quantity_calculation(self):
        """Test total_amount includes quantity"""
        item = SaleInvoiceItem.objects.create(
            quantity=2,
            unit_price=100,
            discount_amount=20,
        )
        self.assertEqual(item.total_amount, 180)  # (100*2) - 20

class SaleInvoiceTestCase(TestCase):
    def test_tax_calculation(self):
        """Test tax calculation"""
        invoice = SaleInvoice(
            tax_rate=20,
            subtotal=1000,
        )
        invoice.calculate_totals()
        self.assertEqual(invoice.tax_amount, 200)  # 1000 * 20%

    def test_status_transition_validation(self):
        """Test invalid transitions rejected"""
        invoice = SaleInvoice(status='delivered')
        with self.assertRaises(ValidationError):
            invoice.transition_to('draft')
```

#### Integration Tests
```python
# tests/test_views.py
class InvoiceCreateTestCase(TestCase):
    def test_create_invoice_with_multiple_items(self):
        """Test creating invoice with quantity > 1"""
        # Create with 2 products, quantities 2 and 3
        # Verify totals calculated correctly

    def test_payment_reduces_balance(self):
        """Test payment updates balance_due"""
        # Create invoice
        # Add payment
        # Verify balance_due decreased
```

#### Form Tests
```python
# tests/test_forms.py
class SaleInvoiceFormTestCase(TestCase):
    def test_client_credit_limit_validation(self):
        """Test form rejects over-limit clients"""
        form = SaleInvoiceForm(data={
            'client': over_limit_client.id,
            ...
        })
        self.assertFalse(form.is_valid())
        self.assertIn('credit', str(form.errors))
```

---

## ESTIMATED TIMELINE

| Phase | Task | Estimated Hours |
|-------|------|-----------------|
| 2 | Invoice endpoints (5) | 8-10 hours |
| 2 | Loan/Layaway endpoints (7) | 12-15 hours |
| 3 | Business logic (3 features) | 6-8 hours |
| 4 | Configuration (2 items) | 2-3 hours |
| 5 | Templates (6+ pages) | 6-8 hours |
| 6 | Testing (unit, integration, forms) | 8-10 hours |
| **TOTAL** | **All remaining phases** | **42-54 hours** |

---

## PRIORITY RANKING

**Do First (Core Functionality):**
1. Invoice Edit/Delete endpoints
2. Payment recording endpoint
3. Status transition validation

**Do Next (Important Features):**
4. Delivery update endpoint
5. Loan management endpoints
6. Client balance optimization

**Can Defer (Nice to Have):**
7. Invoice export/print
8. Layaway management
9. Advanced configuration

---

## SUCCESS CRITERIA

After all 5 phases:
- ✅ All CRUD operations work (Create, Read, Update, Delete)
- ✅ Payments can be recorded and tracked
- ✅ Tax properly calculated and displayed
- ✅ Quantity tracking works for multi-item invoices
- ✅ No N+1 queries in any view
- ✅ All forms have proper validation
- ✅ Soft delete prevents data loss
- ✅ Configuration manageable via admin
- ✅ 80%+ code test coverage
- ✅ Performance benchmarks met (<100ms queries)


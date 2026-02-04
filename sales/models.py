"""
Sales models for Bijouterie Hafsa ERP
Includes sales invoices, delivery tracking, and client loans
"""

from django.db import models
from django.utils.translation import gettext_lazy as _
from django.core.validators import MinValueValidator
from decimal import Decimal


class SaleInvoice(models.Model):
    """
    Sales invoice for jewelry sales
    """

    class Status(models.TextChoices):
        DRAFT = 'draft', _('Brouillon')
        UNPAID = 'unpaid', _('Non payée')
        PARTIAL_PAID = 'partial', _('Partiellement payée')
        PAID = 'paid', _('Payée')
        CANCELLED = 'cancelled', _('Annulée')

    class SaleType(models.TextChoices):
        REGULAR = 'regular', _('Vente normale')
        CREDIT = 'credit', _('Vente à crédit')
        LAYAWAY = 'layaway', _('Mise de côté (acompte)')
        CONSIGNMENT = 'consignment', _('Vente consignation')

    # Reference
    reference = models.CharField(
        _('Référence'),
        max_length=50,
        unique=True
    )
    date = models.DateField(_('Date'))
    sale_type = models.CharField(
        _('Type de vente'),
        max_length=20,
        choices=SaleType.choices,
        default=SaleType.REGULAR
    )

    # Client - Optional (can sell without client record for walk-in sales)
    client = models.ForeignKey(
        'clients.Client',
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name='sale_invoices',
        verbose_name=_('Client'),
        help_text=_('Client is optional - can record walk-in or anonymous sales')
    )

    # Status
    status = models.CharField(
        _('Statut'),
        max_length=20,
        choices=Status.choices,
        default=Status.UNPAID
    )

    # Pricing
    subtotal = models.DecimalField(
        _('Sous-total'),
        max_digits=14,
        decimal_places=2,
        default=0
    )

    # Discount
    discount_percent = models.DecimalField(
        _('Remise (%)'),
        max_digits=5,
        decimal_places=2,
        default=0
    )
    discount_amount = models.DecimalField(
        _('Montant remise'),
        max_digits=12,
        decimal_places=2,
        default=0
    )
    discount_approved_by = models.ForeignKey(
        'users.User',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='approved_discounts',
        verbose_name=_('Remise approuvée par')
    )

    # Old gold exchange
    old_gold_amount = models.DecimalField(
        _('Reprise ancien or'),
        max_digits=12,
        decimal_places=2,
        default=0,
        help_text=_('Montant déduit pour ancien or repris')
    )
    old_gold_purchase = models.ForeignKey(
        'clients.OldGoldPurchase',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='applied_to_sales',
        verbose_name=_('Achat ancien or')
    )

    # Tax fields - CRITICAL FIX
    tax_rate = models.DecimalField(
        _('Taux TVA (%)'),
        max_digits=5,
        decimal_places=2,
        default=0,
        help_text=_('Taux de TVA en pourcentage')
    )
    tax_amount = models.DecimalField(
        _('Montant TVA'),
        max_digits=12,
        decimal_places=2,
        default=0
    )

    # Totals
    total_amount = models.DecimalField(
        _('Montant total'),
        max_digits=14,
        decimal_places=2,
        default=0
    )
    amount_paid = models.DecimalField(
        _('Montant payé'),
        max_digits=14,
        decimal_places=2,
        default=0
    )
    balance_due = models.DecimalField(
        _('Solde dû'),
        max_digits=14,
        decimal_places=2,
        default=0
    )

    # Payment method - CRITICAL FIX
    payment_method = models.ForeignKey(
        'settings_app.PaymentMethod',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='sale_invoices',
        verbose_name=_('Méthode de paiement')
    )

    # Bank account for payment - CRITICAL FIX
    bank_account = models.ForeignKey(
        'settings_app.BankAccount',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='sale_invoices',
        verbose_name=_('Compte bancaire')
    )

    # Payment reference (cheque number, bank transfer ref, card number, etc.)
    payment_reference = models.CharField(
        _('Référence de paiement'),
        max_length=100,
        null=True,
        blank=True,
        unique=True,
        help_text=_('N° de chèque, référence virement, n° de carte, etc.')
    )

    # Applied deposit - CRITICAL FIX
    applied_deposit = models.ForeignKey(
        'payments.Deposit',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='applied_to_sales',
        verbose_name=_('Acompte appliqué')
    )

    # Linked quote - CRITICAL FIX
    quote = models.ForeignKey(
        'quotes.Quote',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='converted_sales',
        verbose_name=_('Devis original')
    )

    # Delivery
    delivery_method = models.ForeignKey(
        'settings_app.DeliveryMethod',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        verbose_name=_('Mode de livraison')
    )
    delivery_person = models.ForeignKey(
        'settings_app.DeliveryPerson',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        verbose_name=_('Livreur')
    )
    delivery_address = models.TextField(
        _('Adresse de livraison'),
        blank=True
    )
    delivery_cost = models.DecimalField(
        _('Frais de livraison'),
        max_digits=10,
        decimal_places=2,
        default=0
    )
    delivery_status = models.CharField(
        _('Statut livraison'),
        max_length=20,
        choices=[
            ('pending', _('En attente')),
            ('shipped', _('Expédié')),
            ('in_transit', _('En cours')),
            ('delivered', _('Livré')),
        ],
        default='pending'
    )
    delivery_date = models.DateField(
        _('Date de livraison'),
        null=True,
        blank=True
    )

    # Seller info
    seller = models.ForeignKey(
        'users.User',
        on_delete=models.SET_NULL,
        null=True,
        related_name='sales',
        verbose_name=_('Vendeur')
    )

    # Tracking
    created_by = models.ForeignKey(
        'users.User',
        on_delete=models.SET_NULL,
        null=True,
        related_name='created_sale_invoices',
        verbose_name=_('Créé par')
    )
    notes = models.TextField(_('Notes'), blank=True)
    created_at = models.DateTimeField(_('Créé le'), auto_now_add=True)
    updated_at = models.DateTimeField(_('Modifié le'), auto_now=True)

    # Soft delete field - PHASE 3 FIX
    is_deleted = models.BooleanField(
        _('Supprimé'),
        default=False,
        help_text=_('Marqué comme supprimé (soft delete)')
    )

    class Meta:
        verbose_name = _('Facture de vente')
        verbose_name_plural = _('Factures de vente')
        ordering = ['-date', '-created_at']
        indexes = [
            models.Index(fields=['is_deleted', '-date']),
        ]

    def __str__(self):
        return f"{self.reference} - {self.client.full_name} - {self.total_amount} MAD"

    def calculate_totals(self):
        """Calculate totals from line items"""
        subtotal = self.items.aggregate(
            total=models.Sum('total_amount')
        )['total'] or Decimal('0')

        self.subtotal = subtotal

        # Calculate discount
        if self.discount_percent > 0:
            self.discount_amount = subtotal * (self.discount_percent / 100)

        # FIXED: Calculate tax on subtotal after discount
        after_discount = subtotal - self.discount_amount
        if self.tax_rate > 0:
            self.tax_amount = after_discount * (self.tax_rate / 100)
        else:
            self.tax_amount = Decimal('0')

        # Calculate total with tax
        self.total_amount = (
            subtotal -
            self.discount_amount -
            self.old_gold_amount +
            self.tax_amount +
            self.delivery_cost
        )
        self.balance_due = self.total_amount - self.amount_paid

        # Update status
        self.update_status()

        self.save(update_fields=[
            'subtotal', 'discount_amount', 'tax_amount', 'total_amount', 'balance_due', 'status'
        ])

    def update_status(self):
        """Update status based on payment"""
        if self.amount_paid >= self.total_amount:
            self.status = self.Status.PAID
        elif self.amount_paid > 0:
            self.status = self.Status.PARTIAL_PAID
        else:
            self.status = self.Status.UNPAID

    def update_payment(self, amount):
        """Update payment amount"""
        self.amount_paid += amount
        self.balance_due = self.total_amount - self.amount_paid
        self.update_status()
        self.save(update_fields=['amount_paid', 'balance_due', 'status'])

    @property
    def profit(self):
        """Calculate profit on this sale"""
        total_cost = self.items.aggregate(
            total=models.Sum('product__total_cost')
        )['total'] or Decimal('0')
        return self.total_amount - total_cost

    def save(self, *args, **kwargs):
        # Auto-generate reference if not present
        if not self.reference:
            from utils import generate_sales_invoice_reference
            self.reference = generate_sales_invoice_reference()
        super().save(*args, **kwargs)

    @property
    def profit_margin(self):
        """Calculate profit margin percentage"""
        total_cost = self.items.aggregate(
            total=models.Sum('product__total_cost')
        )['total'] or Decimal('0')
        if total_cost > 0:
            return ((self.total_amount - total_cost) / total_cost) * 100
        return 0

    # Status Transition Validation
    def can_transition_to(self, new_status):
        """
        Validate status transition is allowed.
        Returns True if transition is valid, False otherwise.
        """
        valid_transitions = {
            self.Status.UNPAID: [self.Status.PARTIAL_PAID, self.Status.PAID],
            self.Status.PARTIAL_PAID: [self.Status.PAID, self.Status.UNPAID],
            self.Status.PAID: [self.Status.PARTIAL_PAID, self.Status.UNPAID],
        }
        return new_status in valid_transitions.get(self.status, [])

    def transition_to(self, new_status):
        """
        Change status with validation.
        Raises ValidationError if transition is invalid.
        """
        from django.core.exceptions import ValidationError

        if not self.can_transition_to(new_status):
            raise ValidationError(
                f'Cannot transition from {self.get_status_display()} to '
                f'{self.Status(new_status).label}'
            )

        self.status = new_status
        self.save(update_fields=['status'])

    def soft_delete(self):
        """
        Mark invoice as deleted (soft delete).
        Resets product status to 'available'.
        """
        # Reset all product statuses
        for item in self.items.all():
            item.product.status = 'available'
            item.product.save(update_fields=['status'])

        # Mark as deleted and cancelled
        self.is_deleted = True
        self.status = self.Status.CANCELLED
        self.save(update_fields=['is_deleted', 'status'])


class SaleInvoiceItem(models.Model):
    """
    Line items for sales invoices
    """
    invoice = models.ForeignKey(
        SaleInvoice,
        on_delete=models.CASCADE,
        related_name='items',
        verbose_name=_('Facture')
    )

    # Product
    product = models.ForeignKey(
        'products.Product',
        on_delete=models.PROTECT,
        related_name='sale_items',
        verbose_name=_('Produit')
    )

    # Quantity - CRITICAL FIX
    quantity = models.DecimalField(
        _('Quantité'),
        max_digits=10,
        decimal_places=3,
        default=1,
        validators=[MinValueValidator(Decimal('0.001'))],
        help_text=_('Quantité de produits vendus')
    )

    # Pricing
    unit_price = models.DecimalField(
        _('Prix unitaire'),
        max_digits=12,
        decimal_places=2
    )
    original_price = models.DecimalField(
        _('Prix original'),
        max_digits=12,
        decimal_places=2,
        help_text=_('Prix avant négociation')
    )
    negotiated_price = models.DecimalField(
        _('Prix négocié'),
        max_digits=12,
        decimal_places=2,
        null=True,
        blank=True
    )
    discount_amount = models.DecimalField(
        _('Remise'),
        max_digits=10,
        decimal_places=2,
        default=0
    )
    total_amount = models.DecimalField(
        _('Montant total'),
        max_digits=12,
        decimal_places=2
    )

    # Notes
    notes = models.TextField(_('Notes'), blank=True)

    class Meta:
        verbose_name = _('Ligne de facture vente')
        verbose_name_plural = _('Lignes de facture vente')

    def __str__(self):
        return f"{self.product.reference} × {self.quantity} - {self.total_amount} MAD"

    def save(self, *args, **kwargs):
        # Set original price from product
        if not self.original_price:
            self.original_price = self.product.selling_price

        # Use negotiated price if set, otherwise original
        self.unit_price = self.negotiated_price or self.original_price

        # FIXED: Calculate total with quantity
        self.total_amount = (self.unit_price * self.quantity) - self.discount_amount

        super().save(*args, **kwargs)

        # Update product status
        if self.invoice.status not in ['draft', 'cancelled']:
            self.product.status = 'sold'
            self.product.save(update_fields=['status'])

        # Update invoice totals
        self.invoice.calculate_totals()


class ClientLoan(models.Model):
    """
    Track items loaned to clients for viewing/approval
    Client takes item home to show family before buying
    """

    class Status(models.TextChoices):
        ACTIVE = 'active', _('Actif')
        RETURNED = 'returned', _('Retourné')
        SOLD = 'sold', _('Vendu')
        OVERDUE = 'overdue', _('En retard')

    # Reference
    reference = models.CharField(
        _('Référence'),
        max_length=50,
        unique=True
    )
    date = models.DateField(_('Date'))

    # Client
    client = models.ForeignKey(
        'clients.Client',
        on_delete=models.PROTECT,
        related_name='loans',
        verbose_name=_('Client')
    )

    # Status
    status = models.CharField(
        _('Statut'),
        max_length=20,
        choices=Status.choices,
        default=Status.ACTIVE
    )

    # Terms
    return_date = models.DateField(_('Date de retour prévue'))
    deposit_amount = models.DecimalField(
        _('Montant du dépôt'),
        max_digits=12,
        decimal_places=2,
        default=0,
        help_text=_('Acompte laissé par le client')
    )

    # Dates
    actual_return_date = models.DateField(
        _('Date de retour effectif'),
        null=True,
        blank=True
    )

    # Tracking
    created_by = models.ForeignKey(
        'users.User',
        on_delete=models.SET_NULL,
        null=True,
        verbose_name=_('Créé par')
    )
    notes = models.TextField(_('Notes'), blank=True)
    created_at = models.DateTimeField(_('Créé le'), auto_now_add=True)
    updated_at = models.DateTimeField(_('Modifié le'), auto_now=True)

    class Meta:
        verbose_name = _('Prêt client')
        verbose_name_plural = _('Prêts clients')
        ordering = ['-date']

    def __str__(self):
        return f"{self.reference} - {self.client.full_name}"

    @property
    def total_value(self):
        """Total value of loaned items"""
        return self.items.aggregate(
            total=models.Sum('product__selling_price')
        )['total'] or Decimal('0')

    @property
    def is_overdue(self):
        """Check if loan is overdue"""
        from django.utils import timezone
        if self.status == self.Status.ACTIVE:
            return timezone.now().date() > self.return_date
        return False


class ClientLoanItem(models.Model):
    """
    Items in a client loan
    """
    loan = models.ForeignKey(
        ClientLoan,
        on_delete=models.CASCADE,
        related_name='items',
        verbose_name=_('Prêt')
    )
    product = models.ForeignKey(
        'products.Product',
        on_delete=models.PROTECT,
        related_name='loan_items',
        verbose_name=_('Produit')
    )

    # Status
    is_returned = models.BooleanField(_('Retourné'), default=False)
    is_sold = models.BooleanField(_('Vendu'), default=False)
    sale_invoice = models.ForeignKey(
        SaleInvoice,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='from_loan_items',
        verbose_name=_('Facture de vente')
    )

    class Meta:
        verbose_name = _('Article prêté')
        verbose_name_plural = _('Articles prêtés')

    def __str__(self):
        return f"{self.product.reference} - {self.loan.reference}"


class Layaway(models.Model):
    """
    Layaway / Mise de côté - Client reserves item with deposit
    Payment over time, item delivered when fully paid
    """

    class Status(models.TextChoices):
        ACTIVE = 'active', _('Actif')
        COMPLETED = 'completed', _('Complété')
        CANCELLED = 'cancelled', _('Annulé')
        EXPIRED = 'expired', _('Expiré')

    # Reference
    reference = models.CharField(
        _('Référence'),
        max_length=50,
        unique=True
    )
    date = models.DateField(_('Date'))

    # Client
    client = models.ForeignKey(
        'clients.Client',
        on_delete=models.PROTECT,
        related_name='layaways',
        verbose_name=_('Client')
    )

    # Product
    product = models.ForeignKey(
        'products.Product',
        on_delete=models.PROTECT,
        related_name='layaways',
        verbose_name=_('Produit')
    )

    # Status
    status = models.CharField(
        _('Statut'),
        max_length=20,
        choices=Status.choices,
        default=Status.ACTIVE
    )

    # Pricing
    agreed_price = models.DecimalField(
        _('Prix convenu'),
        max_digits=12,
        decimal_places=2
    )
    total_paid = models.DecimalField(
        _('Total payé'),
        max_digits=12,
        decimal_places=2,
        default=0
    )
    balance_due = models.DecimalField(
        _('Solde dû'),
        max_digits=12,
        decimal_places=2,
        default=0
    )

    # Terms
    expiry_date = models.DateField(
        _('Date d\'expiration'),
        help_text=_('Date limite pour compléter le paiement')
    )

    # Completion
    completed_date = models.DateField(
        _('Date de complétion'),
        null=True,
        blank=True
    )
    sale_invoice = models.ForeignKey(
        SaleInvoice,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='from_layaway',
        verbose_name=_('Facture de vente')
    )

    # Tracking
    created_by = models.ForeignKey(
        'users.User',
        on_delete=models.SET_NULL,
        null=True,
        verbose_name=_('Créé par')
    )
    notes = models.TextField(_('Notes'), blank=True)
    created_at = models.DateTimeField(_('Créé le'), auto_now_add=True)
    updated_at = models.DateTimeField(_('Modifié le'), auto_now=True)

    class Meta:
        verbose_name = _('Mise de côté')
        verbose_name_plural = _('Mises de côté')
        ordering = ['-date']

    def __str__(self):
        return f"{self.reference} - {self.client.full_name} - {self.product.reference}"

    def save(self, *args, **kwargs):
        self.balance_due = self.agreed_price - self.total_paid
        super().save(*args, **kwargs)

    def add_payment(self, amount):
        """Add payment to layaway"""
        self.total_paid += amount
        self.balance_due = self.agreed_price - self.total_paid

        if self.balance_due <= 0:
            self.status = self.Status.COMPLETED
            from django.utils import timezone
            self.completed_date = timezone.now().date()

        self.save()

    @property
    def is_expired(self):
        """Check if layaway has expired"""
        from django.utils import timezone
        if self.status == self.Status.ACTIVE:
            return timezone.now().date() > self.expiry_date
        return False

    @property
    def payment_progress(self):
        """Calculate payment progress percentage"""
        if self.agreed_price > 0:
            return (self.total_paid / self.agreed_price) * 100
        return 0

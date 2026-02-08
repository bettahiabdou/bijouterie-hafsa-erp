"""
Payment models for Bijouterie Hafsa ERP
Includes client payments, supplier payments, and deposits
"""

from django.db import models
from django.utils.translation import gettext_lazy as _
from django.core.validators import MinValueValidator
from decimal import Decimal


class ClientPayment(models.Model):
    """
    Payments received from clients
    Can be linked to invoices, layaways, or as deposits
    """

    class PaymentType(models.TextChoices):
        INVOICE = 'invoice', _('Paiement facture')
        DEPOSIT = 'deposit', _('Acompte')
        LAYAWAY = 'layaway', _('Paiement mise de côté')
        LOAN_DEPOSIT = 'loan_deposit', _('Dépôt pour prêt')
        ADVANCE = 'advance', _('Avance')
        REFUND = 'refund', _('Remboursement')

    # Reference - must be unique, cannot be duplicated
    reference = models.CharField(
        _('Référence'),
        max_length=100,
        unique=True,
        help_text=_('Référence unique du paiement (numéro de chèque, virement, etc.)')
    )
    date = models.DateField(_('Date'))
    payment_type = models.CharField(
        _('Type de paiement'),
        max_length=20,
        choices=PaymentType.choices,
        default=PaymentType.INVOICE
    )

    # Client (optional for anonymous sales)
    client = models.ForeignKey(
        'clients.Client',
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name='payments',
        verbose_name=_('Client')
    )

    # Amount
    amount = models.DecimalField(
        _('Montant'),
        max_digits=14,
        decimal_places=2,
        validators=[MinValueValidator(Decimal('0.01'))]
    )

    # Payment method
    payment_method = models.ForeignKey(
        'settings_app.PaymentMethod',
        on_delete=models.PROTECT,
        verbose_name=_('Mode de paiement')
    )

    # Bank account (if applicable)
    bank_account = models.ForeignKey(
        'settings_app.BankAccount',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        verbose_name=_('Compte bancaire'),
        help_text=_('Compte où le paiement a été reçu')
    )

    # Links to related objects
    sale_invoice = models.ForeignKey(
        'sales.SaleInvoice',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='payments',
        verbose_name=_('Facture de vente')
    )
    layaway = models.ForeignKey(
        'sales.Layaway',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='payments',
        verbose_name=_('Mise de côté')
    )
    client_loan = models.ForeignKey(
        'sales.ClientLoan',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='payments',
        verbose_name=_('Prêt client')
    )

    # Check details (if payment by check)
    check_number = models.CharField(
        _('Numéro de chèque'),
        max_length=50,
        blank=True
    )
    check_bank = models.CharField(
        _('Banque du chèque'),
        max_length=100,
        blank=True
    )
    check_date = models.DateField(
        _('Date du chèque'),
        null=True,
        blank=True
    )
    check_deposited = models.BooleanField(
        _('Chèque déposé'),
        default=False
    )
    check_deposit_date = models.DateField(
        _('Date de dépôt'),
        null=True,
        blank=True
    )
    check_cleared = models.BooleanField(
        _('Chèque encaissé'),
        default=False
    )
    check_bounce = models.BooleanField(
        _('Chèque impayé'),
        default=False
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
        verbose_name = _('Paiement client')
        verbose_name_plural = _('Paiements clients')
        ordering = ['-date', '-created_at']

    def __str__(self):
        return f"{self.reference} - {self.client.full_name} - {self.amount} MAD"

    def save(self, *args, **kwargs):
        # Auto-generate reference if not present
        if not self.reference:
            from utils import generate_payment_reference
            self.reference = generate_payment_reference('PAY')

        is_new = self.pk is None
        super().save(*args, **kwargs)

        # Update related objects after payment
        if is_new:
            if self.sale_invoice:
                self.sale_invoice.update_payment(self.amount)
            if self.layaway:
                self.layaway.add_payment(self.amount)

        # PHASE 3: Invalidate client balance cache when payment is recorded
        from django.core.cache import cache
        cache.delete(f'client_balance_{self.client.id}')


class SupplierPayment(models.Model):
    """
    Payments made to suppliers
    """

    class PaymentType(models.TextChoices):
        INVOICE = 'invoice', _('Paiement facture')
        ADVANCE = 'advance', _('Avance')
        CONSIGNMENT = 'consignment', _('Paiement consignation')
        ARTISAN = 'artisan', _('Paiement artisan')

    # Reference - must be unique
    reference = models.CharField(
        _('Référence'),
        max_length=100,
        unique=True
    )
    date = models.DateField(_('Date'))
    payment_type = models.CharField(
        _('Type de paiement'),
        max_length=20,
        choices=PaymentType.choices,
        default=PaymentType.INVOICE
    )

    # Supplier
    supplier = models.ForeignKey(
        'suppliers.Supplier',
        on_delete=models.PROTECT,
        related_name='payments',
        verbose_name=_('Fournisseur')
    )

    # Amount
    amount = models.DecimalField(
        _('Montant'),
        max_digits=14,
        decimal_places=2,
        validators=[MinValueValidator(Decimal('0.01'))]
    )

    # Payment method
    payment_method = models.ForeignKey(
        'settings_app.PaymentMethod',
        on_delete=models.PROTECT,
        verbose_name=_('Mode de paiement')
    )

    # Bank accounts
    from_bank_account = models.ForeignKey(
        'settings_app.BankAccount',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='outgoing_payments',
        verbose_name=_('Depuis compte'),
        help_text=_('Notre compte d\'où part le paiement')
    )
    to_supplier_account = models.ForeignKey(
        'suppliers.SupplierBankAccount',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='received_payments',
        verbose_name=_('Vers compte fournisseur')
    )

    # Links to related objects
    purchase_invoice = models.ForeignKey(
        'purchases.PurchaseInvoice',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='payments',
        verbose_name=_('Facture d\'achat')
    )
    consignment = models.ForeignKey(
        'purchases.Consignment',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='payments',
        verbose_name=_('Consignation')
    )
    artisan_job = models.ForeignKey(
        'suppliers.ArtisanJob',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='payments',
        verbose_name=_('Travail artisan')
    )

    # Check details (if payment by check)
    check_number = models.CharField(
        _('Numéro de chèque'),
        max_length=50,
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
        verbose_name = _('Paiement fournisseur')
        verbose_name_plural = _('Paiements fournisseurs')
        ordering = ['-date', '-created_at']

    def __str__(self):
        return f"{self.reference} - {self.supplier.name} - {self.amount} MAD"

    def save(self, *args, **kwargs):
        # Auto-generate reference if not present
        if not self.reference:
            from utils import generate_payment_reference
            self.reference = generate_payment_reference('SUP-PAY')

        is_new = self.pk is None
        super().save(*args, **kwargs)

        # Update related invoice after payment
        if is_new and self.purchase_invoice:
            self.purchase_invoice.update_payment(self.amount)


class Deposit(models.Model):
    """
    Unified deposits tracking - for both clients and suppliers
    Deposits that are waiting to be applied to invoices
    """

    class DepositType(models.TextChoices):
        CLIENT = 'client', _('Acompte client')
        SUPPLIER = 'supplier', _('Avance fournisseur')

    class Status(models.TextChoices):
        PENDING = 'pending', _('En attente')
        PARTIAL_APPLIED = 'partial', _('Partiellement appliqué')
        APPLIED = 'applied', _('Appliqué')
        REFUNDED = 'refunded', _('Remboursé')
        CANCELLED = 'cancelled', _('Annulé')

    # Reference
    reference = models.CharField(
        _('Référence'),
        max_length=100,
        unique=True
    )
    date = models.DateField(_('Date'))
    deposit_type = models.CharField(
        _('Type'),
        max_length=20,
        choices=DepositType.choices
    )

    # Client or Supplier
    client = models.ForeignKey(
        'clients.Client',
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name='deposits',
        verbose_name=_('Client')
    )
    supplier = models.ForeignKey(
        'suppliers.Supplier',
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name='deposits',
        verbose_name=_('Fournisseur')
    )

    # Amount
    original_amount = models.DecimalField(
        _('Montant original'),
        max_digits=14,
        decimal_places=2
    )
    amount_applied = models.DecimalField(
        _('Montant appliqué'),
        max_digits=14,
        decimal_places=2,
        default=0
    )
    amount_remaining = models.DecimalField(
        _('Montant restant'),
        max_digits=14,
        decimal_places=2,
        default=0
    )

    # Status
    status = models.CharField(
        _('Statut'),
        max_length=20,
        choices=Status.choices,
        default=Status.PENDING
    )

    # Payment info
    payment_method = models.ForeignKey(
        'settings_app.PaymentMethod',
        on_delete=models.PROTECT,
        verbose_name=_('Mode de paiement')
    )
    payment_reference = models.CharField(
        _('Référence paiement'),
        max_length=100,
        blank=True
    )
    bank_account = models.ForeignKey(
        'settings_app.BankAccount',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        verbose_name=_('Compte bancaire')
    )

    # Purpose (what is this deposit for)
    purpose = models.CharField(
        _('Objet'),
        max_length=500,
        blank=True,
        help_text=_('Ex: Acompte pour bague sur mesure')
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
        verbose_name = _('Acompte/Avance')
        verbose_name_plural = _('Acomptes/Avances')
        ordering = ['-date', '-created_at']

    def __str__(self):
        party = self.client.full_name if self.client else self.supplier.name
        return f"{self.reference} - {party} - {self.amount_remaining} MAD restant"

    def save(self, *args, **kwargs):
        # Auto-generate reference if not present
        if not self.reference:
            from utils import generate_payment_reference
            self.reference = generate_payment_reference('DEP')

        self.amount_remaining = self.original_amount - self.amount_applied

        if self.amount_remaining <= 0:
            self.status = self.Status.APPLIED
        elif self.amount_applied > 0:
            self.status = self.Status.PARTIAL_APPLIED

        super().save(*args, **kwargs)

    def apply_to_invoice(self, amount, invoice):
        """Apply deposit amount to an invoice"""
        if amount > self.amount_remaining:
            raise ValueError(_('Montant supérieur au solde disponible'))

        self.amount_applied += amount
        self.save()

        # Record the application
        DepositApplication.objects.create(
            deposit=self,
            amount=amount,
            sale_invoice=invoice if self.deposit_type == 'client' else None,
            purchase_invoice=invoice if self.deposit_type == 'supplier' else None
        )

        return amount


class DepositApplication(models.Model):
    """
    Track how deposits are applied to invoices
    """
    deposit = models.ForeignKey(
        Deposit,
        on_delete=models.CASCADE,
        related_name='applications',
        verbose_name=_('Acompte')
    )
    date = models.DateField(_('Date'), auto_now_add=True)
    amount = models.DecimalField(
        _('Montant'),
        max_digits=14,
        decimal_places=2
    )

    # Applied to
    sale_invoice = models.ForeignKey(
        'sales.SaleInvoice',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='deposit_applications',
        verbose_name=_('Facture de vente')
    )
    purchase_invoice = models.ForeignKey(
        'purchases.PurchaseInvoice',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='deposit_applications',
        verbose_name=_('Facture d\'achat')
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

    class Meta:
        verbose_name = _('Application d\'acompte')
        verbose_name_plural = _('Applications d\'acomptes')
        ordering = ['-date']

    def __str__(self):
        return f"{self.deposit.reference} -> {self.amount} MAD"


class PendingPayment(models.Model):
    """
    Track pending/scheduled payments
    For managing credit sales and deferred payments
    """

    class Status(models.TextChoices):
        PENDING = 'pending', _('En attente')
        PARTIAL = 'partial', _('Partiellement payé')
        PAID = 'paid', _('Payé')
        OVERDUE = 'overdue', _('En retard')
        CANCELLED = 'cancelled', _('Annulé')

    class PartyType(models.TextChoices):
        CLIENT = 'client', _('Client')
        SUPPLIER = 'supplier', _('Fournisseur')

    # Reference
    reference = models.CharField(
        _('Référence'),
        max_length=100,
        unique=True
    )

    # Party
    party_type = models.CharField(
        _('Type'),
        max_length=20,
        choices=PartyType.choices
    )
    client = models.ForeignKey(
        'clients.Client',
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name='pending_payments',
        verbose_name=_('Client')
    )
    supplier = models.ForeignKey(
        'suppliers.Supplier',
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name='pending_payments',
        verbose_name=_('Fournisseur')
    )

    # Related invoice
    sale_invoice = models.ForeignKey(
        'sales.SaleInvoice',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='pending_payments',
        verbose_name=_('Facture de vente')
    )
    purchase_invoice = models.ForeignKey(
        'purchases.PurchaseInvoice',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='pending_payments',
        verbose_name=_('Facture d\'achat')
    )

    # Amount
    amount_due = models.DecimalField(
        _('Montant dû'),
        max_digits=14,
        decimal_places=2
    )
    amount_paid = models.DecimalField(
        _('Montant payé'),
        max_digits=14,
        decimal_places=2,
        default=0
    )
    amount_remaining = models.DecimalField(
        _('Montant restant'),
        max_digits=14,
        decimal_places=2,
        default=0
    )

    # Due date
    due_date = models.DateField(_('Date d\'échéance'))

    # Status
    status = models.CharField(
        _('Statut'),
        max_length=20,
        choices=Status.choices,
        default=Status.PENDING
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
        verbose_name = _('Paiement en attente')
        verbose_name_plural = _('Paiements en attente')
        ordering = ['due_date']

    def __str__(self):
        party = self.client.full_name if self.client else self.supplier.name
        return f"{self.reference} - {party} - {self.amount_remaining} MAD"

    def save(self, *args, **kwargs):
        self.amount_remaining = self.amount_due - self.amount_paid

        if self.amount_remaining <= 0:
            self.status = self.Status.PAID
        elif self.amount_paid > 0:
            self.status = self.Status.PARTIAL
        else:
            # Check if overdue
            from django.utils import timezone
            if timezone.now().date() > self.due_date:
                self.status = self.Status.OVERDUE
            else:
                self.status = self.Status.PENDING

        super().save(*args, **kwargs)

    @property
    def is_overdue(self):
        """Check if payment is overdue"""
        from django.utils import timezone
        return (
            self.status in [self.Status.PENDING, self.Status.PARTIAL] and
            timezone.now().date() > self.due_date
        )

    @property
    def days_overdue(self):
        """Calculate days overdue"""
        from django.utils import timezone
        if self.is_overdue:
            return (timezone.now().date() - self.due_date).days
        return 0

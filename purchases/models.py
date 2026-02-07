"""
Purchase models for Bijouterie Hafsa ERP
Includes purchase orders, purchase invoices, and consignment
"""

from django.db import models
from django.utils.translation import gettext_lazy as _
from django.core.validators import MinValueValidator
from decimal import Decimal


class PurchaseOrder(models.Model):
    """
    Purchase order - request to buy from supplier or artisan
    Can be created by seller, needs approval for execution
    """

    class Status(models.TextChoices):
        DRAFT = 'draft', _('Brouillon')
        PENDING = 'pending', _('En attente d\'approbation')
        APPROVED = 'approved', _('Approuvé')
        ORDERED = 'ordered', _('Commandé')
        PARTIAL = 'partial', _('Partiellement reçu')
        RECEIVED = 'received', _('Reçu')
        CANCELLED = 'cancelled', _('Annulé')

    class OrderType(models.TextChoices):
        FINISHED_JEWELRY = 'finished', _('Bijoux finis')
        RAW_MATERIAL = 'raw_material', _('Matière première')
        STONES = 'stones', _('Pierres')
        ARTISAN_WORK = 'artisan', _('Travail artisan')
        CUSTOM_ORDER = 'custom', _('Commande sur mesure client')

    # Reference
    reference = models.CharField(
        _('Référence'),
        max_length=50,
        unique=True
    )
    date = models.DateField(_('Date'))
    order_type = models.CharField(
        _('Type de commande'),
        max_length=20,
        choices=OrderType.choices,
        default=OrderType.FINISHED_JEWELRY
    )

    # Supplier/Artisan
    supplier = models.ForeignKey(
        'suppliers.Supplier',
        on_delete=models.PROTECT,
        related_name='purchase_orders',
        verbose_name=_('Fournisseur')
    )

    # For custom orders
    client = models.ForeignKey(
        'clients.Client',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='custom_purchase_orders',
        verbose_name=_('Client (commande sur mesure)')
    )

    # Status
    status = models.CharField(
        _('Statut'),
        max_length=20,
        choices=Status.choices,
        default=Status.DRAFT
    )

    # Dates
    expected_date = models.DateField(
        _('Date prévue'),
        null=True,
        blank=True
    )

    # Totals (calculated)
    total_amount = models.DecimalField(
        _('Montant total'),
        max_digits=14,
        decimal_places=2,
        default=0
    )

    # Approval
    approved_by = models.ForeignKey(
        'users.User',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='approved_purchase_orders',
        verbose_name=_('Approuvé par')
    )
    approved_at = models.DateTimeField(
        _('Date d\'approbation'),
        null=True,
        blank=True
    )

    # Tracking
    created_by = models.ForeignKey(
        'users.User',
        on_delete=models.SET_NULL,
        null=True,
        related_name='created_purchase_orders',
        verbose_name=_('Créé par')
    )
    notes = models.TextField(_('Notes'), blank=True)
    created_at = models.DateTimeField(_('Créé le'), auto_now_add=True)
    updated_at = models.DateTimeField(_('Modifié le'), auto_now=True)

    class Meta:
        verbose_name = _('Bon de commande')
        verbose_name_plural = _('Bons de commande')
        ordering = ['-date', '-created_at']

    def __str__(self):
        return f"{self.reference} - {self.supplier.name}"

    def save(self, *args, **kwargs):
        # Auto-generate reference if not present
        if not self.reference:
            from utils import generate_purchase_order_reference
            self.reference = generate_purchase_order_reference()
        super().save(*args, **kwargs)

    def calculate_total(self):
        """Calculate total from line items"""
        total = self.items.aggregate(
            total=models.Sum('total_amount')
        )['total'] or Decimal('0')
        self.total_amount = total
        self.save(update_fields=['total_amount'])


class PurchaseOrderItem(models.Model):
    """
    Line items for purchase orders
    """
    purchase_order = models.ForeignKey(
        PurchaseOrder,
        on_delete=models.CASCADE,
        related_name='items',
        verbose_name=_('Bon de commande')
    )

    # Item description
    description = models.CharField(_('Description'), max_length=500)
    category = models.ForeignKey(
        'settings_app.ProductCategory',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        verbose_name=_('Catégorie')
    )

    # Metal details
    metal_type = models.ForeignKey(
        'settings_app.MetalType',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        verbose_name=_('Type de métal')
    )
    metal_purity = models.ForeignKey(
        'settings_app.MetalPurity',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        verbose_name=_('Titre')
    )

    # Quantity and weight
    quantity = models.PositiveIntegerField(_('Quantité'), default=1)
    estimated_weight = models.DecimalField(
        _('Poids estimé (g)'),
        max_digits=10,
        decimal_places=3,
        default=0
    )

    # Pricing
    estimated_price_per_gram = models.DecimalField(
        _('Prix estimé par gramme'),
        max_digits=10,
        decimal_places=2,
        default=0
    )
    estimated_labor_cost = models.DecimalField(
        _('Main d\'œuvre estimée'),
        max_digits=10,
        decimal_places=2,
        default=0
    )
    total_amount = models.DecimalField(
        _('Montant total'),
        max_digits=12,
        decimal_places=2,
        default=0
    )

    # Received tracking
    quantity_received = models.PositiveIntegerField(
        _('Quantité reçue'),
        default=0
    )

    # Notes
    notes = models.TextField(_('Notes'), blank=True)

    class Meta:
        verbose_name = _('Ligne de commande')
        verbose_name_plural = _('Lignes de commande')

    def __str__(self):
        return f"{self.description} x {self.quantity}"

    def save(self, *args, **kwargs):
        # Calculate total
        metal_cost = self.estimated_weight * self.estimated_price_per_gram
        self.total_amount = (metal_cost + self.estimated_labor_cost) * self.quantity
        super().save(*args, **kwargs)

        # Update order total
        self.purchase_order.calculate_total()


class PurchaseInvoice(models.Model):
    """
    Purchase invoice - actual purchase from supplier
    """

    class Status(models.TextChoices):
        DRAFT = 'draft', _('Brouillon')
        CONFIRMED = 'confirmed', _('Confirmé')
        PARTIAL_PAID = 'partial', _('Partiellement payé')
        PAID = 'paid', _('Payé')
        CANCELLED = 'cancelled', _('Annulé')

    class InvoiceType(models.TextChoices):
        FINISHED_JEWELRY = 'finished', _('Bijoux finis')
        RAW_MATERIAL = 'raw_material', _('Matière première')
        STONES = 'stones', _('Pierres')
        LABOR_ONLY = 'labor', _('Main d\'œuvre seule')
        MIXED = 'mixed', _('Mixte')

    # Reference
    reference = models.CharField(
        _('Référence'),
        max_length=50,
        unique=True
    )
    supplier_invoice_ref = models.CharField(
        _('Référence facture fournisseur'),
        max_length=100,
        blank=True
    )
    date = models.DateField(_('Date'))
    invoice_type = models.CharField(
        _('Type de facture'),
        max_length=20,
        choices=InvoiceType.choices,
        default=InvoiceType.FINISHED_JEWELRY
    )

    # Supplier
    supplier = models.ForeignKey(
        'suppliers.Supplier',
        on_delete=models.PROTECT,
        related_name='purchase_invoices',
        verbose_name=_('Fournisseur')
    )

    # Link to purchase order
    purchase_order = models.ForeignKey(
        PurchaseOrder,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='invoices',
        verbose_name=_('Bon de commande')
    )

    # Status
    status = models.CharField(
        _('Statut'),
        max_length=20,
        choices=Status.choices,
        default=Status.DRAFT
    )

    # Totals
    subtotal = models.DecimalField(
        _('Sous-total'),
        max_digits=14,
        decimal_places=2,
        default=0
    )
    discount_amount = models.DecimalField(
        _('Remise'),
        max_digits=10,
        decimal_places=2,
        default=0
    )
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

    # Tracking
    created_by = models.ForeignKey(
        'users.User',
        on_delete=models.SET_NULL,
        null=True,
        related_name='created_purchase_invoices',
        verbose_name=_('Créé par')
    )
    notes = models.TextField(_('Notes'), blank=True)
    created_at = models.DateTimeField(_('Créé le'), auto_now_add=True)
    updated_at = models.DateTimeField(_('Modifié le'), auto_now=True)

    class Meta:
        verbose_name = _('Facture d\'achat')
        verbose_name_plural = _('Factures d\'achat')
        ordering = ['-date', '-created_at']

    def __str__(self):
        return f"{self.reference} - {self.supplier.name} - {self.total_amount} MAD"

    def save(self, *args, **kwargs):
        # Auto-generate reference if not present
        if not self.reference:
            from utils import generate_purchase_invoice_reference
            self.reference = generate_purchase_invoice_reference()
        super().save(*args, **kwargs)

    def calculate_totals(self):
        """Calculate totals from line items"""
        subtotal = self.items.aggregate(
            total=models.Sum('total_amount')
        )['total'] or Decimal('0')

        self.subtotal = subtotal
        self.total_amount = subtotal - self.discount_amount
        self.balance_due = self.total_amount - self.amount_paid

        # Update status based on payment
        if self.amount_paid >= self.total_amount:
            self.status = self.Status.PAID
        elif self.amount_paid > 0:
            self.status = self.Status.PARTIAL_PAID

        self.save(update_fields=['subtotal', 'total_amount', 'balance_due', 'status'])

    def update_payment(self, amount):
        """Update payment amount"""
        self.amount_paid += amount
        self.balance_due = self.total_amount - self.amount_paid

        if self.balance_due <= 0:
            self.status = self.Status.PAID
        elif self.amount_paid > 0:
            self.status = self.Status.PARTIAL_PAID

        self.save(update_fields=['amount_paid', 'balance_due', 'status'])


class PurchaseInvoiceItem(models.Model):
    """
    Line items for purchase invoices
    Each item represents a jewelry piece purchased
    """
    invoice = models.ForeignKey(
        PurchaseInvoice,
        on_delete=models.CASCADE,
        related_name='items',
        verbose_name=_('Facture')
    )

    # Product (will be created from this)
    product = models.ForeignKey(
        'products.Product',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='purchase_items',
        verbose_name=_('Produit')
    )

    # Item details
    description = models.CharField(_('Description'), max_length=500)
    category = models.ForeignKey(
        'settings_app.ProductCategory',
        on_delete=models.PROTECT,
        verbose_name=_('Catégorie')
    )

    # Metal details
    metal_type = models.ForeignKey(
        'settings_app.MetalType',
        on_delete=models.PROTECT,
        verbose_name=_('Type de métal')
    )
    metal_purity = models.ForeignKey(
        'settings_app.MetalPurity',
        on_delete=models.PROTECT,
        verbose_name=_('Titre')
    )

    # Weight
    gross_weight = models.DecimalField(
        _('Poids brut (g)'),
        max_digits=10,
        decimal_places=3,
        validators=[MinValueValidator(Decimal('0'))]
    )
    net_weight = models.DecimalField(
        _('Poids net (g)'),
        max_digits=10,
        decimal_places=3,
        validators=[MinValueValidator(Decimal('0'))]
    )

    # Pricing
    price_per_gram = models.DecimalField(
        _('Prix par gramme'),
        max_digits=10,
        decimal_places=2,
        validators=[MinValueValidator(Decimal('0'))]
    )
    metal_cost = models.DecimalField(
        _('Coût métal'),
        max_digits=12,
        decimal_places=2,
        default=0
    )
    labor_cost = models.DecimalField(
        _('Main d\'œuvre'),
        max_digits=10,
        decimal_places=2,
        default=0
    )
    stone_cost = models.DecimalField(
        _('Coût pierres'),
        max_digits=12,
        decimal_places=2,
        default=0
    )
    other_cost = models.DecimalField(
        _('Autres coûts'),
        max_digits=10,
        decimal_places=2,
        default=0
    )
    total_amount = models.DecimalField(
        _('Montant total'),
        max_digits=12,
        decimal_places=2,
        default=0
    )

    # Notes
    notes = models.TextField(_('Notes'), blank=True)

    class Meta:
        verbose_name = _('Ligne de facture achat')
        verbose_name_plural = _('Lignes de facture achat')

    def __str__(self):
        return f"{self.description} - {self.net_weight}g"

    def save(self, *args, **kwargs):
        # Calculate costs
        self.metal_cost = self.net_weight * self.price_per_gram
        self.total_amount = (
            self.metal_cost +
            self.labor_cost +
            self.stone_cost +
            self.other_cost
        )
        super().save(*args, **kwargs)

        # Update invoice totals
        self.invoice.calculate_totals()


class PurchaseInvoiceAction(models.Model):
    """
    Track returns and exchanges on purchase invoices
    """

    class ActionType(models.TextChoices):
        RETURN = 'return', _('Retour')
        EXCHANGE = 'exchange', _('Échange')

    invoice = models.ForeignKey(
        PurchaseInvoice,
        on_delete=models.CASCADE,
        related_name='actions',
        verbose_name=_('Facture')
    )

    action_type = models.CharField(
        _('Type d\'action'),
        max_length=20,
        choices=ActionType.choices
    )

    # The product that was returned or exchanged
    original_product = models.ForeignKey(
        'products.Product',
        on_delete=models.SET_NULL,
        null=True,
        related_name='purchase_returns',
        verbose_name=_('Produit original')
    )
    original_product_ref = models.CharField(
        _('Référence produit original'),
        max_length=100,
        blank=True
    )

    # For exchanges: the replacement product
    replacement_product = models.ForeignKey(
        'products.Product',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='purchase_replacements',
        verbose_name=_('Produit de remplacement')
    )

    # Tracking
    notes = models.TextField(_('Notes'), blank=True)
    created_by = models.ForeignKey(
        'users.User',
        on_delete=models.SET_NULL,
        null=True,
        verbose_name=_('Créé par')
    )
    created_at = models.DateTimeField(_('Date'), auto_now_add=True)

    class Meta:
        verbose_name = _('Action facture achat')
        verbose_name_plural = _('Actions facture achat')
        ordering = ['-created_at']

    def __str__(self):
        if self.action_type == self.ActionType.EXCHANGE:
            return f"Échange: {self.original_product_ref} → {self.replacement_product.reference if self.replacement_product else '?'}"
        return f"Retour: {self.original_product_ref}"


class Consignment(models.Model):
    """
    Consignment (Dépôt-vente) - items received but not paid until sold
    """

    class Status(models.TextChoices):
        ACTIVE = 'active', _('Actif')
        PARTIAL_SOLD = 'partial', _('Partiellement vendu')
        SOLD = 'sold', _('Tout vendu')
        RETURNED = 'returned', _('Retourné')
        CLOSED = 'closed', _('Clôturé')

    # Reference
    reference = models.CharField(
        _('Référence'),
        max_length=50,
        unique=True
    )
    date_received = models.DateField(_('Date de réception'))

    # Supplier
    supplier = models.ForeignKey(
        'suppliers.Supplier',
        on_delete=models.PROTECT,
        related_name='consignments',
        verbose_name=_('Fournisseur')
    )

    # Status
    status = models.CharField(
        _('Statut'),
        max_length=20,
        choices=Status.choices,
        default=Status.ACTIVE
    )

    # Terms
    return_deadline = models.DateField(
        _('Date limite de retour'),
        null=True,
        blank=True
    )
    commission_percent = models.DecimalField(
        _('Commission (%)'),
        max_digits=5,
        decimal_places=2,
        default=0,
        help_text=_('Pourcentage gardé sur les ventes')
    )

    # Totals
    total_items = models.PositiveIntegerField(_('Total articles'), default=0)
    total_value = models.DecimalField(
        _('Valeur totale'),
        max_digits=14,
        decimal_places=2,
        default=0
    )
    items_sold = models.PositiveIntegerField(_('Articles vendus'), default=0)
    amount_due = models.DecimalField(
        _('Montant dû au fournisseur'),
        max_digits=14,
        decimal_places=2,
        default=0
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
        verbose_name = _('Consignation')
        verbose_name_plural = _('Consignations')
        ordering = ['-date_received']

    def __str__(self):
        return f"{self.reference} - {self.supplier.name}"

    def save(self, *args, **kwargs):
        # Auto-generate reference if not present
        if not self.reference:
            from utils import generate_consignment_reference
            self.reference = generate_consignment_reference()
        super().save(*args, **kwargs)

    def update_totals(self):
        """Update totals from items"""
        items = self.items.all()
        self.total_items = items.count()
        self.total_value = items.aggregate(
            total=models.Sum('agreed_price')
        )['total'] or Decimal('0')

        sold_items = items.filter(status='sold')
        self.items_sold = sold_items.count()

        # Calculate amount due (sold value minus commission)
        sold_value = sold_items.aggregate(
            total=models.Sum('sold_price')
        )['total'] or Decimal('0')
        self.amount_due = sold_value * (1 - self.commission_percent / 100)

        # Update status
        if self.items_sold == self.total_items and self.total_items > 0:
            self.status = self.Status.SOLD
        elif self.items_sold > 0:
            self.status = self.Status.PARTIAL_SOLD

        self.save()


class ConsignmentItem(models.Model):
    """
    Items in consignment
    """

    class Status(models.TextChoices):
        AVAILABLE = 'available', _('Disponible')
        SOLD = 'sold', _('Vendu')
        RETURNED = 'returned', _('Retourné')

    consignment = models.ForeignKey(
        Consignment,
        on_delete=models.CASCADE,
        related_name='items',
        verbose_name=_('Consignation')
    )

    # Product
    product = models.ForeignKey(
        'products.Product',
        on_delete=models.PROTECT,
        related_name='consignment_items',
        verbose_name=_('Produit')
    )

    # Pricing
    agreed_price = models.DecimalField(
        _('Prix convenu'),
        max_digits=12,
        decimal_places=2,
        help_text=_('Prix à payer au fournisseur si vendu')
    )
    minimum_selling_price = models.DecimalField(
        _('Prix de vente minimum'),
        max_digits=12,
        decimal_places=2
    )
    sold_price = models.DecimalField(
        _('Prix de vente effectif'),
        max_digits=12,
        decimal_places=2,
        null=True,
        blank=True
    )

    # Status
    status = models.CharField(
        _('Statut'),
        max_length=20,
        choices=Status.choices,
        default=Status.AVAILABLE
    )

    # Dates
    date_sold = models.DateField(
        _('Date de vente'),
        null=True,
        blank=True
    )
    date_returned = models.DateField(
        _('Date de retour'),
        null=True,
        blank=True
    )

    # Notes
    notes = models.TextField(_('Notes'), blank=True)

    class Meta:
        verbose_name = _('Article en consignation')
        verbose_name_plural = _('Articles en consignation')

    def __str__(self):
        return f"{self.product.reference} - {self.consignment.reference}"

    def mark_as_sold(self, selling_price, sale_date=None):
        """Mark item as sold"""
        from django.utils import timezone
        self.status = self.Status.SOLD
        self.sold_price = selling_price
        self.date_sold = sale_date or timezone.now().date()
        self.save()

        # Update product status
        self.product.status = 'sold'
        self.product.save()

        # Update consignment totals
        self.consignment.update_totals()

    def mark_as_returned(self, return_date=None):
        """Mark item as returned to supplier"""
        from django.utils import timezone
        self.status = self.Status.RETURNED
        self.date_returned = return_date or timezone.now().date()
        self.save()

        # Update product status
        self.product.status = 'returned'
        self.product.save()

        # Update consignment totals
        self.consignment.update_totals()

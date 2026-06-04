"""
Client Stock Storage models for Bijouterie Hafsa ERP
Tracks items that clients leave in-store after purchase for later pickup
"""

from django.db import models
from django.utils.translation import gettext_lazy as _
from django.utils import timezone
from decimal import Decimal


class StockStorageAccount(models.Model):
    """
    Per-client stock storage account.
    Auto-created when a client's invoice uses 'en_stock' delivery.
    """

    client = models.OneToOneField(
        'clients.Client',
        on_delete=models.PROTECT,
        related_name='stock_storage_account',
        verbose_name=_('Client')
    )
    is_active = models.BooleanField(_('Actif'), default=True)
    notes = models.TextField(_('Notes'), blank=True)
    created_by = models.ForeignKey(
        'users.User',
        on_delete=models.SET_NULL,
        null=True,
        related_name='created_stock_storage_accounts',
        verbose_name=_('Créé par')
    )
    created_at = models.DateTimeField(_('Créé le'), auto_now_add=True)
    updated_at = models.DateTimeField(_('Modifié le'), auto_now=True)

    class Meta:
        verbose_name = _('Compte Stock Client')
        verbose_name_plural = _('Comptes Stock Client')
        ordering = ['-created_at']

    def __str__(self):
        return f"Stock - {self.client.full_name}"

    @property
    def total_items(self):
        return self.items.count()

    @property
    def waiting_items(self):
        return self.items.filter(status=StockStorageItem.Status.WAITING).count()

    @property
    def picked_up_items(self):
        return self.items.filter(status=StockStorageItem.Status.PICKED_UP).count()

    @property
    def total_value_waiting(self):
        total = self.items.filter(
            status=StockStorageItem.Status.WAITING
        ).aggregate(total=models.Sum('price'))['total']
        return total or Decimal('0')

    @property
    def last_activity_date(self):
        last_item = self.items.order_by('-stored_at').first()
        last_pickup = self.items.filter(
            picked_up_at__isnull=False
        ).order_by('-picked_up_at').first()
        dates = []
        if last_item:
            dates.append(last_item.stored_at)
        if last_pickup and last_pickup.picked_up_at:
            dates.append(last_pickup.picked_up_at)
        return max(dates) if dates else self.created_at


class StockStorageItem(models.Model):
    """
    Individual product stored for a client.
    Created when an invoice with delivery_method_type='en_stock' is completed.
    """

    class Status(models.TextChoices):
        WAITING = 'waiting', _('En attente')
        PICKED_UP = 'picked_up', _('Récupéré')

    class PickupMethod(models.TextChoices):
        MAGASIN = 'magasin', _('Magasin (Retrait)')
        AMANA = 'amana', _('AMANA')
        TRANSPORTEUR = 'transporteur', _('Autre Transporteur')

    account = models.ForeignKey(
        StockStorageAccount,
        on_delete=models.PROTECT,
        related_name='items',
        verbose_name=_('Compte')
    )
    invoice = models.ForeignKey(
        'sales.SaleInvoice',
        on_delete=models.PROTECT,
        related_name='stock_storage_items',
        verbose_name=_('Facture')
    )
    product = models.ForeignKey(
        'products.Product',
        on_delete=models.PROTECT,
        related_name='stock_storage_items',
        verbose_name=_('Produit')
    )

    # Snapshot fields (denormalized for display)
    product_reference = models.CharField(_('Réf. produit'), max_length=100)
    product_name = models.CharField(_('Nom produit'), max_length=200)
    product_weight = models.DecimalField(
        _('Poids (g)'), max_digits=10, decimal_places=3, default=0
    )
    price = models.DecimalField(
        _('Prix'), max_digits=12, decimal_places=2, default=0
    )

    status = models.CharField(
        _('Statut'),
        max_length=20,
        choices=Status.choices,
        default=Status.WAITING
    )
    stored_at = models.DateTimeField(_('Date de stockage'), auto_now_add=True)
    picked_up_at = models.DateTimeField(
        _('Date de récupération'), null=True, blank=True
    )
    picked_up_by = models.ForeignKey(
        'users.User',
        on_delete=models.SET_NULL,
        null=True, blank=True,
        related_name='stock_pickups',
        verbose_name=_('Récupéré par')
    )

    # How the item left storage (in-store / shipped)
    pickup_method = models.CharField(
        _('Mode de récupération'),
        max_length=20,
        choices=PickupMethod.choices,
        default=PickupMethod.MAGASIN
    )
    carrier = models.ForeignKey(
        'settings_app.Carrier',
        on_delete=models.SET_NULL,
        null=True, blank=True,
        related_name='stock_storage_items',
        verbose_name=_('Transporteur')
    )
    tracking_number = models.CharField(
        _('Numéro de suivi'),
        max_length=100,
        blank=True
    )

    notes = models.TextField(_('Notes'), blank=True)
    created_by = models.ForeignKey(
        'users.User',
        on_delete=models.SET_NULL,
        null=True,
        related_name='created_stock_storage_items',
        verbose_name=_('Créé par')
    )

    class Meta:
        verbose_name = _('Article en Stock Client')
        verbose_name_plural = _('Articles en Stock Client')
        ordering = ['-stored_at']
        indexes = [
            models.Index(fields=['status', '-stored_at']),
            models.Index(fields=['account', 'status']),
        ]

    def __str__(self):
        return f"{self.product_reference} - {self.account.client.full_name} ({self.get_status_display()})"

    @property
    def tracking_url(self):
        """Build a clickable tracking URL from the carrier template, if available."""
        if self.carrier and self.carrier.tracking_url_template and self.tracking_number:
            try:
                return self.carrier.tracking_url_template.format(tracking_code=self.tracking_number)
            except Exception:
                return ''
        return ''

    def mark_picked_up(self, user, pickup_method=None, carrier=None, tracking_number=''):
        self.status = self.Status.PICKED_UP
        self.picked_up_at = timezone.now()
        self.picked_up_by = user
        self.pickup_method = pickup_method or self.PickupMethod.MAGASIN
        self.carrier = carrier
        self.tracking_number = tracking_number or ''
        self.save(update_fields=[
            'status', 'picked_up_at', 'picked_up_by',
            'pickup_method', 'carrier', 'tracking_number',
        ])

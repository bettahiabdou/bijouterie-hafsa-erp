"""
Client models for Bijouterie Hafsa ERP
"""

from django.db import models
from django.utils.translation import gettext_lazy as _
from decimal import Decimal


class Client(models.Model):
    """
    Client model
    """

    class ClientType(models.TextChoices):
        REGULAR = 'regular', _('Particulier')
        VIP = 'vip', _('VIP')
        WHOLESALE = 'wholesale', _('Grossiste')

    # Basic info
    code = models.CharField(
        _('Code'),
        max_length=20,
        unique=True
    )
    first_name = models.CharField(_('Prénom'), max_length=100)
    last_name = models.CharField(_('Nom'), max_length=100)
    first_name_ar = models.CharField(
        _('Prénom (Arabe)'),
        max_length=100,
        blank=True
    )
    last_name_ar = models.CharField(
        _('Nom (Arabe)'),
        max_length=100,
        blank=True
    )
    client_type = models.CharField(
        _('Type de client'),
        max_length=20,
        choices=ClientType.choices,
        default=ClientType.REGULAR
    )

    # Contact info
    phone = models.CharField(_('Téléphone'), max_length=20)
    phone_2 = models.CharField(_('Téléphone 2'), max_length=20, blank=True)
    email = models.EmailField(_('Email'), blank=True)
    address = models.TextField(_('Adresse'), blank=True)
    city = models.CharField(_('Ville'), max_length=100, blank=True)

    # Identity
    cin = models.CharField(
        _('CIN'),
        max_length=20,
        blank=True,
        help_text=_('Carte d\'Identité Nationale')
    )

    # Personal info
    date_of_birth = models.DateField(
        _('Date de naissance'),
        null=True,
        blank=True
    )
    wedding_anniversary = models.DateField(
        _('Anniversaire de mariage'),
        null=True,
        blank=True
    )

    # Preferences
    preferences = models.TextField(
        _('Préférences'),
        blank=True,
        help_text=_('Ex: Préfère or 18K, style moderne')
    )
    preferred_metal = models.ForeignKey(
        'settings_app.MetalType',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        verbose_name=_('Métal préféré')
    )
    preferred_purity = models.ForeignKey(
        'settings_app.MetalPurity',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        verbose_name=_('Titre préféré')
    )

    # Credit
    credit_limit = models.DecimalField(
        _('Limite de crédit'),
        max_digits=12,
        decimal_places=2,
        default=0,
        help_text=_('Montant maximum de crédit autorisé')
    )

    # Loyalty (for future use)
    loyalty_points = models.PositiveIntegerField(
        _('Points de fidélité'),
        default=0
    )

    # Status
    is_active = models.BooleanField(_('Actif'), default=True)

    # Tracking
    notes = models.TextField(_('Notes'), blank=True)
    created_at = models.DateTimeField(_('Créé le'), auto_now_add=True)
    updated_at = models.DateTimeField(_('Modifié le'), auto_now=True)

    class Meta:
        verbose_name = _('Client')
        verbose_name_plural = _('Clients')
        ordering = ['last_name', 'first_name']

    def __str__(self):
        return f"{self.code} - {self.full_name}"

    @property
    def full_name(self):
        return f"{self.first_name} {self.last_name}"

    @property
    def full_name_ar(self):
        if self.first_name_ar and self.last_name_ar:
            return f"{self.first_name_ar} {self.last_name_ar}"
        return ""

    @property
    def current_balance(self):
        """Calculate current balance (what client owes us)"""
        from sales.models import SaleInvoice
        from payments.models import ClientPayment

        total_sales = SaleInvoice.objects.filter(
            client=self
        ).aggregate(
            total=models.Sum('total_amount')
        )['total'] or Decimal('0')

        total_payments = ClientPayment.objects.filter(
            client=self
        ).aggregate(
            total=models.Sum('amount')
        )['total'] or Decimal('0')

        return total_sales - total_payments

    @property
    def is_over_credit_limit(self):
        """Check if client is over credit limit"""
        if self.credit_limit > 0:
            return self.current_balance > self.credit_limit
        return False

    def save(self, *args, **kwargs):
        # Auto-generate client code if not present
        if not self.code:
            from utils import generate_client_code
            self.code = generate_client_code(self.first_name, self.last_name)
        super().save(*args, **kwargs)


class OldGoldPurchase(models.Model):
    """
    Track old gold purchases from clients
    Separate transaction from sales
    """

    # Reference
    reference = models.CharField(
        _('Référence'),
        max_length=50,
        unique=True
    )
    date = models.DateField(_('Date'))

    # Client (optional - can buy from walk-in)
    client = models.ForeignKey(
        Client,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='old_gold_sales',
        verbose_name=_('Client')
    )

    # Client identity (required for traceability)
    client_name = models.CharField(_('Nom du vendeur'), max_length=200)
    client_cin = models.CharField(
        _('CIN'),
        max_length=20,
        blank=True
    )
    client_phone = models.CharField(
        _('Téléphone'),
        max_length=20,
        blank=True
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
    tested_purity = models.DecimalField(
        _('Pureté testée (%)'),
        max_digits=5,
        decimal_places=2,
        help_text=_('Pureté réelle après test')
    )

    # Weight and pricing
    gross_weight = models.DecimalField(
        _('Poids brut (g)'),
        max_digits=10,
        decimal_places=3
    )
    net_weight = models.DecimalField(
        _('Poids net (g)'),
        max_digits=10,
        decimal_places=3,
        help_text=_('Poids après déduction (pierres, etc.)')
    )
    price_per_gram = models.DecimalField(
        _('Prix par gramme'),
        max_digits=10,
        decimal_places=2
    )
    total_amount = models.DecimalField(
        _('Montant total'),
        max_digits=12,
        decimal_places=2
    )

    # Payment
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

    # Destination
    destination = models.CharField(
        _('Destination'),
        max_length=50,
        choices=[
            ('stock', _('Stock matière première')),
            ('melting', _('Fonte')),
            ('resale', _('Revente')),
            ('refinery', _('Raffinerie')),
        ],
        default='stock'
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
        verbose_name = _('Achat ancien or')
        verbose_name_plural = _('Achats ancien or')
        ordering = ['-date']

    def __str__(self):
        return f"{self.reference} - {self.client_name} - {self.net_weight}g"

    def save(self, *args, **kwargs):
        # Calculate total amount
        self.total_amount = self.net_weight * self.price_per_gram
        super().save(*args, **kwargs)

from django.db import models
from django.utils.translation import gettext_lazy as _
from django.core.validators import MinValueValidator
from decimal import Decimal


class Quote(models.Model):
    """Model for customer quotes/estimates"""

    class Status(models.TextChoices):
        DRAFT = 'draft', _('Brouillon')
        SENT = 'sent', _('Envoyé')
        ACCEPTED = 'accepted', _('Accepté')
        REJECTED = 'rejected', _('Rejeté')
        EXPIRED = 'expired', _('Expiré')
        CONVERTED = 'converted', _('Converti en commande')

    # Identification
    reference = models.CharField(
        _('Référence'),
        max_length=50,
        unique=True
    )

    # Client info
    client = models.ForeignKey(
        'clients.Client',
        on_delete=models.PROTECT,
        related_name='quotes',
        verbose_name=_('Client')
    )
    contact_person = models.CharField(
        _('Personne contact'),
        max_length=200,
        blank=True
    )

    # Quote details
    description = models.TextField(
        _('Description'),
        blank=True
    )
    specifications = models.JSONField(
        _('Spécifications'),
        default=dict,
        blank=True
    )

    # Costs
    subtotal_dh = models.DecimalField(
        _('Sous-total (DH)'),
        max_digits=12,
        decimal_places=2,
        validators=[MinValueValidator(Decimal('0'))]
    )
    discount_percent = models.DecimalField(
        _('Remise (%)'),
        max_digits=5,
        decimal_places=2,
        default=0,
        validators=[MinValueValidator(Decimal('0'))]
    )
    discount_amount_dh = models.DecimalField(
        _('Montant de la remise (DH)'),
        max_digits=12,
        decimal_places=2,
        default=0,
        validators=[MinValueValidator(Decimal('0'))]
    )
    tax_amount_dh = models.DecimalField(
        _('Montant taxe (DH)'),
        max_digits=12,
        decimal_places=2,
        default=0,
        validators=[MinValueValidator(Decimal('0'))]
    )
    total_amount_dh = models.DecimalField(
        _('Montant total (DH)'),
        max_digits=12,
        decimal_places=2,
        validators=[MinValueValidator(Decimal('0'))]
    )

    # Validity
    issued_date = models.DateField(
        _('Date d\'émission'),
        auto_now_add=True
    )
    valid_until_date = models.DateField(
        _('Valide jusqu\'au')
    )

    # Status
    status = models.CharField(
        _('Statut'),
        max_length=20,
        choices=Status.choices,
        default=Status.DRAFT
    )

    # Related sale
    converted_sale = models.OneToOneField(
        'sales.SaleInvoice',
        on_delete=models.SET_NULL,
        related_name='source_quote',
        verbose_name=_('Commande convertie'),
        null=True,
        blank=True
    )

    # Metadata
    notes = models.TextField(
        _('Notes internes'),
        blank=True
    )
    terms_conditions = models.TextField(
        _('Conditions générales'),
        blank=True
    )
    created_by = models.ForeignKey(
        'users.User',
        on_delete=models.SET_NULL,
        related_name='quotes_created',
        verbose_name=_('Créé par'),
        null=True
    )
    created_at = models.DateTimeField(_('Créé le'), auto_now_add=True)
    updated_at = models.DateTimeField(_('Modifié le'), auto_now=True)

    class Meta:
        verbose_name = _('Devis')
        verbose_name_plural = _('Devis')
        ordering = ['-issued_date']

    def __str__(self):
        return f"{self.reference} - {self.client.name}"

    def save(self, *args, **kwargs):
        # Auto-generate reference if not present
        if not self.reference:
            from utils import generate_quote_reference
            self.reference = generate_quote_reference()

        # Auto-calculate totals
        self.discount_amount_dh = self.subtotal_dh * (self.discount_percent / 100)
        self.total_amount_dh = (
            self.subtotal_dh -
            self.discount_amount_dh +
            self.tax_amount_dh
        )
        super().save(*args, **kwargs)


class QuoteItem(models.Model):
    """Line items in a quote"""

    quote = models.ForeignKey(
        Quote,
        on_delete=models.CASCADE,
        related_name='items',
        verbose_name=_('Devis')
    )
    product = models.ForeignKey(
        'products.Product',
        on_delete=models.SET_NULL,
        related_name='quote_items',
        verbose_name=_('Produit'),
        null=True,
        blank=True
    )
    description = models.CharField(
        _('Description'),
        max_length=500
    )
    quantity = models.PositiveIntegerField(
        _('Quantité'),
        default=1
    )
    unit_price_dh = models.DecimalField(
        _('Prix unitaire (DH)'),
        max_digits=12,
        decimal_places=2,
        validators=[MinValueValidator(Decimal('0'))]
    )
    line_total_dh = models.DecimalField(
        _('Total (DH)'),
        max_digits=12,
        decimal_places=2,
        validators=[MinValueValidator(Decimal('0'))]
    )

    class Meta:
        verbose_name = _('Article de devis')
        verbose_name_plural = _('Articles de devis')

    def __str__(self):
        return f"{self.quote.reference} - {self.description}"

    def save(self, *args, **kwargs):
        self.line_total_dh = self.quantity * self.unit_price_dh
        super().save(*args, **kwargs)

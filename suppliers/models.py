"""
Supplier models for Bijouterie Hafsa ERP
Includes suppliers, artisans (façonniers), and their bank accounts
"""

from django.db import models
from django.utils.translation import gettext_lazy as _
from decimal import Decimal


class Supplier(models.Model):
    """
    Supplier model - includes jewelry suppliers, raw material suppliers,
    stone suppliers, and artisans (façonniers)
    """

    class SupplierType(models.TextChoices):
        JEWELRY = 'jewelry', _('Grossiste bijoux')
        RAW_MATERIAL = 'raw_material', _('Fournisseur matière première')
        STONES = 'stones', _('Fournisseur pierres')
        ARTISAN = 'artisan', _('Artisan/Façonnier')
        OTHER = 'other', _('Autre')

    # Basic info
    code = models.CharField(
        _('Code'),
        max_length=20,
        unique=True
    )
    name = models.CharField(_('Nom'), max_length=200)
    name_ar = models.CharField(_('Nom (Arabe)'), max_length=200, blank=True)
    supplier_type = models.CharField(
        _('Type de fournisseur'),
        max_length=20,
        choices=SupplierType.choices,
        default=SupplierType.JEWELRY
    )

    # Contact info
    contact_person = models.CharField(
        _('Personne de contact'),
        max_length=100,
        blank=True
    )
    phone = models.CharField(_('Téléphone'), max_length=20, blank=True)
    phone_2 = models.CharField(_('Téléphone 2'), max_length=20, blank=True)
    email = models.EmailField(_('Email'), blank=True)
    address = models.TextField(_('Adresse'), blank=True)
    city = models.CharField(_('Ville'), max_length=100, blank=True)

    # Business info
    ice = models.CharField(
        _('ICE'),
        max_length=20,
        blank=True,
        help_text=_('Identifiant Commun de l\'Entreprise')
    )
    rc = models.CharField(
        _('RC'),
        max_length=20,
        blank=True,
        help_text=_('Registre de Commerce')
    )

    # For artisans
    specialty = models.CharField(
        _('Spécialité'),
        max_length=200,
        blank=True,
        help_text=_('Ex: Bagues, Chaînes, Sertissage')
    )

    # Financial
    credit_limit = models.DecimalField(
        _('Limite de crédit'),
        max_digits=12,
        decimal_places=2,
        default=0,
        help_text=_('Montant maximum de crédit autorisé')
    )
    payment_terms = models.CharField(
        _('Conditions de paiement'),
        max_length=100,
        blank=True,
        help_text=_('Ex: 30 jours, Comptant')
    )

    # Status
    is_active = models.BooleanField(_('Actif'), default=True)

    # Tracking
    notes = models.TextField(_('Notes'), blank=True)
    created_at = models.DateTimeField(_('Créé le'), auto_now_add=True)
    updated_at = models.DateTimeField(_('Modifié le'), auto_now=True)

    class Meta:
        verbose_name = _('Fournisseur')
        verbose_name_plural = _('Fournisseurs')
        ordering = ['name']

    def __str__(self):
        return f"{self.code} - {self.name}"

    @property
    def is_artisan(self):
        return self.supplier_type == self.SupplierType.ARTISAN

    @property
    def current_balance(self):
        """Calculate current balance (what we owe)"""
        from purchases.models import PurchaseInvoice
        from payments.models import SupplierPayment

        total_purchases = PurchaseInvoice.objects.filter(
            supplier=self
        ).aggregate(
            total=models.Sum('total_amount')
        )['total'] or Decimal('0')

        total_payments = SupplierPayment.objects.filter(
            supplier=self
        ).aggregate(
            total=models.Sum('amount')
        )['total'] or Decimal('0')

        return total_purchases - total_payments

    def save(self, *args, **kwargs):
        # Auto-generate supplier code if not present
        if not self.code:
            from utils import generate_supplier_code
            self.code = generate_supplier_code()
        super().save(*args, **kwargs)


class SupplierBankAccount(models.Model):
    """
    Bank accounts for suppliers
    """
    supplier = models.ForeignKey(
        Supplier,
        on_delete=models.CASCADE,
        related_name='bank_accounts',
        verbose_name=_('Fournisseur')
    )
    bank_name = models.CharField(_('Nom de la banque'), max_length=100)
    account_name = models.CharField(
        _('Nom du titulaire'),
        max_length=100,
        blank=True
    )
    account_number = models.CharField(
        _('Numéro de compte'),
        max_length=50,
        blank=True
    )
    rib = models.CharField(
        _('RIB'),
        max_length=30,
        blank=True
    )
    is_default = models.BooleanField(_('Compte par défaut'), default=False)
    created_at = models.DateTimeField(_('Créé le'), auto_now_add=True)

    class Meta:
        verbose_name = _('Compte bancaire fournisseur')
        verbose_name_plural = _('Comptes bancaires fournisseurs')

    def __str__(self):
        return f"{self.supplier.name} - {self.bank_name}"

    def save(self, *args, **kwargs):
        if self.is_default:
            SupplierBankAccount.objects.filter(
                supplier=self.supplier, is_default=True
            ).exclude(pk=self.pk).update(is_default=False)
        super().save(*args, **kwargs)


class ArtisanJob(models.Model):
    """
    Track jobs sent to artisans
    Includes gold given and gold returned
    """

    class JobStatus(models.TextChoices):
        PENDING = 'pending', _('En attente')
        IN_PROGRESS = 'in_progress', _('En cours')
        COMPLETED = 'completed', _('Terminé')
        DELIVERED = 'delivered', _('Livré')
        CANCELLED = 'cancelled', _('Annulé')

    # Reference
    reference = models.CharField(
        _('Référence'),
        max_length=50,
        unique=True
    )

    # Artisan
    artisan = models.ForeignKey(
        Supplier,
        on_delete=models.PROTECT,
        related_name='jobs',
        verbose_name=_('Artisan'),
        limit_choices_to={'supplier_type': 'artisan'}
    )

    # Job details
    description = models.TextField(_('Description du travail'))
    status = models.CharField(
        _('Statut'),
        max_length=20,
        choices=JobStatus.choices,
        default=JobStatus.PENDING
    )

    # Metal given to artisan
    metal_type = models.ForeignKey(
        'settings_app.MetalType',
        on_delete=models.PROTECT,
        verbose_name=_('Type de métal'),
        null=True,
        blank=True
    )
    metal_purity = models.ForeignKey(
        'settings_app.MetalPurity',
        on_delete=models.PROTECT,
        verbose_name=_('Titre'),
        null=True,
        blank=True
    )
    weight_given = models.DecimalField(
        _('Poids donné (g)'),
        max_digits=10,
        decimal_places=3,
        default=0
    )

    # Stones given (optional)
    stones_given = models.TextField(
        _('Pierres données'),
        blank=True,
        help_text=_('Description des pierres fournies')
    )

    # Returned
    weight_returned = models.DecimalField(
        _('Poids retourné (g)'),
        max_digits=10,
        decimal_places=3,
        default=0,
        help_text=_('Poids total des pièces finies')
    )
    pieces_count = models.PositiveIntegerField(
        _('Nombre de pièces'),
        default=0
    )

    # Pricing
    labor_cost_per_piece = models.DecimalField(
        _('Coût main d\'œuvre par pièce'),
        max_digits=10,
        decimal_places=2,
        default=0
    )
    total_labor_cost = models.DecimalField(
        _('Coût total main d\'œuvre'),
        max_digits=12,
        decimal_places=2,
        default=0
    )

    # Dates
    date_sent = models.DateField(_('Date d\'envoi'))
    expected_date = models.DateField(
        _('Date prévue'),
        null=True,
        blank=True
    )
    date_received = models.DateField(
        _('Date de réception'),
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
        verbose_name = _('Travail artisan')
        verbose_name_plural = _('Travaux artisans')
        ordering = ['-date_sent']

    def __str__(self):
        return f"{self.reference} - {self.artisan.name}"

    def save(self, *args, **kwargs):
        # Calculate total labor cost
        self.total_labor_cost = self.pieces_count * self.labor_cost_per_piece
        super().save(*args, **kwargs)

    @property
    def weight_loss(self):
        """Calculate weight loss during fabrication"""
        if self.weight_given and self.weight_returned:
            return self.weight_given - self.weight_returned
        return 0

    @property
    def weight_loss_percentage(self):
        """Calculate weight loss percentage"""
        if self.weight_given > 0 and self.weight_returned:
            return ((self.weight_given - self.weight_returned) / self.weight_given) * 100
        return 0

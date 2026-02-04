"""
Settings models for Bijouterie Hafsa ERP
Configurable parameters: metal types, categories, purities, etc.
"""

from django.db import models
from django.utils.translation import gettext_lazy as _
from django.core.validators import MinValueValidator, MaxValueValidator


class MetalType(models.Model):
    """
    Types of metals (Or, Argent, Platine, etc.)
    """
    name = models.CharField(_('Nom'), max_length=50, unique=True)
    name_ar = models.CharField(_('Nom (Arabe)'), max_length=50, blank=True)
    code = models.CharField(_('Code'), max_length=10, unique=True)
    is_active = models.BooleanField(_('Actif'), default=True)
    created_at = models.DateTimeField(_('Créé le'), auto_now_add=True)
    updated_at = models.DateTimeField(_('Modifié le'), auto_now=True)

    class Meta:
        verbose_name = _('Type de métal')
        verbose_name_plural = _('Types de métaux')
        ordering = ['name']

    def __str__(self):
        return self.name


class MetalPurity(models.Model):
    """
    Metal purities (18K, 21K, 24K, 925, etc.)
    """
    metal_type = models.ForeignKey(
        MetalType,
        on_delete=models.CASCADE,
        related_name='purities',
        verbose_name=_('Type de métal')
    )
    name = models.CharField(_('Nom'), max_length=20)  # e.g., "18K", "750", "925"
    purity_percentage = models.DecimalField(
        _('Pourcentage de pureté'),
        max_digits=5,
        decimal_places=2,
        validators=[MinValueValidator(0), MaxValueValidator(100)],
        help_text=_('Exemple: 75.00 pour 18K')
    )
    hallmark = models.CharField(
        _('Poinçon'),
        max_length=20,
        blank=True,
        help_text=_('Poinçon officiel')
    )
    is_active = models.BooleanField(_('Actif'), default=True)
    created_at = models.DateTimeField(_('Créé le'), auto_now_add=True)

    class Meta:
        verbose_name = _('Titre/Pureté')
        verbose_name_plural = _('Titres/Puretés')
        ordering = ['metal_type', '-purity_percentage']
        unique_together = ['metal_type', 'name']

    def __str__(self):
        return f"{self.metal_type.name} {self.name} ({self.purity_percentage}%)"


class ProductCategory(models.Model):
    """
    Product categories (Bagues, Colliers, Bracelets, etc.)
    """
    name = models.CharField(_('Nom'), max_length=100, unique=True)
    name_ar = models.CharField(_('Nom (Arabe)'), max_length=100, blank=True)
    parent = models.ForeignKey(
        'self',
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name='children',
        verbose_name=_('Catégorie parente')
    )
    code = models.CharField(_('Code'), max_length=20, unique=True)
    description = models.TextField(_('Description'), blank=True)
    is_active = models.BooleanField(_('Actif'), default=True)
    display_order = models.PositiveIntegerField(_('Ordre d\'affichage'), default=0)
    created_at = models.DateTimeField(_('Créé le'), auto_now_add=True)
    updated_at = models.DateTimeField(_('Modifié le'), auto_now=True)

    class Meta:
        verbose_name = _('Catégorie de produit')
        verbose_name_plural = _('Catégories de produits')
        ordering = ['display_order', 'name']

    def __str__(self):
        if self.parent:
            return f"{self.parent.name} > {self.name}"
        return self.name


class StoneType(models.Model):
    """
    Types of stones (Diamant, Rubis, Saphir, etc.)
    """
    name = models.CharField(_('Nom'), max_length=50, unique=True)
    name_ar = models.CharField(_('Nom (Arabe)'), max_length=50, blank=True)
    code = models.CharField(_('Code'), max_length=10, unique=True)
    is_precious = models.BooleanField(
        _('Pierre précieuse'),
        default=False,
        help_text=_('Diamant, Rubis, Saphir, Émeraude')
    )
    requires_certificate = models.BooleanField(
        _('Certificat requis'),
        default=False
    )
    is_active = models.BooleanField(_('Actif'), default=True)
    created_at = models.DateTimeField(_('Créé le'), auto_now_add=True)

    class Meta:
        verbose_name = _('Type de pierre')
        verbose_name_plural = _('Types de pierres')
        ordering = ['name']

    def __str__(self):
        return self.name


class StoneClarity(models.Model):
    """
    Stone clarity grades (IF, VVS1, VVS2, VS1, VS2, SI1, SI2, I1, I2, I3)
    """
    code = models.CharField(_('Code'), max_length=10, unique=True)
    name = models.CharField(_('Nom'), max_length=50)
    description = models.TextField(_('Description'), blank=True)
    rank = models.PositiveIntegerField(
        _('Rang'),
        default=0,
        help_text=_('Plus le rang est bas, meilleure est la clarté')
    )
    is_active = models.BooleanField(_('Actif'), default=True)

    class Meta:
        verbose_name = _('Clarté de pierre')
        verbose_name_plural = _('Clartés de pierres')
        ordering = ['rank']

    def __str__(self):
        return f"{self.code} - {self.name}"


class StoneColor(models.Model):
    """
    Stone color grades (D, E, F, G, H, I, J, K, etc.)
    """
    code = models.CharField(_('Code'), max_length=10, unique=True)
    name = models.CharField(_('Nom'), max_length=50)
    description = models.TextField(_('Description'), blank=True)
    rank = models.PositiveIntegerField(
        _('Rang'),
        default=0,
        help_text=_('Plus le rang est bas, meilleure est la couleur')
    )
    is_active = models.BooleanField(_('Actif'), default=True)

    class Meta:
        verbose_name = _('Couleur de pierre')
        verbose_name_plural = _('Couleurs de pierres')
        ordering = ['rank']

    def __str__(self):
        return f"{self.code} - {self.name}"


class StoneCut(models.Model):
    """
    Stone cut grades (Excellent, Very Good, Good, Fair, Poor)
    """
    code = models.CharField(_('Code'), max_length=20, unique=True)
    name = models.CharField(_('Nom'), max_length=50)
    name_ar = models.CharField(_('Nom (Arabe)'), max_length=50, blank=True)
    rank = models.PositiveIntegerField(_('Rang'), default=0)
    is_active = models.BooleanField(_('Actif'), default=True)

    class Meta:
        verbose_name = _('Taille de pierre')
        verbose_name_plural = _('Tailles de pierres')
        ordering = ['rank']

    def __str__(self):
        return self.name


class PaymentMethod(models.Model):
    """
    Payment methods (Espèces, Carte bancaire, Virement, Chèque, etc.)
    """
    name = models.CharField(_('Nom'), max_length=50, unique=True)
    name_ar = models.CharField(_('Nom (Arabe)'), max_length=50, blank=True)
    code = models.CharField(_('Code'), max_length=20, unique=True)
    requires_reference = models.BooleanField(
        _('Référence obligatoire'),
        default=False,
        help_text=_('Ex: numéro de chèque, référence virement')
    )
    requires_bank_account = models.BooleanField(
        _('Compte bancaire obligatoire'),
        default=False
    )
    is_active = models.BooleanField(_('Actif'), default=True)
    display_order = models.PositiveIntegerField(_('Ordre d\'affichage'), default=0)
    created_at = models.DateTimeField(_('Créé le'), auto_now_add=True)

    class Meta:
        verbose_name = _('Mode de paiement')
        verbose_name_plural = _('Modes de paiement')
        ordering = ['display_order', 'name']

    def __str__(self):
        return self.name


class BankAccount(models.Model):
    """
    Bank accounts for the business
    """
    # Auto-generated reference
    reference = models.CharField(
        _('Référence'),
        max_length=50,
        unique=True,
        editable=False,
        help_text=_('Référence unique générée automatiquement')
    )
    bank_name = models.CharField(_('Nom de la banque'), max_length=100)
    account_name = models.CharField(_('Nom du compte'), max_length=100)
    account_number = models.CharField(
        _('Numéro de compte'),
        max_length=50,
        blank=True
    )
    rib = models.CharField(
        _('RIB'),
        max_length=30,
        blank=True,
        help_text=_('Relevé d\'Identité Bancaire')
    )
    swift = models.CharField(
        _('Code SWIFT'),
        max_length=20,
        blank=True
    )
    is_active = models.BooleanField(_('Actif'), default=True)
    is_default = models.BooleanField(
        _('Compte par défaut'),
        default=False
    )
    notes = models.TextField(_('Notes'), blank=True)
    created_at = models.DateTimeField(_('Créé le'), auto_now_add=True)
    updated_at = models.DateTimeField(_('Modifié le'), auto_now=True)

    class Meta:
        verbose_name = _('Compte bancaire')
        verbose_name_plural = _('Comptes bancaires')
        ordering = ['bank_name', 'account_name']

    def __str__(self):
        return f"{self.reference} - {self.bank_name} - {self.account_name}"

    def save(self, *args, **kwargs):
        # Auto-generate reference if not present
        if not self.reference:
            from utils import generate_bank_account_code
            self.reference = generate_bank_account_code()

        # Ensure only one default account
        if self.is_default:
            BankAccount.objects.filter(is_default=True).exclude(pk=self.pk).update(is_default=False)
        super().save(*args, **kwargs)


class StockLocation(models.Model):
    """
    Stock locations (Vitrine 1, Coffre, Réserve, etc.)
    """
    name = models.CharField(_('Nom'), max_length=100, unique=True)
    name_ar = models.CharField(_('Nom (Arabe)'), max_length=100, blank=True)
    code = models.CharField(_('Code'), max_length=20, unique=True)
    description = models.TextField(_('Description'), blank=True)
    is_secure = models.BooleanField(
        _('Emplacement sécurisé'),
        default=False,
        help_text=_('Coffre-fort, etc.')
    )
    is_active = models.BooleanField(_('Actif'), default=True)
    created_at = models.DateTimeField(_('Créé le'), auto_now_add=True)

    class Meta:
        verbose_name = _('Emplacement de stock')
        verbose_name_plural = _('Emplacements de stock')
        ordering = ['name']

    def __str__(self):
        return self.name


class DeliveryMethod(models.Model):
    """
    Delivery methods (Retrait boutique, Livraison interne, Amana, etc.)
    """
    name = models.CharField(_('Nom'), max_length=100, unique=True)
    name_ar = models.CharField(_('Nom (Arabe)'), max_length=100, blank=True)
    code = models.CharField(_('Code'), max_length=20, unique=True)
    is_internal = models.BooleanField(
        _('Livraison interne'),
        default=False,
        help_text=_('Livreur de la boutique')
    )
    default_cost = models.DecimalField(
        _('Coût par défaut'),
        max_digits=10,
        decimal_places=2,
        default=0
    )
    is_active = models.BooleanField(_('Actif'), default=True)
    created_at = models.DateTimeField(_('Créé le'), auto_now_add=True)

    class Meta:
        verbose_name = _('Mode de livraison')
        verbose_name_plural = _('Modes de livraison')
        ordering = ['name']

    def __str__(self):
        return self.name


class DeliveryPerson(models.Model):
    """
    Internal delivery persons
    """
    name = models.CharField(_('Nom'), max_length=100)
    phone = models.CharField(_('Téléphone'), max_length=20)
    is_active = models.BooleanField(_('Actif'), default=True)
    notes = models.TextField(_('Notes'), blank=True)
    created_at = models.DateTimeField(_('Créé le'), auto_now_add=True)

    class Meta:
        verbose_name = _('Livreur')
        verbose_name_plural = _('Livreurs')
        ordering = ['name']

    def __str__(self):
        return self.name


class RepairType(models.Model):
    """
    Types of repairs (Mise à taille, Soudure, Polissage, etc.)
    """
    name = models.CharField(_('Nom'), max_length=100, unique=True)
    name_ar = models.CharField(_('Nom (Arabe)'), max_length=100, blank=True)
    code = models.CharField(_('Code'), max_length=20, unique=True)
    default_price = models.DecimalField(
        _('Prix par défaut'),
        max_digits=10,
        decimal_places=2,
        default=0
    )
    estimated_duration_days = models.PositiveIntegerField(
        _('Durée estimée (jours)'),
        default=1
    )
    is_active = models.BooleanField(_('Actif'), default=True)
    created_at = models.DateTimeField(_('Créé le'), auto_now_add=True)

    class Meta:
        verbose_name = _('Type de réparation')
        verbose_name_plural = _('Types de réparations')
        ordering = ['name']

    def __str__(self):
        return self.name


class CertificateIssuer(models.Model):
    """
    Certificate issuers (GIA, IGI, HRD, etc.)
    """
    name = models.CharField(_('Nom'), max_length=100, unique=True)
    code = models.CharField(_('Code'), max_length=20, unique=True)
    website = models.URLField(_('Site web'), blank=True)
    is_active = models.BooleanField(_('Actif'), default=True)
    created_at = models.DateTimeField(_('Créé le'), auto_now_add=True)

    class Meta:
        verbose_name = _('Émetteur de certificat')
        verbose_name_plural = _('Émetteurs de certificats')
        ordering = ['name']

    def __str__(self):
        return self.name


class CompanySettings(models.Model):
    """
    Company-wide settings (singleton)
    """
    company_name = models.CharField(_('Nom de l\'entreprise'), max_length=200)
    company_name_ar = models.CharField(
        _('Nom de l\'entreprise (Arabe)'),
        max_length=200,
        blank=True
    )
    address = models.TextField(_('Adresse'), blank=True)
    phone = models.CharField(_('Téléphone'), max_length=20, blank=True)
    email = models.EmailField(_('Email'), blank=True)
    website = models.URLField(_('Site web'), blank=True)
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
    logo = models.ImageField(
        _('Logo'),
        upload_to='company/',
        blank=True,
        null=True
    )

    # Default margins
    default_margin_type = models.CharField(
        _('Type de marge par défaut'),
        max_length=20,
        choices=[
            ('percentage', _('Pourcentage')),
            ('fixed', _('Montant fixe')),
        ],
        default='percentage'
    )
    default_margin_value = models.DecimalField(
        _('Valeur de marge par défaut'),
        max_digits=10,
        decimal_places=2,
        default=25,
        help_text=_('Pourcentage ou montant fixe selon le type')
    )

    # Quote settings
    quote_validity_days = models.PositiveIntegerField(
        _('Validité des devis (jours)'),
        default=30
    )

    # Custom order settings
    custom_order_deposit_percent = models.DecimalField(
        _('Acompte commande sur mesure (%)'),
        max_digits=5,
        decimal_places=2,
        default=50
    )

    created_at = models.DateTimeField(_('Créé le'), auto_now_add=True)
    updated_at = models.DateTimeField(_('Modifié le'), auto_now=True)

    class Meta:
        verbose_name = _('Paramètres de l\'entreprise')
        verbose_name_plural = _('Paramètres de l\'entreprise')

    def __str__(self):
        return self.company_name

    def save(self, *args, **kwargs):
        # Ensure only one instance exists
        self.pk = 1
        super().save(*args, **kwargs)

    @classmethod
    def get_settings(cls):
        """Get or create company settings"""
        obj, created = cls.objects.get_or_create(pk=1, defaults={
            'company_name': 'Bijouterie Hafsa'
        })
        return obj

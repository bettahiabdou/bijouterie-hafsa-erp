"""
Product models for Bijouterie Hafsa ERP
Core models for jewelry items, stones, and raw materials
"""

from django.db import models
from django.utils.translation import gettext_lazy as _
from django.core.validators import MinValueValidator
from decimal import Decimal


class Product(models.Model):
    """
    Main product model for jewelry items
    Each piece has a unique ID and can be tracked individually
    """

    class Status(models.TextChoices):
        AVAILABLE = 'available', _('Disponible')
        RESERVED = 'reserved', _('Réservé')
        SOLD = 'sold', _('Vendu')
        IN_REPAIR = 'in_repair', _('En réparation')
        CONSIGNED_IN = 'consigned_in', _('En consignation (reçu)')
        CONSIGNED_OUT = 'consigned_out', _('En consignation (prêté)')
        RETURNED = 'returned', _('Retourné')
        CUSTOM_ORDER = 'custom_order', _('Commande sur mesure')

    class ProductType(models.TextChoices):
        FINISHED = 'finished', _('Bijou fini')
        RAW_MATERIAL = 'raw_material', _('Matière première')
        STONE = 'stone', _('Pierre')
        COMPONENT = 'component', _('Composant')

    # Identification
    reference = models.CharField(
        _('Référence'),
        max_length=50,
        unique=True,
        help_text=_('Référence unique du produit')
    )
    barcode = models.CharField(
        _('Code-barres'),
        max_length=100,
        unique=True,
        blank=True,
        null=True
    )
    rfid_tag = models.CharField(
        _('Tag RFID'),
        max_length=100,
        unique=True,
        blank=True,
        null=True
    )

    # Basic info
    name = models.CharField(_('Nom'), max_length=200)
    name_ar = models.CharField(_('Nom (Arabe)'), max_length=200, blank=True)
    description = models.TextField(_('Description'), blank=True)
    product_type = models.CharField(
        _('Type de produit'),
        max_length=20,
        choices=ProductType.choices,
        default=ProductType.FINISHED
    )

    # Classification
    category = models.ForeignKey(
        'settings_app.ProductCategory',
        on_delete=models.PROTECT,
        related_name='products',
        verbose_name=_('Catégorie')
    )

    # Metal details
    metal_type = models.ForeignKey(
        'settings_app.MetalType',
        on_delete=models.PROTECT,
        related_name='products',
        verbose_name=_('Type de métal'),
        null=True,
        blank=True
    )
    metal_purity = models.ForeignKey(
        'settings_app.MetalPurity',
        on_delete=models.PROTECT,
        related_name='products',
        verbose_name=_('Titre/Pureté'),
        null=True,
        blank=True
    )

    # Weight
    gross_weight = models.DecimalField(
        _('Poids brut (g)'),
        max_digits=10,
        decimal_places=3,
        validators=[MinValueValidator(Decimal('0'))],
        default=0
    )
    net_weight = models.DecimalField(
        _('Poids net (g)'),
        max_digits=10,
        decimal_places=3,
        validators=[MinValueValidator(Decimal('0'))],
        default=0,
        help_text=_('Poids du métal sans les pierres')
    )

    # Dimensions
    size = models.CharField(
        _('Taille'),
        max_length=20,
        blank=True,
        help_text=_('Taille de bague, longueur de chaîne, etc.')
    )
    length = models.DecimalField(
        _('Longueur (cm)'),
        max_digits=6,
        decimal_places=2,
        null=True,
        blank=True
    )

    # Pricing - Purchase
    purchase_price_per_gram = models.DecimalField(
        _('Prix d\'achat par gramme'),
        max_digits=10,
        decimal_places=2,
        validators=[MinValueValidator(Decimal('0'))],
        default=0
    )
    metal_cost = models.DecimalField(
        _('Coût métal'),
        max_digits=12,
        decimal_places=2,
        validators=[MinValueValidator(Decimal('0'))],
        default=0,
        help_text=_('Calculé: poids net × prix/gramme')
    )
    labor_cost = models.DecimalField(
        _('Main d\'œuvre (façon)'),
        max_digits=10,
        decimal_places=2,
        validators=[MinValueValidator(Decimal('0'))],
        default=0
    )
    stone_cost = models.DecimalField(
        _('Coût des pierres'),
        max_digits=12,
        decimal_places=2,
        validators=[MinValueValidator(Decimal('0'))],
        default=0
    )
    other_cost = models.DecimalField(
        _('Autres coûts'),
        max_digits=10,
        decimal_places=2,
        validators=[MinValueValidator(Decimal('0'))],
        default=0
    )
    total_cost = models.DecimalField(
        _('Coût total'),
        max_digits=12,
        decimal_places=2,
        validators=[MinValueValidator(Decimal('0'))],
        default=0,
        help_text=_('Calculé: métal + main d\'œuvre + pierres + autres')
    )

    # Pricing - Sale
    margin_type = models.CharField(
        _('Type de marge'),
        max_length=20,
        choices=[
            ('percentage', _('Pourcentage')),
            ('fixed', _('Montant fixe')),
        ],
        default='percentage'
    )
    margin_value = models.DecimalField(
        _('Valeur de marge'),
        max_digits=10,
        decimal_places=2,
        default=25
    )
    selling_price = models.DecimalField(
        _('Prix de vente'),
        max_digits=12,
        decimal_places=2,
        validators=[MinValueValidator(Decimal('0'))],
        default=0
    )
    minimum_price = models.DecimalField(
        _('Prix minimum'),
        max_digits=12,
        decimal_places=2,
        validators=[MinValueValidator(Decimal('0'))],
        default=0,
        help_text=_('Prix en dessous duquel la vente nécessite approbation')
    )

    # Stock info
    status = models.CharField(
        _('Statut'),
        max_length=20,
        choices=Status.choices,
        default=Status.AVAILABLE
    )
    location = models.ForeignKey(
        'settings_app.StockLocation',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='products',
        verbose_name=_('Emplacement')
    )

    # Images
    main_image = models.ImageField(
        _('Image principale'),
        upload_to='products/',
        blank=True,
        null=True
    )

    # Certificate
    has_certificate = models.BooleanField(_('Avec certificat'), default=False)
    certificate_number = models.CharField(
        _('Numéro de certificat'),
        max_length=100,
        blank=True
    )
    certificate_issuer = models.ForeignKey(
        'settings_app.CertificateIssuer',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='products',
        verbose_name=_('Émetteur du certificat')
    )
    certificate_file = models.FileField(
        _('Fichier certificat'),
        upload_to='certificates/',
        blank=True,
        null=True
    )

    # Supplier info
    supplier = models.ForeignKey(
        'suppliers.Supplier',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='products',
        verbose_name=_('Fournisseur')
    )
    purchase_invoice = models.ForeignKey(
        'purchases.PurchaseInvoice',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='products',
        verbose_name=_('Facture d\'achat')
    )

    # Payment info
    bank_account = models.ForeignKey(
        'settings_app.BankAccount',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='product_purchases',
        verbose_name=_('Compte bancaire')
    )

    # Custom order
    is_custom_order = models.BooleanField(
        _('Commande sur mesure'),
        default=False
    )
    custom_order_client = models.ForeignKey(
        'clients.Client',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='custom_orders',
        verbose_name=_('Client (commande sur mesure)')
    )

    # Tracking
    created_by = models.ForeignKey(
        'users.User',
        on_delete=models.SET_NULL,
        null=True,
        related_name='created_products',
        verbose_name=_('Créé par')
    )
    created_at = models.DateTimeField(_('Créé le'), auto_now_add=True)
    updated_at = models.DateTimeField(_('Modifié le'), auto_now=True)

    # Notes
    notes = models.TextField(_('Notes'), blank=True)

    class Meta:
        verbose_name = _('Produit')
        verbose_name_plural = _('Produits')
        ordering = ['-created_at']

    def __str__(self):
        return f"{self.reference} - {self.name}"

    def save(self, *args, **kwargs):
        # Auto-generate reference if not present
        if not self.reference:
            from utils import generate_product_reference
            product_type = 'FIN' if self.product_type == self.ProductType.FINISHED else 'RAW'
            self.reference = generate_product_reference(product_type)

        # Calculate metal cost
        self.metal_cost = self.net_weight * self.purchase_price_per_gram

        # Calculate total cost
        self.total_cost = (
            self.metal_cost +
            self.labor_cost +
            self.stone_cost +
            self.other_cost
        )

        # Calculate selling price based on margin
        # Ensure all values are Decimal to avoid type errors
        if self.margin_type == 'percentage':
            margin_val = Decimal(str(self.margin_value or 0))
            total_cost = Decimal(str(self.total_cost or 0))
            self.selling_price = total_cost * (Decimal('1') + margin_val / Decimal('100'))
        else:
            total_cost = Decimal(str(self.total_cost or 0))
            margin_val = Decimal(str(self.margin_value or 0))
            self.selling_price = total_cost + margin_val

        # Set minimum price to cost if not specified
        if not self.minimum_price:
            self.minimum_price = self.total_cost

        super().save(*args, **kwargs)

    @property
    def profit_margin(self):
        """Calculate profit margin percentage"""
        if self.total_cost > 0:
            return ((self.selling_price - self.total_cost) / self.total_cost) * 100
        return 0

    @property
    def is_below_minimum(self):
        """Check if selling price is below minimum"""
        return self.selling_price < self.minimum_price


class ProductImage(models.Model):
    """
    Additional images for products
    """
    product = models.ForeignKey(
        Product,
        on_delete=models.CASCADE,
        related_name='images',
        verbose_name=_('Produit')
    )
    image = models.ImageField(
        _('Image'),
        upload_to='products/'
    )
    is_primary = models.BooleanField(_('Image principale'), default=False)
    display_order = models.PositiveIntegerField(_('Ordre'), default=0)
    created_at = models.DateTimeField(_('Créé le'), auto_now_add=True)

    class Meta:
        verbose_name = _('Image produit')
        verbose_name_plural = _('Images produit')
        ordering = ['display_order']

    def __str__(self):
        return f"Image de {self.product.reference}"


class ProductStone(models.Model):
    """
    Stones attached to a product
    Tracks the 4Cs for diamonds and other stone details
    """
    product = models.ForeignKey(
        Product,
        on_delete=models.CASCADE,
        related_name='stones',
        verbose_name=_('Produit')
    )
    stone_type = models.ForeignKey(
        'settings_app.StoneType',
        on_delete=models.PROTECT,
        related_name='product_stones',
        verbose_name=_('Type de pierre')
    )

    # Quantity and weight
    quantity = models.PositiveIntegerField(_('Quantité'), default=1)
    carat_weight = models.DecimalField(
        _('Poids (carats)'),
        max_digits=8,
        decimal_places=3,
        validators=[MinValueValidator(Decimal('0'))],
        default=0
    )
    total_carat_weight = models.DecimalField(
        _('Poids total (carats)'),
        max_digits=8,
        decimal_places=3,
        validators=[MinValueValidator(Decimal('0'))],
        default=0,
        help_text=_('Calculé: quantité × poids unitaire')
    )

    # 4Cs (for diamonds)
    clarity = models.ForeignKey(
        'settings_app.StoneClarity',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='product_stones',
        verbose_name=_('Clarté')
    )
    color = models.ForeignKey(
        'settings_app.StoneColor',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='product_stones',
        verbose_name=_('Couleur')
    )
    cut = models.ForeignKey(
        'settings_app.StoneCut',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='product_stones',
        verbose_name=_('Taille')
    )

    # Shape
    shape = models.CharField(
        _('Forme'),
        max_length=50,
        blank=True,
        help_text=_('Rond, Princesse, Ovale, etc.')
    )

    # Pricing
    cost_per_carat = models.DecimalField(
        _('Coût par carat'),
        max_digits=12,
        decimal_places=2,
        validators=[MinValueValidator(Decimal('0'))],
        default=0
    )
    total_cost = models.DecimalField(
        _('Coût total'),
        max_digits=12,
        decimal_places=2,
        validators=[MinValueValidator(Decimal('0'))],
        default=0
    )

    # Certificate
    has_certificate = models.BooleanField(_('Avec certificat'), default=False)
    certificate_number = models.CharField(
        _('Numéro de certificat'),
        max_length=100,
        blank=True
    )
    certificate_issuer = models.ForeignKey(
        'settings_app.CertificateIssuer',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        verbose_name=_('Émetteur du certificat')
    )
    certificate_file = models.FileField(
        _('Fichier certificat'),
        upload_to='certificates/stones/',
        blank=True,
        null=True
    )

    # Notes
    notes = models.TextField(_('Notes'), blank=True)
    created_at = models.DateTimeField(_('Créé le'), auto_now_add=True)
    updated_at = models.DateTimeField(_('Modifié le'), auto_now=True)

    class Meta:
        verbose_name = _('Pierre du produit')
        verbose_name_plural = _('Pierres du produit')

    def __str__(self):
        return f"{self.stone_type.name} - {self.total_carat_weight} ct"

    def save(self, *args, **kwargs):
        # Calculate total carat weight
        self.total_carat_weight = self.quantity * self.carat_weight

        # Calculate total cost
        self.total_cost = self.total_carat_weight * self.cost_per_carat

        super().save(*args, **kwargs)

        # Update product stone cost
        self.update_product_stone_cost()

    def delete(self, *args, **kwargs):
        product = self.product
        super().delete(*args, **kwargs)
        # Update product stone cost after deletion
        total_stone_cost = product.stones.aggregate(
            total=models.Sum('total_cost')
        )['total'] or 0
        product.stone_cost = total_stone_cost
        product.save()

    def update_product_stone_cost(self):
        """Update the product's total stone cost"""
        total_stone_cost = self.product.stones.aggregate(
            total=models.Sum('total_cost')
        )['total'] or 0
        self.product.stone_cost = total_stone_cost
        self.product.save()


class RawMaterial(models.Model):
    """
    Raw materials inventory (gold, silver by weight)
    Tracked by total weight, not individual pieces
    """
    metal_type = models.ForeignKey(
        'settings_app.MetalType',
        on_delete=models.PROTECT,
        related_name='raw_materials',
        verbose_name=_('Type de métal')
    )
    metal_purity = models.ForeignKey(
        'settings_app.MetalPurity',
        on_delete=models.PROTECT,
        related_name='raw_materials',
        verbose_name=_('Titre/Pureté')
    )

    # Stock
    current_weight = models.DecimalField(
        _('Poids actuel (g)'),
        max_digits=12,
        decimal_places=3,
        validators=[MinValueValidator(Decimal('0'))],
        default=0
    )
    minimum_weight = models.DecimalField(
        _('Poids minimum (g)'),
        max_digits=12,
        decimal_places=3,
        validators=[MinValueValidator(Decimal('0'))],
        default=0,
        help_text=_('Alerte quand le stock est en dessous')
    )

    # Pricing
    average_cost_per_gram = models.DecimalField(
        _('Coût moyen par gramme'),
        max_digits=10,
        decimal_places=2,
        validators=[MinValueValidator(Decimal('0'))],
        default=0
    )

    # Location
    location = models.ForeignKey(
        'settings_app.StockLocation',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        verbose_name=_('Emplacement')
    )

    # Tracking
    last_updated = models.DateTimeField(_('Dernière mise à jour'), auto_now=True)
    notes = models.TextField(_('Notes'), blank=True)

    class Meta:
        verbose_name = _('Matière première')
        verbose_name_plural = _('Matières premières')
        unique_together = ['metal_type', 'metal_purity']

    def __str__(self):
        return f"{self.metal_type.name} {self.metal_purity.name} - {self.current_weight}g"

    @property
    def total_value(self):
        """Calculate total value of raw material"""
        return self.current_weight * self.average_cost_per_gram

    @property
    def is_below_minimum(self):
        """Check if stock is below minimum"""
        return self.current_weight < self.minimum_weight


class RawMaterialMovement(models.Model):
    """
    Track movements of raw materials (in/out)
    """

    class MovementType(models.TextChoices):
        PURCHASE = 'purchase', _('Achat')
        SALE = 'sale', _('Vente')
        ARTISAN_OUT = 'artisan_out', _('Envoi artisan')
        ARTISAN_IN = 'artisan_in', _('Retour artisan')
        OLD_GOLD_IN = 'old_gold_in', _('Achat ancien or')
        ADJUSTMENT = 'adjustment', _('Ajustement')
        LOSS = 'loss', _('Perte')

    raw_material = models.ForeignKey(
        RawMaterial,
        on_delete=models.CASCADE,
        related_name='movements',
        verbose_name=_('Matière première')
    )
    movement_type = models.CharField(
        _('Type de mouvement'),
        max_length=20,
        choices=MovementType.choices
    )
    weight = models.DecimalField(
        _('Poids (g)'),
        max_digits=12,
        decimal_places=3,
        help_text=_('Positif pour entrée, négatif pour sortie')
    )
    price_per_gram = models.DecimalField(
        _('Prix par gramme'),
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

    # Reference to related document
    reference = models.CharField(
        _('Référence'),
        max_length=100,
        blank=True,
        help_text=_('Numéro de facture, bon, etc.')
    )

    # Related objects
    supplier = models.ForeignKey(
        'suppliers.Supplier',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        verbose_name=_('Fournisseur')
    )
    artisan = models.ForeignKey(
        'suppliers.Supplier',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='material_movements',
        verbose_name=_('Artisan')
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
        verbose_name = _('Mouvement matière première')
        verbose_name_plural = _('Mouvements matière première')
        ordering = ['-created_at']

    def __str__(self):
        return f"{self.get_movement_type_display()} - {self.weight}g"

    def save(self, *args, **kwargs):
        # Calculate total amount
        self.total_amount = abs(self.weight) * self.price_per_gram

        super().save(*args, **kwargs)

        # Update raw material stock
        self.update_raw_material_stock()

    def update_raw_material_stock(self):
        """Update raw material weight and average cost"""
        movements = self.raw_material.movements.all()

        total_in_weight = Decimal('0')
        total_in_cost = Decimal('0')
        total_out_weight = Decimal('0')

        for movement in movements:
            if movement.weight > 0:
                total_in_weight += movement.weight
                total_in_cost += movement.total_amount
            else:
                total_out_weight += abs(movement.weight)

        self.raw_material.current_weight = total_in_weight - total_out_weight

        if total_in_weight > 0:
            self.raw_material.average_cost_per_gram = total_in_cost / total_in_weight

        self.raw_material.save()


class PrintQueue(models.Model):
    """
    Print queue for Zebra printer labels.
    Stores print jobs when the printer is not directly accessible from the server.
    A local print agent (running in Morocco) polls this queue and sends to printer.
    """

    class Status(models.TextChoices):
        PENDING = 'pending', _('En attente')
        PRINTING = 'printing', _('En cours')
        PRINTED = 'printed', _('Imprimé')
        FAILED = 'failed', _('Échec')
        CANCELLED = 'cancelled', _('Annulé')

    class LabelType(models.TextChoices):
        PRODUCT = 'product', _('Étiquette produit')
        PRICE = 'price', _('Étiquette prix')
        TEST = 'test', _('Test')

    # Reference to product (optional for test labels)
    product = models.ForeignKey(
        Product,
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name='print_jobs',
        verbose_name=_('Produit')
    )

    # Label details
    label_type = models.CharField(
        _('Type d\'étiquette'),
        max_length=20,
        choices=LabelType.choices,
        default=LabelType.PRODUCT
    )
    quantity = models.PositiveIntegerField(
        _('Quantité'),
        default=1
    )

    # ZPL data (the raw print data)
    zpl_data = models.TextField(
        _('Données ZPL'),
        help_text=_('Commandes ZPL brutes à envoyer à l\'imprimante')
    )

    # Status tracking
    status = models.CharField(
        _('Statut'),
        max_length=20,
        choices=Status.choices,
        default=Status.PENDING
    )
    error_message = models.TextField(
        _('Message d\'erreur'),
        blank=True
    )
    attempts = models.PositiveIntegerField(
        _('Tentatives'),
        default=0
    )

    # Timestamps
    created_at = models.DateTimeField(_('Créé le'), auto_now_add=True)
    updated_at = models.DateTimeField(_('Modifié le'), auto_now=True)
    printed_at = models.DateTimeField(_('Imprimé le'), null=True, blank=True)
    created_by = models.ForeignKey(
        'users.User',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        verbose_name=_('Créé par'),
        related_name='print_jobs'
    )

    class Meta:
        verbose_name = _('File d\'impression')
        verbose_name_plural = _('File d\'impression')
        ordering = ['-created_at']

    def __str__(self):
        if self.product:
            return f"Print: {self.product.reference} ({self.get_status_display()})"
        return f"Print: {self.get_label_type_display()} ({self.get_status_display()})"

    @classmethod
    def get_pending_count(cls):
        """Return count of pending print jobs"""
        return cls.objects.filter(status=cls.Status.PENDING).count()

    @classmethod
    def get_pending_jobs(cls):
        """Return all pending print jobs ordered by creation"""
        return cls.objects.filter(status=cls.Status.PENDING).order_by('created_at')

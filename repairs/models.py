from django.db import models
from django.utils.translation import gettext_lazy as _
from django.core.validators import MinValueValidator
from decimal import Decimal


class Repair(models.Model):
    """Model for jewelry repair orders"""

    class Status(models.TextChoices):
        RECEIVED = 'received', _('Reçu')
        ASSESSING = 'assessing', _('En évaluation')
        APPROVED = 'approved', _('Approuvé')
        IN_PROGRESS = 'in_progress', _('En cours')
        COMPLETED = 'completed', _('Terminé')
        DELIVERED = 'delivered', _('Livré')
        CANCELLED = 'cancelled', _('Annulé')

    class Priority(models.TextChoices):
        LOW = 'low', _('Faible')
        MEDIUM = 'medium', _('Moyen')
        HIGH = 'high', _('Élevé')
        URGENT = 'urgent', _('Urgent')

    # Identification
    reference = models.CharField(
        _('Référence'),
        max_length=50,
        unique=True
    )

    # Client and item
    client = models.ForeignKey(
        'clients.Client',
        on_delete=models.PROTECT,
        related_name='repairs',
        verbose_name=_('Client')
    )
    product = models.ForeignKey(
        'products.Product',
        on_delete=models.PROTECT,
        related_name='repairs',
        verbose_name=_('Article'),
        null=True,
        blank=True
    )
    item_description = models.TextField(
        _('Description de l\'article'),
        blank=True,
        help_text=_('Description si l\'article n\'est pas dans la base de données')
    )

    # Repair details
    repair_type = models.ForeignKey(
        'settings_app.RepairType',
        on_delete=models.PROTECT,
        verbose_name=_('Type de réparation')
    )
    issue_description = models.TextField(
        _('Description du problème')
    )
    repair_notes = models.TextField(
        _('Notes de réparation'),
        blank=True
    )

    # Costs
    assessment_cost_dh = models.DecimalField(
        _('Coût d\'évaluation (DH)'),
        max_digits=10,
        decimal_places=2,
        default=0,
        validators=[MinValueValidator(Decimal('0'))]
    )
    labor_cost_dh = models.DecimalField(
        _('Coût de main-d\'œuvre (DH)'),
        max_digits=10,
        decimal_places=2,
        default=0,
        validators=[MinValueValidator(Decimal('0'))]
    )
    material_cost_dh = models.DecimalField(
        _('Coût des matériaux (DH)'),
        max_digits=10,
        decimal_places=2,
        default=0,
        validators=[MinValueValidator(Decimal('0'))]
    )
    total_cost_dh = models.DecimalField(
        _('Coût total (DH)'),
        max_digits=10,
        decimal_places=2,
        default=0,
        validators=[MinValueValidator(Decimal('0'))]
    )

    # Status and dates
    status = models.CharField(
        _('Statut'),
        max_length=20,
        choices=Status.choices,
        default=Status.RECEIVED
    )
    priority = models.CharField(
        _('Priorité'),
        max_length=10,
        choices=Priority.choices,
        default=Priority.MEDIUM
    )
    received_date = models.DateField(
        _('Date de réception'),
        auto_now_add=True
    )
    estimated_completion_date = models.DateField(
        _('Date d\'achèvement estimée')
    )
    completion_date = models.DateField(
        _('Date d\'achèvement'),
        null=True,
        blank=True
    )
    delivery_date = models.DateField(
        _('Date de livraison'),
        null=True,
        blank=True
    )

    # Assignment
    assigned_to = models.ForeignKey(
        'suppliers.Supplier',
        on_delete=models.SET_NULL,
        related_name='repairs',
        verbose_name=_('Assigné à'),
        null=True,
        blank=True
    )

    created_at = models.DateTimeField(_('Créé le'), auto_now_add=True)
    updated_at = models.DateTimeField(_('Modifié le'), auto_now=True)

    class Meta:
        verbose_name = _('Réparation')
        verbose_name_plural = _('Réparations')
        ordering = ['-received_date']

    def __str__(self):
        return f"{self.reference} - {self.client.name}"

    def save(self, *args, **kwargs):
        # Auto-generate reference if not present
        if not self.reference:
            from utils import generate_repair_reference
            self.reference = generate_repair_reference()

        # Auto-calculate total cost
        self.total_cost_dh = (
            self.assessment_cost_dh +
            self.labor_cost_dh +
            self.material_cost_dh
        )
        super().save(*args, **kwargs)

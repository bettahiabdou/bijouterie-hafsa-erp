"""
User models for Bijouterie Hafsa ERP
Includes custom user model with role-based permissions
"""

from django.contrib.auth.models import AbstractUser, BaseUserManager
from django.db import models
from django.utils.translation import gettext_lazy as _


class UserManager(BaseUserManager):
    """Custom user manager for User model"""

    def create_user(self, username, email=None, password=None, **extra_fields):
        if not username:
            raise ValueError(_('Le nom d\'utilisateur est obligatoire'))
        email = self.normalize_email(email) if email else None
        user = self.model(username=username, email=email, **extra_fields)
        user.set_password(password)
        user.save(using=self._db)
        return user

    def create_superuser(self, username, email=None, password=None, **extra_fields):
        extra_fields.setdefault('is_staff', True)
        extra_fields.setdefault('is_superuser', True)
        extra_fields.setdefault('role', User.Role.ADMIN)

        if extra_fields.get('is_staff') is not True:
            raise ValueError(_('Superuser must have is_staff=True.'))
        if extra_fields.get('is_superuser') is not True:
            raise ValueError(_('Superuser must have is_superuser=True.'))

        return self.create_user(username, email, password, **extra_fields)


class User(AbstractUser):
    """
    Custom User model for Bijouterie Hafsa ERP
    Supports role-based access control
    """

    class Role(models.TextChoices):
        ADMIN = 'admin', _('Administrateur')
        MANAGER = 'manager', _('Gérant')
        SELLER = 'seller', _('Vendeur')
        CASHIER = 'cashier', _('Caissier')

    # Basic info
    role = models.CharField(
        _('Rôle'),
        max_length=20,
        choices=Role.choices,
        default=Role.SELLER
    )
    phone = models.CharField(
        _('Téléphone'),
        max_length=20,
        blank=True
    )

    # Permissions flags
    can_view_purchase_cost = models.BooleanField(
        _('Peut voir le coût d\'achat'),
        default=False,
        help_text=_('Permet de voir le prix d\'achat des articles')
    )
    can_give_discount = models.BooleanField(
        _('Peut donner des remises'),
        default=False
    )
    max_discount_percent = models.DecimalField(
        _('Remise maximale autorisée (%)'),
        max_digits=5,
        decimal_places=2,
        default=0,
        help_text=_('Pourcentage maximum de remise que l\'utilisateur peut accorder')
    )
    can_sell_below_cost = models.BooleanField(
        _('Peut vendre en dessous du coût'),
        default=False,
        help_text=_('Nécessite généralement l\'approbation du manager')
    )
    can_create_purchase_order = models.BooleanField(
        _('Peut créer des bons de commande'),
        default=False
    )
    can_approve_discount = models.BooleanField(
        _('Peut approuver les remises'),
        default=False,
        help_text=_('Peut approuver les remises importantes des autres vendeurs')
    )
    can_delete_invoices = models.BooleanField(
        _('Peut supprimer des factures'),
        default=False
    )
    can_manage_users = models.BooleanField(
        _('Peut gérer les utilisateurs'),
        default=False
    )
    can_view_reports = models.BooleanField(
        _('Peut voir les rapports'),
        default=False
    )
    can_manage_stock = models.BooleanField(
        _('Peut gérer le stock'),
        default=False
    )

    objects = UserManager()

    class Meta:
        verbose_name = _('Utilisateur')
        verbose_name_plural = _('Utilisateurs')

    def __str__(self):
        return f"{self.get_full_name() or self.username} ({self.get_role_display()})"

    def save(self, *args, **kwargs):
        # Auto-set permissions based on role
        if self.role == self.Role.ADMIN:
            self.is_staff = True
            self.can_view_purchase_cost = True
            self.can_give_discount = True
            self.max_discount_percent = 100
            self.can_sell_below_cost = True
            self.can_create_purchase_order = True
            self.can_approve_discount = True
            self.can_delete_invoices = True
            self.can_manage_users = True
            self.can_view_reports = True
            self.can_manage_stock = True
        elif self.role == self.Role.MANAGER:
            self.can_view_purchase_cost = True
            self.can_give_discount = True
            self.max_discount_percent = 50
            self.can_sell_below_cost = True
            self.can_create_purchase_order = True
            self.can_approve_discount = True
            self.can_delete_invoices = False
            self.can_manage_users = False
            self.can_view_reports = True
            self.can_manage_stock = True
        elif self.role == self.Role.SELLER:
            self.can_view_purchase_cost = False
            self.can_give_discount = True
            self.max_discount_percent = 10
            self.can_sell_below_cost = False
            self.can_create_purchase_order = True
            self.can_approve_discount = False
            self.can_delete_invoices = False
            self.can_manage_users = False
            self.can_view_reports = False
            self.can_manage_stock = False
        elif self.role == self.Role.CASHIER:
            self.can_view_purchase_cost = False
            self.can_give_discount = False
            self.max_discount_percent = 0
            self.can_sell_below_cost = False
            self.can_create_purchase_order = False
            self.can_approve_discount = False
            self.can_delete_invoices = False
            self.can_manage_users = False
            self.can_view_reports = False
            self.can_manage_stock = False

        super().save(*args, **kwargs)

    @property
    def is_admin(self):
        return self.role == self.Role.ADMIN

    @property
    def is_manager(self):
        return self.role == self.Role.MANAGER

    @property
    def is_seller(self):
        return self.role == self.Role.SELLER

    @property
    def is_cashier(self):
        return self.role == self.Role.CASHIER

    def can_approve_discount_amount(self, discount_percent):
        """Check if user can approve a specific discount percentage"""
        if self.role in [self.Role.ADMIN, self.Role.MANAGER]:
            return True
        return discount_percent <= self.max_discount_percent


class ActivityLog(models.Model):
    """
    Track user activities for audit purposes
    """

    class ActionType(models.TextChoices):
        LOGIN = 'login', _('Connexion')
        LOGOUT = 'logout', _('Déconnexion')
        CREATE = 'create', _('Création')
        UPDATE = 'update', _('Modification')
        DELETE = 'delete', _('Suppression')
        VIEW = 'view', _('Consultation')
        PRINT = 'print', _('Impression')
        EXPORT = 'export', _('Export')
        APPROVE = 'approve', _('Approbation')
        REJECT = 'reject', _('Rejet')

    user = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        null=True,
        related_name='activity_logs',
        verbose_name=_('Utilisateur')
    )
    action = models.CharField(
        _('Action'),
        max_length=20,
        choices=ActionType.choices
    )
    model_name = models.CharField(
        _('Type d\'objet'),
        max_length=100,
        blank=True
    )
    object_id = models.CharField(
        _('ID de l\'objet'),
        max_length=50,
        blank=True
    )
    object_repr = models.CharField(
        _('Description de l\'objet'),
        max_length=255,
        blank=True
    )
    details = models.JSONField(
        _('Détails'),
        default=dict,
        blank=True
    )
    ip_address = models.GenericIPAddressField(
        _('Adresse IP'),
        null=True,
        blank=True
    )
    created_at = models.DateTimeField(
        _('Date et heure'),
        auto_now_add=True
    )

    class Meta:
        verbose_name = _('Journal d\'activité')
        verbose_name_plural = _('Journaux d\'activité')
        ordering = ['-created_at']

    def __str__(self):
        return f"{self.user} - {self.get_action_display()} - {self.created_at}"

"""
Client Deposit Fund models for Bijouterie Hafsa ERP
Manages client prepaid accounts and transactions
"""

from django.db import models
from django.utils.translation import gettext_lazy as _
from django.utils import timezone
from decimal import Decimal


class DepositAccount(models.Model):
    """
    Client deposit account - prepaid fund management
    Each client can have one deposit account
    """

    # Link to client (OneToOne)
    client = models.OneToOneField(
        'clients.Client',
        on_delete=models.PROTECT,
        related_name='deposit_account',
        verbose_name=_('Client')
    )

    # Status
    is_active = models.BooleanField(
        _('Actif'),
        default=True
    )

    # Notes
    notes = models.TextField(
        _('Notes'),
        blank=True
    )

    # Tracking
    created_by = models.ForeignKey(
        'users.User',
        on_delete=models.SET_NULL,
        null=True,
        related_name='created_deposit_accounts',
        verbose_name=_('Créé par')
    )
    created_at = models.DateTimeField(_('Créé le'), auto_now_add=True)
    updated_at = models.DateTimeField(_('Modifié le'), auto_now=True)

    class Meta:
        verbose_name = _('Compte Dépôt')
        verbose_name_plural = _('Comptes Dépôt')
        ordering = ['-created_at']

    def __str__(self):
        return f"Dépôt - {self.client.full_name}"

    @property
    def balance(self):
        """Calculate current balance from all transactions"""
        total = self.transactions.aggregate(
            total=models.Sum('amount')
        )['total'] or Decimal('0')
        return total

    @property
    def total_deposits(self):
        """Total amount deposited (positive transactions)"""
        return self.transactions.filter(
            transaction_type=DepositTransaction.TransactionType.DEPOSIT
        ).aggregate(
            total=models.Sum('amount')
        )['total'] or Decimal('0')

    @property
    def total_purchases(self):
        """Total amount used for purchases (absolute value)"""
        total = self.transactions.filter(
            transaction_type=DepositTransaction.TransactionType.PURCHASE
        ).aggregate(
            total=models.Sum('amount')
        )['total'] or Decimal('0')
        return abs(total)

    @property
    def transaction_count(self):
        """Number of transactions"""
        return self.transactions.count()

    @property
    def last_transaction_date(self):
        """Date of last transaction"""
        last = self.transactions.order_by('-created_at').first()
        return last.created_at if last else None


class DepositTransaction(models.Model):
    """
    Individual transaction in a deposit account
    Positive amount = deposit/add funds
    Negative amount = purchase/withdrawal
    """

    class TransactionType(models.TextChoices):
        DEPOSIT = 'deposit', _('Dépôt')
        PURCHASE = 'purchase', _('Achat')
        WITHDRAWAL = 'withdrawal', _('Retrait')
        ADJUSTMENT = 'adjustment', _('Ajustement')
        REFUND = 'refund', _('Remboursement')

    # Link to account
    account = models.ForeignKey(
        DepositAccount,
        on_delete=models.PROTECT,
        related_name='transactions',
        verbose_name=_('Compte')
    )

    # Transaction details
    transaction_type = models.CharField(
        _('Type'),
        max_length=20,
        choices=TransactionType.choices
    )

    # Amount (positive for deposit, negative for purchase/withdrawal)
    amount = models.DecimalField(
        _('Montant'),
        max_digits=12,
        decimal_places=2,
        help_text=_('Positif pour dépôt, négatif pour achat/retrait')
    )

    # Payment method (for deposits)
    payment_method = models.ForeignKey(
        'settings_app.PaymentMethod',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        verbose_name=_('Mode de paiement')
    )

    # Payment reference (for bank transfers, checks)
    payment_reference = models.CharField(
        _('Référence paiement'),
        max_length=100,
        blank=True
    )

    # Bank account (for bank transfers)
    bank_account = models.ForeignKey(
        'settings_app.BankAccount',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        verbose_name=_('Compte bancaire')
    )

    # Link to invoice (for purchases)
    invoice = models.ForeignKey(
        'sales.SaleInvoice',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='deposit_transactions',
        verbose_name=_('Facture')
    )

    # Link to product (for purchases - optional reference)
    product = models.ForeignKey(
        'products.Product',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='deposit_purchases',
        verbose_name=_('Produit')
    )

    # Description
    description = models.CharField(
        _('Description'),
        max_length=255,
        blank=True
    )

    # Notes
    notes = models.TextField(
        _('Notes'),
        blank=True
    )

    # Balance after this transaction (for quick reference)
    balance_after = models.DecimalField(
        _('Solde après'),
        max_digits=12,
        decimal_places=2,
        default=0
    )

    # Tracking
    created_by = models.ForeignKey(
        'users.User',
        on_delete=models.SET_NULL,
        null=True,
        related_name='deposit_transactions',
        verbose_name=_('Créé par')
    )
    created_at = models.DateTimeField(_('Créé le'), auto_now_add=True)

    class Meta:
        verbose_name = _('Transaction Dépôt')
        verbose_name_plural = _('Transactions Dépôt')
        ordering = ['-created_at']

    def __str__(self):
        sign = '+' if self.amount >= 0 else ''
        return f"{self.get_transaction_type_display()} {sign}{self.amount} DH - {self.account.client.full_name}"

    def save(self, *args, **kwargs):
        # Calculate balance after this transaction
        if not self.pk:  # New transaction
            current_balance = self.account.balance
            self.balance_after = current_balance + self.amount
        super().save(*args, **kwargs)

    @property
    def is_deposit(self):
        return self.transaction_type == self.TransactionType.DEPOSIT

    @property
    def is_purchase(self):
        return self.transaction_type == self.TransactionType.PURCHASE

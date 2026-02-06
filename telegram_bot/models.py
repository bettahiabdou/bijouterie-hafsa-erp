"""
Telegram Bot Models for tracking pending photo uploads
"""

from django.db import models
from django.utils.translation import gettext_lazy as _


class PendingPhotoSession(models.Model):
    """
    Track active photo upload sessions.
    When a salesperson starts a /vente command, we create a session
    to collect all their photos until they click "Terminer"
    """

    class Status(models.TextChoices):
        COLLECTING = 'collecting', _('En cours de collecte')
        COMPLETED = 'completed', _('Terminé')
        CANCELLED = 'cancelled', _('Annulé')
        EXPIRED = 'expired', _('Expiré')

    # Link to user
    user = models.ForeignKey(
        'users.User',
        on_delete=models.CASCADE,
        related_name='telegram_sessions',
        verbose_name=_('Utilisateur')
    )

    # Telegram info
    telegram_chat_id = models.CharField(
        _('Chat ID'),
        max_length=50
    )

    # Status
    status = models.CharField(
        _('Statut'),
        max_length=20,
        choices=Status.choices,
        default=Status.COLLECTING
    )

    # The invoice that will be created (null until completed)
    invoice = models.ForeignKey(
        'sales.SaleInvoice',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='telegram_session',
        verbose_name=_('Facture')
    )

    # Photo count during collection
    photo_count = models.PositiveIntegerField(
        _('Nombre de photos'),
        default=0
    )

    # Timestamps
    started_at = models.DateTimeField(
        _('Démarré le'),
        auto_now_add=True
    )
    completed_at = models.DateTimeField(
        _('Terminé le'),
        null=True,
        blank=True
    )

    # Last message ID (to update the count message)
    last_message_id = models.CharField(
        _('Dernier message ID'),
        max_length=50,
        blank=True
    )

    class Meta:
        verbose_name = _('Session photo Telegram')
        verbose_name_plural = _('Sessions photo Telegram')
        ordering = ['-started_at']

    def __str__(self):
        return f"Session {self.id} - {self.user.username} - {self.photo_count} photos"


class TempPhoto(models.Model):
    """
    Temporary storage for photos before invoice is created.
    Photos are moved to InvoicePhoto when session is completed.
    """

    session = models.ForeignKey(
        PendingPhotoSession,
        on_delete=models.CASCADE,
        related_name='temp_photos',
        verbose_name=_('Session')
    )

    # Telegram file info
    telegram_file_id = models.CharField(
        _('Telegram File ID'),
        max_length=255
    )

    # Local file path (after download)
    file_path = models.CharField(
        _('Chemin du fichier'),
        max_length=500,
        blank=True
    )

    # Metadata
    caption = models.TextField(
        _('Légende'),
        blank=True
    )

    uploaded_at = models.DateTimeField(
        _('Téléchargé le'),
        auto_now_add=True
    )

    class Meta:
        verbose_name = _('Photo temporaire')
        verbose_name_plural = _('Photos temporaires')
        ordering = ['uploaded_at']

    def __str__(self):
        return f"TempPhoto {self.id} - Session {self.session_id}"

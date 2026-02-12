"""
Telegram Bot Handler for Bijouterie Hafsa ERP
Handles sales submissions from salespeople via Telegram

Commands:
- /start - Register and get help
- /vente - Start new sale (photo collection)
- /fin - Finish current sale submission
- /ajouter FA-XXXX - Add photos to existing pending invoice
- /mes_ventes - List my pending invoices
- /aide - Show help
"""

import os
import logging
from datetime import datetime
from django.conf import settings
from django.utils import timezone
from django.core.files.base import ContentFile
from asgiref.sync import sync_to_async

logger = logging.getLogger(__name__)

# Check if python-telegram-bot is installed
try:
    from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup, InputMediaPhoto
    from telegram.ext import (
        Application,
        CommandHandler,
        MessageHandler,
        CallbackQueryHandler,
        ContextTypes,
        filters
    )
    TELEGRAM_AVAILABLE = True
except ImportError:
    TELEGRAM_AVAILABLE = False
    logger.warning("python-telegram-bot not installed. Telegram bot features disabled.")


# Database helper functions wrapped with sync_to_async
@sync_to_async
def get_user_by_chat_id(chat_id):
    from users.models import User
    try:
        return User.objects.get(telegram_chat_id=chat_id)
    except User.DoesNotExist:
        return None


@sync_to_async
def get_verified_user(chat_id):
    from users.models import User
    try:
        return User.objects.get(telegram_chat_id=chat_id, is_telegram_verified=True)
    except User.DoesNotExist:
        return None


@sync_to_async
def link_user_by_username(telegram_username, chat_id):
    from users.models import User
    from django.db.models import Q

    if not telegram_username:
        return None

    # Normalize username - remove @ if present for comparison
    username_clean = telegram_username.lstrip('@')
    username_with_at = f'@{username_clean}'

    try:
        # Try to find user with either format: @username or username
        user = User.objects.get(
            Q(telegram_username__iexact=username_clean) | Q(telegram_username__iexact=username_with_at),
            is_telegram_verified=False
        )
        user.telegram_chat_id = chat_id
        user.is_telegram_verified = True
        user.save()
        return user
    except User.DoesNotExist:
        return None


@sync_to_async
def get_active_session(user):
    from .models import PendingPhotoSession
    return PendingPhotoSession.objects.filter(
        user=user,
        status=PendingPhotoSession.Status.COLLECTING
    ).first()


@sync_to_async
def create_session(user, chat_id, invoice=None):
    from .models import PendingPhotoSession
    return PendingPhotoSession.objects.create(
        user=user,
        telegram_chat_id=chat_id,
        status=PendingPhotoSession.Status.COLLECTING,
        invoice=invoice
    )


@sync_to_async
def create_temp_photo(session, file_id, caption=""):
    from .models import TempPhoto
    return TempPhoto.objects.create(
        session=session,
        telegram_file_id=file_id,
        caption=caption
    )


@sync_to_async
def update_session_photo_count(session):
    session.photo_count += 1
    session.save()
    return session.photo_count


@sync_to_async
def get_session_by_id(session_id, user):
    from .models import PendingPhotoSession
    try:
        return PendingPhotoSession.objects.get(
            id=session_id,
            user=user,
            status=PendingPhotoSession.Status.COLLECTING
        )
    except PendingPhotoSession.DoesNotExist:
        return None


@sync_to_async
def cancel_session(session):
    from .models import PendingPhotoSession
    session.status = PendingPhotoSession.Status.CANCELLED
    session.save()
    session.temp_photos.all().delete()


@sync_to_async
def get_temp_photos(session):
    return list(session.temp_photos.all())


@sync_to_async
def create_draft_invoice(user):
    from sales.models import SaleInvoice
    from django.db import IntegrityError, transaction
    import time

    max_retries = 5
    for attempt in range(max_retries):
        try:
            with transaction.atomic():
                invoice = SaleInvoice(
                    date=timezone.now().date(),
                    status=SaleInvoice.Status.DRAFT,
                    seller=user,
                    created_by=user,
                    notes=f"Créé via Telegram par {user.get_full_name() or user.username}"
                )
                # Reference will be generated fresh in save() using max existing reference
                invoice.save()
                return invoice
        except IntegrityError as e:
            if 'duplicate key' in str(e) and attempt < max_retries - 1:
                # Wait a bit and retry - the reference generator will find the new max
                time.sleep(0.2 * (attempt + 1))
                continue
            raise
    raise Exception("Failed to create invoice after multiple retries")


@sync_to_async
def save_invoice_photo(invoice, file_id, file_bytes, photo_index, caption=""):
    from sales.models import InvoicePhoto
    filename = f"invoice_{invoice.reference}_{photo_index}.jpg"
    invoice_photo = InvoicePhoto(
        invoice=invoice,
        telegram_file_id=file_id,
        caption=caption,
        photo_type=InvoicePhoto.PhotoType.OTHER
    )
    invoice_photo.image.save(filename, ContentFile(bytes(file_bytes)))
    invoice_photo.save()
    return invoice_photo


@sync_to_async
def complete_session(session, invoice):
    from .models import PendingPhotoSession
    session.status = PendingPhotoSession.Status.COMPLETED
    session.invoice = invoice
    session.completed_at = timezone.now()
    session.save()
    session.temp_photos.all().delete()


@sync_to_async
def get_pending_invoices(user, limit=10):
    from sales.models import SaleInvoice
    return list(SaleInvoice.objects.filter(
        seller=user,
        status=SaleInvoice.Status.DRAFT
    ).order_by('-created_at')[:limit])


@sync_to_async
def get_invoice_by_reference(reference):
    from sales.models import SaleInvoice
    try:
        return SaleInvoice.objects.get(reference=reference)
    except SaleInvoice.DoesNotExist:
        return None


@sync_to_async
def get_invoice_photo_count(invoice):
    return invoice.photos.count()


@sync_to_async
def get_session_invoice(session):
    """Get the invoice attached to a session (if any)"""
    if session.invoice_id:
        from sales.models import SaleInvoice
        try:
            return SaleInvoice.objects.get(id=session.invoice_id)
        except SaleInvoice.DoesNotExist:
            return None
    return None


@sync_to_async
def cancel_user_active_sessions(user):
    from .models import PendingPhotoSession
    PendingPhotoSession.objects.filter(
        user=user,
        status=PendingPhotoSession.Status.COLLECTING
    ).update(status=PendingPhotoSession.Status.CANCELLED)


class TelegramBotHandler:
    """Main handler for Telegram bot interactions"""

    def __init__(self, token):
        if not TELEGRAM_AVAILABLE:
            raise ImportError("python-telegram-bot is required. Install with: pip install python-telegram-bot")

        self.token = token
        self.application = None

    def _get_main_menu_keyboard(self):
        """Get the main menu keyboard with all action buttons"""
        keyboard = [
            [InlineKeyboardButton("📸 Nouvelle Vente", callback_data="new_sale")],
            [InlineKeyboardButton("📋 Mes Ventes en Attente", callback_data="my_sales")],
            [InlineKeyboardButton("❓ Aide", callback_data="help")]
        ]
        return InlineKeyboardMarkup(keyboard)

    async def _send_main_menu(self, chat_id, context, user, welcome_message=""):
        """Send the main menu with action buttons"""
        keyboard = self._get_main_menu_keyboard()

        message = welcome_message if welcome_message else f"👋 Bonjour {user.get_full_name() or user.username}!"
        message += "\n\n🔷 Que voulez-vous faire?"

        await context.bot.send_message(
            chat_id=chat_id,
            text=message,
            reply_markup=keyboard
        )

    async def start_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle /start command - Registration"""
        chat_id = str(update.effective_chat.id)
        telegram_username = update.effective_user.username or ""
        first_name = update.effective_user.first_name or ""

        # Debug logging
        print(f"[DEBUG] /start received from chat_id={chat_id}, username={telegram_username}, first_name={first_name}")

        # Check if user is already linked
        user = await get_user_by_chat_id(chat_id)
        print(f"[DEBUG] get_user_by_chat_id result: {user}")
        if user:
            await self._send_main_menu(
                chat_id,
                context,
                user,
                f"✅ Bonjour {user.get_full_name() or user.username}!\nVous êtes connecté."
            )
            return

        # Check if there's a user with matching telegram_username waiting to be linked
        if telegram_username:
            print(f"[DEBUG] Trying to link username={telegram_username}")
            user = await link_user_by_username(telegram_username, chat_id)
            print(f"[DEBUG] link_user_by_username result: {user}")
            if user:
                await self._send_main_menu(
                    chat_id,
                    context,
                    user,
                    f"✅ Bienvenue {user.get_full_name() or user.username}!\nVotre compte Telegram a été lié avec succès."
                )
                return

        # User not found - provide instructions
        await update.message.reply_text(
            f"👋 Bonjour {first_name}!\n\n"
            f"Pour utiliser ce bot, demandez à votre administrateur "
            f"d'ajouter votre nom d'utilisateur Telegram dans le système:\n\n"
            f"Votre username: @{telegram_username or 'Non défini'}\n\n"
            f"Une fois configuré, revenez ici et le bot vous connectera automatiquement."
        )

    async def vente_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle /vente command - Start new sale"""
        chat_id = str(update.effective_chat.id)

        # Get user
        user = await get_verified_user(chat_id)
        if not user:
            await update.message.reply_text(
                "❌ Vous n'êtes pas enregistré.\n"
                "Tapez /start pour commencer."
            )
            return

        # Check for existing active session
        active_session = await get_active_session(user)

        if active_session:
            keyboard = [[
                InlineKeyboardButton("✅ Terminer la vente actuelle", callback_data=f"finish_{active_session.id}"),
                InlineKeyboardButton("❌ Annuler", callback_data=f"cancel_{active_session.id}")
            ]]
            reply_markup = InlineKeyboardMarkup(keyboard)

            await update.message.reply_text(
                f"⚠️ Vous avez déjà une vente en cours avec {active_session.photo_count} photo(s).\n\n"
                f"Terminez-la d'abord ou annulez-la.",
                reply_markup=reply_markup
            )
            return

        # Create new session
        await create_session(user, chat_id)

        await update.message.reply_text(
            "📸 Nouvelle vente\n\n"
            "Envoyez les photos:\n"
            "• Photo du produit\n"
            "• Facture manuscrite\n"
            "• Preuve de paiement (si applicable)\n\n"
            "Quand vous avez terminé, cliquez sur le bouton 'Terminer' "
            "ou tapez /fin"
        )

    async def handle_photo(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle incoming photos"""
        chat_id = str(update.effective_chat.id)

        # Get user
        user = await get_verified_user(chat_id)
        if not user:
            await update.message.reply_text(
                "❌ Vous n'êtes pas enregistré.\nTapez /start pour commencer."
            )
            return

        # Get active session
        session = await get_active_session(user)

        if not session:
            # No active session - offer to start one
            keyboard = [[InlineKeyboardButton("📸 Nouvelle vente", callback_data="new_sale")]]
            reply_markup = InlineKeyboardMarkup(keyboard)

            await update.message.reply_text(
                "⚠️ Aucune vente en cours.\n"
                "Tapez /vente pour commencer une nouvelle vente.",
                reply_markup=reply_markup
            )
            return

        # Get photo file
        photo = update.message.photo[-1]  # Get highest resolution
        file_id = photo.file_id
        caption = update.message.caption or ""

        # Save temp photo reference
        await create_temp_photo(session, file_id, caption)

        # Update session count
        photo_count = await update_session_photo_count(session)

        # Send confirmation with finish button
        keyboard = [[InlineKeyboardButton(f"✅ Terminer la vente ({photo_count} photos)", callback_data=f"finish_{session.id}")]]
        reply_markup = InlineKeyboardMarkup(keyboard)

        await update.message.reply_text(
            f"📷 {photo_count} photo(s) reçue(s)\n\n"
            f"Continuez à envoyer des photos ou cliquez pour terminer.",
            reply_markup=reply_markup
        )

    async def fin_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle /fin command - Finish current sale"""
        chat_id = str(update.effective_chat.id)

        user = await get_verified_user(chat_id)
        if not user:
            await update.message.reply_text("❌ Vous n'êtes pas enregistré.")
            return

        session = await get_active_session(user)

        if not session:
            await update.message.reply_text("❌ Aucune vente en cours.")
            return

        if session.photo_count == 0:
            await update.message.reply_text(
                "❌ Vous devez envoyer au moins une photo.\n"
                "Envoyez des photos puis tapez /fin"
            )
            return

        # Complete the session
        await self._complete_session(session, user, update, context)

    async def _complete_session(self, session, user, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Complete a photo session and create invoice or add to existing"""
        # Check if session already has an invoice (adding photos to existing)
        existing_invoice = await get_session_invoice(session)

        if existing_invoice:
            invoice = existing_invoice
            is_new_invoice = False
        else:
            invoice = await create_draft_invoice(user)
            is_new_invoice = True

        # Get temp photos
        temp_photos = await get_temp_photos(session)

        # Get current photo count for numbering
        current_photo_count = await get_invoice_photo_count(invoice) if not is_new_invoice else 0

        # Download and save photos + collect file_ids for recap
        photos_saved = 0
        saved_file_ids = []
        for temp_photo in temp_photos:
            try:
                # Get file from Telegram
                file = await context.bot.get_file(temp_photo.telegram_file_id)

                # Download file
                file_bytes = await file.download_as_bytearray()

                # Save to InvoicePhoto
                await save_invoice_photo(invoice, temp_photo.telegram_file_id, file_bytes, current_photo_count + photos_saved + 1, temp_photo.caption)
                saved_file_ids.append(temp_photo.telegram_file_id)
                photos_saved += 1
            except Exception as e:
                logger.error(f"Error saving photo: {e}")

        # Update session
        await complete_session(session, invoice)

        # Send photo recap FIRST as media group (max 10 photos per group)
        chat_id = update.effective_chat.id
        if saved_file_ids:
            try:
                # Send photos in batches of 10 (Telegram limit)
                for i in range(0, len(saved_file_ids), 10):
                    batch = saved_file_ids[i:i+10]
                    if len(batch) == 1:
                        # Single photo - add caption
                        caption = f"📋 #{invoice.reference}" if i == 0 else None
                        await context.bot.send_photo(
                            chat_id=chat_id,
                            photo=batch[0],
                            caption=caption
                        )
                    else:
                        # Multiple photos - media group
                        media_group = []
                        for j, file_id in enumerate(batch):
                            caption = f"📋 #{invoice.reference}" if i == 0 and j == 0 else None
                            media_group.append(InputMediaPhoto(media=file_id, caption=caption))
                        await context.bot.send_media_group(
                            chat_id=chat_id,
                            media=media_group
                        )
            except Exception as e:
                logger.error(f"Error sending photo recap: {e}")

        # Send confirmation message with action buttons AFTER photos
        keyboard = [
            [InlineKeyboardButton("📷 Ajouter des photos", callback_data=f"add_photos_{invoice.reference}")],
            [
                InlineKeyboardButton("📸 Nouvelle Vente", callback_data="new_sale"),
                InlineKeyboardButton("🏠 Menu", callback_data="main_menu")
            ]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)

        total_photos = current_photo_count + photos_saved

        if is_new_invoice:
            await context.bot.send_message(
                chat_id=chat_id,
                text=f"✅ Facture #{invoice.reference} créée\n\n"
                f"👤 Vendeur: {user.get_full_name() or user.username}\n"
                f"📷 {photos_saved} photos\n"
                f"⏰ {timezone.now().strftime('%H:%M')}\n\n"
                f"En attente de saisie par l'équipe admin.",
                reply_markup=reply_markup
            )
        else:
            await context.bot.send_message(
                chat_id=chat_id,
                text=f"✅ {photos_saved} photo(s) ajoutée(s) à #{invoice.reference}\n\n"
                f"📷 Total: {total_photos} photos\n\n"
                f"En attente de saisie par l'équipe admin.",
                reply_markup=reply_markup
            )

    async def callback_handler(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle inline button callbacks"""
        query = update.callback_query
        await query.answer()

        data = query.data
        chat_id = str(update.effective_chat.id)

        user = await get_verified_user(chat_id)
        if not user:
            await query.edit_message_text("❌ Vous n'êtes pas enregistré.")
            return

        if data.startswith("finish_"):
            session_id = int(data.split("_")[1])
            session = await get_session_by_id(session_id, user)

            if not session:
                await query.edit_message_text("❌ Session non trouvée ou déjà terminée.")
                return

            if session.photo_count == 0:
                await query.edit_message_text("❌ Vous devez envoyer au moins une photo.")
                return

            await self._complete_session_callback(session, user, query, context)

        elif data.startswith("cancel_"):
            session_id = int(data.split("_")[1])
            session = await get_session_by_id(session_id, user)

            if not session:
                await query.edit_message_text("❌ Session non trouvée.")
                return

            await cancel_session(session)
            await query.edit_message_text("❌ Vente annulée.")
            # Show main menu after cancel
            await self._send_main_menu(chat_id, context, user)

        elif data == "new_sale":
            # Start new sale from button
            await self._start_new_sale_from_callback(user, query, context)

        elif data == "my_sales":
            # Show pending invoices from button
            await self._show_my_sales_from_callback(user, query, context)

        elif data == "help":
            # Show help from button
            await self._show_help_from_callback(query)

        elif data == "main_menu":
            # Go back to main menu - preserve "Ajouter des photos" button on invoice messages
            old_text = query.message.text or ""
            if "Facture #" in old_text:
                # This is an invoice confirmation message - keep "Ajouter des photos" button
                import re
                match = re.search(r'#([\w-]+)', old_text)
                if match:
                    invoice_ref = match.group(1)
                    old_keyboard = [[InlineKeyboardButton("📷 Ajouter des photos", callback_data=f"add_photos_{invoice_ref}")]]
                    try:
                        await query.edit_message_reply_markup(reply_markup=InlineKeyboardMarkup(old_keyboard))
                    except Exception:
                        pass
                # Send main menu as new message
                await context.bot.send_message(
                    chat_id=chat_id,
                    text=f"👋 Bonjour {user.get_full_name() or user.username}!\n\n🔷 Que voulez-vous faire?",
                    reply_markup=self._get_main_menu_keyboard()
                )
            else:
                # Not an invoice message - safe to edit
                await query.edit_message_text(
                    f"👋 Bonjour {user.get_full_name() or user.username}!\n\n🔷 Que voulez-vous faire?",
                    reply_markup=self._get_main_menu_keyboard()
                )

        elif data.startswith("add_photos_"):
            invoice_ref = data.split("_", 2)[2]
            await self._start_add_photos(invoice_ref, user, query, context)

    async def _complete_session_callback(self, session, user, query, context):
        """Complete session from callback"""
        # Check if session already has an invoice (adding photos to existing)
        existing_invoice = await get_session_invoice(session)

        if existing_invoice:
            invoice = existing_invoice
            is_new_invoice = False
        else:
            invoice = await create_draft_invoice(user)
            is_new_invoice = True

        # Get temp photos
        temp_photos = await get_temp_photos(session)

        # Get current photo count for numbering
        current_photo_count = await get_invoice_photo_count(invoice) if not is_new_invoice else 0

        # Download and save photos + collect file_ids for recap
        photos_saved = 0
        saved_file_ids = []
        for temp_photo in temp_photos:
            try:
                file = await context.bot.get_file(temp_photo.telegram_file_id)
                file_bytes = await file.download_as_bytearray()
                await save_invoice_photo(invoice, temp_photo.telegram_file_id, file_bytes, current_photo_count + photos_saved + 1, temp_photo.caption)
                saved_file_ids.append(temp_photo.telegram_file_id)
                photos_saved += 1
            except Exception as e:
                logger.error(f"Error saving photo: {e}")

        # Update session
        await complete_session(session, invoice)

        # First, edit the original message to remove buttons (processing indicator)
        chat_id = query.message.chat.id
        await query.edit_message_text("⏳ Traitement en cours...")

        # Send photo recap as media group (max 10 photos per group)
        if saved_file_ids:
            try:
                # Send photos in batches of 10 (Telegram limit)
                for i in range(0, len(saved_file_ids), 10):
                    batch = saved_file_ids[i:i+10]
                    if len(batch) == 1:
                        # Single photo - add caption
                        caption = f"📋 #{invoice.reference}" if i == 0 else None
                        await context.bot.send_photo(
                            chat_id=chat_id,
                            photo=batch[0],
                            caption=caption
                        )
                    else:
                        # Multiple photos - media group
                        media_group = []
                        for j, file_id in enumerate(batch):
                            caption = f"📋 #{invoice.reference}" if i == 0 and j == 0 else None
                            media_group.append(InputMediaPhoto(media=file_id, caption=caption))
                        await context.bot.send_media_group(
                            chat_id=chat_id,
                            media=media_group
                        )
            except Exception as e:
                logger.error(f"Error sending photo recap: {e}")

        # Send confirmation message with action buttons as NEW message (after photos)
        keyboard = [
            [InlineKeyboardButton("📷 Ajouter des photos", callback_data=f"add_photos_{invoice.reference}")],
            [
                InlineKeyboardButton("📸 Nouvelle Vente", callback_data="new_sale"),
                InlineKeyboardButton("🏠 Menu", callback_data="main_menu")
            ]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)

        total_photos = current_photo_count + photos_saved

        if is_new_invoice:
            await context.bot.send_message(
                chat_id=chat_id,
                text=f"✅ Facture #{invoice.reference} créée\n\n"
                f"👤 Vendeur: {user.get_full_name() or user.username}\n"
                f"📷 {photos_saved} photos\n"
                f"⏰ {timezone.now().strftime('%H:%M')}\n\n"
                f"En attente de saisie par l'équipe admin.",
                reply_markup=reply_markup
            )
        else:
            await context.bot.send_message(
                chat_id=chat_id,
                text=f"✅ {photos_saved} photo(s) ajoutée(s) à #{invoice.reference}\n\n"
                f"📷 Total: {total_photos} photos\n\n"
                f"En attente de saisie par l'équipe admin.",
                reply_markup=reply_markup
            )

    async def _start_new_sale_from_callback(self, user, query, context):
        """Start a new sale from callback button"""
        chat_id = str(query.message.chat.id)

        # Check for existing active session
        active_session = await get_active_session(user)

        if active_session:
            keyboard = [[
                InlineKeyboardButton("✅ Terminer", callback_data=f"finish_{active_session.id}"),
                InlineKeyboardButton("❌ Annuler", callback_data=f"cancel_{active_session.id}")
            ]]
            reply_markup = InlineKeyboardMarkup(keyboard)

            # Send as new message to preserve old invoice's "Ajouter des photos" button
            await context.bot.send_message(
                chat_id=chat_id,
                text=f"⚠️ Vous avez déjà une vente en cours avec {active_session.photo_count} photo(s).\n\n"
                f"Terminez-la d'abord ou annulez-la.",
                reply_markup=reply_markup
            )
            return

        # Create new session
        await create_session(user, chat_id)

        # Update old message to keep only "Ajouter des photos" button (extract invoice ref if present)
        old_text = query.message.text or ""
        if "Facture #" in old_text:
            # Extract invoice reference from old message
            import re
            match = re.search(r'#([\w-]+)', old_text)
            if match:
                invoice_ref = match.group(1)
                # Keep only the "Ajouter des photos" button on old message
                old_keyboard = [[InlineKeyboardButton("📷 Ajouter des photos", callback_data=f"add_photos_{invoice_ref}")]]
                try:
                    await query.edit_message_reply_markup(reply_markup=InlineKeyboardMarkup(old_keyboard))
                except Exception:
                    pass  # Message might not be editable

        # Send NEW message for the new sale
        keyboard = [[InlineKeyboardButton("🏠 Menu", callback_data="main_menu")]]
        reply_markup = InlineKeyboardMarkup(keyboard)

        await context.bot.send_message(
            chat_id=chat_id,
            text="📸 Nouvelle vente\n\n"
            "Envoyez les photos:\n"
            "• Photo du produit\n"
            "• Facture manuscrite\n"
            "• Preuve de paiement (si applicable)\n\n"
            "Quand vous avez terminé, cliquez sur le bouton 'Terminer' "
            "ou tapez /fin",
            reply_markup=reply_markup
        )

    async def _show_my_sales_from_callback(self, user, query, context):
        """Show pending invoices from callback button"""
        pending = await get_pending_invoices(user)

        if not pending:
            keyboard = [
                [InlineKeyboardButton("📸 Nouvelle Vente", callback_data="new_sale")],
                [InlineKeyboardButton("🏠 Menu", callback_data="main_menu")]
            ]
            reply_markup = InlineKeyboardMarkup(keyboard)

            await query.edit_message_text(
                "📋 Aucune vente en attente.\n\n"
                "Créez une nouvelle vente!",
                reply_markup=reply_markup
            )
            return

        message = "📋 Vos ventes en attente:\n\n"

        keyboard = []
        for invoice in pending:
            photos_count = await get_invoice_photo_count(invoice)
            created_time = invoice.created_at.strftime('%d/%m %H:%M')
            message += f"• #{invoice.reference} - {created_time} - {photos_count} 📷\n"
            keyboard.append([
                InlineKeyboardButton(f"📷 Ajouter à #{invoice.reference}", callback_data=f"add_photos_{invoice.reference}")
            ])

        keyboard.append([
            InlineKeyboardButton("📸 Nouvelle Vente", callback_data="new_sale"),
            InlineKeyboardButton("🏠 Menu", callback_data="main_menu")
        ])

        reply_markup = InlineKeyboardMarkup(keyboard)

        await query.edit_message_text(message, reply_markup=reply_markup)

    async def _show_help_from_callback(self, query):
        """Show help from callback button"""
        keyboard = [[InlineKeyboardButton("🏠 Menu", callback_data="main_menu")]]
        reply_markup = InlineKeyboardMarkup(keyboard)

        await query.edit_message_text(
            "🔷 Bot Ventes - Bijouterie Hafsa\n\n"
            "📌 Comment utiliser:\n\n"
            "1️⃣ Cliquez sur '📸 Nouvelle Vente'\n"
            "2️⃣ Envoyez les photos (produit, facture...)\n"
            "3️⃣ Cliquez 'Terminer' quand c'est fini\n\n"
            "📋 Vos ventes en attente seront traitées par l'équipe admin.\n\n"
            "💡 Astuce: Vous pouvez ajouter des photos à une vente existante "
            "en cliquant sur '📷 Ajouter des photos'",
            reply_markup=reply_markup
        )

    async def _start_add_photos(self, invoice_ref, user, query, context):
        """Start adding photos to existing invoice"""
        from sales.models import SaleInvoice

        invoice = await get_invoice_by_reference(invoice_ref)

        if not invoice:
            await query.edit_message_text(f"❌ Facture #{invoice_ref} non trouvée.")
            return

        # Check if invoice is still draft
        if invoice.status != SaleInvoice.Status.DRAFT:
            await query.edit_message_text(
                f"❌ Impossible d'ajouter des photos.\n"
                f"Facture #{invoice_ref} est déjà validée."
            )
            return

        # Check if user owns this invoice
        if invoice.seller_id != user.id:
            await query.edit_message_text(
                f"❌ Cette facture appartient à un autre vendeur."
            )
            return

        # Create new session for adding photos
        await create_session(user, str(query.message.chat.id), invoice)

        photo_count = await get_invoice_photo_count(invoice)

        await query.edit_message_text(
            f"📎 Facture #{invoice_ref}\n"
            f"Photos actuelles: {photo_count}\n\n"
            f"Envoyez les photos supplémentaires."
        )

    async def ajouter_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle /ajouter command - Add photos to existing invoice"""
        from sales.models import SaleInvoice

        chat_id = str(update.effective_chat.id)

        user = await get_verified_user(chat_id)
        if not user:
            await update.message.reply_text("❌ Vous n'êtes pas enregistré.")
            return

        # Get invoice reference from command
        if not context.args:
            await update.message.reply_text(
                "❌ Usage: /ajouter FA-XXXX-XXXX\n\n"
                "Tapez /mes_ventes pour voir vos factures en attente."
            )
            return

        invoice_ref = context.args[0].upper()

        invoice = await get_invoice_by_reference(invoice_ref)

        if not invoice:
            await update.message.reply_text(f"❌ Facture #{invoice_ref} non trouvée.")
            return

        if invoice.status != SaleInvoice.Status.DRAFT:
            await update.message.reply_text(
                f"❌ Impossible d'ajouter des photos.\n"
                f"Facture #{invoice_ref} est déjà validée.\n\n"
                f"Contactez l'administrateur si nécessaire."
            )
            return

        if invoice.seller_id != user.id:
            await update.message.reply_text(
                f"❌ Cette facture appartient à un autre vendeur."
            )
            return

        # Cancel any existing session and start add photos session
        await cancel_user_active_sessions(user)

        await create_session(user, chat_id, invoice)

        photo_count = await get_invoice_photo_count(invoice)

        await update.message.reply_text(
            f"📎 Facture #{invoice_ref}\n"
            f"Photos actuelles: {photo_count}\n\n"
            f"Envoyez les photos supplémentaires, puis tapez /fin"
        )

    async def mes_ventes_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle /mes_ventes command - List pending invoices"""
        chat_id = str(update.effective_chat.id)

        user = await get_verified_user(chat_id)
        if not user:
            await update.message.reply_text("❌ Vous n'êtes pas enregistré.")
            return

        # Get pending invoices
        pending = await get_pending_invoices(user)

        if not pending:
            await update.message.reply_text(
                "📋 Aucune vente en attente.\n\n"
                "Tapez /vente pour créer une nouvelle vente."
            )
            return

        message = "📋 Vos ventes en attente:\n\n"

        keyboard = []
        for invoice in pending:
            photos_count = await get_invoice_photo_count(invoice)
            created_time = invoice.created_at.strftime('%d/%m %H:%M')
            message += f"• #{invoice.reference} - {created_time} - {photos_count} 📷\n"
            keyboard.append([
                InlineKeyboardButton(f"📷 Ajouter à #{invoice.reference}", callback_data=f"add_photos_{invoice.reference}")
            ])

        reply_markup = InlineKeyboardMarkup(keyboard)

        message += "\nCliquez pour ajouter des photos ou utilisez:\n"
        message += "/ajouter FA-XXXX-XXXX"

        await update.message.reply_text(message, reply_markup=reply_markup)

    async def aide_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle /aide command - Show help"""
        await update.message.reply_text(
            "🔷 Bot Ventes - Bijouterie Hafsa\n\n"
            "📌 Commandes disponibles:\n\n"
            "/vente - Démarrer une nouvelle vente\n"
            "  Envoyez les photos puis cliquez 'Terminer'\n\n"
            "/fin - Terminer l'envoi de photos\n\n"
            "/ajouter FA-XXXX - Ajouter des photos\n"
            "  à une facture existante (en attente)\n\n"
            "/mes_ventes - Voir vos factures en attente\n\n"
            "/aide - Afficher cette aide\n\n"
            "💡 Astuce: Envoyez plusieurs photos d'un coup\n"
            "(produit, facture manuscrite, paiement...)"
        )

    def setup_handlers(self, application):
        """Set up all command handlers"""
        application.add_handler(CommandHandler("start", self.start_command))
        application.add_handler(CommandHandler("vente", self.vente_command))
        application.add_handler(CommandHandler("fin", self.fin_command))
        application.add_handler(CommandHandler("ajouter", self.ajouter_command))
        application.add_handler(CommandHandler("mes_ventes", self.mes_ventes_command))
        application.add_handler(CommandHandler("aide", self.aide_command))
        application.add_handler(MessageHandler(filters.PHOTO, self.handle_photo))
        application.add_handler(CallbackQueryHandler(self.callback_handler))

    async def error_handler(self, update, context):
        """Handle errors in the bot"""
        logger.error(f"Bot error: {context.error}", exc_info=context.error)

        # Try to notify user of the error
        try:
            if update and update.effective_chat:
                await context.bot.send_message(
                    chat_id=update.effective_chat.id,
                    text="⚠️ Une erreur s'est produite. Veuillez réessayer."
                )
        except Exception as e:
            logger.error(f"Failed to send error message: {e}")

    def run(self):
        """Start the bot"""
        self.application = Application.builder().token(self.token).build()
        self.setup_handlers(self.application)

        # Add error handler to prevent crashes
        self.application.add_error_handler(self.error_handler)

        logger.info("Starting Telegram bot...")
        self.application.run_polling(drop_pending_updates=True)


def run_bot():
    """Entry point for running the bot"""
    from django.conf import settings

    token = getattr(settings, 'TELEGRAM_BOT_TOKEN', None)

    if not token:
        logger.error("TELEGRAM_BOT_TOKEN not set in settings")
        return

    if not TELEGRAM_AVAILABLE:
        logger.error("python-telegram-bot not installed")
        return

    bot = TelegramBotHandler(token)
    bot.run()


if __name__ == "__main__":
    # Setup Django when running directly
    import os
    import sys
    import django

    # Add project root to path
    project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    sys.path.insert(0, project_root)

    # Setup Django settings
    if not os.environ.get('DJANGO_SETTINGS_MODULE'):
        os.environ['DJANGO_SETTINGS_MODULE'] = 'config.settings'

    django.setup()

    # Configure logging for console output
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
    )

    print("Starting Telegram Bot for Bijouterie Hafsa ERP...")
    run_bot()

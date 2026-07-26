"""
Telegram Admin Notifications for Sales
Sends notification to admin when a sale is confirmed/completed with:
- Product photos attached to the invoice
- Sale details (reference, seller, client, total, items)
- Payment details (method, amounts)
"""

import logging
import requests
from decimal import Decimal
from django.conf import settings

logger = logging.getLogger(__name__)


def _get_telegram_config():
    """
    Return (bot_token, chat_ids_str, enabled).

    Recipients and token come from SystemConfig (editable in Settings >
    Configuration Système — no terminal needed); environment variables are used
    only as a fallback when the DB values are empty.
    """
    token = ''
    chat_ids_str = ''
    enabled = True
    try:
        from settings_app.models import SystemConfig
        cfg = SystemConfig.get_config()
        token = (cfg.telegram_bot_token or '').strip()
        chat_ids_str = (cfg.telegram_chat_id or '').strip()
        enabled = bool(cfg.telegram_enabled)
    except Exception:
        logger.warning("Telegram: could not read SystemConfig, using env fallback")

    if not token:
        token = (getattr(settings, 'TELEGRAM_BOT_TOKEN', '') or '').strip()
    if not chat_ids_str:
        chat_ids_str = (getattr(settings, 'TELEGRAM_ADMIN_CHAT_ID', '') or '').strip()
    return token, chat_ids_str, enabled


def notify_admin_new_sale(invoice):
    """
    Send a Telegram notification to all admins about a new/completed sale.
    Sends invoice photos (if any) with sale details as caption.
    Recipients come from SystemConfig.telegram_chat_id (comma-separated for
    multiple admins), editable from the Settings page.

    Args:
        invoice: SaleInvoice instance (should have items, photos, payments prefetched ideally)
    """
    bot_token, admin_chat_ids_str, enabled = _get_telegram_config()

    if not enabled:
        logger.info("Telegram admin notification skipped: notifications disabled")
        return

    if not bot_token or not admin_chat_ids_str:
        logger.warning("Telegram admin notification skipped: missing bot token or admin chat ID")
        return

    # Support multiple admin chat IDs (comma-separated)
    admin_chat_ids = [cid.strip() for cid in admin_chat_ids_str.split(',') if cid.strip()]

    if not admin_chat_ids:
        return

    try:
        # Build the message text
        message = _build_sale_message(invoice)

        # Get invoice photos
        photos = list(invoice.photos.all())

        # Send to each admin
        for chat_id in admin_chat_ids:
            try:
                if photos:
                    _send_photos_with_caption(bot_token, chat_id, photos, message)
                else:
                    _send_text_message(bot_token, chat_id, message)
            except Exception as e:
                logger.error(f"Error sending notification to {chat_id} for {invoice.reference}: {e}")

    except Exception as e:
        logger.error(f"Error sending admin notification for invoice {invoice.reference}: {e}")


def _build_sale_message(invoice):
    """Build the notification message text for a sale"""
    lines = []

    # Header
    lines.append(f"🧾 Nouvelle Vente Confirmée")
    lines.append(f"━━━━━━━━━━━━━━━━━━━━")

    # Invoice reference
    lines.append(f"📋 Réf: #{invoice.reference}")

    # Date
    if invoice.date:
        lines.append(f"📅 Date: {invoice.date.strftime('%d/%m/%Y')}")

    # Seller
    if invoice.seller:
        seller_name = invoice.seller.get_full_name() or invoice.seller.username
        lines.append(f"👤 Vendeur: {seller_name}")

    # Client
    if invoice.client:
        lines.append(f"🏷️ Client: {invoice.client.full_name}")
    else:
        lines.append(f"🏷️ Client: Vente anonyme")

    # Items
    lines.append(f"\n📦 Articles:")
    items = list(invoice.items.select_related('product').all())
    total_weight = Decimal('0')

    for item in items:
        product = item.product
        price_str = f"{item.unit_price:,.0f}".replace(",", " ")
        item_line = f"  • {product.reference}"
        if hasattr(product, 'weight') and product.weight:
            item_line += f" ({product.weight}g)"
            total_weight += product.weight
        item_line += f" — {price_str} DH"

        # Show discount if any
        if item.discount_amount and item.discount_amount > 0:
            item_line += f" (remise: {item.discount_amount:,.0f} DH)"

        lines.append(item_line)

    # Totals
    lines.append(f"\n💰 Détails:")
    total_str = f"{invoice.total_amount:,.0f}".replace(",", " ")
    lines.append(f"  Total: {total_str} DH")

    if total_weight > 0:
        lines.append(f"  Poids total: {total_weight}g")

    # Payment details
    from payments.models import ClientPayment
    payments = list(ClientPayment.objects.filter(
        sale_invoice=invoice
    ).select_related('payment_method'))

    if payments:
        lines.append(f"\n💳 Paiements:")
        for payment in payments:
            pay_amount = f"{payment.amount:,.0f}".replace(",", " ")
            method_name = payment.payment_method.name if payment.payment_method else "N/A"
            pay_line = f"  • {method_name}: {pay_amount} DH"
            if payment.reference and not payment.reference.startswith('PAY-'):
                pay_line += f" (réf: {payment.reference})"
            lines.append(pay_line)

        paid_str = f"{invoice.amount_paid:,.0f}".replace(",", " ")
        lines.append(f"  Total payé: {paid_str} DH")

        if invoice.balance_due and invoice.balance_due > 0:
            balance_str = f"{invoice.balance_due:,.0f}".replace(",", " ")
            lines.append(f"  ⚠️ Reste à payer: {balance_str} DH")
    else:
        lines.append(f"\n💳 Paiement: Aucun enregistré")

    # Status
    status_map = {
        'paid': '✅ Payée',
        'partial_paid': '🟡 Partiellement payée',
        'unpaid': '🔴 Non payée',
    }
    status_display = status_map.get(invoice.status, invoice.get_status_display())
    lines.append(f"\n📊 Statut: {status_display}")

    # Delivery method
    delivery_map = {
        'magasin': '🏪 Magasin',
        'amana': '📦 AMANA',
        'transporteur': '🚚 Transporteur',
    }
    delivery_display = delivery_map.get(invoice.delivery_method_type, invoice.delivery_method_type or 'Magasin')
    lines.append(f"🚚 Livraison: {delivery_display}")

    if invoice.tracking_number:
        lines.append(f"📍 Suivi: {invoice.tracking_number}")

    return "\n".join(lines)


def _send_photos_with_caption(bot_token, chat_id, photos, caption):
    """Send photos to admin via Telegram API"""
    base_url = f"https://api.telegram.org/bot{bot_token}"

    # Truncate caption if needed (Telegram limit: 1024 for media caption)
    if len(caption) > 1024:
        caption = caption[:1021] + "..."

    if len(photos) == 1:
        # Single photo with caption
        photo = photos[0]
        if photo.telegram_file_id:
            # Use telegram file_id (fastest - no re-upload needed)
            data = {
                'chat_id': chat_id,
                'photo': photo.telegram_file_id,
                'caption': caption,
                'parse_mode': 'HTML'
            }
            response = requests.post(f"{base_url}/sendPhoto", data=data, timeout=30)
        elif photo.image:
            # Upload from file
            with open(photo.image.path, 'rb') as f:
                data = {
                    'chat_id': chat_id,
                    'caption': caption,
                    'parse_mode': 'HTML'
                }
                files = {'photo': f}
                response = requests.post(f"{base_url}/sendPhoto", data=data, files=files, timeout=30)
        else:
            # No photo available, send text only
            _send_text_message(bot_token, chat_id, caption)
            return

        if not response.ok:
            logger.error(f"Telegram sendPhoto failed: {response.text}")
            # Fallback to text
            _send_text_message(bot_token, chat_id, caption)
    else:
        # Multiple photos - use sendMediaGroup
        # Caption goes on the first photo only
        media = []
        for i, photo in enumerate(photos[:10]):  # Telegram limit: 10 per group
            media_item = {
                'type': 'photo',
            }

            if photo.telegram_file_id:
                media_item['media'] = photo.telegram_file_id
            elif photo.image:
                media_item['media'] = f"attach://photo_{i}"
            else:
                continue

            if i == 0:
                media_item['caption'] = caption
                media_item['parse_mode'] = 'HTML'

            media.append(media_item)

        if not media:
            _send_text_message(bot_token, chat_id, caption)
            return

        import json

        # Prepare files dict for upload
        files = {}
        for i, photo in enumerate(photos[:10]):
            if not photo.telegram_file_id and photo.image:
                try:
                    files[f'photo_{i}'] = open(photo.image.path, 'rb')
                except (FileNotFoundError, OSError):
                    continue

        data = {
            'chat_id': chat_id,
            'media': json.dumps(media)
        }

        try:
            response = requests.post(f"{base_url}/sendMediaGroup", data=data, files=files if files else None, timeout=30)
            if not response.ok:
                logger.error(f"Telegram sendMediaGroup failed: {response.text}")
                # Fallback: try sending just the first photo
                _send_photos_with_caption(bot_token, chat_id, [photos[0]], caption)
        finally:
            # Close any opened file handles
            for f in files.values():
                f.close()


def _send_text_message(bot_token, chat_id, text):
    """Send a text-only message to admin"""
    base_url = f"https://api.telegram.org/bot{bot_token}"

    data = {
        'chat_id': chat_id,
        'text': text,
        'parse_mode': 'HTML'
    }

    try:
        response = requests.post(f"{base_url}/sendMessage", data=data, timeout=30)
        if not response.ok:
            logger.error(f"Telegram sendMessage failed: {response.text}")
    except Exception as e:
        logger.error(f"Error sending Telegram message: {e}")

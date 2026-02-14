"""
Zebra Printer Utilities for Bijouterie Hafsa ERP

Two printing modes:
1. Direct TCP (port 9100) - for local network access
2. Queue-based - jobs stored in DB, printed via browser when in shop

The browser-based approach uses HTTP POST to the printer's web interface
at http://<printer_ip>/pstprnt when the user is on the local network.
"""

import socket
from django.conf import settings


def get_printer_settings():
    """
    Get printer settings from SystemConfig (database) or fall back to Django settings.
    """
    import logging
    logger = logging.getLogger(__name__)

    try:
        from settings_app.models import SystemConfig
        config = SystemConfig.get_config()
        logger.info(f"Printer config from DB: IP={config.zebra_printer_ip}, Port={config.zebra_printer_port}, Enabled={config.zebra_printer_enabled}")
        if config.zebra_printer_ip and config.zebra_printer_enabled:
            return str(config.zebra_printer_ip), config.zebra_printer_port or 9100
    except Exception as e:
        logger.exception(f"Error getting printer config from DB: {e}")

    # Fallback to environment variables
    host = getattr(settings, 'ZEBRA_PRINTER_HOST', '')
    port = getattr(settings, 'ZEBRA_PRINTER_PORT', 9100)
    logger.info(f"Using fallback printer config: IP={host}, Port={port}")
    return host, port


def send_to_printer(zpl_data):
    """
    Send ZPL data to Zebra printer via TCP
    Returns (success, message)
    """
    host, port = get_printer_settings()

    if not host:
        return False, "Printer not configured (set IP in Configuration Environnement)"

    try:
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sock.settimeout(10)
        sock.connect((host, port))
        sock.sendall(zpl_data.encode('utf-8'))
        sock.close()
        return True, "Print job sent successfully"
    except socket.timeout:
        return False, "Printer connection timeout"
    except ConnectionRefusedError:
        return False, "Printer connection refused"
    except Exception as e:
        return False, f"Print error: {str(e)}"


def queue_print_job(zpl_data, product=None, label_type='product', quantity=1, user=None):
    """
    Add a print job to the queue for later printing via browser.
    This is used when the server can't directly reach the printer.

    Returns (success, message)
    """
    from .models import PrintQueue

    try:
        job = PrintQueue.objects.create(
            product=product,
            label_type=label_type,
            quantity=quantity,
            zpl_data=zpl_data,
            created_by=user
        )
        return True, f"Job #{job.id} ajouté à la file d'impression"
    except Exception as e:
        return False, f"Erreur lors de l'ajout à la file: {str(e)}"


def print_or_queue(zpl_data, product=None, label_type='product', quantity=1, user=None):
    """
    Try to print directly. If that fails, queue the job.
    Returns (success, message, queued)
    """
    # First try direct printing
    success, message = send_to_printer(zpl_data)

    if success:
        return True, message, False

    # If direct print failed, queue the job
    queue_success, queue_message = queue_print_job(
        zpl_data=zpl_data,
        product=product,
        label_type=label_type,
        quantity=quantity,
        user=user
    )

    if queue_success:
        return True, f"Imprimante inaccessible. {queue_message}", True

    return False, f"Impression échouée et mise en file échouée: {message}", False


def string_to_hex(text, max_bytes=12):
    """
    Convert a string to hexadecimal representation for RFID encoding.
    Default: 24 hex characters (12 bytes = 96 bits) which is standard EPC length.

    If text is longer than max_bytes, takes the LAST max_bytes characters
    to preserve the unique part (e.g., date-sequence from product reference).
    """
    # If text is too long, take the last part (the unique identifier)
    if len(text) > max_bytes:
        text = text[-max_bytes:]

    hex_str = text.encode('utf-8').hex().upper()
    # Pad to max_bytes * 2 hex characters
    target_len = max_bytes * 2
    if len(hex_str) < target_len:
        hex_str = hex_str.ljust(target_len, '0')
    return hex_str


def generate_product_label_zpl(product, quantity=1, encode_rfid=True):
    """
    Generate ZPL for RFID jewelry hang tag with loop
    Total tag: 68x26mm - print on RIGHT side (the visible tag head)
    Left side has the loop/antenna

    Layout:
    - Line 1: Weight + Purity (e.g., "5.2g 18K")
    - Line 2: Size if available (e.g., "T: 45cm")
    - Bottom: Barcode + Reference

    RFID: Encodes product reference into the RFID chip
    """
    # Full reference for RFID encoding
    full_reference = product.reference or "UNKNOWN"

    # Reference parts - get date and sequence (e.g., "20260207-0001" from "PRD-FIN-20260207-0001")
    ref_parts = full_reference.split("-")
    if len(ref_parts) >= 2:
        # Get last two parts: date and sequence
        short_ref = f"{ref_parts[-2]}-{ref_parts[-1]}"
        barcode_data = short_ref  # Keep dashes for search compatibility
    else:
        short_ref = ref_parts[-1] if ref_parts else "0000"
        barcode_data = short_ref

    # Weight - compact
    weight_value = product.net_weight or product.gross_weight
    weight = f"{weight_value:.1f}" if weight_value else ""

    # Purity (e.g., "18K")
    purity = ""
    if product.metal_purity:
        purity = product.metal_purity.name

    # Size (e.g., "45" or "18")
    size = product.size.strip() if product.size else ""

    # RFID encoding command - writes product reference to EPC memory
    # ^RS8 = RFID setup (8 = UHF Gen2)
    # ^RFW,E = Write to EPC memory bank, Hex format
    # ^RFV = Verify after write (optional, adds reliability)
    rfid_commands = ""
    if encode_rfid:
        rfid_hex = string_to_hex(full_reference)
        rfid_commands = f"""^RS8
^RFW,H,1,12,1^FD{rfid_hex}^FS
"""

    # ZPL for 68x26mm tag - print on RIGHT side
    # Tag is 544 dots wide (68mm at 8 dots/mm)
    # Print area is approximately half the tag (right side)
    # X offset ~270 to start printing on right half
    if size:
        # Layout with size - adjust positions for RIGHT side
        zpl = f"""^XA
^CI28
^PW544
^LL208
{rfid_commands}^FO349,25^A0N,20,18^FD{weight}g {purity}^FS
^FO349,50^A0N,18,16^FDT: {size}cm^FS
^FO339,142^BY1^BCN,32,N,N,N^FD{barcode_data}^FS
^FO349,182^A0N,14,12^FD{short_ref}^FS
^PQ{quantity}
^XZ"""
    else:
        # Layout without size - RIGHT side
        zpl = f"""^XA
^CI28
^PW544
^LL208
{rfid_commands}^FO349,31^A0N,22,20^FD{weight}g {purity}^FS
^FO339,162^BY1^BCN,35,N,N,N^FD{barcode_data}^FS
^FO349,207^A0N,16,14^FD{short_ref}^FS
^PQ{quantity}
^XZ"""
    return zpl


def generate_price_tag_zpl(product, quantity=1):
    """
    Generate ZPL for jewelry price tag - price only on RIGHT side
    """
    price = f"{product.selling_price:.0f}" if product.selling_price else "0"

    # Purity (e.g., "18K")
    purity = ""
    if product.metal_purity:
        purity = product.metal_purity.name

    # ZPL for 68x26mm tag - print on RIGHT side
    zpl = f"""^XA
^CI28
^PW544
^LL208
^FO350,30^A0N,45,40^FD{purity}^FS
^FO350,90^A0N,70,60^FD{price}^FS
^PQ{quantity}
^XZ"""
    return zpl


def print_product_label(product, quantity=1):
    """Print a product label"""
    zpl = generate_product_label_zpl(product, quantity)
    return send_to_printer(zpl)


def print_price_tag(product, quantity=1):
    """Print a price tag"""
    zpl = generate_price_tag_zpl(product, quantity)
    return send_to_printer(zpl)


def print_test_label(encode_rfid=True):
    """Print a test label for jewelry RFID hang tag - RIGHT side with barcode
    Also encodes RFID with test reference if encode_rfid=True
    """
    test_reference = "PRD-TEST-20260210-0001"

    # RFID encoding for test
    rfid_commands = ""
    if encode_rfid:
        rfid_hex = string_to_hex(test_reference)
        rfid_commands = f"""^RS8
^RFW,H,1,12,1^FD{rfid_hex}^FS
"""

    zpl = f"""^XA
^CI28
^PW544
^LL208
{rfid_commands}^FO349,31^A0N,22,20^FD5.2g 18K^FS
^FO339,162^BY1^BCN,35,N,N,N^FD20260210-0001^FS
^FO349,207^A0N,16,14^FD20260210-0001^FS
^XZ"""
    return send_to_printer(zpl)

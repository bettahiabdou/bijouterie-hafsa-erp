"""
Zebra Printer Utilities for Bijouterie Hafsa ERP
Sends ZPL commands to Zebra printer via TCP
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


def generate_product_label_zpl(product, quantity=1):
    """
    Generate ZPL for RFID jewelry hang tag with loop
    Total tag: 68x26mm - print on LEFT side (the visible tag head)
    Right side has the loop/antenna

    Layout:
    - Line 1: Weight + Purity (e.g., "5.2g 18K")
    - Line 2: Size if available (e.g., "T: 45cm")
    - Bottom: Barcode + Reference
    """
    # Reference parts - get date and sequence (e.g., "20260207-0001" from "PRD-FIN-20260207-0001")
    ref_parts = (product.reference or "").split("-")
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

    # ZPL for 68x26mm tag - print on LEFT side
    # Line 1 (Weight + Purity): X=34, Y=31
    # Line 2 (Size): X=34, Y=55 (below purity line, only if size exists)
    # Barcode: X=26, Y=130 (or Y=110 if size exists to make room)
    # Reference: X=34, Y=175 (or Y=155 if size exists)

    if size:
        # Layout with size - adjust positions
        zpl = f"""^XA
^CI28
^PW544
^LL208
^FO34,25^A0N,20,18^FD{weight}g {purity}^FS
^FO34,50^A0N,18,16^FDT: {size}cm^FS
^FO26,110^BY1^BCN,32,N,N,N^FD{barcode_data}^FS
^FO34,150^A0N,14,12^FD{short_ref}^FS
^PQ{quantity}
^XZ"""
    else:
        # Layout without size - original spacing
        zpl = f"""^XA
^CI28
^PW544
^LL208
^FO34,31^A0N,22,20^FD{weight}g {purity}^FS
^FO26,130^BY1^BCN,35,N,N,N^FD{barcode_data}^FS
^FO34,175^A0N,16,14^FD{short_ref}^FS
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


def print_test_label():
    """Print a test label for jewelry RFID hang tag - LEFT side with barcode"""
    zpl = """^XA
^CI28
^PW544
^LL208
^FO34,31^A0N,22,20^FD5.2g 18K^FS
^FO26,130^BY1^BCN,35,N,N,N^FD20260207-0001^FS
^FO34,175^A0N,16,14^FD20260207-0001^FS
^XZ"""
    return send_to_printer(zpl)

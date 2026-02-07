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
    try:
        from settings_app.models import SystemConfig
        config = SystemConfig.get_config()
        if config.zebra_printer_ip and config.zebra_printer_enabled:
            return str(config.zebra_printer_ip), config.zebra_printer_port or 9100
    except Exception:
        pass  # Fall back to Django settings

    # Fallback to environment variables
    host = getattr(settings, 'ZEBRA_PRINTER_HOST', '')
    port = getattr(settings, 'ZEBRA_PRINTER_PORT', 9100)
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
    Printable area: ~22x22mm square (the tag head, not the loop/tail)
    Total tag: 68x26mm but only small square is printable

    Layout (very compact):
    - Line 1: Weight + Purity (e.g., "5.2g 18K")
    - Line 2: Price (e.g., "2500")
    - Line 3: Reference short code
    """
    # Short reference - last 4 digits
    ref_parts = (product.reference or "").split("-")
    short_ref = ref_parts[-1] if ref_parts else "0000"

    # Weight - compact
    weight_value = product.net_weight or product.gross_weight
    weight = f"{weight_value:.1f}" if weight_value else ""

    # Price - no decimals for compact display
    price = f"{product.selling_price:.0f}" if product.selling_price else "0"

    # Purity (e.g., "18K")
    purity = ""
    if product.metal_purity:
        purity = product.metal_purity.name

    # ZPL for small printable area (~22x22mm = ~176x176 dots at 203dpi)
    # Very compact 3-line layout
    zpl = f"""^XA
^CI28
^PW176
^LL176
^FO5,8^A0N,28,24^FD{weight}g {purity}^FS
^FO5,45^A0N,50,42^FD{price}^FS
^FO5,105^A0N,24,20^FD#{short_ref}^FS
^PQ{quantity}
^XZ"""
    return zpl


def generate_price_tag_zpl(product, quantity=1):
    """
    Generate ZPL for jewelry price tag - price only (22x22mm printable area)
    """
    price = f"{product.selling_price:.0f}" if product.selling_price else "0"

    # Purity (e.g., "18K")
    purity = ""
    if product.metal_purity:
        purity = product.metal_purity.name

    # ZPL for small printable area - just price and purity
    zpl = f"""^XA
^CI28
^PW176
^LL176
^FO5,20^A0N,35,30^FD{purity}^FS
^FO5,70^A0N,60,50^FD{price}^FS
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
    """Print a test label for jewelry RFID hang tag (22x22mm print area)"""
    zpl = """^XA
^CI28
^PW176
^LL176
^FO5,8^A0N,28,24^FD5.2g 18K^FS
^FO5,45^A0N,50,42^FD2500^FS
^FO5,105^A0N,24,20^FD#0001^FS
^XZ"""
    return send_to_printer(zpl)

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
    Generate ZPL for a jewelry hang tag (barbell/dumbbell shape)
    Typical size: 10x50mm or 12x45mm with string hole

    Layout optimized for small jewelry tags:
    - Reference code (short)
    - Weight
    - Price
    """
    # Short reference - last part only (e.g., "0001" from "PRD-FIN-20260207-0001")
    ref_parts = (product.reference or "").split("-")
    short_ref = ref_parts[-1] if ref_parts else "0000"

    # Weight
    weight_value = product.net_weight or product.gross_weight
    weight = f"{weight_value:.2f}g" if weight_value else ""

    # Price - compact format
    price = f"{product.selling_price:.0f}" if product.selling_price else "0"

    # Purity (e.g., "18K")
    purity = ""
    if product.metal_purity:
        purity = product.metal_purity.name

    # ZPL for small jewelry tag (approx 50x10mm or 45x12mm)
    # Using small fonts and tight spacing
    zpl = f"""^XA
^CI28
^PW400
^LL80
^FO10,5^A0N,20,18^FD{short_ref}^FS
^FO10,28^A0N,22,20^FD{weight} {purity}^FS
^FO10,52^A0N,24,22^FD{price}DH^FS
^PQ{quantity}
^XZ"""
    return zpl


def generate_price_tag_zpl(product, quantity=1):
    """
    Generate ZPL for jewelry price tag (even smaller - price only)
    """
    price = f"{product.selling_price:.0f}" if product.selling_price else "0"

    # Purity (e.g., "18K")
    purity = ""
    if product.metal_purity:
        purity = product.metal_purity.name

    zpl = f"""^XA
^CI28
^PW400
^LL80
^FO10,15^A0N,22,20^FD{purity}^FS
^FO10,42^A0N,28,26^FD{price}DH^FS
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
    """Print a test label for jewelry tag"""
    zpl = """^XA
^CI28
^PW400
^LL80
^FO10,5^A0N,20,18^FD0001^FS
^FO10,28^A0N,22,20^FD5.25g 18K^FS
^FO10,52^A0N,24,22^FD2500DH^FS
^XZ"""
    return send_to_printer(zpl)

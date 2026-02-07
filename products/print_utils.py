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
    Total tag: 68x26mm - print on RIGHT side (the visible tag head)
    Left side has the loop/antenna, right side is for printing

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

    # ZPL for 68x26mm tag - full width, print shifted to RIGHT side
    # 68mm width = ~544 dots, 26mm height = ~208 dots at 203dpi
    # X offset ~350 to start printing on the right portion
    zpl = f"""^XA
^CI28
^PW544
^LL208
^FO350,15^A0N,35,30^FD{weight}g {purity}^FS
^FO350,60^A0N,55,50^FD{price}^FS
^FO350,130^A0N,30,25^FD#{short_ref}^FS
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
    """Print a test label for jewelry RFID hang tag - RIGHT side"""
    zpl = """^XA
^CI28
^PW544
^LL208
^FO350,15^A0N,35,30^FD5.2g 18K^FS
^FO350,60^A0N,55,50^FD2500^FS
^FO350,130^A0N,30,25^FD#0001^FS
^XZ"""
    return send_to_printer(zpl)

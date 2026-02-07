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
    Generate ZPL for a product label
    Label size: approximately 50x30mm
    """
    name = product.name[:25] + "..." if len(product.name) > 25 else product.name
    reference = product.reference or ""
    # Use net_weight (the actual product weight) or gross_weight as fallback
    weight_value = product.net_weight or product.gross_weight
    weight = f"{weight_value:.2f}" if weight_value else "N/A"
    price = f"{product.selling_price:.2f}" if product.selling_price else "0.00"

    # Use reference as barcode data
    barcode_data = reference.replace("-", "")[:20] if reference else "000000"

    zpl = f"""^XA
^CI28
^FO30,20^A0N,32,32^FD{name}^FS
^FO30,60^A0N,24,24^FDRef: {reference}^FS
^FO30,90^A0N,24,24^FDPoids: {weight}g^FS
^FO30,125^A0N,40,40^FD{price} DH^FS
^FO30,175^BY2^BCN,50,N,N,N^FD{barcode_data}^FS
^PQ{quantity}
^XZ"""
    return zpl


def generate_price_tag_zpl(product, quantity=1):
    """
    Generate ZPL for a small price tag
    """
    name = product.name[:20] + "..." if len(product.name) > 20 else product.name
    price = f"{product.selling_price:.2f}" if product.selling_price else "0.00"

    zpl = f"""^XA
^CI28
^FO20,15^A0N,28,28^FD{name}^FS
^FO20,50^A0N,45,45^FD{price} DH^FS
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
    """Print a test label"""
    zpl = """^XA
^FO50,30^A0N,45,45^FDBijouterie Hafsa^FS
^FO50,90^A0N,30,30^FDTest Label - OK^FS
^FO50,140^BY2^BCN,80,Y,N,N^FD123456789^FS
^XZ"""
    return send_to_printer(zpl)

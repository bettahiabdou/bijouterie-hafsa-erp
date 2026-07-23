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


DPMM = 8  # 203 DPI = 8 dots per mm

# Fallback geometry (mm) if SystemConfig is unavailable
_GEOMETRY_DEFAULTS = {
    'width_mm': 70,
    'height_mm': 48,
    'x_mm': 29,
    'weight_y_mm': 6,
    'size_y_mm': 9,
    'ref_y_mm': 12,
    'barcode_y_mm': 20,
}


def get_label_geometry():
    """
    Label geometry from SystemConfig, in printer dots (8 dpmm).

    Everything is stored in millimetres so the shop can adjust label size and
    element positions from Settings > Configuration Système when the label
    stock changes — no code edit needed.
    """
    g = dict(_GEOMETRY_DEFAULTS)
    try:
        from settings_app.models import SystemConfig
        c = SystemConfig.get_config()
        mapping = {
            'width_mm': 'zebra_label_width',
            'height_mm': 'zebra_label_height',
            'x_mm': 'zebra_label_x_mm',
            'weight_y_mm': 'zebra_label_weight_y_mm',
            'size_y_mm': 'zebra_label_size_y_mm',
            'ref_y_mm': 'zebra_label_ref_y_mm',
            'barcode_y_mm': 'zebra_label_barcode_y_mm',
        }
        for key, field in mapping.items():
            val = getattr(c, field, None)
            if val:
                g[key] = val
    except Exception:
        import logging
        logging.getLogger(__name__).warning("Label geometry: falling back to defaults")

    return {
        'pw': int(g['width_mm'] * DPMM),
        'll': int(g['height_mm'] * DPMM),
        'x': int(g['x_mm'] * DPMM),
        'weight_y': int(g['weight_y_mm'] * DPMM),
        'size_y': int(g['size_y_mm'] * DPMM),
        'ref_y': int(g['ref_y_mm'] * DPMM),
        'barcode_y': int(g['barcode_y_mm'] * DPMM),
        'mm': g,
    }


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
    Generate ZPL for RFID jewelry hang tag
    Total label: 70x48mm at 8 dpmm (203 DPI) ZD621R = 560×384 dots
    """
    full_reference = product.reference or "UNKNOWN"

    ref_parts = full_reference.split("-")
    if len(ref_parts) >= 2:
        short_ref = f"{ref_parts[-2]}-{ref_parts[-1]}"
        barcode_data = short_ref
    else:
        short_ref = ref_parts[-1] if ref_parts else "0000"
        barcode_data = short_ref

    weight_value = product.net_weight or product.gross_weight
    weight = f"{weight_value:.2f}" if weight_value else ""

    purity = ""
    if product.metal_purity:
        purity = product.metal_purity.name

    size = product.size.strip() if product.size else ""

    rfid_commands = ""
    if encode_rfid:
        rfid_hex = string_to_hex(full_reference)
        if not product.rfid_tag or product.rfid_tag != rfid_hex:
            from .models import Product as ProductModel
            ProductModel.objects.filter(pk=product.pk).update(rfid_tag=rfid_hex)
        rfid_commands = f"""^RS8,,,10,N,240
^RFW,H,2,12,1^FD{rfid_hex}^FS
"""

    # Geometry comes from SystemConfig (mm -> dots), adjustable without code changes
    g = get_label_geometry()
    x = g['x']
    if size:
        zpl = f"""^XA
^CI28
^LH0,0^LT0
^PW{g['pw']}
^LL{g['ll']}
{rfid_commands}^FO{x},{g['weight_y']}^A0N,22,20^FD{weight}g {purity}^FS
^FO{x},{g['size_y']}^A0N,16,14^FDT: {size}cm^FS
^FO{x},{g['ref_y']}^A0N,22,20^FD{short_ref}^FS
^FO{x},{g['barcode_y']}^BY1^BCN,50,N,N,N^FD{barcode_data}^FS
^PQ{quantity}
^XZ"""
    else:
        zpl = f"""^XA
^CI28
^LH0,0^LT0
^PW{g['pw']}
^LL{g['ll']}
{rfid_commands}^FO{x},{g['weight_y']}^A0N,24,22^FD{weight}g {purity}^FS
^FO{x},{g['ref_y']}^A0N,26,24^FD{short_ref}^FS
^FO{x},{g['barcode_y']}^BY1^BCN,55,N,N,N^FD{barcode_data}^FS
^PQ{quantity}
^XZ"""
    return zpl


def generate_price_tag_zpl(product, quantity=1):
    """
    Generate ZPL for jewelry price tag — 70x48mm at 8 dpmm (203 DPI)
    """
    price = f"{product.selling_price:.0f}" if product.selling_price else "0"

    purity = ""
    if product.metal_purity:
        purity = product.metal_purity.name

    g = get_label_geometry()
    x = g['x']
    zpl = f"""^XA
^CI28
^LH0,0^LT0
^PW{g['pw']}
^LL{g['ll']}
^FO{x},{g['weight_y']}^A0N,36,30^FD{purity}^FS
^FO{x},{g['ref_y']}^A0N,50,45^FD{price}^FS
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


def test_label_zpl(encode_rfid=True):
    """Build the ZPL for a sample hang tag (uses the configured geometry)."""
    test_reference = "PRD-TEST-20260210-0001"

    rfid_commands = ""
    if encode_rfid:
        rfid_hex = string_to_hex(test_reference)
        rfid_commands = f"""^RS8,,,10,N,240
^RFW,H,2,12,1^FD{rfid_hex}^FS
"""

    g = get_label_geometry()
    x = g['x']
    return f"""^XA
^CI28
^LH0,0^LT0
^PW{g['pw']}
^LL{g['ll']}
{rfid_commands}^FO{x},{g['weight_y']}^A0N,24,22^FD5.2g 18K^FS
^FO{x},{g['ref_y']}^A0N,26,24^FD20260210-0001^FS
^FO{x},{g['barcode_y']}^BY1^BCN,55,N,N,N^FD20260210-0001^FS
^XZ"""


def print_test_label(encode_rfid=True):
    """Print a test label for RFID jewelry hang tag (direct TCP)."""
    return send_to_printer(test_label_zpl(encode_rfid))


def calibration_zpl():
    """
    ZPL that re-runs the printer's media calibration.

    Required after changing label stock: the printer must re-learn the label
    length and gap position, otherwise it keeps using the previous pitch and
    prints across the gap onto the liner / VOID section.
    """
    # ~JC = force media calibration on next feed; ^JUS saves settings
    return "^XA^JUS^XZ\n~JC\n"


def calibrate_printer():
    """Send a media calibration to the printer (direct TCP)."""
    return send_to_printer(calibration_zpl())


def geometry_ruler_zpl():
    """
    ZPL for a diagnostic label: a box at the configured label size, so the
    printed area can be measured against the real stock.
    """
    g = get_label_geometry()
    pw, ll = g['pw'], g['ll']
    mm = g['mm']
    return f"""^XA
^CI28
^LH0,0^LT0
^PW{pw}
^LL{ll}
^FO0,0^GB{pw},{ll},2^FS
^FO8,8^A0N,18,16^FD{mm['width_mm']}x{mm['height_mm']}mm^FS
^FO{g['x']},{g['weight_y']}^GB60,2,2^FS
^FO{g['x']},{g['ref_y']}^A0N,18,16^FDX{mm['x_mm']} Y{mm['ref_y_mm']}^FS
^XZ"""


def print_geometry_ruler():
    """Print the geometry ruler label (direct TCP)."""
    return send_to_printer(geometry_ruler_zpl())


def queue_zpl(zpl, label_type='test', quantity=1, user=None):
    """
    Put raw ZPL into the print queue instead of sending it over TCP.

    Used when the printer is on a different network from the server: the local
    print agent in the shop polls the queue and forwards jobs to the printer.
    """
    from .models import PrintQueue
    job = PrintQueue.objects.create(
        label_type=label_type,
        quantity=quantity,
        zpl_data=zpl,
        status=PrintQueue.Status.PENDING,
        created_by=user,
    )
    return job

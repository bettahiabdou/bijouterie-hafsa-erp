"""
Secure Print Server for Bijouterie Hafsa ERP
Receives print jobs from the ERP and sends to Zebra printer

Run: python print_server.py
"""

import socket
import os
from flask import Flask, request, jsonify
from functools import wraps

app = Flask(__name__)

# Configuration - Can be overridden with environment variables
PRINTER_IP = os.environ.get("PRINTER_IP", "196.79.122.67")
PRINTER_PORT = int(os.environ.get("PRINTER_PORT", "9100"))
API_KEY = os.environ.get("PRINT_API_KEY", "hafsa-print-secret-2024")  # Change this!

def require_api_key(f):
    """Decorator to require API key for endpoints"""
    @wraps(f)
    def decorated(*args, **kwargs):
        key = request.headers.get('X-API-Key') or request.args.get('api_key')
        if key != API_KEY:
            return jsonify({"error": "Invalid API key"}), 401
        return f(*args, **kwargs)
    return decorated

def send_to_printer(zpl_data):
    """Send ZPL data directly to Zebra printer via TCP"""
    try:
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sock.settimeout(10)
        sock.connect((PRINTER_IP, PRINTER_PORT))
        sock.sendall(zpl_data.encode('utf-8'))
        sock.close()
        return True, "Print job sent successfully"
    except socket.timeout:
        return False, "Printer connection timeout"
    except ConnectionRefusedError:
        return False, "Printer connection refused - check if printer is on"
    except Exception as e:
        return False, f"Print error: {str(e)}"

@app.route('/health', methods=['GET'])
def health():
    """Health check endpoint"""
    return jsonify({"status": "ok", "printer": f"{PRINTER_IP}:{PRINTER_PORT}"})

@app.route('/print', methods=['POST'])
@require_api_key
def print_label():
    """
    Print a label

    Body (JSON):
    {
        "zpl": "^XA^FO50,50^A0N,50,50^FDHello^FS^XZ"
    }

    Or for product label:
    {
        "type": "product",
        "reference": "PRD-123",
        "name": "Bracelet Or",
        "price": "1500.00",
        "weight": "10.5",
        "barcode": "123456789"
    }
    """
    data = request.get_json()

    if not data:
        return jsonify({"error": "No data provided"}), 400

    # If raw ZPL provided
    if 'zpl' in data:
        zpl = data['zpl']

    # If product label requested
    elif data.get('type') == 'product':
        zpl = generate_product_label(
            reference=data.get('reference', ''),
            name=data.get('name', ''),
            price=data.get('price', ''),
            weight=data.get('weight', ''),
            barcode=data.get('barcode', '')
        )

    else:
        return jsonify({"error": "Invalid request - provide 'zpl' or 'type'"}), 400

    success, message = send_to_printer(zpl)

    if success:
        return jsonify({"success": True, "message": message})
    else:
        return jsonify({"success": False, "error": message}), 500

@app.route('/print/test', methods=['POST'])
@require_api_key
def print_test():
    """Print a test label"""
    zpl = """^XA
^FO50,30^A0N,45,45^FDBijouterie Hafsa^FS
^FO50,90^A0N,30,30^FDTest Label - OK^FS
^FO50,140^BY2^BCN,80,Y,N,N^FD123456789^FS
^XZ"""

    success, message = send_to_printer(zpl)

    if success:
        return jsonify({"success": True, "message": "Test label printed!"})
    else:
        return jsonify({"success": False, "error": message}), 500

def generate_product_label(reference, name, price, weight, barcode):
    """Generate ZPL for a product label (50x30mm label)"""
    # Truncate name if too long
    if len(name) > 25:
        name = name[:22] + "..."

    zpl = f"""^XA
^CI28
^FO30,20^A0N,28,28^FD{name}^FS
^FO30,55^A0N,22,22^FDRef: {reference}^FS
^FO30,85^A0N,22,22^FDPoids: {weight}g^FS
^FO30,115^A0N,35,35^FD{price} DH^FS
^FO30,160^BY2^BCN,60,N,N,N^FD{barcode}^FS
^XZ"""
    return zpl

if __name__ == '__main__':
    print("=" * 50)
    print("Bijouterie Hafsa - Print Server")
    print("=" * 50)
    print(f"Printer: {PRINTER_IP}:{PRINTER_PORT}")
    print(f"API Key: {API_KEY}")
    print("")
    print("Starting server on http://localhost:5000")
    print("Use ngrok to expose: ngrok http 5000")
    print("=" * 50)

    app.run(host='0.0.0.0', port=5000, debug=False)

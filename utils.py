"""
Utility functions for Bijouterie Hafsa ERP
"""

from django.utils import timezone
from decimal import Decimal
import uuid
import logging

logger = logging.getLogger(__name__)

# Optional imports for gold price service
try:
    import requests
    REQUESTS_AVAILABLE = True
except ImportError:
    REQUESTS_AVAILABLE = False
    logger.warning("requests library not available - gold price service disabled")

try:
    from django.core.cache import cache
    CACHE_AVAILABLE = True
except ImportError:
    CACHE_AVAILABLE = False


def generate_reference(prefix, model_class=None, date_based=True):
    """
    Generate a unique reference code for any entity

    Args:
        prefix (str): Reference prefix (e.g., 'CLIENT', 'BANK', 'SUPPLIER')
        model_class: Django model class to check for existing references
        date_based (bool): Include date in reference (format: PREFIX-YYYYMMDD-####)

    Returns:
        str: Generated reference code

    Examples:
        generate_reference('CLIENT', Client) → 'CLIENT-20260204-0001'
        generate_reference('BANK', BankAccount) → 'BANK-20260204-0001'
        generate_reference('SUPP', Supplier) → 'SUPP-20260204-0001'
    """
    if date_based and model_class:
        today = timezone.now().date()
        # Count records created today
        count = model_class.objects.filter(
            created_at__date=today if hasattr(model_class, 'created_at') else None
        ).count() + 1
        return f'{prefix}-{today.strftime("%Y%m%d")}-{count:04d}'
    else:
        # Use UUID-based reference without date
        unique_id = str(uuid.uuid4())[:8].upper()
        return f'{prefix}-{unique_id}'


def generate_client_code(first_name='', last_name=''):
    """
    Generate a unique client code
    Format: CLI-YYYYMMDD-####
    """
    from clients.models import Client
    today = timezone.now().date()
    count = Client.objects.filter(created_at__date=today).count() + 1
    return f'CLI-{today.strftime("%Y%m%d")}-{count:04d}'


def generate_supplier_code():
    """
    Generate a unique supplier code
    Format: SUP-YYYYMMDD-####
    """
    from suppliers.models import Supplier
    today = timezone.now().date()
    count = Supplier.objects.filter(created_at__date=today).count() + 1
    return f'SUP-{today.strftime("%Y%m%d")}-{count:04d}'


def generate_product_reference(product_type='FIN'):
    """
    Generate a unique product reference
    Format: PRD-TYPE-YYYYMMDD-####

    Args:
        product_type (str): Product type prefix
            - 'FIN' for Finished products
            - 'RAW' for Raw materials
            - 'STN' for Stones
            - 'CMP' for Components
    """
    from products.models import Product
    import re

    today = timezone.now().date()
    date_str = today.strftime("%Y%m%d")

    # Find the highest existing reference number for today
    # Look for references containing today's date and extract the sequence number
    today_products = Product.objects.filter(
        reference__contains=date_str
    )

    max_num = 0
    for product in today_products:
        # Extract the last 4-digit sequence number from the reference
        match = re.search(r'-(\d{4})$', product.reference)
        if match:
            num = int(match.group(1))
            if num > max_num:
                max_num = num

    next_num = max_num + 1
    return f'PRD-{product_type}-{date_str}-{next_num:04d}'


def generate_bank_account_code():
    """
    Generate a unique bank account code
    Format: BANK-YYYYMMDD-####
    """
    from settings_app.models import BankAccount
    today = timezone.now().date()
    count = BankAccount.objects.filter(created_at__date=today).count() + 1
    return f'BANK-{today.strftime("%Y%m%d")}-{count:04d}'


def generate_purchase_order_reference():
    """
    Generate a unique purchase order reference
    Format: PO-YYYYMMDD-####
    """
    from purchases.models import PurchaseOrder
    today = timezone.now().date()
    count = PurchaseOrder.objects.filter(date=today).count() + 1
    return f'PO-{today.strftime("%Y%m%d")}-{count:04d}'


def generate_purchase_invoice_reference():
    """
    Generate a unique purchase invoice reference
    Format: PI-YYYYMMDD-####
    """
    from purchases.models import PurchaseInvoice
    today = timezone.now().date()
    count = PurchaseInvoice.objects.filter(date=today).count() + 1
    return f'PI-{today.strftime("%Y%m%d")}-{count:04d}'


def generate_consignment_reference():
    """
    Generate a unique consignment reference
    Format: CS-YYYYMMDD-####
    """
    from purchases.models import Consignment
    today = timezone.now().date()
    count = Consignment.objects.filter(created_at__date=today).count() + 1
    return f'CS-{today.strftime("%Y%m%d")}-{count:04d}'


def generate_sales_invoice_reference():
    """
    Generate a unique sales invoice reference
    Format: INV-YYYYMMDD-####
    """
    from sales.models import SaleInvoice
    today = timezone.now().date()
    count = SaleInvoice.objects.filter(date=today).count() + 1
    return f'INV-{today.strftime("%Y%m%d")}-{count:04d}'


def generate_quote_reference():
    """
    Generate a unique quote reference
    Format: QT-YYYYMMDD-####
    """
    from quotes.models import Quote
    today = timezone.now().date()
    count = Quote.objects.filter(created_at__date=today).count() + 1
    return f'QT-{today.strftime("%Y%m%d")}-{count:04d}'


def generate_repair_reference():
    """
    Generate a unique repair reference
    Format: REP-YYYYMMDD-####
    """
    from repairs.models import Repair
    today = timezone.now().date()
    count = Repair.objects.filter(created_at__date=today).count() + 1
    return f'REP-{today.strftime("%Y%m%d")}-{count:04d}'


def generate_payment_reference(payment_type='PAY'):
    """
    Generate a unique payment reference
    Format: PAY-YYYYMMDD-#### or SUP-PAY-YYYYMMDD-####
    """
    from payments.models import ClientPayment
    today = timezone.now().date()
    count = ClientPayment.objects.filter(payment_date=today).count() + 1
    return f'{payment_type}-{today.strftime("%Y%m%d")}-{count:04d}'


def generate_old_gold_reference():
    """
    Generate a unique old gold reference
    Format: OG-YYYYMMDD-####
    """
    from clients.models import OldGoldPurchase
    today = timezone.now().date()
    count = OldGoldPurchase.objects.filter(created_at__date=today).count() + 1
    return f'OG-{today.strftime("%Y%m%d")}-{count:04d}'


# ============================================================================
# CONFIGURATION MODEL CODE GENERATION FUNCTIONS
# ============================================================================
# These functions generate automatic codes for configuration models
# Format: PREFIX-YYYYMMDD-#### (date-based sequential)

def generate_metal_type_code():
    """Generate a unique metal type code: MTL-YYYYMMDD-####"""
    from settings_app.models import MetalType
    today = timezone.now().date()
    count = MetalType.objects.filter(created_at__date=today).count() + 1
    return f'MTL-{today.strftime("%Y%m%d")}-{count:04d}'


def generate_category_code():
    """Generate a unique product category code: CAT-YYYYMMDD-####"""
    from settings_app.models import ProductCategory
    today = timezone.now().date()
    count = ProductCategory.objects.filter(created_at__date=today).count() + 1
    return f'CAT-{today.strftime("%Y%m%d")}-{count:04d}'


def generate_stone_type_code():
    """Generate a unique stone type code: STN-YYYYMMDD-####"""
    from settings_app.models import StoneType
    today = timezone.now().date()
    count = StoneType.objects.filter(created_at__date=today).count() + 1
    return f'STN-{today.strftime("%Y%m%d")}-{count:04d}'


def generate_stone_clarity_code():
    """Generate a unique stone clarity code: CLR-####"""
    from settings_app.models import StoneClarity
    count = StoneClarity.objects.count() + 1
    return f'CLR-{count:04d}'


def generate_stone_color_code():
    """Generate a unique stone color code: COL-####"""
    from settings_app.models import StoneColor
    count = StoneColor.objects.count() + 1
    return f'COL-{count:04d}'


def generate_stone_cut_code():
    """Generate a unique stone cut code: CUT-####"""
    from settings_app.models import StoneCut
    count = StoneCut.objects.count() + 1
    return f'CUT-{count:04d}'


def generate_payment_method_code():
    """Generate a unique payment method code: PMT-YYYYMMDD-####"""
    from settings_app.models import PaymentMethod
    today = timezone.now().date()
    count = PaymentMethod.objects.filter(created_at__date=today).count() + 1
    return f'PMT-{today.strftime("%Y%m%d")}-{count:04d}'


def generate_stock_location_code():
    """Generate a unique stock location code: LOC-YYYYMMDD-####"""
    from settings_app.models import StockLocation
    today = timezone.now().date()
    count = StockLocation.objects.filter(created_at__date=today).count() + 1
    return f'LOC-{today.strftime("%Y%m%d")}-{count:04d}'


def generate_delivery_method_code():
    """Generate a unique delivery method code: DEL-YYYYMMDD-####"""
    from settings_app.models import DeliveryMethod
    today = timezone.now().date()
    count = DeliveryMethod.objects.filter(created_at__date=today).count() + 1
    return f'DEL-{today.strftime("%Y%m%d")}-{count:04d}'


def generate_repair_type_code():
    """Generate a unique repair type code: REP-YYYYMMDD-####"""
    from settings_app.models import RepairType
    today = timezone.now().date()
    count = RepairType.objects.filter(created_at__date=today).count() + 1
    return f'REP-{today.strftime("%Y%m%d")}-{count:04d}'


def generate_certificate_issuer_code():
    """Generate a unique certificate issuer code: CERT-YYYYMMDD-####"""
    from settings_app.models import CertificateIssuer
    today = timezone.now().date()
    count = CertificateIssuer.objects.filter(created_at__date=today).count() + 1
    return f'CERT-{today.strftime("%Y%m%d")}-{count:04d}'


# ============================================================================
# GOLD PRICE SERVICE
# ============================================================================
# Free APIs used:
# - Gold price: https://api.gold-api.com/price/XAU (no API key, no limits)
# - Exchange rate: https://open.er-api.com/v6/latest/USD (no API key, free)

# Troy ounce to gram conversion
TROY_OUNCE_TO_GRAM = Decimal('31.1035')

# Cache timeout in seconds (5 minutes)
GOLD_PRICE_CACHE_TIMEOUT = 300


def get_gold_price_usd():
    """
    Get current gold price in USD per troy ounce from Gold-API.com

    Returns:
        dict: {'price': Decimal, 'updated_at': str} or None if failed
    """
    if not REQUESTS_AVAILABLE:
        return None

    cache_key = 'gold_price_usd'
    if CACHE_AVAILABLE:
        cached = cache.get(cache_key)
        if cached:
            return cached

    try:
        response = requests.get(
            'https://api.gold-api.com/price/XAU',
            timeout=10
        )
        response.raise_for_status()
        data = response.json()

        result = {
            'price': Decimal(str(data['price'])),
            'updated_at': data.get('updatedAt', ''),
            'name': data.get('name', 'Gold'),
        }

        if CACHE_AVAILABLE:
            cache.set(cache_key, result, GOLD_PRICE_CACHE_TIMEOUT)
        return result
    except Exception as e:
        logger.error(f"Failed to fetch gold price: {e}")
        return None


def get_usd_to_mad_rate():
    """
    Get current USD to MAD exchange rate from Open Exchange Rates API

    Returns:
        Decimal: Exchange rate or None if failed
    """
    if not REQUESTS_AVAILABLE:
        return None

    cache_key = 'usd_mad_rate'
    if CACHE_AVAILABLE:
        cached = cache.get(cache_key)
        if cached:
            return cached

    try:
        response = requests.get(
            'https://open.er-api.com/v6/latest/USD',
            timeout=10
        )
        response.raise_for_status()
        data = response.json()

        rate = Decimal(str(data['rates']['MAD']))
        if CACHE_AVAILABLE:
            cache.set(cache_key, rate, GOLD_PRICE_CACHE_TIMEOUT)
        return rate
    except Exception as e:
        logger.error(f"Failed to fetch USD/MAD rate: {e}")
        return None


def get_gold_price_mad():
    """
    Get current gold prices in MAD (Moroccan Dirham)

    Returns:
        dict: {
            'price_per_ounce_usd': Decimal,
            'price_per_ounce_mad': Decimal,
            'price_per_gram_mad': Decimal,
            'price_24k_gram': Decimal,
            'price_22k_gram': Decimal,
            'price_21k_gram': Decimal,
            'price_18k_gram': Decimal,
            'price_14k_gram': Decimal,
            'usd_mad_rate': Decimal,
            'updated_at': str,
        } or None if failed
    """
    if not REQUESTS_AVAILABLE:
        return None

    cache_key = 'gold_price_mad_full'
    if CACHE_AVAILABLE:
        cached = cache.get(cache_key)
        if cached:
            return cached

    gold_usd = get_gold_price_usd()
    mad_rate = get_usd_to_mad_rate()

    if not gold_usd or not mad_rate:
        return None

    price_per_ounce_usd = gold_usd['price']
    price_per_ounce_mad = price_per_ounce_usd * mad_rate
    price_per_gram_mad = price_per_ounce_mad / TROY_OUNCE_TO_GRAM

    # Calculate prices for different karats (24K = 100% pure)
    result = {
        'price_per_ounce_usd': price_per_ounce_usd.quantize(Decimal('0.01')),
        'price_per_ounce_mad': price_per_ounce_mad.quantize(Decimal('0.01')),
        'price_per_gram_mad': price_per_gram_mad.quantize(Decimal('0.01')),
        'price_24k_gram': price_per_gram_mad.quantize(Decimal('0.01')),
        'price_22k_gram': (price_per_gram_mad * Decimal('22') / Decimal('24')).quantize(Decimal('0.01')),
        'price_21k_gram': (price_per_gram_mad * Decimal('21') / Decimal('24')).quantize(Decimal('0.01')),
        'price_18k_gram': (price_per_gram_mad * Decimal('18') / Decimal('24')).quantize(Decimal('0.01')),
        'price_14k_gram': (price_per_gram_mad * Decimal('14') / Decimal('24')).quantize(Decimal('0.01')),
        'usd_mad_rate': mad_rate.quantize(Decimal('0.0001')),
        'updated_at': gold_usd['updated_at'],
    }

    if CACHE_AVAILABLE:
        cache.set(cache_key, result, GOLD_PRICE_CACHE_TIMEOUT)
    return result

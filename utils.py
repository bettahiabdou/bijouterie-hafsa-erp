"""
Utility functions for Bijouterie Hafsa ERP
"""

from django.utils import timezone
import uuid


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

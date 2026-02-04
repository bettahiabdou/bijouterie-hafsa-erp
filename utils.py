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
    today = timezone.now().date()
    count = Product.objects.filter(created_at__date=today).count() + 1
    return f'PRD-{product_type}-{today.strftime("%Y%m%d")}-{count:04d}'


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

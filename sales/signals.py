"""
Signals for the sales app.

Keeps the product-circulation register (online-selling flow) in sync with
invoice line items:

  * When a product that is currently OUT (en circulation) is added to any
    invoice - draft "vente en attente" or finalized - its circulation record
    is auto-flipped to SOLD and linked to that invoice.
  * If that line item is later removed and the product no longer appears on
    any active invoice, the circulation record reverts to OUT so it shows up
    again in the circulation list.
"""
from django.db.models.signals import post_save, post_delete
from django.dispatch import receiver
from django.utils import timezone

from .models import SaleInvoiceItem, ProductCirculation


@receiver(post_save, sender=SaleInvoiceItem)
def mark_circulation_sold(sender, instance, created, **kwargs):
    """Flip an active OUT circulation to SOLD when its product is invoiced."""
    if not created or not instance.product_id:
        return

    active = ProductCirculation.objects.filter(
        product_id=instance.product_id,
        status=ProductCirculation.Status.OUT,
    ).first()
    if active:
        active.status = ProductCirculation.Status.SOLD
        active.invoice = instance.invoice
        active.date_back = timezone.now()
        active.save(update_fields=['status', 'invoice', 'date_back'])


@receiver(post_delete, sender=SaleInvoiceItem)
def revert_circulation_on_item_removed(sender, instance, **kwargs):
    """
    If a line item is removed and the product is no longer on any active
    (non-deleted) invoice, put its SOLD circulation back to OUT.
    """
    if not instance.product_id:
        return

    still_invoiced = SaleInvoiceItem.objects.filter(
        product_id=instance.product_id,
        invoice__is_deleted=False,
    ).exists()
    if still_invoiced:
        return

    sold = ProductCirculation.objects.filter(
        product_id=instance.product_id,
        status=ProductCirculation.Status.SOLD,
    ).order_by('-date_back').first()
    if sold:
        sold.status = ProductCirculation.Status.OUT
        sold.invoice = None
        sold.date_back = None
        sold.save(update_fields=['status', 'invoice', 'date_back'])

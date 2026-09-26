"""
Mobile sale entry: the seller enters the whole sale on the phone (articles,
prices, client, delivery, payments, photos) and submits it; an admin/manager
validates it in one click (or sends it back). Scanned pieces are reserved at
submission so no one else can sell them.

The stored `SaleInvoice.submission` payload uses the exact shape consumed by
`_complete_draft` (same logic as pending_invoice_complete_api), so validation
reuses the existing completion code.
"""
import io
import json
import logging
from decimal import Decimal, InvalidOperation

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.db import transaction
from django.db.models import Q
from django.http import JsonResponse, HttpResponseForbidden
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils import timezone
from django.views.decorators.http import require_http_methods

from clients.models import Client
from products.models import Product
from settings_app.models import Carrier, PaymentMethod
from users.models import ActivityLog

from .models import InvoicePhoto, SaleInvoice

logger = logging.getLogger(__name__)

PHOTO_FIELDS = {
    'photos_invoice': InvoicePhoto.PhotoType.INVOICE,
    'photos_product': InvoicePhoto.PhotoType.PRODUCT,
    'photos_delivery': InvoicePhoto.PhotoType.DELIVERY,
    'photos_payment': InvoicePhoto.PhotoType.PAYMENT,
}
DELIVERY_TYPES = ('magasin', 'amana', 'transporteur', 'en_stock')


def _can_validate(user):
    return bool(user.is_superuser or getattr(user, 'role', None) in ('admin', 'manager'))


def _product_image(p):
    try:
        if p.main_image:
            return p.main_image.url
    except Exception:
        pass
    img = p.images.first()
    try:
        return img.image.url if img and img.image else ''
    except Exception:
        return ''


def _product_json(p):
    return {
        'id': p.id,
        'reference': p.reference,
        'name': p.name or '',
        'status': p.status,
        'status_display': p.get_status_display(),
        'available': p.status == 'available',
        'image': _product_image(p),
        'weight': f'{p.gross_weight:.2f}' if p.gross_weight is not None else '',
        'metal': p.metal_type.name if p.metal_type_id else '',
        'selling_price': f'{(p.selling_price or 0):.2f}',
        'minimum_price': f'{(p.minimum_price or 0):.2f}',
    }


def _payment_methods():
    # Dépôt client needs the deposit-account debit flow of the classic page;
    # keep it out of the phone form for now.
    return [m for m in PaymentMethod.objects.filter(is_active=True).order_by('display_order', 'name')
            if 'dépôt' not in m.name.lower() and 'depot' not in m.name.lower()]


def _unreserve(invoice):
    ids = (invoice.submission or {}).get('reserved_ids') or []
    if ids:
        Product.objects.filter(id__in=ids, status='reserved').update(status='available')


def _compress(upload, max_side=1800):
    """Downscale big phone photos server-side too (belt and braces)."""
    try:
        from PIL import Image, ImageOps
        from django.core.files.uploadedfile import InMemoryUploadedFile
        im = Image.open(upload)
        im = ImageOps.exif_transpose(im)
        if max(im.size) <= max_side and (upload.size or 0) < 1_500_000:
            upload.seek(0)
            return upload
        im.thumbnail((max_side, max_side))
        if im.mode not in ('RGB', 'L'):
            im = im.convert('RGB')
        buf = io.BytesIO()
        im.save(buf, 'JPEG', quality=82, optimize=True)
        buf.seek(0)
        name = (upload.name.rsplit('.', 1)[0] or 'photo') + '.jpg'
        return InMemoryUploadedFile(buf, 'image', name, 'image/jpeg', buf.getbuffer().nbytes, None)
    except Exception:
        upload.seek(0)
        return upload


# ---------------------------------------------------------------------------
# Seller side
# ---------------------------------------------------------------------------

@login_required(login_url='login')
def mobile_sale(request, reference=None):
    """Phone sale form. With `reference`: reopen one of my sales sent back
    for correction (prefilled from its submission)."""
    invoice = None
    prefill = None
    if reference:
        invoice = get_object_or_404(SaleInvoice, reference=reference, is_deleted=False,
                                    status=SaleInvoice.Status.DRAFT)
        if invoice.seller_id != request.user.id and not _can_validate(request.user):
            return HttpResponseForbidden('Cette vente appartient à un autre vendeur.')
        if invoice.submitted_at:
            messages.info(request, 'Cette vente est déjà en attente de validation.')
            return redirect('sales:mobile_sale_mine')
        sub = invoice.submission or {}
        items = []
        for it in sub.get('items') or []:
            p = Product.objects.select_related('metal_type').filter(pk=it.get('product_id')).first()
            if p:
                pj = _product_json(p)
                pj['price'] = str(it.get('selling_price') or '')
                items.append(pj)
        client = None
        cid = (sub.get('client') or {}).get('id')
        if cid:
            c = Client.objects.filter(pk=cid).first()
            if c:
                client = {'id': c.id, 'name': c.full_name, 'phone': c.phone or ''}
        prefill = {
            'reference': sub.get('handwritten_ref') or '',
            'items': items,
            'client': client,
            'delivery': sub.get('delivery') or {},
            'payments': sub.get('payments') or [],
            'existing_photos': {
                t: invoice.photos.filter(photo_type=t).count()
                for t in PHOTO_FIELDS.values()
            },
        }

    methods = _payment_methods()
    returned_count = SaleInvoice.objects.filter(
        seller=request.user, status=SaleInvoice.Status.DRAFT, is_deleted=False,
        submitted_at__isnull=True, submission__isnull=False).count()
    return render(request, 'sales/mobile_sale.html', {
        'invoice': invoice,
        'prefill_json': json.dumps(prefill) if prefill else 'null',
        'methods_json': json.dumps([{
            'id': m.id, 'name': m.name, 'cod': bool(m.collected_by_carrier),
            'needs_ref': bool(m.requires_reference),
        } for m in methods]),
        'carriers': Carrier.objects.filter(is_active=True).order_by('name'),
        'returned_count': returned_count,
    })


@login_required(login_url='login')
def mobile_sale_lookup(request):
    """Resolve a scanned/typed code to a product (barcode, reference, RFID)."""
    from products.views import _resolve_product_by_code
    code = (request.GET.get('code') or '').strip()
    if not code:
        return JsonResponse({'ok': False, 'error': 'Code vide.'}, status=400)
    p = _resolve_product_by_code(code)
    if not p:
        return JsonResponse({'ok': False, 'error': f'Aucun produit pour « {code} ».'}, status=404)
    return JsonResponse({'ok': True, 'product': _product_json(p)})


@login_required(login_url='login')
@require_http_methods(["POST"])
def mobile_sale_submit(request):
    """Validate the seller's sale, reserve the pieces, store photos, and queue
    it for admin validation."""
    def fail(msg, status=400):
        return JsonResponse({'ok': False, 'error': msg}, status=status)

    try:
        data = json.loads(request.POST.get('payload') or '{}')
    except ValueError:
        return fail('Données invalides.')

    # --- Items & prices ---
    items_in = data.get('items') or []
    if not items_in:
        return fail('Ajoutez au moins un article.')
    seen, items = set(), []
    for it in items_in:
        try:
            pid = int(it.get('product_id'))
            price = Decimal(str(it.get('selling_price')))
        except (TypeError, ValueError, InvalidOperation):
            return fail('Prix de vente invalide.')
        if pid in seen:
            return fail('Un même article est ajouté deux fois.')
        if price <= 0:
            return fail('Chaque article doit avoir un prix de vente.')
        seen.add(pid)
        items.append({'product_id': pid, 'selling_price': str(price), 'quantity': 1})
    total = sum(Decimal(i['selling_price']) for i in items)

    # --- Delivery ---
    d = data.get('delivery') or {}
    dtype = (d.get('type') or 'magasin').strip()
    if dtype not in DELIVERY_TYPES:
        return fail('Mode de livraison invalide.')
    tracking = (d.get('tracking_number') or '').strip().upper().replace(' ', '')
    carrier_id = d.get('carrier_id') or None
    if dtype == 'amana' and not tracking:
        return fail('Le code AMANA est obligatoire pour une livraison AMANA.')
    if dtype == 'transporteur' and not carrier_id:
        return fail('Choisissez le transporteur.')
    delivery = {'type': dtype, 'tracking_number': tracking}
    if carrier_id:
        delivery['carrier_id'] = int(carrier_id)

    # --- Client ---
    client = None
    cid = (data.get('client') or {}).get('id')
    if cid:
        if not Client.objects.filter(pk=cid).exists():
            return fail('Client introuvable.')
        client = {'id': int(cid)}
    if dtype in ('amana', 'transporteur', 'en_stock') and not client:
        return fail('Le client (nom + téléphone) est obligatoire pour cette livraison.')

    # --- Payments ---
    methods = {m.id: m for m in _payment_methods()}
    payments, paid = [], Decimal('0')
    today = timezone.localdate().isoformat()
    for p in data.get('payments') or []:
        try:
            amount = Decimal(str(p.get('amount') or '0'))
        except InvalidOperation:
            return fail('Montant de paiement invalide.')
        if amount <= 0:
            continue
        m = methods.get(int(p.get('method_id') or 0))
        if not m:
            return fail('Mode de paiement invalide.')
        pref = (p.get('reference') or '').strip()
        if m.requires_reference and not pref:
            return fail(f'La référence est obligatoire pour « {m.name} ».')
        payments.append({'method_id': m.id, 'amount': str(amount), 'reference': pref, 'date': today})
        paid += amount
    if paid > total:
        return fail(f'Les paiements ({paid} DH) dépassent le total ({total} DH).')

    # --- Handwritten reference (becomes the invoice reference on validation) ---
    hw_ref = (data.get('reference') or '').strip()
    existing_ref = (data.get('existing_reference') or '').strip()

    with transaction.atomic():
        invoice = None
        if existing_ref:
            invoice = SaleInvoice.objects.select_for_update().filter(
                reference=existing_ref, is_deleted=False, status=SaleInvoice.Status.DRAFT).first()
            if not invoice or (invoice.seller_id != request.user.id and not _can_validate(request.user)):
                return fail('Vente introuvable.', 404)
            if invoice.submitted_at:
                return fail('Cette vente est déjà en attente de validation.', 409)
        if hw_ref:
            clash = SaleInvoice.objects.filter(reference=hw_ref, is_deleted=False)
            if invoice:
                clash = clash.exclude(pk=invoice.pk)
            if clash.exists():
                return fail(f'La référence {hw_ref} existe déjà.')

        # Lock and check the pieces, then reserve them.
        products = {p.id: p for p in Product.objects.select_for_update().filter(id__in=seen)}
        for pid in seen:
            p = products.get(pid)
            if not p:
                return fail('Un article est introuvable (supprimé ?).')
            if p.status != 'available':
                return fail(f'{p.reference} n’est plus disponible ({p.get_status_display()}).', 409)

        # Photos: facture manuscrite always; bordereau for Amana/transporteur.
        has = {t: bool(request.FILES.getlist(f)) for f, t in PHOTO_FIELDS.items()}
        if invoice:
            for t in PHOTO_FIELDS.values():
                has[t] = has[t] or invoice.photos.filter(photo_type=t).exists()
        if not has[InvoicePhoto.PhotoType.INVOICE]:
            return fail('La photo de la facture manuscrite est obligatoire.')
        if dtype in ('amana', 'transporteur') and not has[InvoicePhoto.PhotoType.DELIVERY]:
            return fail('La photo du bordereau de livraison est obligatoire.')

        if not invoice:
            invoice = SaleInvoice.objects.create(
                date=timezone.localdate(), status=SaleInvoice.Status.DRAFT,
                seller=request.user, created_by=request.user,
                notes=f'Saisie mobile par {request.user.get_full_name() or request.user.username}',
            )

        Product.objects.filter(id__in=seen).update(status='reserved')
        for field, ptype in PHOTO_FIELDS.items():
            for f in request.FILES.getlist(field)[:8]:
                InvoicePhoto.objects.create(invoice=invoice, image=_compress(f), photo_type=ptype)

        invoice.submission = {
            'handwritten_ref': hw_ref,
            'reference': hw_ref,
            'items': items,
            'client': client,
            'delivery': delivery,
            'payments': payments,
            'validate': True,
            'reserved_ids': sorted(seen),
            'total': str(total),
            'paid': str(paid),
        }
        invoice.submitted_at = timezone.now()
        invoice.submitted_by = request.user
        invoice.review_note = ''
        invoice.save(update_fields=['submission', 'submitted_at', 'submitted_by', 'review_note'])

        ActivityLog.objects.create(
            user=request.user, action=ActivityLog.ActionType.CREATE,
            model_name='SaleInvoice', object_id=str(invoice.id),
            object_repr=f'Vente mobile soumise {invoice.reference} ({total} DH)',
        )

    try:
        from telegram_bot.notifications import notify_admin_sale_to_validate
        notify_admin_sale_to_validate(
            invoice, request.build_absolute_uri(reverse('sales:mobile_sale_review', args=[invoice.reference])))
    except Exception:
        logger.exception('mobile sale: telegram notify failed')

    return JsonResponse({'ok': True, 'reference': invoice.reference, 'total': str(total),
                         'paid': str(paid), 'url': reverse('sales:mobile_sale_mine')})


@login_required(login_url='login')
def mobile_sale_mine(request):
    """My phone sales: waiting for validation, sent back, validated."""
    base = SaleInvoice.objects.filter(seller=request.user, is_deleted=False, submission__isnull=False)
    return render(request, 'sales/mobile_sale_mine.html', {
        'pending': base.filter(status=SaleInvoice.Status.DRAFT, submitted_at__isnull=False).order_by('-submitted_at'),
        'returned': base.filter(status=SaleInvoice.Status.DRAFT, submitted_at__isnull=True).order_by('-updated_at'),
        'done': base.exclude(status=SaleInvoice.Status.DRAFT).order_by('-updated_at')[:30],
    })


# ---------------------------------------------------------------------------
# Admin / manager side
# ---------------------------------------------------------------------------

def _review_context(invoice):
    sub = invoice.submission or {}
    pids = [i['product_id'] for i in sub.get('items') or []]
    prods = {p.id: p for p in Product.all_objects.select_related('metal_type').filter(id__in=pids)}
    lines = []
    for it in sub.get('items') or []:
        p = prods.get(it['product_id'])
        price = Decimal(str(it.get('selling_price') or 0))
        lines.append({
            'p': p, 'price': price, 'image': _product_image(p) if p else '',
            'below_min': bool(p and p.minimum_price and price < p.minimum_price),
        })
    methods = {m.id: m for m in PaymentMethod.objects.all()}
    pays = [{'method': methods.get(p['method_id']), 'amount': Decimal(p['amount']),
             'reference': p.get('reference', '')} for p in sub.get('payments') or []]
    cid = (sub.get('client') or {}).get('id')
    carrier = None
    d = sub.get('delivery') or {}
    if d.get('carrier_id'):
        carrier = Carrier.objects.filter(pk=d['carrier_id']).first()
    total = Decimal(sub.get('total') or 0)
    paid = Decimal(sub.get('paid') or 0)
    return {
        'invoice': invoice, 'sub': sub, 'lines': lines, 'payments': pays,
        'client': Client.objects.filter(pk=cid).first() if cid else None,
        'delivery': d, 'carrier': carrier, 'total': total, 'paid': paid,
        'rest': total - paid,
        'photos': invoice.photos.all().order_by('photo_type', 'uploaded_at'),
        'any_below_min': any(l['below_min'] for l in lines),
    }


@login_required(login_url='login')
def mobile_sale_queue(request):
    if not _can_validate(request.user):
        messages.error(request, 'Accès réservé aux administrateurs et gérants.')
        return redirect('dashboard')
    qs = SaleInvoice.objects.filter(
        status=SaleInvoice.Status.DRAFT, is_deleted=False, submitted_at__isnull=False,
    ).select_related('seller', 'submitted_by').order_by('submitted_at')
    rows = []
    for inv in qs:
        sub = inv.submission or {}
        rows.append({'inv': inv, 'total': sub.get('total'), 'n_items': len(sub.get('items') or []),
                     'delivery': (sub.get('delivery') or {}).get('type', 'magasin'),
                     'n_photos': inv.photos.count()})
    return render(request, 'sales/mobile_sale_queue.html', {'rows': rows})


@login_required(login_url='login')
def mobile_sale_review(request, reference):
    if not _can_validate(request.user):
        messages.error(request, 'Accès réservé aux administrateurs et gérants.')
        return redirect('dashboard')
    invoice = get_object_or_404(SaleInvoice, reference=reference, is_deleted=False)

    if request.method == 'POST':
        action = request.POST.get('action')
        if invoice.status != SaleInvoice.Status.DRAFT or not invoice.submitted_at:
            messages.warning(request, 'Cette vente n’est plus en attente de validation.')
            return redirect('sales:mobile_sale_queue')

        if action == 'validate':
            from .views import _complete_draft
            payload = dict(invoice.submission or {})
            payload['validate'] = True
            with transaction.atomic():
                resp = _complete_draft(invoice, payload, request.user)
                ok = resp.status_code == 200
                if not ok:
                    transaction.set_rollback(True)
            body = json.loads(resp.content)
            if not ok:
                err = (body.get('errors') or [{}])[0].get('message', 'Erreur inconnue')
                messages.error(request, f'Validation impossible : {err}')
                return redirect('sales:mobile_sale_review', reference=invoice.reference)
            invoice.refresh_from_db()
            try:
                from telegram_bot.notifications import notify_admin_new_sale
                notify_admin_new_sale(invoice)
            except Exception:
                logger.exception('mobile sale: notify after validation failed')
            for w in body.get('warnings') or []:
                messages.warning(request, w.get('message', ''))
            messages.success(request, f'Vente {body.get("reference")} validée.')
            return redirect('sales:mobile_sale_queue')

        if action == 'reject':
            note = (request.POST.get('note') or '').strip()
            if not note:
                messages.error(request, 'Indiquez le motif du renvoi pour le vendeur.')
                return redirect('sales:mobile_sale_review', reference=invoice.reference)
            with transaction.atomic():
                _unreserve(invoice)
                invoice.submitted_at = None
                invoice.review_note = note
                invoice.save(update_fields=['submitted_at', 'review_note'])
                ActivityLog.objects.create(
                    user=request.user, action=ActivityLog.ActionType.REJECT,
                    model_name='SaleInvoice', object_id=str(invoice.id),
                    object_repr=f'Vente mobile renvoyée {invoice.reference}: {note[:120]}',
                )
            messages.success(request, f'Vente {invoice.reference} renvoyée au vendeur.')
            return redirect('sales:mobile_sale_queue')

    if not invoice.submission:
        messages.error(request, 'Cette facture n’a pas été saisie sur mobile.')
        return redirect('sales:pending_invoices')
    return render(request, 'sales/mobile_sale_review.html', _review_context(invoice))

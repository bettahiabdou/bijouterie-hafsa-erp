"""
Read-only diagnostic: explain how an invoice reached its current payment state.

Dumps totals, items (returned or not), real ClientPayment records, exchange
credits applied TO this invoice (reprise), return/exchange actions taken FROM
it, and the activity log — then reconciles amount_paid against the sum of real
payments + exchange credit so over/under-counting is obvious.

Usage:
    python manage.py invoice_origin 23464          # by reference
    python manage.py invoice_origin --pk 512       # by primary key
(prefix with DJANGO_SETTINGS_MODULE=config.settings_production on the server)
"""
from decimal import Decimal
from django.core.management.base import BaseCommand, CommandError
from sales.models import SaleInvoice
from payments.models import ClientPayment


def D(v):
    return Decimal(str(v or 0))


class Command(BaseCommand):
    help = "Explain how an invoice reached its current payment state (read-only)."

    def add_arguments(self, parser):
        parser.add_argument('reference', nargs='?', help="Invoice reference")
        parser.add_argument('--pk', help="Invoice primary key")

    def handle(self, *args, **options):
        if options.get('pk'):
            try:
                inv = SaleInvoice.objects.get(pk=int(options['pk']))
            except (SaleInvoice.DoesNotExist, ValueError):
                raise CommandError(f"Aucune facture pk={options['pk']}")
        elif options.get('reference'):
            inv = SaleInvoice.objects.filter(reference=options['reference']).first()
            if not inv:
                raise CommandError(f"Aucune facture référence « {options['reference']} »")
        else:
            raise CommandError("Fournir une référence ou --pk.")

        w = self.stdout.write
        w("=" * 68)
        w(f"FACTURE : {inv.reference}   (pk={inv.pk})")
        client = inv.client.full_name if inv.client else "— Vente anonyme —"
        w(f"Client  : {client}")
        w(f"Vendeur : {getattr(inv.seller, 'get_full_name', lambda: inv.seller)() if inv.seller else '—'}")
        w(f"Statut  : {inv.get_status_display()}   |   Date : {inv.date}   |   Créée : {inv.created_at}")
        w("=" * 68)

        # --- Totaux ---
        w("\nTOTAUX :")
        w(f"   Total facture : {inv.total_amount} DH")
        w(f"   Montant payé  : {inv.amount_paid} DH")
        w(f"   Solde         : {inv.balance_due} DH")

        # --- Items ---
        items = list(inv.items.select_related('product').all())
        w(f"\nARTICLES ({len(items)}) :")
        for it in items:
            ref = it.product.reference if it.product else "—"
            flag = "  [RETOURNÉ]" if getattr(it, 'is_returned', False) else ""
            w(f"   - {ref} | {it.total_amount} DH{flag}")

        # --- Real payments ---
        payments = list(inv.payments.select_related('payment_method').all())
        pay_sum = sum((D(p.amount) for p in payments), Decimal('0'))
        w(f"\nPAIEMENTS RÉELS (ClientPayment) — {len(payments)}, total {pay_sum} DH :")
        if not payments:
            w("   (aucun) — donc rien n'a été encaissé en espèces/carte/etc.")
        for p in payments:
            method = p.payment_method.name if p.payment_method else "—"
            w(f"   - {method} : {p.amount} DH | {getattr(p, 'date', '—')} | ref {getattr(p, 'reference', '') or '—'}")

        # --- Exchange credit applied TO this invoice (reprise) ---
        credits = list(inv.exchange_from.filter(action_type='exchange')
                       .select_related('original_invoice', 'original_product'))
        credit_sum = sum((D(a.refund_amount) for a in credits), Decimal('0'))
        w(f"\nCRÉDIT ÉCHANGE APPLIQUÉ (reprise) — {len(credits)}, total {credit_sum} DH :")
        if not credits:
            w("   (aucun)")
        for a in credits:
            src = a.original_invoice.reference if a.original_invoice else "—"
            w(f"   - reprise facture {src} | {a.original_product_ref or '—'} | {a.refund_amount} DH | {a.created_at}")

        # --- Actions taken FROM this invoice (its items returned/exchanged elsewhere) ---
        actions = list(inv.actions.select_related('new_invoice', 'original_product').all())
        if actions:
            w(f"\nACTIONS SUR CETTE FACTURE (retours/échanges de ses articles) — {len(actions)} :")
            for a in actions:
                dest = a.new_invoice.reference if a.new_invoice else "—"
                w(f"   - {a.get_action_type_display()} | {a.original_product_ref or '—'} | {a.refund_amount} DH | vers {dest}")

        # --- Activity log ---
        try:
            from users.models import ActivityLog
            logs = ActivityLog.objects.filter(
                model_name='SaleInvoice', object_id=str(inv.id)
            ).order_by('created_at')
            if logs.exists():
                w(f"\nJOURNAL ({logs.count()}) :")
                for lg in logs[:30]:
                    detail = ''
                    if isinstance(getattr(lg, 'details', None), dict):
                        detail = ' | ' + str(lg.details.get('payments', lg.details.get('action', '')))
                    w(f"   - {lg.created_at} | {lg.get_action_display()} | {lg.user or 'inconnu'}{detail}")
        except Exception:
            pass

        # --- Reconciliation ---
        w("\n" + "-" * 68)
        expected = pay_sum + credit_sum
        w("RÉCONCILIATION :")
        w(f"   paiements réels ({pay_sum}) + crédit échange ({credit_sum}) = {expected} DH")
        w(f"   montant payé enregistré                                   = {inv.amount_paid} DH")
        w(f"   total facture                                             = {inv.total_amount} DH")
        if inv.amount_paid > inv.total_amount:
            surplus = inv.amount_paid - inv.total_amount
            w(self.style.WARNING(f"   ⚠ Montant payé DÉPASSE le total de {surplus} DH (trop-perçu / à rendre au client)."))
        if expected != inv.amount_paid:
            w(self.style.WARNING(f"   ⚠ Écart de {expected - inv.amount_paid} DH entre paiements+échange et montant payé enregistré."))
        if inv.amount_paid <= inv.total_amount and expected == inv.amount_paid:
            w(self.style.SUCCESS("   ✓ Cohérent."))
        w("")

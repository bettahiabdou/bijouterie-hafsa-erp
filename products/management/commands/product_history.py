"""
Full audit trail for one or more products: creation, views, edits, and every
label/barcode print — merged into a single chronological timeline.

Sources:
  - Product fields (created_at / created_by / updated_at / status / tags)
  - ActivityLog (create, view, print, update, delete, export ...)
  - PrintQueue  (label/barcode prints sent to the Zebra, incl. status)

Usage (run with DJANGO_SETTINGS_MODULE=config.settings_production):
    python manage.py product_history PRD-FIN-20260718-0024 PRD-FIN-20260718-0025 ...
"""
from django.core.management.base import BaseCommand, CommandError
from products.models import Product, PrintQueue
from users.models import ActivityLog


def _fmt_user(u):
    if not u:
        return 'inconnu'
    full = u.get_full_name() if hasattr(u, 'get_full_name') else ''
    return full or getattr(u, 'username', str(u))


class Command(BaseCommand):
    help = "Show the full history (created / viewed / printed / edited) of products."

    def add_arguments(self, parser):
        parser.add_argument('references', nargs='+', help="Product reference(s)")

    def handle(self, *args, **options):
        refs = options['references']
        for ref in refs:
            product = Product.objects.filter(reference=ref).select_related('created_by').first()
            if not product:
                self.stdout.write(self.style.ERROR(f"\n{ref} : introuvable"))
                continue
            self._report(product)

    def _report(self, p):
        w = self.stdout.write
        w("\n" + "=" * 70)
        w(f"{p.reference} — {p.name}")
        w("=" * 70)
        w(f"Statut       : {p.get_status_display()}")
        w(f"Créé le      : {p.created_at}  par {_fmt_user(p.created_by)}")
        w(f"Modifié le   : {p.updated_at}")
        w(f"Code-barres  : {p.barcode or '—'}")
        w(f"RFID tag     : {p.rfid_tag or '—'}")

        events = []  # (datetime, label)

        # ActivityLog entries for this product
        logs = ActivityLog.objects.filter(
            model_name='Product', object_id=str(p.id)
        ).select_related('user')
        for lg in logs:
            detail = ''
            if isinstance(getattr(lg, 'details', None), dict) and lg.details:
                detail = ' | ' + '; '.join(f'{k}={v}' for k, v in lg.details.items())
            ip = f' [{lg.ip_address}]' if lg.ip_address else ''
            events.append((lg.created_at,
                           f"{lg.get_action_display():<12} par {_fmt_user(lg.user)}{ip}{detail}"))

        # PrintQueue jobs (label / barcode prints)
        for job in PrintQueue.objects.filter(product=p).select_related('created_by'):
            status = job.get_status_display() if hasattr(job, 'get_status_display') else job.status
            label = f"Impression file ({job.get_label_type_display()}) — {status}"
            if getattr(job, 'printed_at', None):
                label += f" (imprimé {job.printed_at})"
            label += f" par {_fmt_user(job.created_by)}"
            events.append((job.created_at, label))

        events.sort(key=lambda e: e[0])

        w(f"\nHISTORIQUE ({len(events)} évènement(s)) :")
        if not events:
            w("   (aucun évènement enregistré)")
        for dt, label in events:
            w(f"   {dt:%Y-%m-%d %H:%M:%S}  {label}")

        # Quick counts
        views = sum(1 for lg in logs if lg.action == ActivityLog.ActionType.VIEW)
        prints_log = sum(1 for lg in logs if lg.action == ActivityLog.ActionType.PRINT)
        prints_queue = PrintQueue.objects.filter(product=p).count()
        w(f"\nRésumé : {views} consultation(s), "
          f"{prints_log + prints_queue} impression(s) "
          f"(journal {prints_log} + file {prints_queue}).")

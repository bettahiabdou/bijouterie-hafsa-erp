"""
Sanity-check / fix invoice dates that were wrongly stamped with the
completion date.

Background: completing an "En Attente" (Telegram) draft used to set
invoice.date = today, so a pending sale that was validated days later lost
its real date. The correct date is the draft's creation date
(created_at.date()). This command finds Telegram-origin, completed,
non-deleted invoices whose date was pushed *forward* past their creation
date and restores it.

Dry-run by default (reports only). Pass --apply to write the fix.

    python manage.py fix_pending_invoice_dates            # report
    python manage.py fix_pending_invoice_dates --apply     # fix
"""
from django.core.management.base import BaseCommand
from sales.models import SaleInvoice


class Command(BaseCommand):
    help = "Restore the original date on pending invoices whose date was overwritten with the completion date."

    def add_arguments(self, parser):
        parser.add_argument('--apply', action='store_true',
                            help='Apply the fix (default: report only).')
        parser.add_argument('--limit', type=int, default=100,
                            help='Max rows to list in the report (default 100).')

    def handle(self, *args, **opts):
        apply = opts['apply']
        limit = opts['limit']

        qs = (SaleInvoice.objects
              .filter(is_deleted=False, notes__icontains='Créé via Telegram')
              .exclude(status='draft')
              .order_by('created_at'))

        affected = []
        skipped_backdated = 0
        for inv in qs.iterator():
            if not inv.created_at or not inv.date:
                continue
            correct = inv.created_at.date()
            if inv.date == correct:
                continue
            if inv.date < correct:
                # date is *before* creation -> a deliberate manual backdate,
                # not the completion-stamp bug. Leave it untouched.
                skipped_backdated += 1
                continue
            affected.append((inv, correct))

        total = len(affected)
        self.stdout.write(self.style.MIGRATE_HEADING(
            f"\n=== Sanity check: invoice date vs creation date ==="))
        self.stdout.write(
            f"Telegram invoices completed with a date after their creation date: {total}")
        if skipped_backdated:
            self.stdout.write(
                f"(Ignored {skipped_backdated} invoice(s) dated before creation - "
                f"likely deliberate backdating, left untouched.)")

        if not total:
            self.stdout.write(self.style.SUCCESS("Nothing to fix. All dates look correct."))
            return

        self.stdout.write("")
        header = f"{'Référence':<22} {'Actuelle':<12} {'Correcte':<12} {'Écart':>6}  Statut"
        self.stdout.write(header)
        self.stdout.write("-" * len(header))
        for inv, correct in affected[:limit]:
            gap = (inv.date - correct).days
            self.stdout.write(
                f"{inv.reference:<22} {inv.date.isoformat():<12} "
                f"{correct.isoformat():<12} {gap:>4}j  {inv.status}")
        if total > limit:
            self.stdout.write(f"... and {total - limit} more.")

        if not apply:
            self.stdout.write(self.style.WARNING(
                f"\nDRY-RUN: no changes written. Re-run with --apply to fix these {total} invoice(s)."))
            return

        fixed = 0
        for inv, correct in affected:
            SaleInvoice.objects.filter(pk=inv.pk).update(date=correct)
            fixed += 1
        self.stdout.write(self.style.SUCCESS(
            f"\nAPPLIED: restored the original date on {fixed} invoice(s)."))

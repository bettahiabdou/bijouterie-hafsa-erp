"""
Label printer helper: show the configured geometry, recalibrate the printer
after a media change, and print a measuring ruler label.

After changing label stock you MUST recalibrate: otherwise the printer keeps
using the previous label length/gap and prints across the gap onto the liner
(the "VOID" area).

Usage:
    python manage.py printer_labels --show        # print current geometry (no printing)
    python manage.py printer_labels --calibrate   # re-learn media length/gap
    python manage.py printer_labels --ruler       # print a box at the configured size
    python manage.py printer_labels --test        # print a sample product label
"""
from django.core.management.base import BaseCommand, CommandError


class Command(BaseCommand):
    help = "Show label geometry, recalibrate the printer, or print a ruler/test label."

    SETTERS = {
        'width': 'zebra_label_width',
        'height': 'zebra_label_height',
        'x': 'zebra_label_x_mm',
        'weight_y': 'zebra_label_weight_y_mm',
        'size_y': 'zebra_label_size_y_mm',
        'ref_y': 'zebra_label_ref_y_mm',
        'barcode_y': 'zebra_label_barcode_y_mm',
        'font_size': 'zebra_label_font_size',
        'barcode_height': 'zebra_label_barcode_height',
    }

    def add_arguments(self, parser):
        parser.add_argument('--show', action='store_true', help="Show configured geometry")
        parser.add_argument('--calibrate', action='store_true', help="Recalibrate media (after stock change)")
        parser.add_argument('--ruler', action='store_true', help="Print a box at the configured label size")
        parser.add_argument('--test', action='store_true', help="Print a sample label")
        parser.add_argument('--queue', action='store_true',
                            help="Queue the job for the shop's print agent instead of "
                                 "sending over TCP (use when the printer is on another network)")
        parser.add_argument('--media', choices=['gap', 'mark', 'continuous'], default='gap',
                            help="Media sensing for --calibrate (default: gap / die-cut)")
        parser.add_argument('--queue-status', action='store_true',
                            help="Show how many print jobs are waiting in the queue")
        parser.add_argument('--flush-queue', action='store_true',
                            help="Cancel ALL waiting/stuck print jobs (clears a backlog)")
        parser.add_argument('--rfid', choices=['on', 'off'],
                            help="Enable/disable RFID encoding. Turn OFF for plain "
                                 "(non-RFID) labels, otherwise the printer voids each tag.")
        parser.add_argument('--rfid-calibrate', action='store_true',
                            help="Run RFID tag calibration (finds the chip position for "
                                 "the loaded label — do this after changing RFID stock)")
        parser.add_argument('--rfid-retries', type=int,
                            help="Max encode attempts before giving up (lower = fewer "
                                 "voided labels on failure)")
        # Geometry setters (positions in mm)
        for opt in ('width', 'height', 'x', 'weight-y', 'size-y', 'ref-y', 'barcode-y'):
            parser.add_argument(f'--{opt}', type=int, help=f"Set {opt} (mm)")
        # Sizing setters (in dots)
        parser.add_argument('--font-size', type=int, help="Text height in dots (smaller = smaller font)")
        parser.add_argument('--barcode-height', type=int, help="Barcode height in dots")

    def handle(self, *args, **options):
        from products.print_utils import (
            get_label_geometry, calibrate_printer, print_geometry_ruler,
            print_test_label, get_printer_settings,
        )

        # --- RFID settings ---
        if options.get('rfid') or options.get('rfid_retries') is not None:
            from settings_app.models import SystemConfig
            c = SystemConfig.get_config()
            fields = []
            if options.get('rfid'):
                c.zebra_rfid_enabled = (options['rfid'] == 'on')
                fields.append('zebra_rfid_enabled')
            if options.get('rfid_retries') is not None:
                c.zebra_rfid_retries = max(0, options['rfid_retries'])
                fields.append('zebra_rfid_retries')
            c.save(update_fields=fields)
            if 'zebra_rfid_enabled' in fields:
                state = "ACTIVÉ" if c.zebra_rfid_enabled else "DÉSACTIVÉ"
                self.stdout.write(self.style.SUCCESS(f"Encodage RFID {state}."))
            if 'zebra_rfid_retries' in fields:
                self.stdout.write(self.style.SUCCESS(f"Tentatives RFID : {c.zebra_rfid_retries}."))
            options['show'] = True

        # --- Apply any geometry values passed on the command line ---
        updates = {field: options[key] for key, field in self.SETTERS.items()
                   if options.get(key) is not None}
        if updates:
            from settings_app.models import SystemConfig
            c = SystemConfig.get_config()
            for field, value in updates.items():
                setattr(c, field, value)
            c.save(update_fields=list(updates.keys()))
            def _unit(field):
                return ' dots' if field in ('zebra_label_font_size', 'zebra_label_barcode_height') else 'mm'
            self.stdout.write(self.style.SUCCESS(
                "Géométrie enregistrée : " + ", ".join(f"{f}={v}{_unit(f)}" for f, v in updates.items())
            ))
            options['show'] = True  # always confirm what is now stored

        # --- Queue maintenance (do these first; they don't need a printer) ---
        from products.models import PrintQueue
        WAITING = [PrintQueue.Status.PENDING, PrintQueue.Status.PRINTING]

        if options['queue_status']:
            from django.db.models import Count
            counts = dict(PrintQueue.objects.values_list('status').annotate(n=Count('id')))
            self.stdout.write("File d'impression :")
            for st, label in PrintQueue.Status.choices:
                self.stdout.write(f"   {label:<12} : {counts.get(st, 0)}")
            waiting = PrintQueue.objects.filter(status__in=WAITING).count()
            if waiting:
                self.stdout.write(self.style.WARNING(
                    f"\n⚠ {waiting} travail(aux) en attente — ils s'imprimeront tous dès que "
                    "l'agent interroge la file. Utilisez --flush-queue pour les annuler."))
            return

        if options['flush_queue']:
            n = PrintQueue.objects.filter(status__in=WAITING).update(
                status=PrintQueue.Status.CANCELLED,
                error_message='Annulé via --flush-queue',
            )
            self.stdout.write(self.style.SUCCESS(f"{n} travail(aux) en attente annulé(s). File vidée."))
            return

        if not any([options['show'], options['calibrate'], options['ruler'],
                    options['test'], options['rfid_calibrate']]):
            raise CommandError(
                "Choisir une action : --show, --calibrate, --rfid-calibrate, --ruler, "
                "--test, --queue-status, --flush-queue, ou passer des mesures."
            )

        g = get_label_geometry()
        mm = g['mm']
        host, port = get_printer_settings()

        if options['show']:
            from products.print_utils import rfid_enabled
            self.stdout.write("Imprimante : " + (f"{host}:{port}" if host else "non configurée"))
            self.stdout.write("Encodage RFID : " + ("ACTIVÉ" if rfid_enabled() else "désactivé"))
            self.stdout.write("Géométrie actuelle (Paramètres > Configuration Système) :")
            self.stdout.write(f"   Étiquette     : {mm['width_mm']} x {mm['height_mm']} mm "
                              f"({g['pw']} x {g['ll']} dots @8/mm)")
            self.stdout.write(f"   X texte       : {mm['x_mm']} mm ({g['x']} dots)")
            self.stdout.write(f"   Y poids       : {mm['weight_y_mm']} mm ({g['weight_y']} dots)")
            self.stdout.write(f"   Y taille      : {mm['size_y_mm']} mm ({g['size_y']} dots)")
            self.stdout.write(f"   Y référence   : {mm['ref_y_mm']} mm ({g['ref_y']} dots)")
            self.stdout.write(f"   Y code-barres : {mm['barcode_y_mm']} mm ({g['barcode_y']} dots)")
            self.stdout.write(f"   Police texte  : {g['font']} dots")
            self.stdout.write(f"   Hauteur c-b   : {g['barcode_h']} dots")

            # Warn about content that falls outside the physical label — this is what
            # makes the printer spill onto the liner / VOID area.
            problems = []
            BARCODE_MM = max(3, round(g['barcode_h'] / 8))  # dots -> mm
            for label, y, extra in (
                ('poids', mm['weight_y_mm'], 3),
                ('taille', mm['size_y_mm'], 3),
                ('référence', mm['ref_y_mm'], 4),
                ('code-barres', mm['barcode_y_mm'], BARCODE_MM),
            ):
                if y + extra > mm['height_mm']:
                    problems.append(f"{label} finit à ~{y + extra}mm > hauteur {mm['height_mm']}mm")
            if mm['x_mm'] >= mm['width_mm']:
                problems.append(f"X {mm['x_mm']}mm >= largeur {mm['width_mm']}mm")
            if problems:
                self.stdout.write(self.style.ERROR(
                    "\n⚠ Contenu hors étiquette — l'impression débordera sur le VOID :"))
                for p in problems:
                    self.stdout.write(self.style.ERROR(f"     - {p}"))
                self.stdout.write("   Corrigez avec --barcode-y / --ref-y / --height, puis --calibrate.")
            else:
                self.stdout.write(self.style.SUCCESS("\n✓ Tout le contenu tient dans l'étiquette."))
            return

        use_queue = options['queue']

        if not host and not use_queue:
            raise CommandError(
                "Aucune imprimante configurée (Paramètres > Configuration Système).\n"
                "Si l'imprimante est sur un autre réseau, utilisez --queue."
            )

        from products.print_utils import (
            calibration_zpl, geometry_ruler_zpl, test_label_zpl, queue_zpl,
            rfid_calibrate_command, send_to_printer,
        )

        def run(action_label, zpl_builder, sender, extra=None):
            if use_queue:
                job = queue_zpl(zpl_builder())
                self.stdout.write(self.style.SUCCESS(
                    f"{action_label} : mis en file d'attente (job #{job.id})."))
            else:
                ok, msg = sender()
                style = self.style.SUCCESS if ok else self.style.ERROR
                self.stdout.write(style(f"{action_label} : {msg}"))
                if not ok:
                    self.stdout.write(self.style.WARNING(
                        "  L'imprimante n'est pas joignable depuis le serveur. "
                        "Relancez avec --queue pour passer par l'agent de la boutique."))
                    return
            if extra:
                self.stdout.write(extra)

        if options['calibrate']:
            media = options['media']
            run("Calibration", lambda: calibration_zpl(media), lambda: calibrate_printer(media),
                f"Mode média : {media}. L'imprimante avance le papier pour mesurer "
                "l'étiquette et l'espacement (arrêt à chaque découpe).")

        if options['rfid_calibrate']:
            run("Calibration RFID", rfid_calibrate_command,
                lambda: send_to_printer(rfid_calibrate_command()),
                "L'imprimante teste plusieurs positions pour localiser la puce du tag "
                "chargé, puis enregistre la position optimale.")

        if options['ruler']:
            run("Règle", geometry_ruler_zpl, print_geometry_ruler,
                f"Mesurez le cadre : il doit faire {mm['width_mm']} x {mm['height_mm']} mm.")

        if options['test']:
            run("Étiquette test", test_label_zpl, print_test_label)

        if use_queue:
            self.stdout.write(
                "\nLes travaux seront envoyés à l'imprimante dès que l'agent "
                "d'impression de la boutique interrogera la file "
                "(page File d'impression / /products/print-queue/)."
            )

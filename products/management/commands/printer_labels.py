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

    def add_arguments(self, parser):
        parser.add_argument('--show', action='store_true', help="Show configured geometry")
        parser.add_argument('--calibrate', action='store_true', help="Recalibrate media (after stock change)")
        parser.add_argument('--ruler', action='store_true', help="Print a box at the configured label size")
        parser.add_argument('--test', action='store_true', help="Print a sample label")

    def handle(self, *args, **options):
        from products.print_utils import (
            get_label_geometry, calibrate_printer, print_geometry_ruler,
            print_test_label, get_printer_settings,
        )

        if not any([options['show'], options['calibrate'], options['ruler'], options['test']]):
            raise CommandError("Choisir une action : --show, --calibrate, --ruler ou --test.")

        g = get_label_geometry()
        mm = g['mm']
        host, port = get_printer_settings()

        if options['show']:
            self.stdout.write("Imprimante : " + (f"{host}:{port}" if host else "non configurée"))
            self.stdout.write("Géométrie actuelle (Paramètres > Configuration Système) :")
            self.stdout.write(f"   Étiquette     : {mm['width_mm']} x {mm['height_mm']} mm "
                              f"({g['pw']} x {g['ll']} dots @8/mm)")
            self.stdout.write(f"   X texte       : {mm['x_mm']} mm ({g['x']} dots)")
            self.stdout.write(f"   Y poids       : {mm['weight_y_mm']} mm ({g['weight_y']} dots)")
            self.stdout.write(f"   Y taille      : {mm['size_y_mm']} mm ({g['size_y']} dots)")
            self.stdout.write(f"   Y référence   : {mm['ref_y_mm']} mm ({g['ref_y']} dots)")
            self.stdout.write(f"   Y code-barres : {mm['barcode_y_mm']} mm ({g['barcode_y']} dots)")
            return

        if not host:
            raise CommandError("Aucune imprimante configurée (Paramètres > Configuration Système).")

        if options['calibrate']:
            ok, msg = calibrate_printer()
            style = self.style.SUCCESS if ok else self.style.ERROR
            self.stdout.write(style(f"Calibration : {msg}"))
            self.stdout.write("L'imprimante avance le papier pour mesurer l'étiquette et l'espacement.")

        if options['ruler']:
            ok, msg = print_geometry_ruler()
            style = self.style.SUCCESS if ok else self.style.ERROR
            self.stdout.write(style(f"Règle imprimée : {msg}"))
            self.stdout.write(f"Mesurez le cadre : il doit faire {mm['width_mm']} x {mm['height_mm']} mm.")

        if options['test']:
            ok, msg = print_test_label()
            style = self.style.SUCCESS if ok else self.style.ERROR
            self.stdout.write(style(f"Étiquette test : {msg}"))

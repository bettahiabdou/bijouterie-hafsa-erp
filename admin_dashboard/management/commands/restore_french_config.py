"""
Management command to restore and complete French localization of configuration data
"""

from django.core.management.base import BaseCommand
from settings_app.models import (
    StoneClarity, StoneColor, StoneCut, DeliveryMethod, RepairType
)


class Command(BaseCommand):
    help = 'Restore and complete French configuration data'

    def handle(self, *args, **options):
        self.stdout.write(self.style.SUCCESS('Restoring French configuration data...'))

        # Restore Stone Cuts - clear and recreate
        self.stdout.write('Restoring Stone Cuts...')
        StoneCut.objects.all().delete()
        cuts = [
            ('Excellent', 1),
            ('Très Bon', 2),
            ('Bon', 3),
            ('Acceptable', 4),
            ('Faible', 5),
        ]
        for name, rank in cuts:
            StoneCut.objects.create(name=name, rank=rank, is_active=True)

        # Restore Delivery Methods - clear and recreate
        self.stdout.write('Restoring Delivery Methods...')
        DeliveryMethod.objects.all().delete()
        methods = [
            'Retrait en magasin',
            'Livraison à domicile',
            'Livraison express',
            'Coursier',
            'Courrier',
        ]
        for i, name in enumerate(methods, 1):
            DeliveryMethod.objects.create(
                name=name,
                is_internal=i == 1,
                default_cost=0 if i == 1 else 50,
                is_active=True
            )

        # Restore Repair Types - recreate missing ones
        self.stdout.write('Restoring Repair Types...')
        # First clear all to avoid code conflicts
        RepairType.objects.all().delete()
        repairs_to_create = [
            ('Nettoyage', 100, 2),
            ('Polissage', 150, 3),
            ('Sertissage de pierres', 300, 7),
            ('Redimensionnement', 200, 5),
            ('Réparation du métal', 250, 5),
            ('Restauration de bijoux', 400, 10),
            ('Gravure', 100, 2),
        ]
        for name, price, duration in repairs_to_create:
            RepairType.objects.create(
                name=name,
                default_price=price,
                estimated_duration_days=duration,
                is_active=True
            )

        self.stdout.write(self.style.SUCCESS('French configuration data restored successfully!'))

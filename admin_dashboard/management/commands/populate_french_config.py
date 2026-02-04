"""
Management command to populate all configuration data in French
"""

from django.core.management.base import BaseCommand
from settings_app.models import (
    MetalType, MetalPurity, ProductCategory, StoneType,
    StoneClarity, StoneColor, StoneCut, PaymentMethod,
    BankAccount, StockLocation, DeliveryMethod,
    RepairType, CertificateIssuer
)


class Command(BaseCommand):
    help = 'Populate all configuration data in French'

    def handle(self, *args, **options):
        self.stdout.write(self.style.SUCCESS('Populating French configuration data...'))

        # Metal Types & Purities
        self.stdout.write('Creating Metal Types...')
        metals = {
            'Or': [
                ('Or pur (24K)', 99.9),
                ('Or 22 carats', 91.6),
                ('Or 21 carats', 87.5),
                ('Or 18 carats', 75.0),
                ('Or 14 carats', 58.5),
            ],
            'Argent': [
                ('Argent 925', 92.5),
                ('Argent 950', 95.0),
            ],
            'Platine': [
                ('Platine pur', 95.0),
            ],
        }

        for metal_name, purities in metals.items():
            metal = MetalType.objects.create(name=metal_name, is_active=True)
            for purity_name, percentage in purities:
                MetalPurity.objects.create(
                    metal_type=metal,
                    name=purity_name,
                    purity_percentage=percentage,
                    is_active=True
                )

        # Product Categories
        self.stdout.write('Creating Product Categories...')
        categories = [
            'Bagues',
            'Colliers',
            'Bracelets',
            'Boucles d\'oreilles',
            'Chaînes de cheville',
            'Pendentifs',
            'Broches',
            'Montres',
        ]
        for category in categories:
            ProductCategory.objects.create(name=category, is_active=True)

        # Stone Types
        self.stdout.write('Creating Stone Types...')
        stone_types = [
            ('Diamant', True, True),
            ('Rubis', True, False),
            ('Émeraude', True, False),
            ('Saphir', True, False),
            ('Perle', False, False),
            ('Topaze', False, False),
            ('Améthyste', False, False),
            ('Cristal', False, False),
        ]
        for name, is_precious, requires_cert in stone_types:
            StoneType.objects.create(
                name=name,
                is_precious=is_precious,
                requires_certificate=requires_cert,
                is_active=True
            )

        # Stone Clarities
        self.stdout.write('Creating Stone Clarities...')
        clarities = [
            ('Internalement Pur (IF)', 1),
            ('Très Très Légèrement Inclus 1 (VVS1)', 2),
            ('Très Très Légèrement Inclus 2 (VVS2)', 3),
            ('Très Légèrement Inclus 1 (VS1)', 4),
            ('Très Légèrement Inclus 2 (VS2)', 5),
            ('Légèrement Inclus 1 (SI1)', 6),
            ('Légèrement Inclus 2 (SI2)', 7),
            ('Inclus 1 (I1)', 8),
        ]
        for name, rank in clarities:
            StoneClarity.objects.create(name=name, rank=rank, is_active=True)

        # Stone Colors
        self.stdout.write('Creating Stone Colors...')
        colors = [
            ('Incolore (D-F)', 1),
            ('Très Blanc (G-J)', 2),
            ('Teinté (K-M)', 3),
        ]
        for name, rank in colors:
            StoneColor.objects.create(name=name, rank=rank, is_active=True)

        # Stone Cuts
        self.stdout.write('Creating Stone Cuts...')
        cuts = [
            ('Excellent', 1),
            ('Très Bon', 2),
            ('Bon', 3),
            ('Acceptable', 4),
            ('Faible', 5),
        ]
        for name, rank in cuts:
            StoneCut.objects.create(name=name, rank=rank, is_active=True)

        # Payment Methods
        self.stdout.write('Creating Payment Methods...')
        payments = [
            'Espèces',
            'Carte de crédit',
            'Carte de débit',
            'Virement bancaire',
            'Chèque',
            'Paiement mobile',
        ]
        for i, payment in enumerate(payments, 1):
            PaymentMethod.objects.create(
                name=payment,
                display_order=i,
                is_active=True
            )

        # Bank Accounts
        self.stdout.write('Creating Bank Accounts...')
        banks = [
            'Banque Marocaine du Commerce Extérieur',
            'Crédit Agricole du Maroc',
            'Banque Centrale Populaire',
            'Attijariwafa bank',
            'Banque Marocaine pour le Commerce et l\'Industrie',
            'Banque Assafa',
            'Bank Al-Amal',
            'Société Générale Marocaine de Banques',
            'Bank of Africa',
            'Maroc Poste',
            'Western Union',
            'MoneyGram',
        ]
        for i, bank_name in enumerate(banks, 1):
            BankAccount.objects.create(
                bank_name=bank_name,
                account_name=f'Compte {bank_name}',
                is_active=True,
                is_default=(i == 1)
            )

        # Stock Locations
        self.stdout.write('Creating Stock Locations...')
        locations = [
            ('Coffre principal', True),
            ('Vitrine d\'exposition', False),
            ('Salle de stockage', False),
            ('Bureau arrière', False),
            ('Casier sécurisé 1', True),
            ('Casier sécurisé 2', True),
        ]
        for name, is_secure in locations:
            StockLocation.objects.create(
                name=name,
                is_secure=is_secure,
                is_active=True
            )

        # Delivery Methods
        self.stdout.write('Creating Delivery Methods...')
        deliveries = [
            ('Retrait en magasin', True, 0),
            ('Livraison à domicile', False, 50),
            ('Livraison express', False, 100),
            ('Coursier', False, 150),
            ('Courrier', False, 75),
        ]
        for name, is_internal, cost in deliveries:
            DeliveryMethod.objects.create(
                name=name,
                is_internal=is_internal,
                default_cost=cost,
                is_active=True
            )

        # Repair Types
        self.stdout.write('Creating Repair Types...')
        repairs = [
            ('Nettoyage', 100, 2),
            ('Polissage', 150, 3),
            ('Sertissage de pierres', 300, 7),
            ('Redimensionnement', 200, 5),
            ('Réparation du métal', 250, 5),
            ('Restauration de bijoux', 400, 10),
            ('Gravure', 100, 2),
        ]
        for name, price, duration in repairs:
            RepairType.objects.create(
                name=name,
                default_price=price,
                estimated_duration_days=duration,
                is_active=True
            )

        # Certificate Issuers
        self.stdout.write('Creating Certificate Issuers...')
        issuers = [
            'GIA (Institut Gemmologique d\'Amérique)',
            'IGI (Institut International de Gemmologie)',
            'HRD (Association des Diamantaires de Belgique)',
            'AGS (Société d\'Évaluation des Diamants Américaine)',
            'EGL (Laboratoire Européen de Gemmologie)',
        ]
        for name in issuers:
            CertificateIssuer.objects.create(name=name, is_active=True)

        self.stdout.write(self.style.SUCCESS('French configuration data populated successfully!'))
        total = (len(metals) + sum(len(p) for p in metals.values()) + len(categories) +
                len(stone_types) + len(clarities) + len(colors) + len(cuts) +
                len(payments) + len(banks) + len(locations) + len(deliveries) +
                len(repairs) + len(issuers))
        self.stdout.write(self.style.SUCCESS(f'Total items created: {total}'))

"""
Management command to localize all configuration data to French only
Replaces English text with French equivalents
"""

from django.core.management.base import BaseCommand
from settings_app.models import (
    MetalType, MetalPurity, ProductCategory, StoneType,
    StoneClarity, StoneColor, StoneCut, PaymentMethod,
    BankAccount, StockLocation, DeliveryMethod,
    RepairType, CertificateIssuer
)


class Command(BaseCommand):
    help = 'Localize all configuration data to French'

    def handle(self, *args, **options):
        self.stdout.write(self.style.SUCCESS('Starting French localization...'))

        # Metal Types
        self.stdout.write('Localizing Metal Types...')
        metal_translations = {
            'Gold': 'Or',
            'Silver': 'Argent',
            'Platinum': 'Platine',
            'Palladium': 'Palladium',
        }
        for english, french in metal_translations.items():
            # First delete any existing duplicates with French name
            MetalType.objects.filter(name=french).delete()
            # Then update English to French
            MetalType.objects.filter(name=english).update(name=french)

        # Product Categories
        self.stdout.write('Localizing Product Categories...')
        category_translations = {
            'Rings': 'Bagues',
            'Necklaces': 'Colliers',
            'Bracelets': 'Bracelets',
            'Earrings': 'Boucles d\'oreilles',
            'Anklets': 'Chaînes de cheville',
            'Pendants': 'Pendentifs',
            'Brooches': 'Broches',
            'Watches': 'Montres',
        }
        for english, french in category_translations.items():
            ProductCategory.objects.filter(name=french).delete()
            ProductCategory.objects.filter(name=english).update(name=french)

        # Stone Types
        self.stdout.write('Localizing Stone Types...')
        stone_translations = {
            'Diamond': 'Diamant',
            'Ruby': 'Rubis',
            'Emerald': 'Émeraude',
            'Sapphire': 'Saphir',
            'Pearl': 'Perle',
            'Topaz': 'Topaze',
            'Amethyst': 'Améthyste',
            'Crystal': 'Cristal',
        }
        for english, french in stone_translations.items():
            StoneType.objects.filter(name=french).delete()
            StoneType.objects.filter(name=english).update(name=french)

        # Stone Clarities
        self.stdout.write('Localizing Stone Clarities...')
        clarity_translations = {
            'IF': 'IF (Internalement Pur)',
            'VVS1': 'VVS1 (Très Très Légèrement Inclus)',
            'VVS2': 'VVS2 (Très Très Légèrement Inclus)',
            'VS1': 'VS1 (Très Légèrement Inclus)',
            'VS2': 'VS2 (Très Légèrement Inclus)',
            'SI1': 'SI1 (Légèrement Inclus)',
            'SI2': 'SI2 (Légèrement Inclus)',
            'I1': 'I1 (Inclus)',
        }
        for english, french in clarity_translations.items():
            StoneClarity.objects.filter(name=french).delete()
            StoneClarity.objects.filter(name=english).update(name=french)

        # Stone Colors
        self.stdout.write('Localizing Stone Colors...')
        color_translations = {
            'D': 'D (Incolore)',
            'E': 'E (Incolore)',
            'F': 'F (Incolore)',
            'G': 'G (Très Blanc)',
            'H': 'H (Très Blanc)',
            'I': 'I (Blanc)',
            'J': 'J (Blanc)',
            'K': 'K (Légèrement Teinté)',
            'L': 'L (Teinté)',
            'M': 'M (Teinté)',
            'N-Z': 'N-Z (Très Teinté)',
        }
        for english, french in color_translations.items():
            StoneColor.objects.filter(name=french).delete()
            StoneColor.objects.filter(name=english).update(name=french)

        # Stone Cuts
        self.stdout.write('Localizing Stone Cuts...')
        cut_translations = {
            'Round': 'Rond',
            'Princess': 'Princesse',
            'Cushion': 'Coussin',
            'Emerald': 'Émeraude',
            'Oval': 'Ovale',
        }
        for english, french in cut_translations.items():
            StoneCut.objects.filter(name=french).delete()
            StoneCut.objects.filter(name=english).update(name=french)

        # Payment Methods
        self.stdout.write('Localizing Payment Methods...')
        payment_translations = {
            'Cashplus': 'Espèces',
            'Cash': 'Espèces',
            'Credit Card': 'Carte de crédit',
            'Debit Card': 'Carte de débit',
            'Bank Transfer': 'Virement bancaire',
            'Check': 'Chèque',
            'Mobile Money': 'Paiement mobile',
        }
        for english, french in payment_translations.items():
            PaymentMethod.objects.filter(name=french).delete()
            PaymentMethod.objects.filter(name=english).update(name=french)

        # Stock Locations
        self.stdout.write('Localizing Stock Locations...')
        location_translations = {
            'Main Safe': 'Coffre principal',
            'Display Cabinet': 'Vitrine d\'exposition',
            'Storage Room': 'Salle de stockage',
            'Back Office': 'Bureau arrière',
            'Secure Locker 1': 'Casier sécurisé 1',
            'Secure Locker 2': 'Casier sécurisé 2',
            'Workshop': 'Atelier',
        }
        for english, french in location_translations.items():
            StockLocation.objects.filter(name=french).delete()
            StockLocation.objects.filter(name=english).update(name=french)

        # Delivery Methods
        self.stdout.write('Localizing Delivery Methods...')
        delivery_translations = {
            'In-Store Pickup': 'Retrait en magasin',
            'Home Delivery': 'Livraison à domicile',
            'Express Delivery': 'Livraison express',
            'Courier': 'Coursier',
            'Mail': 'Courrier',
            'International': 'International',
            'Click & Collect': 'Retrait en magasin',
        }
        for english, french in delivery_translations.items():
            DeliveryMethod.objects.filter(name=french).delete()
            DeliveryMethod.objects.filter(name=english).update(name=french)

        # Repair Types
        self.stdout.write('Localizing Repair Types...')
        repair_translations = {
            'Cleaning': 'Nettoyage',
            'Polishing': 'Polissage',
            'Stone Setting': 'Sertissage de pierres',
            'Resizing': 'Redimensionnement',
            'Metal Repair': 'Réparation du métal',
            'Jewelry Restoration': 'Restauration de bijoux',
            'Engraving': 'Gravure',
        }
        for english, french in repair_translations.items():
            RepairType.objects.filter(name=french).delete()
            RepairType.objects.filter(name=english).update(name=french)

        # Certificate Issuers
        self.stdout.write('Localizing Certificate Issuers...')
        cert_translations = {
            'GIA': 'GIA (Institut Gemmologique d\'Amérique)',
            'IGI': 'IGI (Institut International de Gemmologie)',
            'HRD': 'HRD (Association des Diamantaires de Belgique)',
            'AGS': 'AGS (Société d\'Évaluation des Diamants Américaine)',
            'EGL': 'EGL (Laboratoire Européen de Gemmologie)',
        }
        for english, french in cert_translations.items():
            CertificateIssuer.objects.filter(name=french).delete()
            CertificateIssuer.objects.filter(name=english).update(name=french)

        self.stdout.write(self.style.SUCCESS('French localization completed successfully!'))

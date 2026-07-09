"""
Diagnostic : liste TOUT ce qui est rattaché à un client.

Répond à la question « pourquoi ce client existe alors qu'il n'a rien acheté ? »
en parcourant automatiquement toutes les relations vers Client (factures dans
n'importe quel état, dépôts, réparations, garde/stock, mises de côté, devis,
commandes spéciales, paiements, …).

Usage :
    python manage.py client_activity CLI-20260415-0008
    python manage.py client_activity 42            # par id
    python manage.py client_activity --phone 0600  # par téléphone
"""
from django.core.management.base import BaseCommand, CommandError
from clients.models import Client


def _show(obj):
    try:
        return str(obj)
    except Exception:
        return f"{obj.__class__.__name__} #{obj.pk}"


class Command(BaseCommand):
    help = "Affiche tous les enregistrements rattachés à un client (factures, dépôts, réparations, garde, etc.)"

    def add_arguments(self, parser):
        parser.add_argument('identifier', nargs='?', help="Code client (CLI-...) ou id")
        parser.add_argument('--phone', help="Rechercher par téléphone")

    def handle(self, *args, **options):
        ident = options.get('identifier')
        phone = options.get('phone')

        if phone:
            qs = Client.objects.filter(phone__icontains=phone)
        elif ident and ident.isdigit():
            qs = Client.objects.filter(pk=int(ident))
        elif ident:
            qs = Client.objects.filter(code=ident)
        else:
            raise CommandError("Fournir un code client, un id, ou --phone.")

        clients = list(qs)
        if not clients:
            raise CommandError(f"Aucun client trouvé pour « {phone or ident} ».")
        if len(clients) > 1:
            self.stdout.write(f"{len(clients)} clients correspondent :")
            for c in clients:
                self.stdout.write(f"   {c.code} — {c.full_name} — {c.phone}")
            self.stdout.write("Relancez avec le code exact.")
            return

        c = clients[0]
        self.stdout.write("=" * 64)
        self.stdout.write(f"CLIENT : {c.code} — {c.full_name}")
        self.stdout.write(f"Téléphone : {c.phone}   |   Créé le : {c.created_at}")
        self.stdout.write("=" * 64)

        found = False
        for rel in c._meta.related_objects:
            name = rel.get_accessor_name()
            try:
                accessor = getattr(c, name)
            except Exception:
                continue  # OneToOne sans ligne

            model_name = rel.related_model.__name__
            if rel.one_to_one:
                found = True
                self.stdout.write(f"\n• {model_name} : {_show(accessor)}")
            else:
                rows = list(accessor.all())
                if rows:
                    found = True
                    self.stdout.write(f"\n• {model_name} — {len(rows)} enregistrement(s) :")
                    for x in rows[:100]:
                        self.stdout.write(f"      - {_show(x)}")

        if not found:
            self.stdout.write(self.style.WARNING(
                "\nAucun enregistrement rattaché — cliente créée mais rien d'autre "
                "(ni facture, ni dépôt, ni réparation, ni garde…)."
            ))
        self.stdout.write("")

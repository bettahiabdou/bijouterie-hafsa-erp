"""
Diagnostic : d'où vient un client et qu'a-t-il de rattaché ?

Parcourt automatiquement toutes les relations vers Client (factures dans
n'importe quel état, dépôts, réparations, garde/stock, mises de côté, devis,
commandes spéciales, paiements, …) et retrace l'origine de création via le
journal d'activité (ActivityLog).

Signal d'origine :
  - Le formulaire client manuel ENREGISTRE un ActivityLog « create ».
  - L'ajout rapide (popup « + » pendant une facture/réparation) n'enregistre RIEN.
  Donc : log de création présent  => saisie manuelle via le formulaire client.
         aucun log de création     => ajout rapide, vente probablement abandonnée.

Usage :
    python manage.py client_activity CLI-20260415-0008
    python manage.py client_activity 42                # par id
    python manage.py client_activity --phone 0660      # par téléphone
    python manage.py client_activity --orphans         # tous les clients sans aucune activité
"""
from django.core.management.base import BaseCommand, CommandError
from clients.models import Client
from users.models import ActivityLog


def _show(obj):
    try:
        return str(obj)
    except Exception:
        return f"{obj.__class__.__name__} #{obj.pk}"


def _is_orphan(client):
    """True si aucune ligne rattachée dans aucune relation."""
    for rel in client._meta.related_objects:
        name = rel.get_accessor_name()
        try:
            accessor = getattr(client, name)
        except Exception:
            continue  # OneToOne sans ligne
        if rel.one_to_one:
            return False
        if accessor.all().exists():
            return False
    return True


def _creation_log(client):
    """Le plus ancien ActivityLog 'create' pour ce client, ou None."""
    return (
        ActivityLog.objects
        .filter(model_name='Client', object_id=str(client.id), action=ActivityLog.ActionType.CREATE)
        .order_by('created_at')
        .first()
    )


class Command(BaseCommand):
    help = "Affiche l'origine et tous les enregistrements rattachés à un client."

    def add_arguments(self, parser):
        parser.add_argument('identifier', nargs='?', help="Code client (CLI-...) ou id")
        parser.add_argument('--phone', help="Rechercher par téléphone")
        parser.add_argument('--orphans', action='store_true',
                            help="Lister tous les clients sans aucune activité")

    # ------------------------------------------------------------------ #
    def handle(self, *args, **options):
        if options.get('orphans'):
            return self._handle_orphans()

        ident = options.get('identifier')
        phone = options.get('phone')

        if phone:
            qs = Client.objects.filter(phone__icontains=phone)
        elif ident and ident.isdigit():
            qs = Client.objects.filter(pk=int(ident))
        elif ident:
            qs = Client.objects.filter(code=ident)
        else:
            raise CommandError("Fournir un code client, un id, --phone, ou --orphans.")

        clients = list(qs)
        if not clients:
            raise CommandError(f"Aucun client trouvé pour « {phone or ident} ».")
        if len(clients) > 1:
            self.stdout.write(f"{len(clients)} clients correspondent :")
            for c in clients:
                self.stdout.write(f"   {c.code} — {c.full_name} — {c.phone}")
            self.stdout.write("Relancez avec le code exact.")
            return

        self._report_client(clients[0])

    # ------------------------------------------------------------------ #
    def _report_client(self, c):
        self.stdout.write("=" * 64)
        self.stdout.write(f"CLIENT : {c.code} — {c.full_name}")
        self.stdout.write(f"Téléphone : {c.phone}   |   Créé le : {c.created_at}")
        self.stdout.write("=" * 64)

        # --- Origine de création ---
        log = _creation_log(c)
        self.stdout.write("\nORIGINE :")
        if log:
            self.stdout.write(self.style.SUCCESS("  Formulaire client (saisie manuelle, journalisée)"))
            self.stdout.write(f"    par     : {log.user or 'inconnu'}")
            self.stdout.write(f"    le      : {log.created_at}")
            self.stdout.write(f"    IP      : {log.ip_address or '—'}")
        else:
            self.stdout.write(self.style.WARNING("  Ajout rapide (popup « + » d'une facture/réparation) — non journalisé"))
            self.stdout.write("    => cliente saisie pendant une vente qui n'a jamais été finalisée.")

        # --- Tout le journal la concernant ---
        logs = ActivityLog.objects.filter(
            model_name='Client', object_id=str(c.id)
        ).order_by('created_at')
        if logs.exists():
            self.stdout.write("\nJOURNAL D'ACTIVITÉ (Client) :")
            for lg in logs[:50]:
                self.stdout.write(f"    - {lg.created_at} | {lg.get_action_display()} | {lg.user or 'inconnu'}")

        # --- Enregistrements rattachés ---
        self.stdout.write("\nRATTACHÉ :")
        found = False
        for rel in c._meta.related_objects:
            name = rel.get_accessor_name()
            try:
                accessor = getattr(c, name)
            except Exception:
                continue
            model_name = rel.related_model.__name__
            if rel.one_to_one:
                found = True
                self.stdout.write(f"  • {model_name} : {_show(accessor)}")
            else:
                rows = list(accessor.all())
                if rows:
                    found = True
                    self.stdout.write(f"  • {model_name} — {len(rows)} :")
                    for x in rows[:100]:
                        self.stdout.write(f"        - {_show(x)}")
        if not found:
            self.stdout.write(self.style.WARNING(
                "  Aucun enregistrement — cliente orpheline (ni facture, ni dépôt, "
                "ni réparation, ni garde…)."
            ))
        self.stdout.write("")

    # ------------------------------------------------------------------ #
    def _handle_orphans(self):
        self.stdout.write("Recherche des clients sans aucune activité…\n")
        orphans = []
        for c in Client.objects.all().iterator():
            if _is_orphan(c):
                orphans.append(c)

        if not orphans:
            self.stdout.write(self.style.SUCCESS("Aucun client orphelin. Tout le monde a au moins un enregistrement."))
            return

        self.stdout.write(self.style.WARNING(
            f"{orphans.__len__()} client(s) orphelin(s) (aucune facture/dépôt/réparation/garde…) :\n"
        ))
        self.stdout.write(f"{'CODE':<22} {'NOM':<28} {'CRÉÉ LE':<20} ORIGINE")
        self.stdout.write("-" * 92)
        n_manual = n_quick = 0
        for c in orphans:
            if _creation_log(c):
                origine = "formulaire (manuel)"
                n_manual += 1
            else:
                origine = "ajout rapide (abandon)"
                n_quick += 1
            created = c.created_at.strftime('%Y-%m-%d %H:%M') if c.created_at else '—'
            self.stdout.write(f"{c.code:<22} {c.full_name[:27]:<28} {created:<20} {origine}")

        self.stdout.write("-" * 92)
        self.stdout.write(f"Total : {len(orphans)}  |  formulaire manuel : {n_manual}  |  ajout rapide (abandon) : {n_quick}")
        self.stdout.write("")

"""
Copy the Telegram bot token + admin chat IDs from environment variables into
SystemConfig, so the existing recipient list shows up (and can be edited) on
the Settings > Configuration Système page.

Read-only preview by default; pass --apply to write.

    python manage.py import_telegram_config            # show what would be imported
    python manage.py import_telegram_config --apply    # write into SystemConfig
    python manage.py import_telegram_config --apply --force   # overwrite existing DB values
"""
from django.conf import settings
from django.core.management.base import BaseCommand


class Command(BaseCommand):
    help = "Import the env Telegram token + admin chat IDs into SystemConfig."

    def add_arguments(self, parser):
        parser.add_argument('--apply', action='store_true', help="Write into SystemConfig")
        parser.add_argument('--force', action='store_true',
                            help="Overwrite DB values even if already set")

    def handle(self, *args, **options):
        from settings_app.models import SystemConfig
        cfg = SystemConfig.get_config()

        env_token = (getattr(settings, 'TELEGRAM_BOT_TOKEN', '') or '').strip()
        env_ids = (getattr(settings, 'TELEGRAM_ADMIN_CHAT_ID', '') or '').strip()

        self.stdout.write("Valeurs dans l'environnement :")
        self.stdout.write(f"   Token   : {'(défini)' if env_token else '(vide)'}")
        self.stdout.write(f"   Chat IDs: {env_ids or '(vide)'}")
        self.stdout.write("\nValeurs actuelles dans la base (page Configuration) :")
        self.stdout.write(f"   Token   : {'(défini)' if cfg.telegram_bot_token else '(vide)'}")
        self.stdout.write(f"   Chat IDs: {cfg.telegram_chat_id or '(vide)'}")

        if not env_token and not env_ids:
            self.stdout.write(self.style.WARNING(
                "\nRien à importer : aucune valeur Telegram dans l'environnement."))
            return

        force = options['force']
        changes = []
        if env_token and (force or not cfg.telegram_bot_token):
            changes.append(('telegram_bot_token', env_token))
        if env_ids and (force or not cfg.telegram_chat_id):
            changes.append(('telegram_chat_id', env_ids))

        if not changes:
            self.stdout.write(self.style.SUCCESS(
                "\nLa base contient déjà des valeurs. Utilisez --force pour les remplacer."))
            return

        if not options['apply']:
            self.stdout.write("\nÀ importer (simulation) :")
            for field, val in changes:
                shown = '(défini)' if field == 'telegram_bot_token' else val
                self.stdout.write(f"   {field} <- {shown}")
            self.stdout.write(self.style.WARNING("Relancez avec --apply pour écrire."))
            return

        for field, val in changes:
            setattr(cfg, field, val)
        cfg.telegram_enabled = True
        cfg.save(update_fields=[f for f, _ in changes] + ['telegram_enabled'])
        self.stdout.write(self.style.SUCCESS(
            f"\nImporté dans la base : {', '.join(f for f, _ in changes)}. "
            "La liste apparaît maintenant sur la page Configuration."))

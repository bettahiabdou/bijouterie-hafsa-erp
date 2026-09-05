"""
Set up and test the WhatsApp 'retour' group.

Examples:
    # show current config (no secrets printed)
    python manage.py whatsapp_group --status

    # create the group with initial participants (E.164 digits, no '+')
    python manage.py whatsapp_group --create --subject "retour" \
        --participants 212664030509,212600000000

    # inspect a group (invite link etc.)
    python manage.py whatsapp_group --info <GROUP_ID>

    # send a test text / image to WHATSAPP_RETOUR_GROUP_ID
    python manage.py whatsapp_group --test-text "Test retour"
    python manage.py whatsapp_group --test-image /path/to/photo.jpg
"""
import json
from django.core.management.base import BaseCommand

from sales import whatsapp


class Command(BaseCommand):
    help = "Create / inspect / test the WhatsApp 'retour' group."

    def add_arguments(self, parser):
        parser.add_argument('--status', action='store_true')
        parser.add_argument('--create', action='store_true')
        parser.add_argument('--subject', default='retour')
        parser.add_argument('--participants', default='',
                            help='Comma-separated E.164 numbers, digits only (e.g. 212664030509)')
        parser.add_argument('--info', default='', help='Group id to inspect')
        parser.add_argument('--test-text', default='')
        parser.add_argument('--test-image', default='')

    def handle(self, *args, **o):
        cfg = whatsapp._cfg()
        if o['status'] or not any([o['create'], o['info'], o['test_text'], o['test_image']]):
            self.stdout.write("WhatsApp config:")
            self.stdout.write(f"  enabled      : {cfg['enabled']}")
            self.stdout.write(f"  token set    : {bool(cfg['token'])}")
            self.stdout.write(f"  phone_id     : {cfg['phone_id'] or '(missing)'}")
            self.stdout.write(f"  group_id     : {cfg['group_id'] or '(missing)'}")
            self.stdout.write(f"  api_version  : {cfg['version']}")
            self.stdout.write(f"  configured   : {whatsapp.is_configured()}")
            return

        if o['create']:
            parts = [p.strip() for p in o['participants'].split(',') if p.strip()]
            if not parts:
                self.stderr.write("Provide --participants (at least one number).")
                return
            res = whatsapp.create_group(o['subject'], parts)
            self.stdout.write(json.dumps(res, indent=2, ensure_ascii=False))
            return

        if o['info']:
            self.stdout.write(json.dumps(whatsapp.get_group(o['info']), indent=2, ensure_ascii=False))
            return

        if o['test_text']:
            self.stdout.write(json.dumps(whatsapp.send_group_text(o['test_text']), indent=2, ensure_ascii=False))
            return

        if o['test_image']:
            mid = whatsapp.upload_media(o['test_image'])
            self.stdout.write(f"media_id: {mid}")
            self.stdout.write(json.dumps(whatsapp.send_group_image('Test image retour', media_id=mid), indent=2, ensure_ascii=False))
            return

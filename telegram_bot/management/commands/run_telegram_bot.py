"""
Management command to run the Telegram bot
Usage: python manage.py run_telegram_bot
"""

from django.core.management.base import BaseCommand
from telegram_bot.bot_handler import run_bot


class Command(BaseCommand):
    help = 'Run the Telegram bot for sales submissions'

    def handle(self, *args, **options):
        self.stdout.write(self.style.SUCCESS('Starting Telegram bot...'))
        run_bot()

from django.apps import AppConfig


class SalesConfig(AppConfig):
    name = 'sales'

    def ready(self):
        # Wire up circulation auto-sold / revert signals
        from . import signals  # noqa: F401

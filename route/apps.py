from django.apps import AppConfig


class RouteConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'route'

    def ready(self):
        from . import signals

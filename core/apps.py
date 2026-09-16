from django.apps import AppConfig


class CoreConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'core'

    def ready(self):
        # Place tes imports de modèles ou de signals ICI si nécessaire
        # Exemple : import core.signals
        pass
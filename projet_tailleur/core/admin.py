from django.contrib import admin
from .models import Client, Mensuration, Tissu, Commande, Depense

admin.site.register(Client)
admin.site.register(Mensuration)
admin.site.register(Tissu)
admin.site.register(Commande)
admin.site.register(Depense)
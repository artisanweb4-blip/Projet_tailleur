import os
import sys
sys.path.append(os.getcwd())  # s'assurer que le dossier courant est dans le path
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'projet_tailleur.settings')
import django
django.setup()

from django.core import serializers
from django.apps import apps
from django.db import connection

# Fermer toute connexion existante pour éviter l'erreur de curseur
connection.close()

all_data = []
for model in apps.get_models():
    qs = model.objects.all()
    if qs.exists():
        print(f"Export de {model._meta.object_name} : {qs.count()} enregistrements")
        all_data.extend(serializers.serialize('json', qs))

# Écriture en UTF-8 sans BOM
with open('data_final.json', 'w', encoding='utf-8') as f:
    f.write('[' + ','.join(all_data) + ']')

print(f"✅ Export terminé ! {len(all_data)} objets exportés dans data_final.json")
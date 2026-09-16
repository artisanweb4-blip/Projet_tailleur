"""
Export de toutes les données de la base vers un fichier JSON.

Usage :
    python export_data.py [fichier_de_sortie.json]

Le nom du module de settings est `tailleur_gestion.settings`
(l'ancien script référençait `projet_tailleur.settings`, qui n'existe pas).
"""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'tailleur_gestion.settings')

import django  # noqa: E402

django.setup()

from django.apps import apps  # noqa: E402
from django.core import serializers  # noqa: E402

# Modèles système à exclure : ils sont recréés par `migrate` et gonflent
# l'export inutilement (permissions, content types, sessions, logs admin).
EXCLUS = {
    'auth.permission',
    'auth.group',
    'contenttypes.contenttype',
    'sessions.session',
    'admin.logentry',
}


def exporter(chemin_sortie):
    objets = []
    for modele in apps.get_models():
        etiquette = modele._meta.label.lower()
        if etiquette in EXCLUS:
            continue
        queryset = modele.objects.all()
        if not queryset.exists():
            continue
        print(f"  {modele._meta.label} : {queryset.count()} enregistrement(s)")
        objets.extend(serializers.serialize('json', queryset))

    # `serializers.serialize` renvoie des chaînes JSON de tableaux ; on les
    # fusionne en un seul tableau valide.
    with open(chemin_sortie, 'w', encoding='utf-8') as f:
        f.write('[' + ','.join(objets) + ']')

    print(f"\n✅ Export terminé : {len(objets)} objet(s) -> {chemin_sortie}")


if __name__ == '__main__':
    sortie = sys.argv[1] if len(sys.argv) > 1 else 'data_final.json'
    exporter(sortie)

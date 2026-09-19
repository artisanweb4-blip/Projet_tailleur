"""Sauvegarde et restauration des données d'un atelier.

La sauvegarde est strictement cloisonnée par atelier (multi-boutique) :
seuls les enregistrements dont le FK `atelier` correspond à l'atelier
courant sont exportés, et une restauration refuse tout fichier dont les
enregistrements viseraient un autre atelier.

Contenu : les douze modèles métier (clients, mensurations, catalogue,
accessoires, commandes et leurs lignes, paiements, mouvements de stock,
dépenses, employés, paies). Les comptes d'accès, l'abonnement et les
fichiers média (photos, logos) ne sont PAS inclus : restaurer des
comptes pourrait verrouiller l'accès à l'atelier.

Les fichiers sont déposés dans <BASE_DIR>/sauvegardes/ sous le nom
sauvegarde_<idAtelier>_<AAAAMMJJ-HHMMSS>.json.
"""
import json
import re
from datetime import datetime
from pathlib import Path

from django.apps import apps
from django.conf import settings
from django.core import serializers
from django.db import transaction

# Ordre de chargement : parents d'abord ( FK satisfaits ).
MODELES_SAUVEGARDES = [
    'Client', 'CatalogueModele', 'Accessoire', 'Commande', 'Mensuration',
    'Depense', 'MouvementStock', 'Paiement', 'LigneCommande',
    'LigneAccessoire', 'Employe', 'Paie',
]
# Suppression avant restauration : enfants d'abord.
ORDRE_SUPPRESSION = list(reversed(MODELES_SAUVEGARDES))

MOTIF_NOM = re.compile(r'^sauvegarde_(\d+)_(\d{8}-\d{6})\.json$')


def _modele(nom):
    return apps.get_model('core', nom)


def dossier_sauvegardes():
    dossier = Path(settings.BASE_DIR) / 'sauvegardes'
    dossier.mkdir(parents=True, exist_ok=True)
    return dossier


def chemin_sauvegarde(atelier, nom):
    """Chemin d'une sauvegarde si elle existe et appartient à l'atelier."""
    motif = MOTIF_NOM.match(nom or '')
    if not motif or motif.group(1) != str(atelier.id):
        return None
    chemin = dossier_sauvegardes() / nom
    return chemin if chemin.is_file() else None


def creer_sauvegarde(atelier):
    """Exporte les données de l'atelier ; retourne le nom du fichier."""
    objets = []
    for nom in MODELES_SAUVEGARDES:
        objets.extend(_modele(nom).objects.filter(atelier=atelier).order_by('pk'))
    contenu = json.loads(serializers.serialize('json', objets))
    enveloppe = {
        'version': 1,
        'application': 'Projet_tailleur',
        'atelier_id': atelier.id,
        'atelier_nom': atelier.nom,
        'cree_le': datetime.now().isoformat(timespec='seconds'),
        'objets': contenu,
    }
    nom = f"sauvegarde_{atelier.id}_{datetime.now():%Y%m%d-%H%M%S}.json"
    (dossier_sauvegardes() / nom).write_text(
        json.dumps(enveloppe, ensure_ascii=False, indent=2), encoding='utf-8')
    return nom


def lister_sauvegardes(atelier):
    """Sauvegardes de l'atelier, plus récentes d'abord."""
    resultats = []
    for chemin in dossier_sauvegardes().glob('sauvegarde_*.json'):
        motif = MOTIF_NOM.match(chemin.name)
        if not motif or motif.group(1) != str(atelier.id):
            continue
        estampille = datetime.strptime(motif.group(2), '%Y%m%d-%H%M%S')
        resultats.append({
            'nom': chemin.name,
            'date': estampille,
            'taille': chemin.stat().st_size,
        })
    resultats.sort(key=lambda e: e['date'], reverse=True)
    return resultats


def supprimer_sauvegarde(atelier, nom):
    chemin = chemin_sauvegarde(atelier, nom)
    if chemin is None:
        return False
    chemin.unlink()
    return True


def _objets_du_fichier(contenu):
    """Valide l'enveloppe et retourne (objets, erreur)."""
    try:
        enveloppe = json.loads(contenu)
    except (ValueError, UnicodeDecodeError):
        return None, "Le fichier n'est pas une sauvegarde JSON valide."
    if not isinstance(enveloppe, dict) or 'objets' not in enveloppe:
        return None, "Structure de sauvegarde non reconnue."
    objets = enveloppe['objets']
    if not isinstance(objets, list):
        return None, "Structure de sauvegarde non reconnue."
    return objets, None


def objets_pour_atelier(atelier, objets):
    """Vérifie que chaque objet appartient au modèle et à l'atelier."""
    autorises = {f'core.{nom.lower()}' for nom in MODELES_SAUVEGARDES}
    for objet in objets:
        if objet.get('model') not in autorises:
            return f"Modèle inattendu dans la sauvegarde : {objet.get('model')}."
        if objet.get('fields', {}).get('atelier') != atelier.id:
            return ("La sauvegarde contient des données d'un autre atelier : "
                    "restauration refusée.")
    return None


def restaurer_sauvegarde(atelier, contenu):
    """Remplace les données de l'atelier par celles du fichier.

    Retourne (succès, message). Tout se passe dans une transaction :
    en cas d'erreur, rien n'est modifié.
    """
    objets, erreur = _objets_du_fichier(contenu)
    if erreur:
        return False, erreur
    erreur = objets_pour_atelier(atelier, objets)
    if erreur:
        return False, erreur
    try:
        with transaction.atomic():
            for nom in ORDRE_SUPPRESSION:
                _modele(nom).objects.filter(atelier=atelier).delete()
            nombre = 0
            flux = json.dumps(objets)
            for deserialise in serializers.deserialize('json', flux):
                deserialise.save()
                nombre += 1
    except Exception as exc:  # fichier corrompu, contraintes…
        return False, f"Restauration interrompue, aucune donnée modifiée : {exc}"
    return True, f"Restauration terminée : {nombre} enregistrements rétablis."

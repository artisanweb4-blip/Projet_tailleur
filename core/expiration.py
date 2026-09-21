"""Cycle de vie des boutiques : expiration, délai de conservation, suppression.

Règle métier (3 mois) :
- une boutique dont l'abonnement est expiré (ou jamais souscrit) est
  bloquée côté locataire mais ses données sont CONSERVÉES ;
- pendant 90 jours après la date de fin (ou la création si aucun
  abonnement), le super-admin peut activer un nouvel abonnement : la
  boutique redevient fonctionnelle avec toutes ses anciennes données ;
- passé ce délai, la boutique devient supprimable : le super-admin peut
  alors la supprimer totalement (données comprises).
"""
from datetime import date, timedelta

DELAI_CONSERVATION_JOURS = 90


def infos_expiration(atelier):
    """Retourne le statut effectif d'une boutique et ses échéances."""
    aujourdhui = date.today()
    abonnement = getattr(atelier, 'abonnement', None)

    if abonnement is None:
        reference = atelier.date_creation.date()
        statut = 'SANS_ABONNEMENT'
        date_fin = None
    else:
        date_fin = abonnement.date_fin
        reference = date_fin
        if abonnement.statut == 'SUSPENDU':
            statut = 'SUSPENDU'
        elif date_fin >= aujourdhui:
            statut = 'ACTIF'
        else:
            statut = 'EXPIRE'

    if statut == 'ACTIF' and not atelier.est_actif:
        statut = 'SUSPENDU'

    echeance = reference + timedelta(days=DELAI_CONSERVATION_JOURS)
    return {
        'statut': statut,
        'date_fin': date_fin,
        'echeance': echeance,
        'jours_restants': (echeance - aujourdhui).days,
        'supprimable': aujourdhui > echeance,
        'fonctionnelle': statut == 'ACTIF' and atelier.est_actif,
    }

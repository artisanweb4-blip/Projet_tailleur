"""
Context processors injectés dans tous les templates.

Configuration : voir TEMPLATES.OPTIONS.context_processors dans settings.py.
"""

from django.core.exceptions import ObjectDoesNotExist


def boutique_context(request):
    """Expose `profil` et `atelier` (alias `boutique`) à tous les templates.

    Corrections apportées :
      * la relation inverse s'appelle `profil` (Profil.user, related_name='profil')
        — et non `profile` ;
      * le champ du tenant s'appelle `atelier` — et non `boutique`.
        L'alias `boutique` est conservé pour ne pas casser les templates existants ;
      * l'`except Exception` global, qui masquait silencieusement toute erreur,
        est remplacé par la capture ciblée des deux cas attendus : profil absent
        (`ObjectDoesNotExist`) ou utilisateur anonyme (`AttributeError`).
    """
    profil = None
    atelier = None

    if request.user.is_authenticated:
        try:
            profil = request.user.profil
            atelier = profil.atelier
        except (AttributeError, ObjectDoesNotExist):
            # `RelatedObjectDoesNotExist` hérite d'`AttributeError` et de
            # `Profil.DoesNotExist` : un compte sans profil est un cas normal
            # (super-admin, compte fraîchement créé).
            profil = None
            atelier = None

    return {
        'profil': profil,
        'atelier': atelier,
        # Alias historique attendu par certains templates du back-office.
        'boutique': atelier,
        # base.html s'appuie sur `current_atelier` pour le titre de la page.
        'current_atelier': atelier,
    }

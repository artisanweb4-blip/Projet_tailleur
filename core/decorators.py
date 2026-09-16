"""
Décorateurs d'autorisation.

Le contrôle par rôle s'appuie sur `core.droits.MATRICE_DROITS`, la matrice
produit. Une vue s'annonce avec :

    @login_required
    @droit_requis('depenses')
    def liste_depenses(request):
        ...

Les anciens décorateurs (`boutique_user_required`, `role_requis`,
`subscription_active_required`) ont été retirés : ils n'étaient importés par
aucune vue, et contenaient trois `redirect()` vers des noms de routes
inexistants (`login`, `mon_profil`, `abonnement_expire`) ainsi que des
relations inverses erronées (`profilutilisateur`, `profile`).
"""

from functools import wraps

from django.contrib import messages
from django.shortcuts import redirect

from .droits import LIBELLES, MATRICE_DROITS, peut


def droit_requis(fonction):
    """Restreint une vue aux rôles cochés sur la ligne `fonction` de la matrice.

    Comportement :
      * anonyme            -> redirection vers la connexion ;
      * super-admin Django -> redirection vers le back-office plateforme
                              (il n'a pas d'atelier par conception) ;
      * compte sans atelier-> redirection vers le profil, avec un message ;
      * rôle non autorisé  -> redirection vers le tableau de bord, avec un
                              message précisant la fonction refusée.

    Le refus renvoie toujours une redirection et jamais une 403 nue : c'est un
    choix d'interface, cohérent avec le reste de l'application.
    """
    if fonction not in MATRICE_DROITS:
        # Erreur de développement : mieux vaut échouer au démarrage
        # qu'ouvrir ou fermer une vue par accident.
        raise ValueError(
            f"droit_requis({fonction!r}) : fonction inconnue de la matrice. "
            f"Fonctions disponibles : {', '.join(sorted(MATRICE_DROITS))}."
        )

    def decorator(view_func):
        @wraps(view_func)
        def _wrapped_view(request, *args, **kwargs):
            if not request.user.is_authenticated:
                return redirect('core:connexion')

            if request.user.is_superuser:
                messages.info(
                    request,
                    "Les administrateurs de la plateforme n'entrent pas dans "
                    "une boutique : passez par le back-office, ou par "
                    "l'impersonnalisation depuis la fiche boutique."
                )
                return redirect('saas_admin:superadmin_dashboard')

            profil = getattr(request.user, 'profil', None)
            atelier = getattr(profil, 'atelier', None) if profil else None
            if not atelier:
                messages.error(
                    request,
                    "Aucun atelier n'est associé à votre compte utilisateur."
                )
                return redirect('core:mon_profil')

            if not peut(request.user, fonction):
                messages.error(
                    request,
                    f"Votre rôle ne permet pas d'accéder à "
                    f"{LIBELLES[fonction]}. Contactez l'administrateur de "
                    f"votre atelier si nécessaire."
                )
                return redirect('core:dashboard')

            request.atelier = atelier
            return view_func(request, *args, **kwargs)

        return _wrapped_view

    return decorator

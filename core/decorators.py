from functools import wraps
from django.contrib import messages
from django.shortcuts import redirect


def boutique_user_required(view_func):
    """
    Décorateur qui interdit l'accès aux Super Admins (is_superuser=True),
    vérifie qu'un atelier est associé au profil, et l'injecte dans request.atelier.
    """
    @wraps(view_func)
    def _wrapped_view(request, *args, **kwargs):
        if not request.user.is_authenticated:
            return redirect('login')
        
        # 1. Bloquer le superadmin s'il tente d'accéder directement aux vues de la boutique
        if request.user.is_superuser:
            messages.error(
                request, 
                "Les administrateurs système n'ont pas accès à l'interface de gestion boutique."
            )
            return redirect('saas_admin:superadmin_dashboard')

        # 2. Récupérer le profil et l'atelier
        profil = getattr(request.user, 'profilutilisateur', None) or getattr(request.user, 'profile', None)
        atelier = getattr(profil, 'atelier', None) if profil else None

        # Si l'utilisateur n'a pas d'atelier lié, éviter le crash sur request.atelier
        if not atelier:
            messages.error(
                request, 
                "Aucun atelier n'est associé à votre compte utilisateur."
            )
            return redirect('mon_profil')

        # Attach de l'atelier à la requête pour l'utiliser dans les vues
        request.atelier = atelier
        return view_func(request, *args, **kwargs)

    return _wrapped_view


# Cartographie des alias/variations pour les 3 rôles principaux
ROLES_MAP = {
    'ADMIN': ['ADMIN', 'ADMINISTRATEUR', 'ADMIN_GENERAL', 'Admin Général', 'admin_general', 'admin'],
    'GESTIONNAIRE': ['GESTIONNAIRE', 'Gestionnaire', 'gestionnaire'],
    'COMPTABLE': ['COMPTABLE', 'Comptable', 'comptable'],
}


def role_requis(*roles_autorises):
    """
    Décorateur restreignant l'accès selon les rôles autorisés :
    - 'ADMIN' (Admin Général)
    - 'GESTIONNAIRE' (Gestionnaire)
    - 'COMPTABLE' (Comptable)
    """
    def decorator(view_func):
        @wraps(view_func)
        def _wrapped_view(request, *args, **kwargs):
            if not request.user.is_authenticated:
                return redirect('login')

            # Récupération du profil utilisateur (profilutilisateur ou profile)
            profil = getattr(request.user, 'profilutilisateur', None) or getattr(request.user, 'profile', None)
            
            # Récupération de la valeur du rôle
            user_role = None
            if profil and hasattr(profil, 'role'):
                user_role = profil.role
            elif hasattr(request.user, 'role'):
                user_role = request.user.role

            if user_role:
                # Normalisation et construction des rôles autorisés
                valeurs_acceptees = set()
                for role in roles_autorises:
                    role_key = str(role).upper()
                    valeurs_acceptees.add(role_key)
                    if role_key in ROLES_MAP:
                        for alias in ROLES_MAP[role_key]:
                            valeurs_acceptees.add(alias.upper())

                # Vérification de l'appartenance
                if str(user_role).upper() in valeurs_acceptees:
                    return view_func(request, *args, **kwargs)

            # Refus d'accès : Redirection vers 'mon_profil' au lieu de 'dashboard' pour éviter les boucles
            messages.error(
                request, 
                "Vous n'avez pas les autorisations nécessaires pour accéder à cette page."
            )
            return redirect('mon_profil')
            
        return _wrapped_view
    return decorator


def subscription_active_required(view_func):
    """
    Décorateur SaaS : vérifie si l'atelier/boutique de l'utilisateur a un abonnement actif.
    """
    @wraps(view_func)
    def _wrapped_view(request, *args, **kwargs):
        if not request.user.is_authenticated:
            return redirect('login')

        profil = getattr(request.user, 'profilutilisateur', None) or getattr(request.user, 'profile', None)
        atelier = getattr(profil, 'atelier', None) if profil else None

        if atelier:
            is_active = getattr(atelier, 'is_subscription_active', True)
            if callable(is_active):
                is_active = is_active()

            if not is_active:
                messages.warning(
                    request,
                    "Votre abonnement a expiré. Veuillez le renouveler pour continuer à utiliser la plateforme."
                )
                return redirect('abonnement_expire')

        return view_func(request, *args, **kwargs)
    return _wrapped_view
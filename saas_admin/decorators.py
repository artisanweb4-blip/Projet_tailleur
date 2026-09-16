from django.shortcuts import redirect
from django.contrib import messages
from functools import wraps

def superadmin_required(view_func):
    """
    Décorateur qui restreint l'accès uniquement aux Superadministrateurs de la plateforme SaaS.
    """
    @wraps(view_func)
    def _wrapped_view(request, *args, **kwargs):
        if not request.user.is_authenticated:
            return redirect('core:connexion')
        
        # Vérification si l'utilisateur est superutilisateur Django ou a un rôle Superadmin dans son profil
        is_saas_admin = request.user.is_superuser or (
            hasattr(request.user, 'profil') and request.user.profil.role == 'SUPERADMIN'
        )

        if not is_saas_admin:
            messages.error(request, "Accès refusé. Vous n'avez pas les permissions d'administration SaaS.")
            return redirect('core:dashboard')

        return view_func(request, *args, **kwargs)
    return _wrapped_view
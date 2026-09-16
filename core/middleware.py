import threading

# Variable globale isolée par thread de requête WSGI/ASGI
_thread_locals = threading.local()


def get_current_atelier():
    """
    Récupère l'atelier de la requête en cours.
    Utilisé par le TenantManager dans models.py pour filtrer l'ORM.
    """
    return getattr(_thread_locals, 'atelier', None)


class TenantMiddleware:
    """
    Middleware Multi-Tenant :
    Intercepte l'atelier de l'utilisateur connecté et le rend
    accessible globalement pour le filtrage automatique de l'ORM.
    """
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        # Réinitialisation par précaution au début de la requête
        _thread_locals.atelier = None
        request.atelier = None

        if hasattr(request, 'user') and request.user.is_authenticated:
            # 1. Ne pas filtrer si c'est un SuperAdmin système
            if request.user.is_superuser:
                _thread_locals.atelier = None
            else:
                # 2. Récupération robuste du profil (profil, profilutilisateur, profile)
                profil = (
                    getattr(request.user, 'profil', None) or 
                    getattr(request.user, 'profilutilisateur', None) or 
                    getattr(request.user, 'profile', None)
                )

                # 3. Affectation de l'atelier
                if profil and hasattr(profil, 'atelier') and profil.atelier:
                    _thread_locals.atelier = profil.atelier
                    request.atelier = profil.atelier

        try:
            response = self.get_response(request)
        finally:
            # Nettoyage systématique, même en cas d'erreur ou d'exception dans la vue
            _thread_locals.atelier = None

        return response
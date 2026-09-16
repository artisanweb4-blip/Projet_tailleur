# core/context_processors.py

def boutique_context(request):
    # 1. Initialiser les variables avec des valeurs par défaut
    profil = None
    boutique = None

    # 2. Ne chercher le profil que si l'utilisateur est authentifié
    if request.user.is_authenticated:
        try:
            profil = request.user.profile  # ou request.user.profil selon votre modèle
            boutique = profil.boutique if profil else None
        except Exception:
            profil = None
            boutique = None

    # 3. Retourner le dictionnaire de contexte
    return {
        'profil': profil,
        'boutique': boutique,
    }
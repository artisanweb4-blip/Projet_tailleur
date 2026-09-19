"""
Matrice des droits — source unique de vérité pour l'autorisation par rôle.

Chaque ligne correspond à une fonction de la matrice produit :

    | Fonction                      | Admin | Gestionnaire | Comptable |
    |-------------------------------|-------|--------------|-----------|
    | Paramètres de l'atelier       |   ✅  |      —       |     —     |
    | Créer / modifier utilisateurs |   ✅  |      —       |     —     |
    | Employés et paies             |   ✅  |      —       |     —     |
    | Catalogue et stock            |   ✅  |      —       |     —     |
    | Clients et mensurations       |   ✅  |      ✅      |     —     |
    | Créer une commande            |   ✅  |      ✅      |     —     |
    | Ventes directes               |   ✅  |      ✅      |     —     |
    | Consulter les commandes       |   ✅  |      ✅      |     ✅    |
    | Enregistrer un paiement       |   ✅  |      ✅      |     ✅    |
    | Dépenses et comptabilité      |   ✅  |      —       |     ✅    |
    | Factures et reçus             |   ✅  |      ✅      |     ✅    |

Convention : au sein d'une fonction, un rôle coché dispose du droit complet
(consulter, créer, modifier, supprimer). La fonction « commandes » est la seule
scindée en deux lignes : consultation (trois rôles) et création / modification
/ suppression (ADMIN et GESTIONNAIRE).

Sont accessibles à tous les rôles, hors matrice : tableau de bord, profil,
mot de passe, calendrier des livraisons (lecture), page d'abonnement expiré.
"""

ADMIN = 'ADMIN'
GESTIONNAIRE = 'GESTIONNAIRE'
COMPTABLE = 'COMPTABLE'

TOUS = frozenset({ADMIN, GESTIONNAIRE, COMPTABLE})

# ----------------------------------------------------------------------
# La matrice, telle quelle.
# ----------------------------------------------------------------------
MATRICE_DROITS = {
    'parametres':      frozenset({ADMIN}),
    'utilisateurs':    frozenset({ADMIN}),
    'employes':        frozenset({ADMIN}),
    'catalogue':       frozenset({ADMIN}),
    'clients':         frozenset({ADMIN, GESTIONNAIRE}),
    'commandes_creer': frozenset({ADMIN, GESTIONNAIRE}),
    'ventes_directes': frozenset({ADMIN, GESTIONNAIRE}),
    'commandes_voir':  TOUS,
    'paiements':       TOUS,
    'depenses':        frozenset({ADMIN, COMPTABLE}),
    'factures':        TOUS,
}

# Libellés produits, pour l'affichage et les messages d'erreur.
LIBELLES = {
    'parametres':      "les paramètres de l'atelier",
    'utilisateurs':    "la création et la modification des utilisateurs",
    'employes':        "la gestion des employés et des paies",
    'catalogue':       "le catalogue et le stock",
    'clients':         "les clients et les mensurations",
    'commandes_creer': "la création et la modification des commandes",
    'ventes_directes': "les ventes directes",
    'commandes_voir':  "la consultation des commandes",
    'paiements':       "l'enregistrement des paiements",
    'depenses':        "les dépenses et la comptabilité",
    'factures':        "les factures et reçus",
}

# Rattachement de chaque vue à sa fonction. Utilisé par le décorateur
# `droit_requis` et documenté dans AUDIT.md.
# Les pages de compte (tableau de bord, mon_profil, mon_abonnement) ne sont
# pas dans la matrice : elles concernent le compte, pas une fonction métier,
# et restent accessibles à tout membre connecté de l'atelier. Les actions qui
# engagent l'atelier, elles, sont rattachées (ex. souscrire_plan -> parametres).
VUES = {
    # Paramètres de l'atelier
    'parametres': [
        'parametres_view', 'souscrire_plan',
        'sauvegarde_creer', 'sauvegarde_telecharger',
        'sauvegarde_supprimer', 'sauvegarde_restaurer',
    ],
    # Créer / modifier des utilisateurs
    'utilisateurs': [
        'ajouter_utilisateur', 'modifier_utilisateur', 'supprimer_utilisateur',
    ],
    # Employés et paies
    'employes': [
        'liste_employes', 'detail_employe', 'ajouter_employe',
        'modifier_employe', 'supprimer_employe', 'creer_paie',
        'plan_charge', 'api_employes',
    ],
    # Catalogue et stock
    'catalogue': [
        'liste_modeles', 'ajouter_modele', 'modifier_modele',
        'supprimer_modele', 'ajouter_accessoire', 'modifier_accessoire',
        'supprimer_accessoire', 'historique_stock', 'ajuster_stock',
    ],
    # Clients et mensurations
    'clients': [
        'liste_clients', 'ajouter_client', 'detail_client', 'modifier_client',
        'supprimer_client', 'ajouter_mensuration', 'modifier_mensuration',
        'supprimer_mensuration', 'detail_mensuration', 'mensuration_pdf',
    ],
    # Créer une commande (création, modification, suppression, production)
    'commandes_creer': [
        'creer_commande', 'modifier_commande', 'supprimer_commande',
        'finaliser_commande', 'ajouter_ligne', 'supprimer_ligne',
        'attribuer_ligne', 'fiche_atelier_pdf', 'fiche_ligne_pdf',
    ],
    # Ventes directes
    'ventes_directes': [
        'liste_ventes_directes', 'creer_vente_directe',
        'detail_vente_directe', 'annuler_vente_directe',
    ],
    # Consulter les commandes
    # api_mensurations_client est rattaché ici et non à « clients » : cet
    # endpoint JSON ne sert qu'aux pages commandes (création et détail), que
    # le comptable consulte. Le bloquer casserait le détail de commande.
    'commandes_voir': [
        'liste_commandes', 'detail_commande', 'calendrier',
        'api_mensurations_client',
    ],
    # Enregistrer un paiement
    'paiements': [
        'ajouter_paiement',
    ],
    # Dépenses et comptabilité
    'depenses': [
        'liste_depenses', 'ajouter_depense', 'modifier_depense',
        'supprimer_depense',
    ],
    # Factures et reçus
    'factures': [
        'recu_paiement', 'recu_paiement_pdf', 'facture_commande',
        'facture_commande_pdf', 'recu_caisse', 'recu_caisse_pdf',
    ],
}

# Index inverse : nom de vue -> fonction. Construit une seule fois.
FONCTION_PAR_VUE = {
    vue: fonction
    for fonction, vues in VUES.items()
    for vue in vues
}


def role_de(user):
    """Rôle du compte, ou None (super-admin, compte sans profil)."""
    profil = getattr(user, 'profil', None)
    return getattr(profil, 'role', None) if profil else None


def peut(user, fonction):
    """True si le rôle de `user` est coché sur la ligne `fonction`."""
    if fonction not in MATRICE_DROITS:
        # Fonction inconnue : on refuse par défaut plutôt que d'ouvrir.
        return False
    return role_de(user) in MATRICE_DROITS[fonction]


def droits_de(user):
    """Dictionnaire {fonction: bool} pour les templates.

    Exposé dans tous les templates sous le nom `peut` par le context
    processor `core.context_processors.boutique_context`, ce qui permet de
    masquer les entrées de menu et les boutons d'action interdits.
    """
    return {fonction: peut(user, fonction) for fonction in MATRICE_DROITS}

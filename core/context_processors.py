"""
Context processors injectés dans tous les templates.

Configuration : voir TEMPLATES.OPTIONS.context_processors dans settings.py.
"""

from django.core.exceptions import ObjectDoesNotExist

from .droits import FONCTION_PAR_VUE, droits_de

# Chaque page de l'application porte un entête standard : icône + titre
# alignés, et la sidebar marque la section active. Tout est déduit de
# l'URL courante, pour que AUCUNE page n'y échappe.
_TITRES_PAR_FONCTION = {
    'parametres':     ("Paramètres de l'atelier", 'bi-gear-fill'),
    'utilisateurs':   ("Utilisateurs de l'atelier", 'bi-person-gear'),
    'employes':       ('Employés & paies', 'bi-person-badge-fill'),
    'catalogue':      ('Catalogue & stock', 'bi-collection-fill'),
    'clients':        ('Clients & mensurations', 'bi-people-fill'),
    'commandes_voir': ('Commandes', 'bi-bag-check-fill'),
    'commandes_creer': ('Commandes', 'bi-bag-check-fill'),
    'ventes_directes': ('Ventes directes', 'bi-cart-check-fill'),
    'paiements':      ('Paiements', 'bi-cash-coin'),
    'factures':       ('Factures & reçus', 'bi-receipt'),
    'depenses':       ('Dépenses & comptabilité', 'bi-cash-stack'),
}

# Réglages fins par vue : titre/icône propres et section de la sidebar.
_PAGES = {
    'dashboard':          ('dashboard', 'Tableau de bord', 'bi-speedometer2'),
    'calendrier':         ('calendrier', 'Agenda des livraisons', 'bi-calendar-event'),
    'plan_charge':        ('employes', 'Plan de charge', 'bi-kanban-fill'),
    'historique_stock':   ('catalogue', 'Historique du stock', 'bi-clock-history'),
    'ajuster_stock':      ('catalogue', 'Historique du stock', 'bi-clock-history'),
    'detail_client':      ('clients', 'Fiche client', 'bi-person-vcard-fill'),
    'modifier_client':    ('clients', 'Fiche client', 'bi-person-vcard-fill'),
    'supprimer_client':   ('clients', 'Fiche client', 'bi-person-vcard-fill'),
    'ajouter_mensuration': ('clients', 'Mensurations', 'bi-rulers'),
    'modifier_mensuration': ('clients', 'Mensurations', 'bi-rulers'),
    'detail_mensuration': ('clients', 'Mensurations', 'bi-rulers'),
    'mensuration_pdf':    ('clients', 'Mensurations', 'bi-rulers'),
    'detail_commande':    ('commandes', 'Détail de la commande', 'bi-bag-detail-fill'),
    'detail_vente_directe': ('commandes', 'Vente directe', 'bi-cart-dash-fill'),
    'detail_employe':     ('employes', 'Fiche employé', 'bi-person-vcard-fill'),
    'mon_profil':         ('profil', 'Mon profil', 'bi-person-circle'),
    'modifier_profil':    ('profil', 'Mon profil', 'bi-person-circle'),
    'changer_mot_de_passe': ('profil', 'Mon profil', 'bi-person-circle'),
    'mon_abonnement':     ('abonnement', 'Abonnements & offres', 'bi-journal-album'),
    'souscrire_plan':     ('abonnement', 'Abonnements & offres', 'bi-journal-album'),
}

# fonction de la matrice -> section de la sidebar
_SECTION_PAR_FONCTION = {
    'clients': 'clients',
    'catalogue': 'catalogue',
    'commandes_voir': 'commandes',
    'commandes_creer': 'commandes',
    'ventes_directes': 'commandes',
    'paiements': 'commandes',
    'factures': 'commandes',
    'depenses': 'comptabilite',
    'employes': 'employes',
    'parametres': 'parametres',
    'utilisateurs': 'parametres',
}


def _infos_page(request):
    if not request.resolver_match:
        return 'dashboard', 'Atelier', 'bi-shop'
    nom = request.resolver_match.url_name
    # Le nom de la fonction vue peut différer du nom d'URL
    # (ex. vue `parametres_view` servie sous l'URL `parametres`).
    nom_vue = getattr(request.resolver_match.func, '__name__', '')
    if nom in _PAGES:
        return _PAGES[nom]
    fonction = FONCTION_PAR_VUE.get(nom_vue) or FONCTION_PAR_VUE.get(nom)
    if fonction:
        titre, icone = _TITRES_PAR_FONCTION.get(
            fonction, ('Atelier', 'bi-shop'))
        return _SECTION_PAR_FONCTION.get(fonction, 'dashboard'), titre, icone
    return 'dashboard', 'Atelier', 'bi-shop'


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

    resultat = {
        'profil': profil,
        'atelier': atelier,
        # Alias historique attendu par certains templates du back-office.
        'boutique': atelier,
        # base.html s'appuie sur `current_atelier` pour le titre de la page.
        'current_atelier': atelier,
        # Matrice des droits : {fonction: bool}, pour masquer menus et boutons
        # interdits au rôle courant. Voir core/droits.py.
        'peut': droits_de(request.user),
    }
    section, titre, icone = _infos_page(request)
    resultat.update({
        # Section de la sidebar à marquer active.
        'section_active': section,
        # Entête standard de page : icône + titre sur la même ligne.
        'titre_page': titre,
        'icone_page': icone,
    })
    return resultat

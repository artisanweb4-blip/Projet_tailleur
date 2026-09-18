# Traductions de l'interface (français -> anglais).
#
# Le sélecteur de langue de l'en-tête bascule la session entre « fr » et
# « en ». Les chaînes traduites couvrent la coquille de l'application
# (menus, en-têtes, pieds de page), les entêtes de pages (titres déduits
# de l'URL) et le tableau de bord. Le contenu métier des pages reste en
# français : la traduction s'étendra progressivement via ce dictionnaire
# et le tag {% tr "…" %} (core/templatetags/trad.py).

EN = {
    # --- Sidebar & coquille ---
    'Menu Principal': 'Main Menu',
    'Préférences': 'Preferences',
    'Tableau de bord': 'Dashboard',
    'Clients': 'Clients',
    'Modèles & Accessoires': 'Patterns & Accessories',
    'Commandes & Achats': 'Orders & Purchases',
    'Calendrier': 'Calendar',
    'Comptabilité': 'Accounting',
    'Employés': 'Employees',
    'Abonnements & Offres': 'Subscriptions & Offers',
    'Mon profil': 'My profile',
    'Paramètres': 'Settings',
    'Bienvenue,': 'Welcome,',
    'Tous droits réservés': 'All rights reserved',
    'Déconnexion': 'Sign out',

    # --- Entêtes de pages (titres du context processor) ---
    'Clients & mensurations': 'Clients & measurements',
    'Catalogue & stock': 'Catalog & stock',
    'Commandes': 'Orders',
    'Ventes directes': 'Direct sales',
    'Paiements': 'Payments',
    'Factures & reçus': 'Invoices & receipts',
    'Dépenses & comptabilité': 'Expenses & accounting',
    'Employés & paies': 'Employees & payroll',
    "Paramètres de l'atelier": 'Shop settings',
    "Utilisateurs de l'atelier": "Shop users",
    'Agenda des livraisons': 'Delivery agenda',
    'Plan de charge': 'Workload plan',
    'Historique du stock': 'Stock history',
    'Fiche client': 'Client file',
    'Mensurations': 'Measurements',
    'Détail de la commande': 'Order details',
    'Vente directe': 'Direct sale',
    'Fiche employé': 'Employee file',
    'Abonnements & offres': 'Subscriptions & offers',
    'Atelier': 'Shop',

    # --- Tableau de bord ---
    "Chiffre d'affaires": 'Revenue',
    'Toutes commandes': 'All orders',
    'Encaissé': 'Collected',
    'du CA': 'of revenue',
    'Reste à recouvrer': 'Outstanding',
    'Créances clients': 'Customer dues',
    'Résultat du mois': 'Monthly result',
    'En cours': 'In progress',
    'Livrées': 'Delivered',
    'Livraisons 7 j': '7-day deliveries',
    'Revenus vs Dépenses': 'Revenue vs Expenses',
    '6 derniers mois': 'Last 6 months',
    'Répartition des commandes': 'Order breakdown',
    'Par statut': 'By status',
    'Commandes récentes': 'Recent orders',
    'Prochaines livraisons': 'Upcoming deliveries',
    'Bonjour': 'Hello',
    "Voici l'activité de": 'Here is the activity of',
}


def traduire(texte, langue):
    """Retourne `texte` traduit si la langue demandée n'est pas le français."""
    if langue == 'fr' or texte is None:
        return texte
    return EN.get(texte, texte)

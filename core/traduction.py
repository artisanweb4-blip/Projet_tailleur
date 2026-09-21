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
    # --- Sauvegarde (onglet Paramètres) ---
    "Sauvegarde": "Backup",
    "Copies & restauration": "Backups & restore",
    "Sauvegarde des données": "Data backup",
    "Copiez et restaurez les données de l'atelier (clients, commandes, paiements, stock, employés).": "Copy and restore shop data (clients, orders, payments, stock, employees).",
    "Les photos et logos (fichiers média) ne sont pas inclus dans la sauvegarde.": "Photos and logos (media files) are not included in the backup.",
    "Créer une sauvegarde": "Create a backup",
    "Sauvegardes existantes": "Existing backups",
    "Fichier": "File",
    "Date": "Date",
    "Taille": "Size",
    "Actions": "Actions",
    "Télécharger": "Download",
    "Supprimer": "Delete",
    "Aucune sauvegarde pour le moment.": "No backup yet.",
    "Restaurer une sauvegarde": "Restore a backup",
    "La restauration remplace les données actuelles de l'atelier par celles du fichier.": "Restoring replaces the shop's current data with the file's.",
    "Je comprends que les données actuelles seront remplacées.": "I understand current data will be replaced.",
    "Restaurer": "Restore",

    # --- Page abonnement expiré ---
    "Boutique suspendue": "Shop suspended",
    "Aucun abonnement n'est actif pour cette boutique.": "No subscription is active for this shop.",
    "L'abonnement de cette boutique a expiré le": "The subscription of this shop expired on",
    "Vos données sont conservées en sécurité jusqu'au": "Your data is safely kept until",
    "encore": "another",
    "jours": "days",
    "Pour réactiver la boutique avec toutes ses anciennes données, contactez le gestionnaire de la plateforme avant cette date : un nouvel abonnement peut être activé à tout moment pendant la période de conservation.": "To reactivate the shop with all its old data, contact the platform manager before this date: a new subscription can be activated at any time during the retention period.",
    "Se déconnecter": "Sign out",

    # --- Marque & sidebar (0019) ---
    "Gestion d'ateliers de couture": "Tailoring shop management",
    "Boutique": "Shop",

}


def traduire(texte, langue):
    """Retourne `texte` traduit si la langue demandée n'est pas le français."""
    if langue == 'fr' or texte is None:
        return texte
    return EN.get(texte, texte)

from django.urls import path
from . import views
from django.views.generic import RedirectView

app_name = 'core'

urlpatterns = [

    # ==========================================
    # 1. AUTHENTIFICATION & SAAS ONBOARDING
    # ==========================================
    path('', RedirectView.as_view(pattern_name='core:connexion'), name='accueil'),
    path('connexion/', views.connexion, name='connexion'),
    path('deconnexion/', views.deconnexion, name='deconnexion'),
    path('inscription/', views.inscription_saas, name='inscription_saas'),

    # ==========================================
    # 2. PROFIL UTILISATEUR & PARAMÈTRES
    # ==========================================
    path('profil/', views.mon_profil, name='mon_profil'),
    path('profil/modifier/', views.modifier_profil, name='modifier_profil'),
    path('profil/mot-de-passe/', views.changer_mot_de_passe, name='changer_mot_de_passe'),
    path('parametres/', views.parametres_view, name='parametres'),

    # ==========================================
    # 3. DASHBOARD
    # ==========================================
    path('dashboard/', views.dashboard, name='dashboard'),

    # ==========================================
    # 4. CLIENTS
    # ==========================================
    path('clients/', views.liste_clients, name='liste_clients'),
    path('clients/ajouter/', views.ajouter_client, name='ajouter_client'),
    path('clients/<int:pk>/', views.detail_client, name='detail_client'),
    path('clients/<int:pk>/modifier/', views.modifier_client, name='modifier_client'),
    path('clients/<int:pk>/supprimer/', views.supprimer_client, name='supprimer_client'),

    # ==========================================
    # 5. MENSURATIONS
    # ==========================================
    path('clients/<int:client_pk>/mensurations/ajouter/',
         views.ajouter_mensuration, name='ajouter_mensuration'),
    path('mensurations/<int:pk>/',
         views.detail_mensuration, name='detail_mensuration'),
    path('mensurations/<int:pk>/modifier/',
         views.modifier_mensuration, name='modifier_mensuration'),
    path('mensurations/<int:pk>/supprimer/',
         views.supprimer_mensuration, name='supprimer_mensuration'),
    path('mensurations/<int:pk>/pdf/',
         views.mensuration_pdf, name='mensuration_pdf'),

    # ==========================================
    # 6. COMMANDES
    # ==========================================
    path('commandes/', views.liste_commandes, name='liste_commandes'),
    path('commandes/creer/', views.creer_commande, name='creer_commande'),
    path('ventes-directes/', views.liste_ventes_directes, name='liste_ventes_directes'),
    path('ventes-directes/creer/', views.creer_vente_directe, name='creer_vente_directe'),
    path('commandes/<int:pk>/', views.detail_commande, name='detail_commande'),
    path('commandes/<int:pk>/modifier/', views.modifier_commande, name='modifier_commande'),
    path('commandes/<int:pk>/supprimer/', views.supprimer_commande, name='supprimer_commande'),
    path('commandes/<int:pk>/finaliser/', views.finaliser_commande, name='finaliser_commande'),

    # Reçu & Facture
    path('commandes/<int:pk>/recu/', views.recu_paiement, name='recu_paiement'),
    path('commandes/<int:pk>/recu/pdf/', views.recu_paiement_pdf, name='recu_paiement_pdf'),
    path('commandes/<int:pk>/facture/', views.facture_commande, name='facture_commande'),
    path('commandes/<int:pk>/facture/pdf/', views.facture_commande_pdf, name='facture_commande_pdf'),
    path('commandes/<int:pk>/recu-caisse/', views.recu_caisse, name='recu_caisse'),
    path('commandes/<int:pk>/recu-caisse/pdf/', views.recu_caisse_pdf, name='recu_caisse_pdf'),

    # Paiements
    path('commandes/<int:commande_pk>/paiement/',
         views.ajouter_paiement, name='ajouter_paiement'),

    # Lignes de commande
    path('commandes/<int:commande_pk>/lignes/ajouter/',
         views.ajouter_ligne, name='ajouter_ligne'),
    path('lignes/<int:pk>/supprimer/',
         views.supprimer_ligne, name='supprimer_ligne'),
    # Fiche atelier (bon de travail pour le couturier)
    path('commandes/<int:pk>/fiche-atelier/',
         views.fiche_atelier_pdf, name='fiche_atelier_pdf'),
    path('lignes/<int:pk>/fiche/',
         views.fiche_ligne_pdf, name='fiche_ligne_pdf'),
             # Stock
    path('stock/historique/', views.historique_stock, name='historique_stock'),
    path('stock/ajuster/', views.ajuster_stock, name='ajuster_stock'),
    # ==========================================
    # 7. API JSON
    # ==========================================
    path('api/clients/<int:client_pk>/mensurations/',
         views.api_mensurations_client, name='api_mensurations_client'),

    # ==========================================
    # 8. CATALOGUE MODÈLES & ACCESSOIRES
    # ==========================================
    path('modeles/', views.liste_modeles, name='liste_modeles'),
    path('modeles/ajouter/', views.ajouter_modele, name='ajouter_modele'),
    path('modeles/<int:pk>/modifier/', views.modifier_modele, name='modifier_modele'),
    path('modeles/<int:pk>/supprimer/', views.supprimer_modele, name='supprimer_modele'),

    path('accessoires/ajouter/', views.ajouter_accessoire, name='ajouter_accessoire'),
    path('accessoires/<int:pk>/modifier/', views.modifier_accessoire, name='modifier_accessoire'),
    path('accessoires/<int:pk>/supprimer/', views.supprimer_accessoire, name='supprimer_accessoire'),

    # ==========================================
    # 9. DÉPENSES / COMPTABILITÉ
    # ==========================================
    path('depenses/', views.liste_depenses, name='liste_depenses'),
    path('depenses/ajouter/', views.ajouter_depense, name='ajouter_depense'),
    path('depenses/<int:pk>/modifier/', views.modifier_depense, name='modifier_depense'),
    path('depenses/<int:pk>/supprimer/', views.supprimer_depense, name='supprimer_depense'),

    # ==========================================
    # 10. ÉQUIPE / UTILISATEURS
    # ==========================================
    path('utilisateurs/ajouter/',
         views.ajouter_utilisateur, name='ajouter_utilisateur'),
    path('utilisateurs/<int:user_id>/modifier/',
         views.modifier_utilisateur, name='modifier_utilisateur'),
    path('utilisateurs/<int:user_id>/supprimer/',
         views.supprimer_utilisateur, name='supprimer_utilisateur'),
    # ==========================================
    # 11. CALENDRIER & ABONNEMENT
    # ==========================================
    path('calendrier/', views.calendrier, name='calendrier'),
    path('abonnement/expire/', views.abonnement_expire, name='abonnement_expire'),


    path('ventes-directes/<int:pk>/annuler/', views.annuler_vente_directe, name='annuler_vente_directe'),
path('ventes-directes/<int:pk>/', views.detail_vente_directe, name='detail_vente_directe'),


    # ==========================================
    # EMPLOYÉS
    # ==========================================
    path('employes/', views.liste_employes, name='liste_employes'),
    path('employes/ajouter/', views.ajouter_employe, name='ajouter_employe'),
    path('employes/<int:pk>/', views.detail_employe, name='detail_employe'),
    path('employes/<int:pk>/modifier/', views.modifier_employe, name='modifier_employe'),
    path('employes/<int:pk>/supprimer/', views.supprimer_employe, name='supprimer_employe'),
    path('employes/<int:pk>/paie/', views.creer_paie, name='creer_paie'),
    path('api/employes/', views.api_employes, name='api_employes'),


        # Attribution d'une couture
    path('lignes/<int:pk>/attribuer/',
         views.attribuer_ligne, name='attribuer_ligne'),

    # Employés
   
    path('employes/plan-charge/', views.plan_charge, name='plan_charge'),
    path('employes/<int:pk>/', views.detail_employe, name='detail_employe'),
    
    # Stock
    path('stock/historique/', views.historique_stock, name='historique_stock'),
    path('stock/ajuster/', views.ajuster_stock, name='ajuster_stock'),
]

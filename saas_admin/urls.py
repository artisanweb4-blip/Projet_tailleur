from django.urls import path
from . import views

app_name = 'saas_admin'

urlpatterns = [
    # ==========================================
    # 1. TABLEAU DE BORD PRINCIPAL
    # ==========================================
    path('dashboard/', views.superadmin_dashboard, name='superadmin_dashboard'),

    # ==========================================
    # 2. GESTION DES BOUTIQUES
    # ==========================================
    path('boutiques/', views.superadmin_liste_boutiques, name='superadmin_liste_boutiques'),
    path('boutiques/ajouter/', views.ajouter_boutique, name='ajouter_boutique'),
    path('boutiques/<int:boutique_id>/', views.detail_boutique, name='detail_boutique'),
    path('boutiques/<int:boutique_id>/modifier/', views.modifier_boutique, name='modifier_boutique'),
    path('boutiques/<int:boutique_id>/changer-plan/', views.changer_plan_boutique, name='changer_plan_boutique'),
    path('boutiques/<int:boutique_id>/suspendre/', views.suspendre_boutique, name='suspendre_boutique'),
    path('boutiques/<int:boutique_id>/reactiver/', views.reactiver_boutique, name='reactiver_boutique'),
    path('boutiques/<int:boutique_id>/supprimer/', views.supprimer_boutique, name='supprimer_boutique'),

    # ==========================================
    # 3. ACTIONS DE SÉCURITÉ & IMPERSONNALISATION
    # ==========================================
    path('boutiques/<int:boutique_id>/reinitialiser-pass/', views.reinitialiser_pass_boutique, name='reinitialiser_pass_boutique'),
    path('boutiques/<int:boutique_id>/impersonner/', views.impersonner_boutique, name='impersonner_boutique'),

    # ==========================================
    # 4. GESTION DES FORMULES D'ABONNEMENT
    # ==========================================
    path('abonnements/', views.liste_abonnements, name='abonnements'),
    path('abonnements/ajouter/', views.ajouter_abonnement, name='ajouter_abonnement'),
    path('abonnements/<int:formule_id>/modifier/', views.modifier_abonnement, name='modifier_abonnement'),
    path('abonnements/<int:formule_id>/supprimer/', views.supprimer_abonnement, name='supprimer_abonnement'),

    # ==========================================
    # 5. GESTION EXCLUSIVE DES SUPER ADMINS & PARAMS
    # ==========================================
    path('utilisateurs/', views.superadmin_liste_utilisateurs, name='superadmin_liste_utilisateurs'),
    path('utilisateurs/ajouter/', views.ajouter_utilisateur, name='ajouter_utilisateur'),
    path('utilisateurs/<int:user_id>/modifier/', views.modifier_utilisateur, name='modifier_utilisateur'),
    path('utilisateurs/<int:user_id>/supprimer/', views.supprimer_utilisateur, name='supprimer_utilisateur'),
    path('utilisateurs/<int:user_id>/changer-statut/', views.changer_statut_utilisateur, name='changer_statut_utilisateur'),
    path('parametres/', views.superadmin_parametres, name='superadmin_parametres'),
]
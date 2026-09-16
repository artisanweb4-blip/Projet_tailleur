from django.urls import path
from . import views

urlpatterns = [
    path('', views.accueil, name='accueil'),
    # Les autres routes seront ajoutées plus tard
]

from django.urls import path
from . import views

urlpatterns = [
    path('', views.connexion, name='connexion'),  # et supprimez l'autre path('', ...) pour accueil
    path('accueil/', views.accueil, name='accueil'),
    path('clients/', views.recherche_clients, name='recherche_clients'),
    path('clients/ajouter/', views.ajouter_client, name='ajouter_client'),  
    path('clients/<int:client_id>/', views.detail_client, name='detail_client'),
    path('clients/<int:client_id>/modifier/', views.modifier_client, name='modifier_client'),   
    path('clients/<int:client_id>/supprimer/', views.supprimer_client, name='supprimer_client'),
    path('commandes/ajouter/', views.ajouter_commande, name='ajouter_commande'), 
    path('commandes/', views.liste_commandes, name='liste_commandes'),
    path('commandes/<int:commande_id>/', views.detail_commande, name='detail_commande'),
    path('commandes/<int:commande_id>/modifier/', views.modifier_commande, name='modifier_commande'),
    path('client/<int:client_id>/mensurations/ajouter/', views.ajouter_mensuration, name='ajouter_mensuration'),
    path('mensurations/<int:mensuration_id>/modifier/', views.modifier_mensuration, name='modifier_mensuration'),
    path('depenses/ajouter/', views.ajouter_depense, name='ajouter_depense'),
    path('depenses/', views.liste_depenses, name='liste_depenses'),
    path('mensurations/<int:mensuration_id>/', views.detail_mensuration, name='detail_mensuration'),
    path('mensurations/<int:mensuration_id>/supprimer/', views.supprimer_mensuration, name='supprimer_mensuration'),
    path('clients/<int:client_id>/data/', views.get_client_data, name='get_client_data'),
    path('commandes/<int:commande_id>/supprimer/', views.supprimer_commande, name='supprimer_commande'),
    path('depenses/<int:depense_id>/modifier/', views.modifier_depense, name='modifier_depense'),
    path('depenses/<int:depense_id>/supprimer/', views.supprimer_depense, name='supprimer_depense'),
    path('calendrier/', views.calendrier, name='calendrier'),
    path('connexion/', views.connexion, name='connexion'),
    path('inscription/', views.inscription, name='inscription'),
    path('deconnexion/', views.deconnexion, name='deconnexion'),
    path('profil/', views.mon_profil, name='mon_profil'),
    path('profil/modifier/', views.modifier_profil, name='modifier_profil'),
    path('profil/changer-mot-de-passe/', views.changer_mot_de_passe, name='changer_mot_de_passe'),

]
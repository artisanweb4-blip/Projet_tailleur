from django.contrib import admin
from .models import (
    Atelier,
    Profil,
    PlanAbonnement,
    Abonnement,
    Client,
    Mensuration,
    CatalogueModele,
    Commande,
    Paiement,
)


# ==================== GESTION SAAS & ATELIERS ====================

@admin.register(Atelier)
class AtelierAdmin(admin.ModelAdmin):
    list_display = ('nom', 'telephone', 'devise', 'est_actif', 'date_creation')
    search_fields = ('nom', 'email', 'telephone')
    prepopulated_fields = {'slug': ('nom',)}


@admin.register(Profil)
class ProfilAdmin(admin.ModelAdmin):
    list_display = ('user', 'atelier', 'role', 'telephone')
    list_filter = ('role', 'atelier')
    search_fields = ('user__username', 'user__first_name', 'user__last_name', 'user__email', 'atelier__nom')


@admin.register(PlanAbonnement)
class PlanAbonnementAdmin(admin.ModelAdmin):
    list_display = ('nom', 'prix_mensuel', 'max_commandes_mois', 'max_utilisateurs', 'support_prioritaire')
    search_fields = ('nom',)


@admin.register(Abonnement)
class AbonnementAdmin(admin.ModelAdmin):
    list_display = ('atelier', 'plan', 'statut', 'date_debut', 'date_fin', 'get_proprietaire')
    list_filter = ('statut', 'plan')
    search_fields = ('atelier__nom', 'atelier__membres__user__username')

    @admin.display(description='Propriétaire')
    def get_proprietaire(self, obj):
        proprio = obj.atelier.membres.filter(role='PROPRIETAIRE').first()
        return proprio.user.get_full_name() or proprio.user.username if proprio else "-"


# ==================== CLIENTS & MEASURES ====================

@admin.register(Client)
class ClientAdmin(admin.ModelAdmin):
    list_display = ('nom', 'prenom', 'telephone', 'genre', 'atelier', 'date_creation')
    list_filter = ('genre', 'atelier')
    search_fields = ('nom', 'prenom', 'telephone', 'email')


@admin.register(Mensuration)
class MensurationAdmin(admin.ModelAdmin):
    list_display = ('libelle', 'client', 'date_prise', 'atelier')
    list_filter = ('atelier',)
    search_fields = ('client__nom', 'client__prenom', 'libelle')


# ==================== COMMANDE & CATALOGUE ====================

@admin.register(CatalogueModele)
class CatalogueModeleAdmin(admin.ModelAdmin):
    list_display = ('nom', 'prix_base', 'atelier', 'date_creation')
    list_filter = ('atelier',)
    search_fields = ('nom', 'description')


@admin.register(Commande)
class CommandeAdmin(admin.ModelAdmin):
    list_display = (
        'code', 
        'client', 
        'statut', 
        'prix_total', 
        'montant_paye', 
        'reste_a_payer', 
        'date_livraison_prevue', 
        'atelier'
    )
    list_filter = ('statut', 'atelier', 'date_commande')
    search_fields = ('code', 'client__nom', 'client__prenom', 'description_vêtement')
    readonly_fields = ('code', 'date_commande', 'date_modification')


# ==================== PAIEMENTS ====================

@admin.register(Paiement)
class PaiementAdmin(admin.ModelAdmin):
    list_display = ('commande', 'montant', 'mode_paiement', 'reference_transaction', 'date_paiement', 'atelier')
    list_filter = ('mode_paiement', 'atelier', 'date_paiement')
    search_fields = ('commande__code', 'reference_transaction', 'commande__client__nom')
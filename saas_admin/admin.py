from django.contrib import admin
from django.contrib.auth import get_user_model
from django.contrib.auth.admin import UserAdmin as BaseUserAdmin
from django.utils.html import format_html
from .models import FormuleAbonnement, Boutique, Facture

User = get_user_model()

# Configuration sécurisée de l'admin Utilisateur
try:
    admin.site.unregister(User)
except admin.sites.NotRegistered:
    pass

@admin.register(User)
class CustomUserAdmin(BaseUserAdmin):
    search_fields = ('username', 'email', 'first_name', 'last_name')


@admin.register(FormuleAbonnement)
class FormuleAbonnementAdmin(admin.ModelAdmin):
    list_display = ('nom', 'prix_formatte', 'duree_mois', 'est_populaire')
    list_filter = ('est_populaire', 'duree_mois')
    search_fields = ('nom',)
    ordering = ('prix',)

    @admin.display(description="Prix (FCFA)")
    def prix_formatte(self, obj):
        return f"{obj.prix:,.0f} FCFA".replace(',', ' ')


class FactureInline(admin.TabularInline):
    """Permet de voir et ajouter des factures directement dans la fiche d'une boutique."""
    model = Facture
    extra = 0
    readonly_fields = ('date_paiement',)
    fields = ('montant', 'mode_paiement', 'est_paye', 'recu_pdf', 'date_paiement')


@admin.register(Boutique)
class BoutiqueAdmin(admin.ModelAdmin):
    list_display = (
        'nom_boutique', 
        'proprietaire', 
        'telephone', 
        'formule_abonnement', 
        'statut_badge', 
        'date_expiration_abonnement', 
        'date_creation'
    )
    list_filter = ('statut', 'formule_abonnement', 'date_creation')
    search_fields = ('nom_boutique', 'slug', 'proprietaire__username', 'proprietaire__email', 'email', 'telephone')
    prepopulated_fields = {'slug': ('nom_boutique',)}
    
    raw_id_fields = ['proprietaire']
    date_hierarchy = 'date_creation'
    inlines = [FactureInline]
    actions = ['passer_en_actif', 'passer_en_suspendu']

    @admin.display(description="Statut")
    def statut_badge(self, obj):
        colors = {
            'ACTIF': '#10b981',
            'ESSAI': '#f59e0b',
            'SUSPENDU': '#ef4444',
        }
        color = colors.get(obj.statut, '#6b7280')
        return format_html(
            '<span style="background-color: {}; color: #fff; padding: 3px 8px; border-radius: 12px; font-weight: bold; font-size: 11px;">{}</span>',
            color,
            obj.get_statut_display()
        )

    @admin.action(description="Marquer les boutiques sélectionnées comme ACTIVES")
    def passer_en_actif(self, request, queryset):
        count = queryset.update(statut='ACTIF')
        self.message_user(request, f"{count} boutique(s) marquée(s) comme active(s).")

    @admin.action(description="Marquer les boutiques sélectionnées comme SUSPENDUES")
    def passer_en_suspendu(self, request, queryset):
        count = queryset.update(statut='SUSPENDU')
        self.message_user(request, f"{count} boutique(s) suspendue(s).")


@admin.register(Facture)
class FactureAdmin(admin.ModelAdmin):
    list_display = ('id', 'boutique', 'montant_formatte', 'mode_paiement', 'est_paye', 'date_paiement')
    list_filter = ('est_paye', 'mode_paiement', 'date_paiement')
    search_fields = ('boutique__nom_boutique', 'mode_paiement')
    raw_id_fields = ['boutique']
    date_hierarchy = 'date_paiement'

    @admin.display(description="Montant")
    def montant_formatte(self, obj):
        return f"{obj.montant:,.0f} FCFA".replace(',', ' ')
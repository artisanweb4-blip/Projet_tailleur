from django.db import models
from django.conf import settings
from django.utils.text import slugify


class FormuleAbonnement(models.Model):
    nom = models.CharField(max_length=100)  # ex: Débutant, Atelier Pro, Grande Maison
    description = models.TextField(blank=True, null=True)
    prix = models.DecimalField(max_digits=10, decimal_places=0)  # Prix en FCFA
    duree_mois = models.PositiveIntegerField(
        default=1, 
        help_text="Durée en mois (ex: 1 pour mensuel, 12 pour annuel)"
    )
    
    # Champs pour la gestion de l'affichage dynamique dans les templates
    fonctionnalites_incluses = models.TextField(blank=True, null=True)
    fonctionnalites_exclues = models.TextField(blank=True, null=True)
    est_populaire = models.BooleanField(default=False)

    def __str__(self):
        return f"{self.nom} ({self.duree_mois} mois - {self.prix:,.0f} FCFA)".replace(',', ' ')

    def get_fonctionnalites_list(self):
        """Retourne la liste des fonctionnalités incluses séparées par ligne."""
        if self.fonctionnalites_incluses:
            return [f.strip() for f in self.fonctionnalites_incluses.splitlines() if f.strip()]
        return []

    def get_non_incluses_list(self):
        """Retourne la liste des fonctionnalités non incluses séparées par ligne."""
        if self.fonctionnalites_exclues:
            return [f.strip() for f in self.fonctionnalites_exclues.splitlines() if f.strip()]
        return []


class Boutique(models.Model):
    STATUT_CHOICES = [
        ('ESSAI', 'Période d\'essai'),
        ('ACTIF', 'Actif'),
        ('SUSPENDU', 'Suspendu'),
    ]

    nom_boutique = models.CharField(max_length=150)
    slug = models.SlugField(unique=True, blank=True)
    proprietaire = models.ForeignKey(
        settings.AUTH_USER_MODEL, 
        on_delete=models.CASCADE, 
        related_name='boutiques'
    )
    email = models.EmailField(blank=True, null=True)
    telephone = models.CharField(max_length=20, blank=True, null=True)
    
    statut = models.CharField(max_length=10, choices=STATUT_CHOICES, default='ESSAI')
    formule_abonnement = models.ForeignKey(
        FormuleAbonnement, 
        on_delete=models.SET_NULL, 
        null=True, 
        blank=True,
        related_name='boutiques'
    )
    date_expiration_abonnement = models.DateField(null=True, blank=True)
    date_creation = models.DateTimeField(auto_now_add=True)

    def save(self, *args, **kwargs):
        if not self.slug:
            self.slug = slugify(self.nom_boutique)
        super().save(*args, **kwargs)

    def __str__(self):
        return self.nom_boutique


class Facture(models.Model):
    boutique = models.ForeignKey(
        Boutique, 
        on_delete=models.CASCADE, 
        related_name='factures'
    )
    montant = models.DecimalField(max_digits=10, decimal_places=0)
    date_paiement = models.DateTimeField(auto_now_add=True)
    mode_paiement = models.CharField(max_length=50)  # ex: Wave, Orange Money, Carte
    est_paye = models.BooleanField(default=True)
    recu_pdf = models.FileField(upload_to='factures/', blank=True, null=True)

    def __str__(self):
        return f"Facture #{self.id} - {self.boutique.nom_boutique} ({self.montant} FCFA)"
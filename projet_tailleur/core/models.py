from django.db import models
from datetime import date  


class Client(models.Model):
    nom = models.CharField(max_length=100)
    email = models.EmailField(blank=True)
    telephone = models.CharField(max_length=20)
    adresse = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return self.nom


class Mensuration(models.Model):
    client = models.ForeignKey(Client, on_delete=models.CASCADE, related_name='mensurations')
    date = models.DateField(auto_now_add=True)
    
    # --- Mesures existantes (gardées pour compatibilité) ---
    tour_poitrine = models.DecimalField(max_digits=5, decimal_places=1, null=True, blank=True, verbose_name="Tour de poitrine (cm)")
    tour_taille = models.DecimalField(max_digits=5, decimal_places=1, null=True, blank=True, verbose_name="Tour de taille (cm)")
    tour_hanches = models.DecimalField(max_digits=5, decimal_places=1, null=True, blank=True, verbose_name="Tour de hanches (cm)")
    longueur_manche = models.DecimalField(max_digits=5, decimal_places=1, null=True, blank=True, verbose_name="Longueur manche (cm)")
    longueur_jambe = models.DecimalField(max_digits=5, decimal_places=1, null=True, blank=True, verbose_name="Longueur jambe (cm)")
    encolure = models.DecimalField(max_digits=5, decimal_places=1, null=True, blank=True, verbose_name="Encolure (cm)")

    # --- Mesures communes (ajoutées) ---
    epaule = models.DecimalField(max_digits=5, decimal_places=1, null=True, blank=True, verbose_name="Épaule (cm)")
    tour_manche = models.DecimalField(max_digits=5, decimal_places=1, null=True, blank=True, verbose_name="Tour de manche (cm)")

    # --- Mesures Femme ---
    longueur_taille = models.DecimalField(max_digits=5, decimal_places=1, null=True, blank=True, verbose_name="Longueur de taille (cm)")
    longueur_bassin = models.DecimalField(max_digits=5, decimal_places=1, null=True, blank=True, verbose_name="Longueur bassin (cm)")
    bassin = models.DecimalField(max_digits=5, decimal_places=1, null=True, blank=True, verbose_name="Bassin (cm)")
    longueur_genou = models.DecimalField(max_digits=5, decimal_places=1, null=True, blank=True, verbose_name="Longueur de genou (cm)")
    tour_genou = models.DecimalField(max_digits=5, decimal_places=1, null=True, blank=True, verbose_name="Tour de genou (cm)")
    longueur_camisole = models.DecimalField(max_digits=5, decimal_places=1, null=True, blank=True, verbose_name="Longueur camisole (cm)")
    longueur_jupe = models.DecimalField(max_digits=5, decimal_places=1, null=True, blank=True, verbose_name="Longueur jupe (cm)")
    longueur_robe = models.DecimalField(max_digits=5, decimal_places=1, null=True, blank=True, verbose_name="Longueur robe (cm)")
    longitude_haut = models.DecimalField(max_digits=5, decimal_places=1, null=True, blank=True, verbose_name="Longitude haut (cm)")

    # --- Mesures Homme (Boubou) ---
    epaule_homme = models.DecimalField(max_digits=5, decimal_places=1, null=True, blank=True, verbose_name="Épaules (cm) - Boubou")
    manche_boubou = models.DecimalField(max_digits=5, decimal_places=1, null=True, blank=True, verbose_name="Manches (cm)")
    tour_manche_homme = models.DecimalField(max_digits=5, decimal_places=1, null=True, blank=True, verbose_name="Tour de manche (cm)")
    coude = models.DecimalField(max_digits=5, decimal_places=1, null=True, blank=True, verbose_name="Coude (cm)")
    poitrine_homme = models.DecimalField(max_digits=5, decimal_places=1, null=True, blank=True, verbose_name="Poitrine (cm)")
    longueur_boubou = models.DecimalField(max_digits=5, decimal_places=1, null=True, blank=True, verbose_name="Longueur du boubou (cm)")
    poignet = models.DecimalField(max_digits=5, decimal_places=1, null=True, blank=True, verbose_name="Poignet (cm)")

    # --- Mesures Pantalon (Homme/Femme) ---
    tour_fesses = models.DecimalField(max_digits=5, decimal_places=1, null=True, blank=True, verbose_name="Tour de fesses (cm)")
    ceinture = models.DecimalField(max_digits=5, decimal_places=1, null=True, blank=True, verbose_name="Ceinture (cm)")
    cuisse = models.DecimalField(max_digits=5, decimal_places=1, null=True, blank=True, verbose_name="Cuisse (cm)")
    longueur_pantalon = models.DecimalField(max_digits=5, decimal_places=1, null=True, blank=True, verbose_name="Longueur du pantalon (cm)")
    ds = models.DecimalField(max_digits=5, decimal_places=1, null=True, blank=True, verbose_name="DS (cm)")
    bas_pantalon = models.DecimalField(max_digits=5, decimal_places=1, null=True, blank=True, verbose_name="Bas du pantalon (cm)")

    def __str__(self):
        return f"Mensurations de {self.client.nom} du {self.date.strftime('%d/%m/%Y')}"


class Tissu(models.Model):
    nom = models.CharField(max_length=100)
    reference = models.CharField(max_length=50)
    prix_metre = models.DecimalField(max_digits=8, decimal_places=2)

    def __str__(self):
        return self.nom


class Commande(models.Model):
    TYPES_VETEMENT = [
        ('costume', 'Costume'),
        ('chemise', 'Chemise'),
        ('robe', 'Robe'),
        ('pantalon', 'Pantalon'),
        ('veste', 'Veste'),
        ('autre', 'Autre'),
    ]
    STATUTS = [
        ('brouillon', 'Brouillon'),
        ('encours', 'En cours'),
        ('termine', 'Terminé'),
        ('livre', 'Livré'),
        ('attente', 'En attente'),
    ]
    client = models.ForeignKey(Client, on_delete=models.CASCADE)
    type_vetement = models.CharField(max_length=20, choices=TYPES_VETEMENT, default='autre')
    date_commande = models.DateField(auto_now_add=True)
    date_livraison_prevue = models.DateField(null=True, blank=True)
    description = models.TextField()
    tissu = models.ForeignKey(Tissu, on_delete=models.SET_NULL, null=True, blank=True)
    metrage = models.DecimalField(max_digits=5, decimal_places=2, default=0)
    prix_total = models.DecimalField(max_digits=8, decimal_places=2)
    montant_paye = models.DecimalField(max_digits=8, decimal_places=2, default=0)
    statut = models.CharField(max_length=20, choices=STATUTS, default='brouillon')

    @property
    def reste(self):
        return self.prix_total - self.montant_paye

    def __str__(self):
        return f"{self.client.nom} - {self.date_commande}"

    def est_en_retard(self):
        if self.date_livraison_prevue and self.statut not in ['termine', 'livre']:
            return self.date_livraison_prevue < date.today()
        return False


# ✅ UNIQUE classe Depense (avec catégories et date modifiable)
class Depense(models.Model):
    CATEGORIES = [
        ('fournitures', 'Fournitures'),
        ('equipement', 'Équipement'),
        ('loyer', 'Loyer'),
        ('salaire', 'Salaire'),  
        ('autre', 'Autre'),
    ]
    commande = models.ForeignKey(Commande, on_delete=models.CASCADE, null=True, blank=True)
    libelle = models.CharField(max_length=200)
    categorie = models.CharField(max_length=20, choices=CATEGORIES, default='autre')
    montant = models.DecimalField(max_digits=8, decimal_places=2)
    date = models.DateField(default=date.today)  # date de la dépense (modifiable)

    def __str__(self):
        return self.libelle
import uuid
from decimal import Decimal
from django.db import models
from django.conf import settings
from django.utils.text import slugify
from django.utils import timezone


# ==========================================
# 1. BASE MULTI-TENANT (ABSTRACT MODEL)
# ==========================================
class TenantAwareModel(models.Model):
    atelier = models.ForeignKey(
        'Atelier',
        on_delete=models.CASCADE,
        related_name="%(class)ss"
    )
    date_creation = models.DateTimeField(auto_now_add=True)
    date_modification = models.DateTimeField(auto_now=True)

    class Meta:
        abstract = True


# ==========================================
# 2. GESTION DES TENANTS & UTILISATEURS
# ==========================================
class Atelier(models.Model):
    DEVISES = [
        ('FCFA', 'Franc CFA (FCFA)'),
        ('EUR', 'Euro (€)'),
        ('USD', 'Dollar ($)'),
        ('GNF', 'Franc Guinéen (GNF)'),
        ('MAD', 'Dirham Marocain (MAD)'),
        ('XOF', 'Franc CFA Ouest (XOF)'),
    ]

    nom = models.CharField(max_length=150)
    slug = models.SlugField(max_length=160, unique=True, blank=True)
    adresse = models.TextField(blank=True, null=True)
    telephone = models.CharField(max_length=20, blank=True, null=True)
    email = models.EmailField(blank=True, null=True)
    logo = models.ImageField(upload_to='ateliers/logos/', blank=True, null=True)
    devise = models.CharField(max_length=10, choices=DEVISES, default='FCFA')
    seuil_stock_faible = models.PositiveIntegerField(
        default=5,
        help_text="Seuil d'alerte pour le stock des articles et accessoires"
    )
    est_actif = models.BooleanField(default=True)
    date_creation = models.DateTimeField(auto_now_add=True)

    def save(self, *args, **kwargs):
        if not self.slug:
            base_slug = slugify(self.nom) or "atelier"
            slug = base_slug
            count = 1
            while Atelier.objects.filter(slug=slug).exclude(pk=self.pk).exists():
                slug = f"{base_slug}-{count}"
                count += 1
            self.slug = slug
        super().save(*args, **kwargs)

    def __str__(self):
        return self.nom


class Profil(models.Model):
    ROLES = (
        ('ADMIN', 'Administrateur (Propriétaire)'),
        ('GESTIONNAIRE', "Gestionnaire de l'atelier"),
        ('COMPTABLE', 'Comptable'),
    )

    DESCRIPTIONS_ROLES = {
        'ADMIN': "Accès complet : paramètres, utilisateurs, employés, "
                 "catalogue, commandes et comptabilité.",
        'GESTIONNAIRE': "Clients, mensurations, commandes, ventes directes "
                        "et suivi des livraisons. Pas d'accès à la comptabilité "
                        "ni aux paramètres.",
        'COMPTABLE': "Dépenses, paiements, factures, reçus et rapports "
                     "financiers. Consultation seule des commandes.",
    }

    ICONES_ROLES = {
        'ADMIN': 'bi-shield-check',
        'GESTIONNAIRE': 'bi-briefcase',
        'COMPTABLE': 'bi-calculator',
    }

    COULEURS_ROLES = {
        'ADMIN': ('#f5f3ff', '#6d28d9', '#ddd6fe'),
        'GESTIONNAIRE': ('#eff6ff', '#0284c7', '#bae6fd'),
        'COMPTABLE': ('#ecfdf5', '#059669', '#a7f3d0'),
    }

    user = models.OneToOneField(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='profil'
    )
    atelier = models.ForeignKey(
        Atelier,
        on_delete=models.CASCADE,
        related_name='membres',
        null=True,
        blank=True
    )
    role = models.CharField(max_length=20, choices=ROLES, default='GESTIONNAIRE')
    telephone = models.CharField(max_length=20, blank=True, null=True)
    photo = models.ImageField(upload_to='profils/', blank=True, null=True)

    # --- Traçabilité ---
    est_fondateur = models.BooleanField(
        default=False,
        help_text="Compte créé à l'inscription. Masqué dans la liste."
    )
    cree_par = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True, blank=True,
        related_name='comptes_crees'
    )
    actif = models.BooleanField(default=True)
    date_creation = models.DateTimeField(auto_now_add=True, null=True)

    class Meta:
        ordering = ['-est_fondateur', 'role', 'user__first_name']

    # ---------- Identité ----------

    @property
    def nom_affiche(self):
        return self.user.get_full_name() or self.user.username

    @property
    def initiales(self):
        u = self.user
        if u.first_name or u.last_name:
            return ((u.first_name[:1] or '') + (u.last_name[:1] or '')).upper()
        return u.username[:2].upper()

    @property
    def description_role(self):
        return self.DESCRIPTIONS_ROLES.get(self.role, "Accès limité.")

    @property
    def icone_role(self):
        return self.ICONES_ROLES.get(self.role, 'bi-person')

    @property
    def style_role(self):
        bg, fg, bd = self.COULEURS_ROLES.get(
            self.role, ('#f3f4f6', '#6b7280', '#e5e7eb'))
        return f"background:{bg}; color:{fg}; border:1px solid {bd};"

    # ---------- Permissions ----------

    @property
    def est_admin(self):
        return self.role == 'ADMIN'

    @property
    def est_gestionnaire(self):
        return self.role == 'GESTIONNAIRE'

    @property
    def est_comptable(self):
        return self.role == 'COMPTABLE'

    # --- Administration ---
    @property
    def peut_gerer_utilisateurs(self):
        return self.est_admin

    @property
    def peut_modifier_parametres(self):
        return self.est_admin

    @property
    def peut_gerer_employes(self):
        return self.est_admin

    @property
    def peut_gerer_catalogue(self):
        return self.est_admin

    # --- Production ---
    @property
    def peut_gerer_clients(self):
        return self.role in ('ADMIN', 'GESTIONNAIRE')

    @property
    def peut_creer_commande(self):
        return self.role in ('ADMIN', 'GESTIONNAIRE')

    @property
    def peut_vendre(self):
        return self.role in ('ADMIN', 'GESTIONNAIRE')

    @property
    def peut_voir_commandes(self):
        return True   # Les trois rôles consultent

    # --- Finance ---
    @property
    def peut_voir_comptabilite(self):
        return self.role in ('ADMIN', 'COMPTABLE')

    @property
    def peut_gerer_depenses(self):
        return self.role in ('ADMIN', 'COMPTABLE')

    @property
    def peut_encaisser(self):
        return True   # Tout le monde peut enregistrer un paiement

    @property
    def peut_verser_salaires(self):
        return self.role in ('ADMIN', 'COMPTABLE')

    def __str__(self):
        return f"{self.nom_affiche} ({self.get_role_display()})"

# ==========================================
# 3. ABONNEMENTS SAAS
# ==========================================
class PlanAbonnement(models.Model):
    nom = models.CharField(max_length=50)
    prix_mensuel = models.DecimalField(max_digits=10, decimal_places=2)
    max_commandes_mois = models.PositiveIntegerField(default=50)
    max_utilisateurs = models.PositiveIntegerField(default=3)
    support_prioritaire = models.BooleanField(default=False)

    def __str__(self):
        return f"{self.nom} - {self.prix_mensuel}"


class Abonnement(models.Model):
    STATUTS = (
        ('ACTIF', 'Actif'),
        ('EXPIRE', 'Expiré'),
        ('SUSPENDU', 'Suspendu'),
    )

    atelier = models.OneToOneField(
        Atelier, on_delete=models.CASCADE, related_name='abonnement'
    )
    plan = models.ForeignKey(PlanAbonnement, on_delete=models.SET_NULL, null=True)
    statut = models.CharField(max_length=20, choices=STATUTS, default='ACTIF')
    date_debut = models.DateField(auto_now_add=True)
    date_fin = models.DateField()

    def __str__(self):
        plan_nom = self.plan.nom if self.plan else 'Aucun plan'
        return f"{self.atelier.nom} - {plan_nom} ({self.statut})"


# ==========================================
# 4. CLIENTS & MENSURATIONS
# ==========================================
class Client(TenantAwareModel):
    GENRE_CHOICES = (
        ('M', 'Masculin'),
        ('F', 'Féminin'),
    )

    ORIGINE_CHOICES = (
        ('recommandation', 'Recommandation'),
        ('boutique', 'Passant / Boutique'),
        ('publicite', 'Publicité'),
        ('bouche_a_oreille', 'Bouche à oreille'),
        ('reseaux_sociaux', 'Réseaux sociaux'),
        ('autre', 'Autre'),
    )

    nom = models.CharField(max_length=100)
    prenom = models.CharField(max_length=100, blank=True)
    genre = models.CharField(max_length=1, choices=GENRE_CHOICES, default='F')
    telephone = models.CharField(max_length=20)
    email = models.EmailField(blank=True, null=True)
    adresse = models.TextField(blank=True, null=True)
    notes = models.TextField(
        blank=True, null=True,
        help_text="Préférences, allergies textiles, etc."
    )
    origine = models.CharField(
        max_length=30, choices=ORIGINE_CHOICES,
        blank=True, null=True,
        verbose_name="Canal d'acquisition"
    )

    class Meta:
        ordering = ['nom', 'prenom']

    @property
    def nom_complet(self):
        return f"{self.nom} {self.prenom}".strip()

    def __str__(self):
        return self.nom_complet


class Mensuration(TenantAwareModel):
    """
    Fiche de mesures dynamique stockée en JSON.
    Peut concerner le client lui-même ou un proche (famille, ami).
    """
    LIENS = (
        ('MOI', 'Le client lui-même'),
        ('EPOUX', 'Époux / Épouse'),
        ('ENFANT', 'Enfant'),
        ('PARENT', 'Parent'),
        ('FRERE_SOEUR', 'Frère / Sœur'),
        ('AMI', 'Ami(e)'),
        ('AUTRE', 'Autre'),
    )

    GENRES_MESURE = (
        ('homme', 'Homme'),
        ('femme', 'Femme'),
    )

    client = models.ForeignKey(
        Client, on_delete=models.CASCADE, related_name='mensurations'
    )
    beneficiaire = models.CharField(
        max_length=150, blank=True,
        help_text="Nom de la personne mesurée. Vide = le client lui-même."
    )
    lien_parente = models.CharField(
        max_length=20, choices=LIENS, default='MOI',
        help_text="Lien entre le client et la personne mesurée"
    )
    genre_mesure = models.CharField(
        max_length=10, choices=GENRES_MESURE, default='homme'
    )
    libelle = models.CharField(
        max_length=100, default="Mesures Standard",
        help_text="Ex: Boubou, Costume, Robe de mariée"
    )
    donnees = models.JSONField(
        default=dict,
        help_text="Paires clé/valeur des mesures en cm"
    )
    date_prise = models.DateField(auto_now_add=True)

    class Meta:
        ordering = ['-date_prise']

    @property
    def nom_personne(self):
        """Nom affiché de la personne mesurée."""
        return self.beneficiaire.strip() or str(self.client)

    @property
    def est_pour_client(self):
        return not self.beneficiaire.strip()

    @property
    def libelle_complet(self):
        """Ex: 'Fatou Diop (Enfant) — Costume'."""
        if self.est_pour_client:
            return f"{self.nom_personne} — {self.libelle}"
        return (
            f"{self.nom_personne} "
            f"({self.get_lien_parente_display()}) — {self.libelle}"
        )

    @property
    def nb_mesures(self):
        return len(self.donnees or {})

    def __str__(self):
        return self.libelle_complet


# ==========================================
# 5. CATALOGUE & ACCESSOIRES
# ==========================================
class CatalogueModele(TenantAwareModel):
    """
    Modèles de vêtements proposés par l'atelier.
    Couture sur mesure (sans stock) OU prêt-à-porter (avec stock).
    """
    TYPE_MODELE = (
        ('COUTURE', 'Couture sur mesure'),
        ('PRET_A_PORTER', 'Prêt-à-porter'),
    )

    nom = models.CharField(max_length=150)
    type_modele = models.CharField(
        max_length=20, choices=TYPE_MODELE, default='COUTURE'
    )
    description = models.TextField(blank=True, null=True)
    prix_base = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    photo = models.ImageField(upload_to='catalogue/', blank=True, null=True)

    # Champs spécifiques prêt-à-porter
    taille_disponible = models.CharField(
        max_length=100, blank=True, null=True,
        help_text="Ex: S, M, L, XL ou 38, 40, 42"
    )
    couleur = models.CharField(max_length=100, blank=True, null=True)
    stock_pret_a_porter = models.PositiveIntegerField(
        default=0,
        help_text="Stock disponible pour le prêt-à-porter"
    )
    seuil_alerte = models.PositiveIntegerField(
        default=3,
        help_text="Seuil en dessous duquel le stock est signalé comme faible"
    )

    class Meta:
        ordering = ['type_modele', 'nom']

    # ---------- Affichage ----------

    @property
    def prix_int(self):
        """Prix sans décimale, pour les attributs HTML (data-*, value)."""
        return int(self.prix_base)

    @property
    def est_pap(self):
        return self.type_modele == 'PRET_A_PORTER'

    # ---------- Stock ----------

    @property
    def gere_stock(self):
        """Seul le prêt-à-porter est suivi en stock."""
        return self.est_pap

    @property
    def stock_epuise(self):
        return self.gere_stock and self.stock_pret_a_porter <= 0

    @property
    def stock_faible(self):
        return (
            self.gere_stock
            and 0 < self.stock_pret_a_porter <= self.seuil_alerte
        )

    @property
    def statut_stock(self):
        """Retourne 'NA', 'RUPTURE', 'FAIBLE' ou 'OK'."""
        if not self.gere_stock:
            return 'NA'
        if self.stock_pret_a_porter <= 0:
            return 'RUPTURE'
        if self.stock_pret_a_porter <= self.seuil_alerte:
            return 'FAIBLE'
        return 'OK'

    @property
    def valeur_stock(self):
        """Valeur monétaire du stock immobilisé."""
        if not self.gere_stock:
            return Decimal('0')
        return self.prix_base * self.stock_pret_a_porter

    def stock_suffisant(self, quantite):
        """True si la quantité demandée est disponible."""
        if not self.gere_stock:
            return True
        return self.stock_pret_a_porter >= quantite

    def retirer_stock(self, quantite):
        """Décrémente le stock (vente). Retourne le stock restant."""
        if not self.gere_stock:
            return None
        self.stock_pret_a_porter = max(0, self.stock_pret_a_porter - quantite)
        self.save(update_fields=['stock_pret_a_porter', 'date_modification'])
        return self.stock_pret_a_porter

    def remettre_stock(self, quantite):
        """Incrémente le stock (annulation / retour)."""
        if not self.gere_stock:
            return None
        self.stock_pret_a_porter += quantite
        self.save(update_fields=['stock_pret_a_porter', 'date_modification'])
        return self.stock_pret_a_porter

    def __str__(self):
        return f"{self.nom} ({self.get_type_modele_display()})"


class Accessoire(TenantAwareModel):
    """
    Accessoires de couture et articles vendus à l'unité.
    """
    CATEGORIES = (
        ('BOUTON', 'Boutons'),
        ('FERMETURE', 'Fermetures / Zips'),
        ('BRODERIE', 'Broderies / Dentelles'),
        ('DOUBLURE', 'Doublures / Entoilages'),
        ('FIL', 'Fils spéciaux'),
        ('ELASTIQUE', 'Élastiques / Rubans'),
        ('CHAUSSURE', 'Chaussures'),
        ('FOULARD', 'Foulards / Voiles'),
        ('BIJOU', 'Bijoux / Ornements'),
        ('AUTRE', 'Autre'),
    )
    UNITES = (
        ('PIECE', 'Pièce'),
        ('METRE', 'Mètre'),
        ('LOT', 'Lot'),
        ('KG', 'Kilogramme'),
        ('PAIRE', 'Paire'),
    )

    nom = models.CharField(max_length=150)
    categorie = models.CharField(max_length=20, choices=CATEGORIES, default='AUTRE')
    description = models.TextField(blank=True, null=True)
    prix_unitaire = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    unite = models.CharField(max_length=10, choices=UNITES, default='PIECE')
    stock_disponible = models.PositiveIntegerField(default=0)
    seuil_alerte = models.PositiveIntegerField(
        default=5,
        help_text="Seuil en dessous duquel le stock est signalé comme faible"
    )
    photo = models.ImageField(upload_to='accessoires/', blank=True, null=True)

    class Meta:
        ordering = ['categorie', 'nom']

    # ---------- Affichage ----------

    @property
    def prix_int(self):
        return int(self.prix_unitaire)

    # ---------- Stock ----------

    @property
    def stock_epuise(self):
        return self.stock_disponible <= 0

    @property
    def stock_faible(self):
        return 0 < self.stock_disponible <= self.seuil_alerte

    @property
    def statut_stock(self):
        if self.stock_disponible <= 0:
            return 'RUPTURE'
        if self.stock_disponible <= self.seuil_alerte:
            return 'FAIBLE'
        return 'OK'

    @property
    def valeur_stock(self):
        return self.prix_unitaire * self.stock_disponible

    def stock_suffisant(self, quantite):
        return self.stock_disponible >= quantite

    def retirer_stock(self, quantite):
        self.stock_disponible = max(0, self.stock_disponible - quantite)
        self.save(update_fields=['stock_disponible', 'date_modification'])
        return self.stock_disponible

    def remettre_stock(self, quantite):
        self.stock_disponible += quantite
        self.save(update_fields=['stock_disponible', 'date_modification'])
        return self.stock_disponible

    def __str__(self):
        return f"{self.nom} ({self.get_categorie_display()})"


# ==========================================
# 6. COMMANDES
# ==========================================
class Commande(TenantAwareModel):
    """
    Commande principale — regroupe plusieurs lignes (coutures, achats, accessoires).
    Le prix_total est calculé automatiquement depuis les lignes.
    """
    STATUTS = (
        ('EN_ATTENTE', 'En attente'),
        ('EN_COURS', 'En cours de confection'),
        ('PRET', 'Prêt à essayer / livrer'),
        ('LIVRE', 'Livré'),
        ('ANNULE', 'Annulé'),
    )

    REMISE_TYPES = (
        ('MONTANT', 'Montant fixe'),
        ('POURCENTAGE', 'Pourcentage'),
    )

    code = models.CharField(
        max_length=50, unique=True,
        default=uuid.uuid4,
        null=True, blank=True,
        editable=False
    )

    # Client principal
    client = models.ForeignKey(
        Client, on_delete=models.CASCADE, related_name='commandes'
    )

    # Attribution globale
    couturier_attribue = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True, blank=True,
        related_name='commandes_attribuees',
        help_text="Compte utilisateur (ancien système, conservé)"
    )
    employe_attribue = models.ForeignKey(
        'Employe', on_delete=models.SET_NULL,
        null=True, blank=True,
        related_name='commandes_employe',
        help_text="Employé responsable de toute la commande"
    )

    # Remise globale sur la commande entière
    remise_type = models.CharField(
        max_length=15, choices=REMISE_TYPES,
        blank=True, null=True
    )
    remise_valeur = models.DecimalField(
        max_digits=10, decimal_places=2, default=0
    )

    # Notes globales
    notes = models.TextField(blank=True, null=True)

    # Suivi
    statut = models.CharField(max_length=20, choices=STATUTS, default='EN_ATTENTE')
    date_commande = models.DateField(auto_now_add=True)
    date_livraison_prevue = models.DateField()
    date_livraison_effective = models.DateField(null=True, blank=True)

    # Gestion de stock (ventes directes)
    stock_decremente = models.BooleanField(
        default=False,
        help_text="Le stock a déjà été retiré pour cette commande."
    )

    class Meta:
        ordering = ['-date_commande', '-id']

    def save(self, *args, **kwargs):
        if not self.code or len(str(self.code)) > 20:
            self.code = f"CMD-{uuid.uuid4().hex[:6].upper()}"
        super().save(*args, **kwargs)

    # ---------- Montants ----------

    @property
    def prix_total(self):
        """Somme des prix nets de toutes les lignes (accessoires liés inclus)."""
        return sum((l.prix_net for l in self.lignes.all()), Decimal('0'))

    @property
    def prix_net(self):
        """Prix total après remise globale."""
        total = self.prix_total
        if self.remise_type == 'MONTANT':
            return max(Decimal('0'), total - self.remise_valeur)
        if self.remise_type == 'POURCENTAGE':
            return max(
                Decimal('0'),
                total * (1 - self.remise_valeur / Decimal('100'))
            )
        return total

    @property
    def montant_remise(self):
        """Montant réel de la remise globale appliquée."""
        return self.prix_total - self.prix_net

    @property
    def montant_paye(self):
        """Somme de tous les paiements enregistrés."""
        return sum((p.montant for p in self.paiements.all()), Decimal('0'))

    @property
    def reste_a_payer(self):
        """Solde restant dû."""
        return max(Decimal('0'), self.prix_net - self.montant_paye)

    @property
    def est_soldee(self):
        return self.reste_a_payer == 0

    @property
    def pct_paye(self):
        """Pourcentage encaissé (entier 0-100), pour les barres de progression."""
        net = self.prix_net
        if net <= 0:
            return 100 if self.montant_paye > 0 else 0
        return int(min(100, self.montant_paye * 100 / net))

    # ---------- Contenu ----------

    @property
    def nb_lignes(self):
        return self.lignes.count()

    @property
    def lignes_couture(self):
        return self.lignes.filter(type_ligne='COUTURE')

    @property
    def est_vente_directe(self):
        """
        Une vente directe est une commande sans aucune ligne de couture sur mesure
        (uniquement prêt-à-porter et/ou accessoires).
        """
        if not self.lignes.exists():
            return False
        return not self.lignes.filter(type_ligne='COUTURE').exists()

    @property
    def est_annulee(self):
        return self.statut == 'ANNULE'

    # ---------- Attribution du travail ----------

    @property
    def employes_impliques(self):
        """Liste sans doublon des employés travaillant sur cette commande."""
        vus = {}
        for ligne in self.lignes.select_related('employe'):
            if ligne.employe_id and ligne.employe_id not in vus:
                vus[ligne.employe_id] = ligne.employe
        return list(vus.values())

    @property
    def nb_lignes_attribuees(self):
        return self.lignes.filter(employe__isnull=False).count()

    @property
    def nb_lignes_non_attribuees(self):
        return self.lignes.filter(
            type_ligne='COUTURE', employe__isnull=True).count()

    @property
    def toutes_attribuees(self):
        """True si chaque couture a un employé assigné."""
        coutures = self.lignes.filter(type_ligne='COUTURE')
        if not coutures.exists():
            return True
        return not coutures.filter(employe__isnull=True).exists()

    @property
    def pct_avancement(self):
        """Pourcentage de coutures terminées (0-100)."""
        coutures = self.lignes.filter(type_ligne='COUTURE')
        total = coutures.count()
        if total == 0:
            return 100 if self.statut == 'LIVRE' else 0
        faites = coutures.filter(etat_travail='TERMINE').count()
        return int(faites * 100 / total)

    @property
    def total_commissions(self):
        """Somme des commissions dues aux employés pour cette commande."""
        return sum(
            (l.commission_due for l in self.lignes.select_related('employe')),
            Decimal('0')
        )

    @property
    def marge_apres_commissions(self):
        """Prix net encaissé moins les commissions à verser."""
        return self.prix_net - self.total_commissions

    # ---------- Stock ----------

    def besoins_stock(self):
        """
        Quantités à mouvementer pour cette commande.
        Retourne {('PAP', id): qte, ('ACC', id): qte}
        Seules les lignes prêt-à-porter et accessoire direct sont concernées.
        """
        besoins = {}
        for ligne in self.lignes.all():
            cle = ligne.cle_stock
            if cle:
                besoins[cle] = besoins.get(cle, 0) + ligne.quantite
        return besoins

    def articles_stock_critique(self):
        """
        Liste des articles de la commande dont le stock est bas après la vente.
        Retourne [(nom, stock_restant, statut), ...]
        """
        resultats = []
        for ligne in self.lignes.all():
            obj = ligne.article_stockable
            if not obj:
                continue
            statut = obj.statut_stock
            if statut in ('RUPTURE', 'FAIBLE'):
                reste = (
                    obj.stock_pret_a_porter
                    if isinstance(obj, CatalogueModele)
                    else obj.stock_disponible
                )
                resultats.append((obj.nom, reste, statut))
        return resultats

    # ---------- Suivi ----------

    def est_en_retard(self):
        if self.statut in ['EN_ATTENTE', 'EN_COURS', 'PRET']:
            return self.date_livraison_prevue < timezone.now().date()
        return False

    @property
    def jours_restants(self):
        """Négatif si en retard, 0 si aujourd'hui."""
        return (self.date_livraison_prevue - timezone.now().date()).days

    def __str__(self):
        return f"{self.code} - {self.client}"

# ==========================================
# 7. LIGNES DE COMMANDE
# ==========================================
class LigneCommande(TenantAwareModel):
    """
    Une ligne = un article dans la commande.
    Types : couture sur mesure, prêt-à-porter, accessoire direct.
    """
    TYPE_LIGNE = (
        ('COUTURE', 'Couture sur mesure'),
        ('PRET_A_PORTER', 'Prêt-à-porter'),
        ('ACCESSOIRE', 'Accessoire / Article'),
    )

    REMISE_TYPES = (
        ('MONTANT', 'Montant fixe'),
        ('POURCENTAGE', 'Pourcentage'),
    )

    ETATS_TRAVAIL = (
        ('A_FAIRE', 'À faire'),
        ('EN_COURS', 'En cours'),
        ('TERMINE', 'Terminé'),
    )

    commande = models.ForeignKey(
        Commande, on_delete=models.CASCADE, related_name='lignes'
    )
    type_ligne = models.CharField(
        max_length=20, choices=TYPE_LIGNE, default='COUTURE'
    )
    ordre = models.PositiveSmallIntegerField(default=1)

    # --- Couture sur mesure ---
    modele = models.ForeignKey(
        CatalogueModele, on_delete=models.SET_NULL,
        null=True, blank=True, related_name='lignes_commande'
    )
    description = models.TextField(
        blank=True, null=True,
        help_text="Détails spécifiques à cette couture"
    )
    client_secondaire = models.ForeignKey(
        Client, on_delete=models.SET_NULL,
        null=True, blank=True,
        related_name='lignes_secondaires',
        help_text="Si cette couture est pour un autre client"
    )
    mensuration = models.ForeignKey(
        Mensuration, on_delete=models.SET_NULL,
        null=True, blank=True, related_name='lignes_commande'
    )

    # --- Attribution du travail ---
    couturier = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True, blank=True,
        related_name='lignes_attribuees',
        help_text="Compte utilisateur (ancien système, conservé)"
    )
    employe = models.ForeignKey(
        'Employe', on_delete=models.SET_NULL,
        null=True, blank=True,
        related_name='lignes_travail',
        help_text="Employé de l'atelier chargé de cette couture"
    )
    etat_travail = models.CharField(
        max_length=15, choices=ETATS_TRAVAIL, default='A_FAIRE',
        help_text="Avancement de cette pièce"
    )
    date_debut_travail = models.DateField(null=True, blank=True)
    date_fin_travail = models.DateField(null=True, blank=True)
    commission_versee = models.BooleanField(
        default=False,
        help_text="La commission de cette pièce a déjà été payée"
    )

    photo_tissu = models.ImageField(
        upload_to='commandes/tissus/', blank=True, null=True
    )
    photo_modele_custom = models.ImageField(
        upload_to='commandes/modeles/', blank=True, null=True
    )

    # --- Prêt-à-porter & Accessoire direct (ventes directes) ---
    accessoire = models.ForeignKey(
        Accessoire, on_delete=models.SET_NULL,
        null=True, blank=True, related_name='lignes_commande'
    )

    # --- Financier commun ---
    quantite = models.PositiveIntegerField(default=1)
    prix_unitaire = models.DecimalField(
        max_digits=10, decimal_places=2, default=0
    )
    remise_type = models.CharField(
        max_length=15, choices=REMISE_TYPES,
        blank=True, null=True
    )
    remise_valeur = models.DecimalField(
        max_digits=10, decimal_places=2, default=0
    )

    class Meta:
        ordering = ['ordre', 'date_creation']

    # ---------- Libellés ----------

    @property
    def libelle(self):
        if self.type_ligne == 'COUTURE':
            return self.modele.nom if self.modele else "Couture sur mesure"
        if self.type_ligne == 'PRET_A_PORTER':
            return self.modele.nom if self.modele else "Prêt-à-porter"
        if self.type_ligne == 'ACCESSOIRE':
            return self.accessoire.nom if self.accessoire else "Accessoire"
        return "Article"

    @property
    def destinataire(self):
        """Client final de cette ligne (secondaire si renseigné)."""
        return self.client_secondaire or self.commande.client

    @property
    def personne_mesuree(self):
        """Nom de la personne dont on utilise les mensurations."""
        if self.mensuration:
            return self.mensuration.nom_personne
        return str(self.destinataire)

    # ---------- Attribution ----------

    @property
    def est_attribuee(self):
        return self.employe_id is not None

    @property
    def nom_employe(self):
        return self.employe.nom_complet if self.employe else "Non attribuée"

    @property
    def commission_due(self):
        """Commission de l'employé pour cette pièce."""
        if not self.employe:
            return Decimal('0')
        return self.employe.commission_pour_ligne(self)

    @property
    def est_terminee(self):
        return self.etat_travail == 'TERMINE'

    # ---------- Stock ----------

    @property
    def article_stockable(self):
        """
        Objet dont le stock est impacté par cette ligne.
        None pour une couture sur mesure.
        """
        if self.type_ligne == 'PRET_A_PORTER' and self.modele_id:
            return self.modele
        if self.type_ligne == 'ACCESSOIRE' and self.accessoire_id:
            return self.accessoire
        return None

    @property
    def cle_stock(self):
        """Clé normalisée pour agréger les besoins : ('PAP'|'ACC', id) ou None."""
        if self.type_ligne == 'PRET_A_PORTER' and self.modele_id:
            return ('PAP', self.modele_id)
        if self.type_ligne == 'ACCESSOIRE' and self.accessoire_id:
            return ('ACC', self.accessoire_id)
        return None

    @property
    def impacte_stock(self):
        return self.cle_stock is not None

    # ---------- Calculs ----------

    @property
    def sous_total_brut(self):
        """Prix de l'article avant remise, hors accessoires liés."""
        return self.prix_unitaire * self.quantite

    @property
    def total_accessoires(self):
        """Somme des accessoires rattachés à cette ligne de couture."""
        return sum(
            (a.sous_total for a in self.accessoires_ligne.all()),
            Decimal('0')
        )

    @property
    def prix_apres_remise(self):
        """Prix de l'article après remise de ligne (hors accessoires)."""
        base = self.sous_total_brut
        if self.remise_type == 'MONTANT':
            return max(Decimal('0'), base - self.remise_valeur)
        if self.remise_type == 'POURCENTAGE':
            return max(
                Decimal('0'),
                base * (1 - self.remise_valeur / Decimal('100'))
            )
        return base

    @property
    def prix_net(self):
        """Total de la ligne : article remisé + accessoires liés."""
        return self.prix_apres_remise + self.total_accessoires

    @property
    def montant_remise(self):
        """Montant réel de la remise appliquée à cette ligne."""
        return self.sous_total_brut - self.prix_apres_remise

    def __str__(self):
        return f"Ligne {self.ordre} — {self.libelle} ({self.commande.code})"

    @property
    def prix_apres_remise(self):
        """Prix de l'article après remise de ligne (hors accessoires)."""
        base = self.sous_total_brut
        if self.remise_type == 'MONTANT':
            return max(Decimal('0'), base - self.remise_valeur)
        if self.remise_type == 'POURCENTAGE':
            return max(
                Decimal('0'),
                base * (1 - self.remise_valeur / Decimal('100'))
            )
        return base

    @property
    def prix_net(self):
        """Total de la ligne : article remisé + accessoires liés."""
        return self.prix_apres_remise + self.total_accessoires

    @property
    def montant_remise(self):
        """Montant réel de la remise appliquée à cette ligne."""
        return self.sous_total_brut - self.prix_apres_remise

    def __str__(self):
        return f"Ligne {self.ordre} — {self.libelle} ({self.commande.code})"


class LigneAccessoire(TenantAwareModel):
    """
    Accessoires liés à une ligne de couture spécifique.
    Ex: 6 boutons dorés + 1 fermeture éclair pour un boubou.
    """
    ligne = models.ForeignKey(
        LigneCommande, on_delete=models.CASCADE,
        related_name='accessoires_ligne'
    )
    accessoire = models.ForeignKey(
        Accessoire, on_delete=models.CASCADE,
        related_name='utilisations'
    )
    quantite = models.PositiveIntegerField(default=1)
    prix_unitaire = models.DecimalField(
        max_digits=10, decimal_places=2, default=0
    )

    @property
    def sous_total(self):
        return self.prix_unitaire * self.quantite

    def __str__(self):
        return f"{self.accessoire.nom} x{self.quantite} — {self.ligne}"


# ==========================================
# 8. PAIEMENTS & RÈGLEMENTS
# ==========================================
class Paiement(TenantAwareModel):
    MODES_PAIEMENT = (
        ('ESPECES', 'Espèces'),
        ('MOBILE_MONEY', 'Mobile Money (Wave, Orange Money, Moov, MTN)'),
        ('CARTE', 'Carte Bancaire'),
        ('VIREMENT', 'Virement Bancaire'),
        ('CHEQUE', 'Chèque'),
    )

    commande = models.ForeignKey(
        Commande, on_delete=models.CASCADE, related_name='paiements'
    )
    montant = models.DecimalField(max_digits=10, decimal_places=2)
    mode_paiement = models.CharField(
        max_length=20, choices=MODES_PAIEMENT, default='ESPECES'
    )
    reference_transaction = models.CharField(
        max_length=100, blank=True, null=True,
        help_text="Numéro de transaction Mobile Money / Chèque"
    )
    date_paiement = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['date_paiement']

    def __str__(self):
        return f"Paiement {self.montant} {self.atelier.devise} — {self.commande.code}"


# ==========================================
# 9. MOUVEMENTS DE STOCK
# ==========================================
class MouvementStock(TenantAwareModel):
    """
    Journal des entrées / sorties de stock.
    Permet de tracer l'historique et de justifier un écart d'inventaire.
    """
    TYPES = (
        ('VENTE', 'Sortie — Vente directe'),
        ('ANNULATION', 'Entrée — Annulation de vente'),
        ('REAPPRO', 'Entrée — Réapprovisionnement'),
        ('PERTE', 'Sortie — Perte / Casse'),
        ('INVENTAIRE', 'Correction d\'inventaire'),
        ('CONSOMMATION', 'Sortie — Consommation atelier'),
    )

    type_mouvement = models.CharField(max_length=20, choices=TYPES)

    modele = models.ForeignKey(
        CatalogueModele, on_delete=models.CASCADE,
        null=True, blank=True, related_name='mouvements'
    )
    accessoire = models.ForeignKey(
        Accessoire, on_delete=models.CASCADE,
        null=True, blank=True, related_name='mouvements'
    )
    commande = models.ForeignKey(
        Commande, on_delete=models.SET_NULL,
        null=True, blank=True, related_name='mouvements_stock'
    )

    quantite = models.IntegerField(
        help_text="Négatif pour une sortie, positif pour une entrée"
    )
    stock_avant = models.PositiveIntegerField(default=0)
    stock_apres = models.PositiveIntegerField(default=0)

    auteur = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL,
        null=True, blank=True, related_name='mouvements_stock'
    )
    commentaire = models.CharField(max_length=255, blank=True)

    class Meta:
        ordering = ['-date_creation']
        verbose_name = "Mouvement de stock"
        verbose_name_plural = "Mouvements de stock"

    @property
    def article(self):
        return self.modele or self.accessoire

    @property
    def nom_article(self):
        art = self.article
        return art.nom if art else "Article supprimé"

    @property
    def est_entree(self):
        return self.quantite > 0

    def __str__(self):
        signe = '+' if self.quantite > 0 else ''
        return f"{self.get_type_mouvement_display()} : {signe}{self.quantite} — {self.nom_article}"


# ==========================================
# 10. COMPTABILITÉ / DÉPENSES
# ==========================================
class Depense(TenantAwareModel):
    CATEGORIES = (
        ('ACHAT_MATERIEL', 'Achat de tissu / mercerie'),
        ('SALAIRE', 'Salaires / Payes tailleurs'),
        ('LOYER', "Loyer de l'atelier"),
        ('FACTURES', 'Eau, Électricité, Internet'),
        ('AUTRE', 'Autre dépense'),
    )

    date = models.DateField()
    categorie = models.CharField(max_length=30, choices=CATEGORIES, default='AUTRE')
    libelle = models.CharField(max_length=200)
    montant = models.DecimalField(max_digits=10, decimal_places=2)

    class Meta:
        ordering = ['-date']

    def __str__(self):
        return f"{self.libelle} - {self.montant} {self.atelier.devise}"
    

# ==========================================
# 11. EMPLOYÉS DE L'ATELIER
# ==========================================
class Employe(TenantAwareModel):
    """
    Personnel de l'atelier (couturiers, brodeurs, apprentis…).
    Aucun lien avec les comptes de connexion : c'est un registre RH.
    """
    POSTES = (
        ('COUTURIER', 'Couturier / Tailleur'),
        ('BRODEUR', 'Brodeur'),
        ('COUPEUR', 'Coupeur'),
        ('FINISSEUR', 'Finisseur / Repassage'),
        ('APPRENTI', 'Apprenti'),
        ('VENDEUR', 'Vendeur / Boutique'),
        ('AUTRE', 'Autre'),
    )

    STATUTS = (
        ('ACTIF', 'Actif'),
        ('CONGE', 'En congé'),
        ('SUSPENDU', 'Suspendu'),
        ('PARTI', 'Ne travaille plus ici'),
    )

    REMUNERATIONS = (
        ('FIXE', 'Salaire fixe mensuel'),
        ('PIECE', 'Paiement à la pièce'),
        ('MIXTE', 'Fixe + commission à la pièce'),
    )

    TYPES_COMMISSION = (
        ('MONTANT', 'Montant fixe par pièce'),
        ('POURCENTAGE', 'Pourcentage du prix de la pièce'),
    )

    # --- Identité ---
    matricule = models.CharField(max_length=20, blank=True)
    nom = models.CharField(max_length=100)
    prenom = models.CharField(max_length=100, blank=True)
    telephone = models.CharField(max_length=20)
    telephone_urgence = models.CharField(max_length=20, blank=True)
    adresse = models.TextField(blank=True)
    photo = models.ImageField(upload_to='employes/', blank=True, null=True)
    date_naissance = models.DateField(null=True, blank=True)

    # --- Poste ---
    poste = models.CharField(max_length=20, choices=POSTES, default='COUTURIER')
    specialites = models.CharField(
        max_length=200, blank=True,
        help_text="Ex : Boubou, Costume homme, Robe de mariée"
    )
    statut = models.CharField(max_length=20, choices=STATUTS, default='ACTIF')
    date_embauche = models.DateField(null=True, blank=True)
    date_depart = models.DateField(null=True, blank=True)

    # --- Rémunération ---
    type_remuneration = models.CharField(
        max_length=10, choices=REMUNERATIONS, default='FIXE'
    )
    salaire_mensuel = models.DecimalField(
        max_digits=10, decimal_places=2, default=0,
        help_text="Montant du fixe mensuel (si applicable)"
    )
    commission_type = models.CharField(
        max_length=15, choices=TYPES_COMMISSION,
        default='MONTANT', blank=True
    )
    commission_valeur = models.DecimalField(
        max_digits=10, decimal_places=2, default=0,
        help_text="Montant par pièce, ou pourcentage du prix de la couture"
    )

    notes = models.TextField(blank=True)

    class Meta:
        ordering = ['nom', 'prenom']
        verbose_name = "Employé"
        verbose_name_plural = "Employés"

    def save(self, *args, **kwargs):
        if not self.matricule:
            dernier = Employe.objects.filter(
                atelier=self.atelier).order_by('-id').first()
            num = (dernier.id + 1) if dernier else 1
            self.matricule = f"EMP-{num:03d}"
        super().save(*args, **kwargs)

    # ---------- Identité ----------

    @property
    def nom_complet(self):
        return f"{self.nom} {self.prenom}".strip()

    @property
    def initiales(self):
        a = self.nom[:1] if self.nom else ''
        b = self.prenom[:1] if self.prenom else ''
        return (a + b).upper() or '?'

    @property
    def est_actif(self):
        return self.statut == 'ACTIF'

    # ---------- Rémunération ----------

    @property
    def a_fixe(self):
        return self.type_remuneration in ('FIXE', 'MIXTE')

    @property
    def a_commission(self):
        return self.type_remuneration in ('PIECE', 'MIXTE')

    @property
    def libelle_remuneration(self):
        if self.type_remuneration == 'FIXE':
            return f"{int(self.salaire_mensuel)} / mois"
        unite = '%' if self.commission_type == 'POURCENTAGE' else '/ pièce'
        if self.type_remuneration == 'PIECE':
            return f"{int(self.commission_valeur)} {unite}"
        return f"{int(self.salaire_mensuel)} / mois + {int(self.commission_valeur)} {unite}"

    def commission_pour_ligne(self, ligne):
        """Commission due pour une couture terminée."""
        if not self.a_commission:
            return Decimal('0')
        if self.commission_type == 'POURCENTAGE':
            return (ligne.prix_apres_remise * self.commission_valeur
                    / Decimal('100'))
        return self.commission_valeur * ligne.quantite

    # ---------- Charge de travail ----------

    @property
    def lignes_en_cours(self):
        return self.lignes_travail.filter(
            commande__statut__in=['EN_ATTENTE', 'EN_COURS', 'PRET']
        )

    @property
    def nb_en_cours(self):
        return self.lignes_en_cours.count()

    @property
    def nb_en_retard(self):
        return sum(1 for l in self.lignes_en_cours
                   if l.commande.est_en_retard())

    @property
    def charge_pct(self):
        """Indicateur visuel : 5 pièces en cours = 100 %."""
        return min(100, self.nb_en_cours * 20)

    @property
    def niveau_charge(self):
        n = self.nb_en_cours
        if n == 0:
            return 'LIBRE'
        if n <= 2:
            return 'NORMAL'
        if n <= 4:
            return 'CHARGE'
        return 'SURCHARGE'

    def __str__(self):
        return f"{self.nom_complet} ({self.get_poste_display()})"


class Paie(TenantAwareModel):
    """Versement de salaire / commissions pour une période donnée."""
    STATUTS = (
        ('BROUILLON', 'Brouillon'),
        ('PAYEE', 'Payée'),
    )

    employe = models.ForeignKey(
        Employe, on_delete=models.CASCADE, related_name='paies'
    )
    periode_debut = models.DateField()
    periode_fin = models.DateField()

    salaire_fixe = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    commissions = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    primes = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    avances = models.DecimalField(max_digits=10, decimal_places=2, default=0)

    nb_pieces = models.PositiveIntegerField(default=0)
    statut = models.CharField(max_length=15, choices=STATUTS, default='BROUILLON')
    date_paiement = models.DateField(null=True, blank=True)
    mode_paiement = models.CharField(max_length=20, default='ESPECES')
    notes = models.TextField(blank=True)

    class Meta:
        ordering = ['-periode_fin', '-id']
        verbose_name = "Paie"
        verbose_name_plural = "Paies"

    @property
    def net_a_payer(self):
        return max(
            Decimal('0'),
            self.salaire_fixe + self.commissions + self.primes - self.avances
        )

    @property
    def periode_libelle(self):
        return f"{self.periode_debut:%d/%m/%Y} — {self.periode_fin:%d/%m/%Y}"

    def __str__(self):
        return f"Paie {self.employe.nom_complet} — {self.periode_libelle}"
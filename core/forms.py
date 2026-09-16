from datetime import timedelta

from django import forms
from django.contrib.auth.models import User
from django.db import transaction
from django.utils import timezone

from .models import (
    Abonnement, Accessoire, Atelier, CatalogueModele, Client,
    Commande, Depense, Employe, LigneAccessoire, LigneCommande,
    Mensuration, Paie, Paiement, PlanAbonnement, Profil,
)


# ==========================================
# 1. INSCRIPTION SAAS & AUTHENTIFICATION
# ==========================================
class InscriptionSaaSForm(forms.Form):
    first_name = forms.CharField(
        label="Prénom", max_length=100,
        widget=forms.TextInput(attrs={
            'class': 'form-control', 'placeholder': 'Ex: Jean'})
    )
    last_name = forms.CharField(
        label="Nom", max_length=100,
        widget=forms.TextInput(attrs={
            'class': 'form-control', 'placeholder': 'Ex: Dupont'})
    )
    email = forms.EmailField(
        label="Adresse email",
        widget=forms.EmailInput(attrs={
            'class': 'form-control', 'placeholder': 'jean.dupont@example.com'})
    )
    username = forms.CharField(
        label="Nom d'utilisateur", max_length=150,
        widget=forms.TextInput(attrs={
            'class': 'form-control', 'placeholder': 'jdupont'})
    )
    password = forms.CharField(
        label="Mot de passe", min_length=6,
        widget=forms.PasswordInput(attrs={
            'class': 'form-control', 'placeholder': '••••••••'})
    )
    confirm_password = forms.CharField(
        label="Confirmer le mot de passe",
        widget=forms.PasswordInput(attrs={
            'class': 'form-control', 'placeholder': '••••••••'})
    )
    nom_atelier = forms.CharField(
        label="Nom de l'atelier", max_length=200,
        widget=forms.TextInput(attrs={
            'class': 'form-control', 'placeholder': 'Ex: Couture & Élégance'})
    )
    telephone_atelier = forms.CharField(
        label="Téléphone de l'atelier", max_length=30,
        widget=forms.TextInput(attrs={
            'class': 'form-control', 'placeholder': '+223 70 00 00 00'})
    )
    devise = forms.ChoiceField(
        label="Devise", choices=Atelier.DEVISES, initial='FCFA',
        widget=forms.Select(attrs={'class': 'form-select'})
    )

    def clean_username(self):
        username = self.cleaned_data.get('username', '').strip()
        if User.objects.filter(username__iexact=username).exists():
            raise forms.ValidationError("Ce nom d'utilisateur est déjà pris.")
        return username

    def clean_email(self):
        email = self.cleaned_data.get('email')
        if email and User.objects.filter(email__iexact=email).exists():
            raise forms.ValidationError(
                "Un compte existe déjà avec cette adresse email.")
        return email

    def clean(self):
        cleaned_data = super().clean()
        password = cleaned_data.get("password")
        confirm = cleaned_data.get("confirm_password")
        if password and confirm and password != confirm:
            self.add_error('confirm_password',
                           "Les mots de passe ne correspondent pas.")
        return cleaned_data

    @transaction.atomic
    def save(self):
        user = User.objects.create_user(
            username=self.cleaned_data['username'],
            email=self.cleaned_data['email'],
            password=self.cleaned_data['password'],
            first_name=self.cleaned_data['first_name'],
            last_name=self.cleaned_data['last_name'],
        )
        atelier = Atelier.objects.create(
            nom=self.cleaned_data['nom_atelier'],
            telephone=self.cleaned_data['telephone_atelier'],
            email=self.cleaned_data['email'],
            devise=self.cleaned_data['devise'],
        )
        # Compte fondateur : masqué dans la liste des utilisateurs
        Profil.objects.create(
            user=user,
            atelier=atelier,
            role='ADMIN',
            telephone=self.cleaned_data['telephone_atelier'],
            est_fondateur=True,
        )

        plan_starter = (
            PlanAbonnement.objects.filter(nom__icontains='Starter').first()
            or PlanAbonnement.objects.first()
        )
        if plan_starter:
            Abonnement.objects.create(
                atelier=atelier,
                plan=plan_starter,
                date_fin=timezone.now().date() + timedelta(days=30),
                statut='ACTIF',
            )
        return user, atelier


# ==========================================
# 2. PROFIL PERSONNEL
# ==========================================
class ProfilForm(forms.ModelForm):
    """Modification de son propre profil."""

    first_name = forms.CharField(
        label="Prénom", max_length=100,
        widget=forms.TextInput(attrs={'class': 'form-control'})
    )
    last_name = forms.CharField(
        label="Nom", max_length=100, required=False,
        widget=forms.TextInput(attrs={'class': 'form-control'})
    )
    email = forms.EmailField(
        label="Email", required=False,
        widget=forms.EmailInput(attrs={'class': 'form-control'})
    )

    class Meta:
        model = Profil
        fields = ['telephone', 'photo']
        widgets = {
            'telephone': forms.TextInput(attrs={'class': 'form-control'}),
            'photo': forms.FileInput(attrs={'class': 'form-control'}),
        }

    def __init__(self, *args, **kwargs):
        self.user = kwargs.pop('user', None)
        super().__init__(*args, **kwargs)
        self.fields['telephone'].required = False
        self.fields['photo'].required = False
        if self.user:
            self.fields['first_name'].initial = self.user.first_name
            self.fields['last_name'].initial = self.user.last_name
            self.fields['email'].initial = self.user.email

    def clean_email(self):
        email = self.cleaned_data.get('email')
        if email and self.user:
            doublon = User.objects.filter(
                email__iexact=email).exclude(pk=self.user.pk).exists()
            if doublon:
                raise forms.ValidationError(
                    "Cette adresse email est déjà utilisée.")
        return email

    def save(self, commit=True):
        profil = super().save(commit=False)
        if self.user:
            self.user.first_name = self.cleaned_data['first_name']
            self.user.last_name = self.cleaned_data.get('last_name', '')
            self.user.email = self.cleaned_data.get('email', '')
            if commit:
                self.user.save()
        if commit:
            profil.save()
        return profil


# ==========================================
# 2bis. UTILISATEURS DE L'APPLICATION
# ==========================================
class UtilisateurCreationForm(forms.ModelForm):
    """
    Création d'un compte d'accès à l'application.
    Réservé à l'administrateur.
    """

    role = forms.ChoiceField(
        label="Rôle",
        choices=Profil.ROLES,
        initial='GESTIONNAIRE',
        widget=forms.RadioSelect(attrs={'class': 'btn-check'})
    )
    telephone = forms.CharField(
        label="Téléphone", max_length=20, required=False,
        widget=forms.TextInput(attrs={
            'class': 'form-control', 'placeholder': '+223 00 00 00 00'})
    )
    password = forms.CharField(
        label="Mot de passe", min_length=6,
        widget=forms.PasswordInput(attrs={
            'class': 'form-control', 'placeholder': '6 caractères minimum'})
    )
    password2 = forms.CharField(
        label="Confirmation du mot de passe",
        widget=forms.PasswordInput(attrs={
            'class': 'form-control', 'placeholder': 'Retapez le mot de passe'})
    )

    class Meta:
        model = User
        fields = ['first_name', 'last_name', 'username', 'email']
        labels = {
            'first_name': 'Prénom',
            'last_name': 'Nom',
            'username': "Nom d'utilisateur",
            'email': 'Email',
        }
        widgets = {
            'first_name': forms.TextInput(attrs={'class': 'form-control'}),
            'last_name': forms.TextInput(attrs={'class': 'form-control'}),
            'username': forms.TextInput(attrs={
                'class': 'form-control', 'placeholder': 'Pour la connexion'}),
            'email': forms.EmailInput(attrs={'class': 'form-control'}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['first_name'].required = True
        self.fields['last_name'].required = False
        self.fields['email'].required = False

    def clean_username(self):
        username = self.cleaned_data.get('username', '').strip()
        if not username:
            raise forms.ValidationError("Le nom d'utilisateur est obligatoire.")
        if User.objects.filter(username__iexact=username).exists():
            raise forms.ValidationError("Ce nom d'utilisateur est déjà pris.")
        return username

    def clean_email(self):
        email = self.cleaned_data.get('email')
        if email and User.objects.filter(email__iexact=email).exists():
            raise forms.ValidationError(
                "Un compte utilise déjà cette adresse email.")
        return email

    def clean(self):
        data = super().clean()
        mdp = data.get('password')
        mdp2 = data.get('password2')
        if mdp and mdp2 and mdp != mdp2:
            self.add_error('password2',
                           "Les mots de passe ne correspondent pas.")
        return data

    def save(self, commit=True):
        user = super().save(commit=False)
        user.set_password(self.cleaned_data['password'])
        if commit:
            user.save()
        return user


class UtilisateurEditionForm(forms.ModelForm):
    """
    Modification d'un compte existant : identité, rôle,
    réinitialisation du mot de passe, activation.
    """

    role = forms.ChoiceField(
        label="Rôle", choices=Profil.ROLES,
        widget=forms.Select(attrs={'class': 'form-select'})
    )
    telephone = forms.CharField(
        label="Téléphone", max_length=20, required=False,
        widget=forms.TextInput(attrs={'class': 'form-control'})
    )
    nouveau_mot_de_passe = forms.CharField(
        label="Nouveau mot de passe", required=False, min_length=6,
        widget=forms.PasswordInput(attrs={
            'class': 'form-control',
            'placeholder': "Laisser vide pour conserver l'actuel"})
    )
    actif = forms.BooleanField(
        label="Compte actif", required=False, initial=True,
        widget=forms.CheckboxInput(attrs={'class': 'form-check-input'})
    )

    class Meta:
        model = User
        fields = ['first_name', 'last_name', 'username', 'email']
        labels = {
            'first_name': 'Prénom',
            'last_name': 'Nom',
            'username': "Nom d'utilisateur",
            'email': 'Email',
        }
        widgets = {
            'first_name': forms.TextInput(attrs={'class': 'form-control'}),
            'last_name': forms.TextInput(attrs={'class': 'form-control'}),
            'username': forms.TextInput(attrs={'class': 'form-control'}),
            'email': forms.EmailInput(attrs={'class': 'form-control'}),
        }

    def __init__(self, *args, **kwargs):
        self.profil = kwargs.pop('profil', None)
        super().__init__(*args, **kwargs)
        self.fields['first_name'].required = True
        self.fields['last_name'].required = False
        self.fields['email'].required = False
        if self.profil:
            self.fields['role'].initial = self.profil.role
            self.fields['telephone'].initial = self.profil.telephone
            self.fields['actif'].initial = self.profil.actif

    def clean_username(self):
        username = self.cleaned_data.get('username', '').strip()
        doublon = User.objects.filter(
            username__iexact=username).exclude(pk=self.instance.pk).exists()
        if doublon:
            raise forms.ValidationError("Ce nom d'utilisateur est déjà pris.")
        return username

    def clean_email(self):
        email = self.cleaned_data.get('email')
        if email:
            doublon = User.objects.filter(
                email__iexact=email).exclude(pk=self.instance.pk).exists()
            if doublon:
                raise forms.ValidationError(
                    "Un autre compte utilise déjà cette adresse email.")
        return email

    def save(self, commit=True):
        user = super().save(commit=False)
        mdp = self.cleaned_data.get('nouveau_mot_de_passe')
        if mdp:
            user.set_password(mdp)
        user.is_active = self.cleaned_data.get('actif', True)
        if commit:
            user.save()
            if self.profil:
                self.profil.role = self.cleaned_data['role']
                self.profil.telephone = self.cleaned_data.get('telephone', '')
                self.profil.actif = self.cleaned_data.get('actif', True)
                self.profil.save()
        return user


class AtelierForm(forms.ModelForm):
    """Paramètres généraux de l'atelier."""

    class Meta:
        model = Atelier
        fields = [
            'nom', 'telephone', 'email', 'adresse',
            'devise', 'seuil_stock_faible', 'logo',
        ]
        labels = {
            'nom': "Nom de l'atelier",
            'telephone': 'Téléphone',
            'email': 'Email de contact',
            'adresse': 'Adresse physique',
            'devise': 'Devise',
            'seuil_stock_faible': "Seuil d'alerte de stock",
            'logo': "Logo de l'atelier",
        }
        widgets = {
            'nom': forms.TextInput(attrs={'class': 'form-control'}),
            'telephone': forms.TextInput(attrs={
                'class': 'form-control', 'placeholder': '+223 00 00 00 00'}),
            'email': forms.EmailInput(attrs={
                'class': 'form-control', 'placeholder': 'contact@atelier.com'}),
            'adresse': forms.Textarea(attrs={
                'class': 'form-control', 'rows': 2,
                'placeholder': 'Rue, quartier, point de repère'}),
            'devise': forms.Select(attrs={'class': 'form-select'}),
            'seuil_stock_faible': forms.NumberInput(attrs={
                'class': 'form-control', 'min': '0'}),
            'logo': forms.FileInput(attrs={
                'class': 'form-control', 'accept': 'image/*'}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        for champ in ('telephone', 'email', 'adresse',
                      'logo', 'seuil_stock_faible'):
            self.fields[champ].required = False


# ==========================================
# 3. CLIENTS & MENSURATIONS
# ==========================================
class ClientForm(forms.ModelForm):
    class Meta:
        model = Client
        fields = ['nom', 'prenom', 'telephone', 'email',
                  'adresse', 'genre', 'origine']
        widgets = {
            'nom': forms.TextInput(attrs={
                'class': 'form-control', 'placeholder': 'Nom'}),
            'prenom': forms.TextInput(attrs={
                'class': 'form-control', 'placeholder': 'Prénom'}),
            'telephone': forms.TextInput(attrs={
                'class': 'form-control', 'placeholder': 'Téléphone'}),
            'email': forms.EmailInput(attrs={
                'class': 'form-control', 'placeholder': 'Email'}),
            'adresse': forms.Textarea(attrs={
                'class': 'form-control', 'rows': 2, 'placeholder': 'Adresse'}),
            'genre': forms.Select(attrs={'class': 'form-select'}),
            'origine': forms.Select(attrs={'class': 'form-select'}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        for champ in ('prenom', 'email', 'adresse', 'origine'):
            self.fields[champ].required = False


class MensurationForm(forms.ModelForm):
    class Meta:
        model = Mensuration
        fields = ['client', 'beneficiaire', 'lien_parente',
                  'genre_mesure', 'libelle', 'donnees']
        widgets = {
            'client': forms.Select(attrs={'class': 'form-select'}),
            'beneficiaire': forms.TextInput(attrs={
                'class': 'form-control',
                'placeholder': 'Vide = le client lui-même'}),
            'lien_parente': forms.Select(attrs={'class': 'form-select'}),
            'genre_mesure': forms.Select(attrs={'class': 'form-select'}),
            'libelle': forms.TextInput(attrs={'class': 'form-control'}),
        }

    def __init__(self, *args, **kwargs):
        atelier = kwargs.pop('atelier', None)
        super().__init__(*args, **kwargs)
        self.fields['beneficiaire'].required = False
        if atelier and 'client' in self.fields:
            self.fields['client'].queryset = Client.objects.filter(
                atelier=atelier)


# ==========================================
# 4. COMMANDES & PAIEMENTS
# ==========================================
class CommandeForm(forms.ModelForm):
    acompte = forms.DecimalField(
        label="Acompte versé", min_value=0, required=False, initial=0,
        widget=forms.NumberInput(attrs={
            'class': 'form-control',
            'placeholder': '0',
            'step': 'any',
            'id': 'id_acompte',
        })
    )
    acompte_mode = forms.ChoiceField(
        label="Mode de paiement de l'acompte",
        choices=Paiement.MODES_PAIEMENT, required=False,
        widget=forms.Select(attrs={
            'class': 'form-select', 'id': 'id_acompte_mode'})
    )

    class Meta:
        model = Commande
        fields = [
            'client',
            'employe_attribue',
            'remise_type',
            'remise_valeur',
            'statut',
            'date_livraison_prevue',
            'notes',
        ]
        widgets = {
            'client': forms.Select(attrs={
                'class': 'form-select', 'id': 'id_client'}),
            'employe_attribue': forms.Select(attrs={
                'class': 'form-select', 'id': 'id_employe_attribue'}),
            'remise_type': forms.Select(attrs={
                'class': 'form-select', 'id': 'id_remise_type'}),
            'remise_valeur': forms.NumberInput(attrs={
                'class': 'form-control', 'step': 'any',
                'min': '0', 'id': 'id_remise_valeur'}),
            'statut': forms.Select(attrs={'class': 'form-select'}),
            'date_livraison_prevue': forms.DateInput(attrs={
                'class': 'form-control', 'type': 'date'}),
            'notes': forms.Textarea(attrs={
                'class': 'form-control', 'rows': 2,
                'placeholder': 'Notes globales sur la commande…'}),
        }

    def __init__(self, *args, **kwargs):
        atelier = kwargs.pop('atelier', None)
        super().__init__(*args, **kwargs)

        for champ in ('remise_type', 'remise_valeur',
                      'employe_attribue', 'notes'):
            self.fields[champ].required = False

        self.fields['remise_type'].empty_label = "Aucune remise"
        self.fields['employe_attribue'].empty_label = "— Non attribuée —"
        self.fields['employe_attribue'].label = "Couturier responsable"

        if atelier:
            self.fields['client'].queryset = Client.objects.filter(
                atelier=atelier).order_by('nom', 'prenom')
            self.fields['employe_attribue'].queryset = Employe.objects.filter(
                atelier=atelier, statut='ACTIF').order_by('nom', 'prenom')

        # L'acompte n'a de sens qu'à la création
        if self.instance and self.instance.pk:
            self.fields.pop('acompte', None)
            self.fields.pop('acompte_mode', None)


class LigneCommandeForm(forms.ModelForm):
    """Ligne de commande (couture, prêt-à-porter, accessoire)."""

    class Meta:
        model = LigneCommande
        fields = [
            'type_ligne',
            'modele',
            'description',
            'client_secondaire',
            'mensuration',
            'employe',
            'etat_travail',
            'accessoire',
            'quantite',
            'prix_unitaire',
            'remise_type',
            'remise_valeur',
            'photo_tissu',
            'photo_modele_custom',
        ]
        widgets = {
            'type_ligne': forms.Select(attrs={
                'class': 'form-select type-ligne-select'}),
            'modele': forms.Select(attrs={
                'class': 'form-select select-modele'}),
            'description': forms.Textarea(attrs={
                'class': 'form-control', 'rows': 2,
                'placeholder': 'Détails spécifiques à cette couture…'}),
            'client_secondaire': forms.Select(attrs={'class': 'form-select'}),
            'mensuration': forms.Select(attrs={
                'class': 'form-select select-mensuration'}),
            'employe': forms.Select(attrs={
                'class': 'form-select select-employe'}),
            'etat_travail': forms.Select(attrs={'class': 'form-select'}),
            'accessoire': forms.Select(attrs={
                'class': 'form-select select-accessoire'}),
            'quantite': forms.NumberInput(attrs={
                'class': 'form-control', 'min': '1', 'step': '1'}),
            'prix_unitaire': forms.NumberInput(attrs={
                'class': 'form-control input-prix-unitaire',
                'step': 'any', 'min': '0'}),
            'remise_type': forms.Select(attrs={'class': 'form-select'}),
            'remise_valeur': forms.NumberInput(attrs={
                'class': 'form-control', 'step': 'any', 'min': '0'}),
            'photo_tissu': forms.FileInput(attrs={'class': 'form-control'}),
            'photo_modele_custom': forms.FileInput(attrs={'class': 'form-control'}),
        }

    def __init__(self, *args, **kwargs):
        atelier = kwargs.pop('atelier', None)
        super().__init__(*args, **kwargs)

        optionnels = (
            'modele', 'description', 'client_secondaire', 'mensuration',
            'employe', 'accessoire', 'remise_type', 'remise_valeur',
            'photo_tissu', 'photo_modele_custom',
        )
        for champ in optionnels:
            self.fields[champ].required = False

        self.fields['remise_type'].empty_label = "Aucune remise"
        self.fields['employe'].empty_label = "— Couturier de la commande —"
        self.fields['employe'].label = "Couturier"

        if atelier:
            self.fields['modele'].queryset = CatalogueModele.objects.filter(
                atelier=atelier).order_by('nom')
            self.fields['client_secondaire'].queryset = Client.objects.filter(
                atelier=atelier).order_by('nom', 'prenom')
            self.fields['accessoire'].queryset = Accessoire.objects.filter(
                atelier=atelier).order_by('nom')
            self.fields['employe'].queryset = Employe.objects.filter(
                atelier=atelier, statut='ACTIF').order_by('nom', 'prenom')
            self.fields['mensuration'].queryset = Mensuration.objects.filter(
                atelier=atelier)


class LigneAccessoireForm(forms.ModelForm):
    """Accessoire rattaché à une ligne de couture."""

    class Meta:
        model = LigneAccessoire
        fields = ['accessoire', 'quantite', 'prix_unitaire']
        widgets = {
            'accessoire': forms.Select(attrs={'class': 'form-select'}),
            'quantite': forms.NumberInput(attrs={
                'class': 'form-control', 'min': '1', 'step': '1'}),
            'prix_unitaire': forms.NumberInput(attrs={
                'class': 'form-control', 'step': 'any', 'min': '0'}),
        }

    def __init__(self, *args, **kwargs):
        atelier = kwargs.pop('atelier', None)
        super().__init__(*args, **kwargs)
        if atelier:
            self.fields['accessoire'].queryset = Accessoire.objects.filter(
                atelier=atelier).order_by('nom')


class PaiementForm(forms.ModelForm):
    class Meta:
        model = Paiement
        fields = ['montant', 'mode_paiement', 'reference_transaction']
        widgets = {
            'montant': forms.NumberInput(attrs={
                'class': 'form-control', 'step': 'any',
                'min': '0', 'placeholder': '0'}),
            'mode_paiement': forms.Select(attrs={'class': 'form-select'}),
            'reference_transaction': forms.TextInput(attrs={
                'class': 'form-control',
                'placeholder': 'Numéro de transaction (optionnel)'}),
        }

    def __init__(self, *args, **kwargs):
        kwargs.pop('atelier', None)
        super().__init__(*args, **kwargs)
        self.fields['reference_transaction'].required = False


class VenteDirecteForm(forms.Form):
    """
    Vente au comptant : prêt-à-porter et accessoires.
    Client en saisie libre, paiement intégral immédiat.
    """
    nom_client = forms.CharField(
        label="Nom du client", max_length=150, required=False,
        widget=forms.TextInput(attrs={
            'class': 'form-control',
            'placeholder': 'Client de passage (optionnel)'})
    )
    telephone_client = forms.CharField(
        label="Téléphone", max_length=20, required=False,
        widget=forms.TextInput(attrs={
            'class': 'form-control', 'placeholder': 'Optionnel'})
    )
    mode_paiement = forms.ChoiceField(
        label="Mode de paiement",
        choices=Paiement.MODES_PAIEMENT, initial='ESPECES',
        widget=forms.Select(attrs={'class': 'form-select'})
    )


# ==========================================
# 5. CATALOGUE & ACCESSOIRES
# ==========================================
class CatalogueModeleForm(forms.ModelForm):
    class Meta:
        model = CatalogueModele
        fields = [
            'nom', 'type_modele', 'description', 'prix_base', 'photo',
            'taille_disponible', 'couleur', 'stock_pret_a_porter',
            'seuil_alerte',
        ]
        widgets = {
            'nom': forms.TextInput(attrs={'class': 'form-control'}),
            'type_modele': forms.Select(attrs={'class': 'form-select'}),
            'description': forms.Textarea(attrs={
                'class': 'form-control', 'rows': 3}),
            'prix_base': forms.NumberInput(attrs={
                'class': 'form-control', 'step': 'any', 'min': '0'}),
            'photo': forms.FileInput(attrs={'class': 'form-control'}),
            'taille_disponible': forms.TextInput(attrs={'class': 'form-control'}),
            'couleur': forms.TextInput(attrs={'class': 'form-control'}),
            'stock_pret_a_porter': forms.NumberInput(attrs={
                'class': 'form-control', 'min': '0'}),
            'seuil_alerte': forms.NumberInput(attrs={
                'class': 'form-control', 'min': '0'}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        for champ in ('description', 'photo', 'taille_disponible',
                      'couleur', 'stock_pret_a_porter', 'seuil_alerte'):
            self.fields[champ].required = False

    def clean(self):
        data = super().clean()
        # La couture sur mesure ne gère pas de stock
        if data.get('type_modele') == 'COUTURE':
            data['stock_pret_a_porter'] = 0
            data['taille_disponible'] = ''
        return data


class AccessoireForm(forms.ModelForm):
    class Meta:
        model = Accessoire
        fields = [
            'nom', 'categorie', 'description', 'prix_unitaire',
            'unite', 'stock_disponible', 'seuil_alerte', 'photo',
        ]
        widgets = {
            'nom': forms.TextInput(attrs={'class': 'form-control'}),
            'categorie': forms.Select(attrs={'class': 'form-select'}),
            'description': forms.Textarea(attrs={
                'class': 'form-control', 'rows': 2}),
            'prix_unitaire': forms.NumberInput(attrs={
                'class': 'form-control', 'step': 'any', 'min': '0'}),
            'unite': forms.Select(attrs={'class': 'form-select'}),
            'stock_disponible': forms.NumberInput(attrs={
                'class': 'form-control', 'min': '0'}),
            'seuil_alerte': forms.NumberInput(attrs={
                'class': 'form-control', 'min': '0'}),
            'photo': forms.FileInput(attrs={'class': 'form-control'}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        for champ in ('description', 'photo', 'seuil_alerte'):
            self.fields[champ].required = False


# ==========================================
# 6. DÉPENSES
# ==========================================
class DepenseForm(forms.ModelForm):
    class Meta:
        model = Depense
        fields = ['date', 'categorie', 'libelle', 'montant']
        widgets = {
            'date': forms.DateInput(attrs={
                'class': 'form-control', 'type': 'date'}),
            'categorie': forms.Select(attrs={'class': 'form-select'}),
            'libelle': forms.TextInput(attrs={
                'class': 'form-control', 'placeholder': 'Ex: Achat tissu wax'}),
            'montant': forms.NumberInput(attrs={
                'class': 'form-control', 'step': 'any',
                'min': '0', 'placeholder': '0'}),
        }


# ==========================================
# 7. EMPLOYÉS & PAIES
# ==========================================
class EmployeForm(forms.ModelForm):
    class Meta:
        model = Employe
        fields = [
            'nom', 'prenom', 'telephone', 'telephone_urgence', 'adresse',
            'photo', 'date_naissance', 'poste', 'specialites', 'statut',
            'date_embauche', 'type_remuneration', 'salaire_mensuel',
            'commission_type', 'commission_valeur', 'notes',
        ]
        widgets = {
            'nom': forms.TextInput(attrs={'class': 'form-control'}),
            'prenom': forms.TextInput(attrs={'class': 'form-control'}),
            'telephone': forms.TextInput(attrs={'class': 'form-control'}),
            'telephone_urgence': forms.TextInput(attrs={'class': 'form-control'}),
            'adresse': forms.Textarea(attrs={
                'class': 'form-control', 'rows': 2}),
            'photo': forms.FileInput(attrs={'class': 'form-control'}),
            'date_naissance': forms.DateInput(attrs={
                'class': 'form-control', 'type': 'date'}),
            'poste': forms.Select(attrs={'class': 'form-select'}),
            'specialites': forms.TextInput(attrs={
                'class': 'form-control',
                'placeholder': 'Ex : Boubou, Costume homme, Broderie'}),
            'statut': forms.Select(attrs={'class': 'form-select'}),
            'date_embauche': forms.DateInput(attrs={
                'class': 'form-control', 'type': 'date'}),
            'type_remuneration': forms.Select(attrs={'class': 'form-select'}),
            'salaire_mensuel': forms.NumberInput(attrs={
                'class': 'form-control', 'step': 'any', 'min': '0'}),
            'commission_type': forms.Select(attrs={'class': 'form-select'}),
            'commission_valeur': forms.NumberInput(attrs={
                'class': 'form-control', 'step': 'any', 'min': '0'}),
            'notes': forms.Textarea(attrs={
                'class': 'form-control', 'rows': 2}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        optionnels = (
            'prenom', 'telephone_urgence', 'adresse', 'photo',
            'date_naissance', 'specialites', 'date_embauche',
            'salaire_mensuel', 'commission_type', 'commission_valeur', 'notes',
        )
        for champ in optionnels:
            self.fields[champ].required = False

    def clean(self):
        data = super().clean()
        type_remu = data.get('type_remuneration')

        if type_remu == 'FIXE':
            data['commission_valeur'] = 0
            if not data.get('salaire_mensuel'):
                self.add_error(
                    'salaire_mensuel',
                    "Indiquez le montant du salaire fixe.")

        elif type_remu == 'PIECE':
            data['salaire_mensuel'] = 0
            if not data.get('commission_valeur'):
                self.add_error(
                    'commission_valeur',
                    "Indiquez le montant ou le pourcentage par pièce.")

        elif type_remu == 'MIXTE':
            if not data.get('salaire_mensuel'):
                self.add_error(
                    'salaire_mensuel',
                    "Indiquez la part fixe du salaire.")
            if not data.get('commission_valeur'):
                self.add_error(
                    'commission_valeur',
                    "Indiquez la commission par pièce.")

        # Un pourcentage ne peut pas dépasser 100
        if (data.get('commission_type') == 'POURCENTAGE'
                and data.get('commission_valeur')
                and data['commission_valeur'] > 100):
            self.add_error(
                'commission_valeur',
                "Un pourcentage ne peut pas dépasser 100.")

        return data


class PaieForm(forms.ModelForm):
    class Meta:
        model = Paie
        fields = [
            'periode_debut', 'periode_fin', 'salaire_fixe',
            'commissions', 'primes', 'avances',
            'mode_paiement', 'notes',
        ]
        widgets = {
            'periode_debut': forms.DateInput(attrs={
                'class': 'form-control', 'type': 'date'}),
            'periode_fin': forms.DateInput(attrs={
                'class': 'form-control', 'type': 'date'}),
            'salaire_fixe': forms.NumberInput(attrs={
                'class': 'form-control', 'step': 'any', 'min': '0'}),
            'commissions': forms.NumberInput(attrs={
                'class': 'form-control', 'step': 'any', 'min': '0'}),
            'primes': forms.NumberInput(attrs={
                'class': 'form-control', 'step': 'any', 'min': '0'}),
            'avances': forms.NumberInput(attrs={
                'class': 'form-control', 'step': 'any', 'min': '0'}),
            'mode_paiement': forms.Select(
                choices=Paiement.MODES_PAIEMENT,
                attrs={'class': 'form-select'}),
            'notes': forms.Textarea(attrs={
                'class': 'form-control', 'rows': 2}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        for champ in ('salaire_fixe', 'commissions',
                      'primes', 'avances', 'notes'):
            self.fields[champ].required = False

    def clean(self):
        data = super().clean()
        debut = data.get('periode_debut')
        fin = data.get('periode_fin')
        if debut and fin and fin < debut:
            self.add_error(
                'periode_fin',
                "La date de fin doit être postérieure à la date de début.")
        return data


class AttributionLigneForm(forms.ModelForm):
    """Réattribuer rapidement une couture à un autre employé."""

    class Meta:
        model = LigneCommande
        fields = ['employe', 'etat_travail']
        widgets = {
            'employe': forms.Select(attrs={'class': 'form-select'}),
            'etat_travail': forms.Select(attrs={'class': 'form-select'}),
        }

    def __init__(self, *args, **kwargs):
        atelier = kwargs.pop('atelier', None)
        super().__init__(*args, **kwargs)
        self.fields['employe'].required = False
        self.fields['employe'].empty_label = "— Non attribuée —"
        if atelier:
            self.fields['employe'].queryset = Employe.objects.filter(
                atelier=atelier, statut='ACTIF').order_by('nom', 'prenom')
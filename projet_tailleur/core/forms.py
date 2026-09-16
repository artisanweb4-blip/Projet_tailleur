from django import forms
from .models import Client, Commande

class ClientForm(forms.ModelForm):
    class Meta:
        model = Client
        fields = ['nom', 'email', 'telephone', 'adresse']

from django import forms
from .models import Commande

class CommandeForm(forms.ModelForm):
    class Meta:
        model = Commande
        fields = ['client', 'type_vetement', 'description', 'prix_total', 'metrage', 'montant_paye', 'statut', 'date_livraison_prevue']
        widgets = {
            'date_livraison_prevue': forms.DateInput(attrs={'type': 'date'}),
        }

from .models import Mensuration

class MensurationForm(forms.ModelForm):
    class Meta:
        model = Mensuration
        exclude = ['client', 'date']  # On gère le client et la date dans la vue
        widgets = {
            'epaule': forms.NumberInput(attrs={'step': '0.1'}),
            'longueur_manche': forms.NumberInput(attrs={'step': '0.1'}),
            # ... tous les champs avec step 0.1
        }

from .models import Depense

from .models import Depense

class DepenseForm(forms.ModelForm):
    class Meta:
        model = Depense
        fields = ['date', 'categorie', 'libelle', 'montant']
        widgets = {
            'date': forms.DateInput(attrs={'type': 'date'}),
            'libelle': forms.TextInput(attrs={'placeholder': 'Ex: Achat wax imprimé, bobines de fil...'}),
        }
from django.shortcuts import render, redirect, get_object_or_404
from django.db.models import Q, Sum, F
from datetime import date, timedelta, datetime
from django.utils import timezone
from django.contrib import messages
from django.contrib.auth import login, authenticate, logout
from django.contrib.auth.decorators import login_required
from django.contrib.auth.forms import UserCreationForm, AuthenticationForm, PasswordChangeForm, UserChangeForm
from django.contrib.auth import update_session_auth_hash
from django.http import JsonResponse
from django.urls import reverse

from .models import Client, Commande, Depense, Tissu, Mensuration
from .forms import ClientForm, CommandeForm, DepenseForm, MensurationForm


# ==================== ACCUEIL ====================
@login_required
def accueil(request):
    nb_clients = Client.objects.count()
    nb_commandes = Commande.objects.count()
    commandes_encours = Commande.objects.filter(statut__in=['encours', 'attente']).count()
    aujourdhui = date.today()
    fin_semaine = aujourdhui + timedelta(days=7)
    livraisons_semaine = Commande.objects.filter(
        date_livraison_prevue__range=[aujourdhui, fin_semaine],
        statut__in=['encours', 'attente', 'brouillon']
    ).count()
    debut_mois = date(aujourdhui.year, aujourdhui.month, 1)
    revenus_mois = Commande.objects.filter(date_commande__gte=debut_mois).aggregate(total=Sum('montant_paye'))['total'] or 0
    depenses_mois = Depense.objects.filter(date__gte=debut_mois).aggregate(total=Sum('montant'))['total'] or 0
    net_mois = revenus_mois - depenses_mois
    toutes_commandes = Commande.objects.all()
    commandes_retard = sum(1 for cmd in toutes_commandes if cmd.est_en_retard())
    dernieres_commandes = Commande.objects.select_related('client').order_by('-date_commande')[:5]
    mois_fr = {1: 'Janvier', 2: 'Février', 3: 'Mars', 4: 'Avril', 5: 'Mai', 6: 'Juin',
               7: 'Juillet', 8: 'Août', 9: 'Septembre', 10: 'Octobre', 11: 'Novembre', 12: 'Décembre'}
    mois_annee_fr = f"{mois_fr[aujourdhui.month]} {aujourdhui.year}"
    context = {
        'nb_clients': nb_clients, 'nb_commandes': nb_commandes,
        'commandes_encours': commandes_encours, 'livraisons_semaine': livraisons_semaine,
        'revenus_mois': revenus_mois, 'depenses_mois': depenses_mois, 'net_mois': net_mois,
        'commandes_retard': commandes_retard, 'dernieres_commandes': dernieres_commandes,
        'mois_annee_fr': mois_annee_fr,
    }
    return render(request, 'core/accueil.html', context)


# ==================== REDIRECTION ====================
def home(request):
    if request.user.is_authenticated:
        return redirect('accueil')
    return redirect('connexion')


# ==================== CLIENTS ====================
def recherche_clients(request):
    query = request.GET.get('q', '')
    clients = Client.objects.all()
    if query:
        clients = clients.filter(Q(nom__icontains=query) | Q(email__icontains=query) | Q(telephone__icontains=query))
    return render(request, 'core/clients.html', {'clients': clients, 'query': query})


def ajouter_client(request):
    if request.method == 'POST':
        form = ClientForm(request.POST)
        if form.is_valid():
            form.save()
            messages.success(request, "Client ajouté avec succès.")
            return redirect('recherche_clients')
        else:
            messages.error(request, "Erreur dans le formulaire. Vérifiez les champs.")
            return redirect('recherche_clients')
    else:
        form = ClientForm()
    return render(request, 'core/ajouter_client.html', {'form': form})


def detail_client(request, client_id):
    client = get_object_or_404(Client, id=client_id)
    mensurations = client.mensurations.all().order_by('-date')
    commandes = Commande.objects.filter(client=client).order_by('-date_commande')
    form = MensurationForm()
    return render(request, 'core/detail_client.html', {
        'client': client, 'mensurations': mensurations, 'commandes': commandes, 'form': form
    })


def modifier_client(request, client_id):
    client = get_object_or_404(Client, id=client_id)
    if request.method == 'POST':
        form = ClientForm(request.POST, instance=client)
        if form.is_valid():
            form.save()
            messages.success(request, "Client modifié avec succès.")
            if request.headers.get('x-requested-with') == 'XMLHttpRequest':
                return JsonResponse({'success': True})
            return redirect('detail_client', client_id=client.id)
        else:
            messages.error(request, "Erreur dans le formulaire.")
            if request.headers.get('x-requested-with') == 'XMLHttpRequest':
                return JsonResponse({'success': False, 'error': form.errors.as_json()}, status=400)
            return redirect('detail_client', client_id=client.id)
    return redirect('detail_client', client_id=client.id)


def supprimer_client(request, client_id):
    client = get_object_or_404(Client, id=client_id)
    if request.method == 'POST':
        client.delete()
        messages.success(request, "Client supprimé avec succès.")
        return redirect('recherche_clients')
    return render(request, 'core/supprimer_client.html', {'client': client})


def get_client_data(request, client_id):
    client = get_object_or_404(Client, id=client_id)
    return JsonResponse({
        'id': client.id, 'nom': client.nom, 'email': client.email,
        'telephone': client.telephone, 'adresse': client.adresse,
    })


# ==================== COMMANDES ====================
def ajouter_commande(request):
    client_id = request.GET.get('client')
    if request.method == 'POST':
        form = CommandeForm(request.POST)
        if form.is_valid():
            commande = form.save()
            messages.success(request, "Commande ajoutée avec succès.")
            return redirect('detail_commande', commande_id=commande.id)
        else:
            messages.error(request, "Erreur dans le formulaire de commande.")
    else:
        initial = {}
        if client_id:
            initial['client'] = client_id
        initial['date_livraison_prevue'] = timezone.now().date() + timedelta(days=7)
        initial['type_vetement'] = 'costume'
        initial['statut'] = 'encours'
        form = CommandeForm(initial=initial)
    return render(request, 'core/ajouter_commande.html', {'form': form})


def liste_commandes(request):
    commandes = Commande.objects.select_related('client').all()
    statut = request.GET.get('statut', '')
    if statut:
        commandes = commandes.filter(statut=statut)
    paiement = request.GET.get('paiement', '')
    if paiement == 'paye':
        commandes = commandes.filter(montant_paye__gte=F('prix_total'))
    elif paiement == 'impaye':
        commandes = commandes.filter(montant_paye=0)
    elif paiement == 'partiel':
        commandes = commandes.filter(montant_paye__gt=0, montant_paye__lt=F('prix_total'))
    date_debut = request.GET.get('date_debut', '')
    date_fin = request.GET.get('date_fin', '')
    if date_debut:
        try:
            date_debut_obj = datetime.strptime(date_debut, '%Y-%m-%d').date()
            commandes = commandes.filter(date_commande__gte=date_debut_obj)
        except ValueError:
            pass
    if date_fin:
        try:
            date_fin_obj = datetime.strptime(date_fin, '%Y-%m-%d').date()
            commandes = commandes.filter(date_commande__lte=date_fin_obj)
        except ValueError:
            pass
    total_global = commandes.aggregate(total=Sum('prix_total'))['total'] or 0
    total_paye = commandes.aggregate(paye=Sum('montant_paye'))['paye'] or 0
    total_restant = total_global - total_paye
    context = {
        'commandes': commandes, 'statut_actuel': statut, 'paiement_actuel': paiement,
        'date_debut': date_debut, 'date_fin': date_fin,
        'total_global': total_global, 'total_paye': total_paye, 'total_restant': total_restant,
    }
    return render(request, 'core/commandes.html', context)


def detail_commande(request, commande_id):
    commande = get_object_or_404(Commande, id=commande_id)
    return render(request, 'core/detail_commande.html', {'commande': commande})


def modifier_commande(request, commande_id):
    commande = get_object_or_404(Commande, id=commande_id)
    if request.method == 'POST':
        form = CommandeForm(request.POST, instance=commande)
        if form.is_valid():
            form.save()
            messages.success(request, "Commande modifiée avec succès.")
            return redirect('detail_commande', commande_id=commande.id)
        else:
            messages.error(request, "Erreur dans le formulaire de modification.")
    else:
        form = CommandeForm(instance=commande)
    return render(request, 'core/modifier_commande.html', {'form': form, 'commande': commande})


def supprimer_commande(request, commande_id):
    commande = get_object_or_404(Commande, id=commande_id)
    client_id = commande.client.id
    if request.method == 'POST':
        commande.delete()
        messages.success(request, "Commande supprimée avec succès.")
        return redirect('detail_client', client_id=client_id)
    return render(request, 'core/supprimer_commande.html', {'commande': commande})


# ==================== MENSURATIONS ====================
def ajouter_mensuration(request, client_id):
    client = get_object_or_404(Client, id=client_id)
    if request.method == 'POST':
        form = MensurationForm(request.POST)
        if form.is_valid():
            mensuration = form.save(commit=False)
            mensuration.client = client
            mensuration.save()
            messages.success(request, "Mensurations ajoutées avec succès.")
            return redirect('detail_client', client_id=client.id)
        else:
            messages.error(request, "Erreur dans le formulaire de mensurations.")
    else:
        form = MensurationForm()
    return render(request, 'core/ajouter_mensuration.html', {'form': form, 'client': client})


def modifier_mensuration(request, mensuration_id):
    mensuration = get_object_or_404(Mensuration, id=mensuration_id)
    if request.method == 'POST':
        form = MensurationForm(request.POST, instance=mensuration)
        if form.is_valid():
            form.save()
            messages.success(request, "Mensurations modifiées avec succès.")
            return redirect('detail_client', client_id=mensuration.client.id)
        else:
            messages.error(request, "Erreur dans le formulaire de modification.")
    else:
        form = MensurationForm(instance=mensuration)
    return render(request, 'core/modifier_mensuration.html', {'form': form, 'mensuration': mensuration})


def detail_mensuration(request, mensuration_id):
    mensuration = get_object_or_404(Mensuration, id=mensuration_id)
    return render(request, 'core/detail_mensuration.html', {'mensuration': mensuration})


def supprimer_mensuration(request, mensuration_id):
    mensuration = get_object_or_404(Mensuration, id=mensuration_id)
    client_id = mensuration.client.id
    if request.method == 'POST':
        mensuration.delete()
        messages.success(request, "Mensurations supprimées avec succès.")
        return redirect('detail_client', client_id=client_id)
    return render(request, 'core/supprimer_mensuration.html', {'mensuration': mensuration})


# ==================== DÉPENSES ====================
def ajouter_depense(request):
    if request.method == 'POST':
        form = DepenseForm(request.POST)
        if form.is_valid():
            form.save()
            if request.headers.get('x-requested-with') == 'XMLHttpRequest':
                return JsonResponse({'success': True})
            messages.success(request, "Dépense ajoutée avec succès.")
            return redirect('liste_depenses')
        else:
            if request.headers.get('x-requested-with') == 'XMLHttpRequest':
                return JsonResponse({'success': False, 'error': form.errors.as_json()}, status=400)
            messages.error(request, "Erreur dans le formulaire de dépense.")
            return redirect('liste_depenses?open_modal=ajouter')
    else:
        form = DepenseForm()
    return render(request, 'core/liste_depenses.html', {'form': form, 'open_modal': True})


def liste_depenses(request):
    mois = request.GET.get('mois')
    categorie_filtre = request.GET.get('categorie')
    depenses = Depense.objects.all()
    aujourdhui = date.today()
    debut_mois = date(aujourdhui.year, aujourdhui.month, 1)
    if mois:
        try:
            annee, mois_num = map(int, mois.split('-'))
            debut_mois = date(annee, mois_num, 1)
        except:
            pass
    fin_mois = (debut_mois.replace(month=debut_mois.month + 1, day=1) - timedelta(days=1)) if debut_mois.month < 12 else date(debut_mois.year, 12, 31)
    depenses_mois = depenses.filter(date__range=[debut_mois, fin_mois])
    total_depenses = depenses_mois.aggregate(total=Sum('montant'))['total'] or 0
    revenus_mois = Commande.objects.filter(date_commande__range=[debut_mois, fin_mois]).aggregate(total=Sum('montant_paye'))['total'] or 0
    rentabilite = revenus_mois - total_depenses
    categories = dict(Depense.CATEGORIES)
    resume_categories = {}
    for cat_code, cat_label in categories.items():
        total_cat = depenses_mois.filter(categorie=cat_code).aggregate(total=Sum('montant'))['total'] or 0
        resume_categories[cat_label] = total_cat
    if categorie_filtre:
        depenses = depenses.filter(categorie=categorie_filtre)
    if mois:
        depenses = depenses.filter(date__range=[debut_mois, fin_mois])
    mois_fr = {1: 'Janvier', 2: 'Février', 3: 'Mars', 4: 'Avril', 5: 'Mai', 6: 'Juin',
               7: 'Juillet', 8: 'Août', 9: 'Septembre', 10: 'Octobre', 11: 'Novembre', 12: 'Décembre'}
    mois_options = []
    for i in range(12):
        annee = aujourdhui.year
        mois_num = aujourdhui.month - i
        if mois_num <= 0:
            mois_num += 12
            annee -= 1
        mois_options.append((f"{annee}-{mois_num:02d}", f"{mois_fr[mois_num]} {annee}"))
    mois_options.reverse()
    context = {
        'depenses': depenses.order_by('-date'), 'total_depenses': total_depenses,
        'revenus_mois': revenus_mois, 'rentabilite': rentabilite,
        'resume_categories': resume_categories, 'mois_selectionne': mois,
        'categorie_filtre': categorie_filtre, 'mois_options': mois_options,
        'categories': categories, 'form': DepenseForm(),
    }
    return render(request, 'core/liste_depenses.html', context)


def modifier_depense(request, depense_id):
    depense = get_object_or_404(Depense, id=depense_id)
    if request.method == 'POST':
        form = DepenseForm(request.POST, instance=depense)
        if form.is_valid():
            form.save()
            if request.headers.get('x-requested-with') == 'XMLHttpRequest':
                return JsonResponse({'success': True})
            messages.success(request, "Dépense modifiée avec succès.")
            return redirect('liste_depenses')
        else:
            if request.headers.get('x-requested-with') == 'XMLHttpRequest':
                return JsonResponse({'success': False, 'errors': form.errors.as_json()}, status=400)
            messages.error(request, "Erreur dans la modification de la dépense.")
            return redirect('liste_depenses')
    else:
        if request.headers.get('x-requested-with') == 'XMLHttpRequest':
            data = {
                'id': depense.id, 'date': depense.date.strftime('%Y-%m-%d'),
                'categorie': depense.categorie, 'libelle': depense.libelle,
                'montant': float(depense.montant),
            }
            return JsonResponse(data)
        else:
            return redirect(f"{reverse('liste_depenses')}?open_modal=modifier&id={depense_id}")


def supprimer_depense(request, depense_id):
    depense = get_object_or_404(Depense, id=depense_id)
    if request.method == 'POST':
        depense.delete()
        messages.success(request, "Dépense supprimée avec succès.")
        return redirect('liste_depenses')
    return render(request, 'core/supprimer_depense.html', {'depense': depense})


# ==================== CALENDRIER ====================
def calendrier(request):
    commandes = Commande.objects.filter(date_livraison_prevue__isnull=False).exclude(statut='livre').order_by('date_livraison_prevue')
    return render(request, 'core/calendrier.html', {'commandes': commandes})


# ==================== AUTHENTIFICATION ====================
def inscription(request):
    if request.method == 'POST':
        form = UserCreationForm(request.POST)
        if form.is_valid():
            user = form.save()
            login(request, user)
            messages.success(request, "Inscription réussie ! Bienvenue.")
            return redirect('accueil')
        else:
            messages.error(request, "Erreur dans le formulaire d'inscription.")
    else:
        form = UserCreationForm()
    return render(request, 'core/inscription.html', {'form': form})


def connexion(request):
    if request.method == 'POST':
        form = AuthenticationForm(request, data=request.POST)
        if form.is_valid():
            username = form.cleaned_data.get('username')
            password = form.cleaned_data.get('password')
            user = authenticate(username=username, password=password)
            if user is not None:
                login(request, user)
                messages.success(request, f"Bienvenue {username} !")
                return redirect('accueil')
            else:
                messages.error(request, "Nom d'utilisateur ou mot de passe incorrect.")
        else:
            messages.error(request, "Nom d'utilisateur ou mot de passe incorrect.")
    else:
        form = AuthenticationForm()
    return render(request, 'core/connexion.html', {'form': form})


def deconnexion(request):
    logout(request)
    messages.info(request, "Vous êtes déconnecté.")
    return redirect('connexion')


# ==================== PROFIL UTILISATEUR ====================
@login_required
def mon_profil(request):
    return render(request, 'core/mon_profil.html', {'user': request.user})


@login_required
def modifier_profil(request):
    if request.method == 'POST':
        form = UserChangeForm(request.POST, instance=request.user)
        if form.is_valid():
            form.save()
            messages.success(request, "Votre profil a été mis à jour.")
            return redirect('mon_profil')
        else:
            messages.error(request, "Erreur lors de la mise à jour du profil.")
    else:
        form = UserChangeForm(instance=request.user)
    return render(request, 'core/modifier_profil.html', {'form': form})


@login_required
def changer_mot_de_passe(request):
    if request.method == 'POST':
        form = PasswordChangeForm(request.user, request.POST)
        if form.is_valid():
            user = form.save()
            update_session_auth_hash(request, user)
            messages.success(request, "Votre mot de passe a été changé.")
            return redirect('mon_profil')
        else:
            messages.error(request, "Veuillez corriger les erreurs.")
    else:
        form = PasswordChangeForm(request.user)
    return render(request, 'core/changer_mot_de_passe.html', {'form': form})


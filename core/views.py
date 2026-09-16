import calendar as cal
import json
import uuid
from datetime import date, timedelta
from decimal import Decimal, InvalidOperation

from django.contrib import messages
from django.contrib.auth import login, logout, update_session_auth_hash
from django.contrib.auth.decorators import login_required
from django.contrib.auth.forms import AuthenticationForm, PasswordChangeForm
from django.core.paginator import Paginator
from django.db import transaction
from django.db.models import Count, F, Q, Sum
from django.http import HttpResponse, JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils import timezone

from .models import (
    Accessoire, CatalogueModele, Client, Commande, Depense, Employe,
    LigneAccessoire, LigneCommande, Mensuration, MouvementStock,
    Paie, Paiement, PlanAbonnement, Profil,
)
from .forms import (
    AccessoireForm, AtelierForm, AttributionLigneForm, CatalogueModeleForm,
    ClientForm, CommandeForm, DepenseForm, EmployeForm, InscriptionSaaSForm,
    PaiementForm, ProfilForm, UtilisateurCreationForm, UtilisateurEditionForm,
    VenteDirecteForm,
)

MOIS_FR = [
    "Janvier", "Février", "Mars", "Avril", "Mai", "Juin",
    "Juillet", "Août", "Septembre", "Octobre", "Novembre", "Décembre",
]

MOIS_COURT = [
    "Jan", "Fév", "Mar", "Avr", "Mai", "Jun",
    "Jul", "Aoû", "Sep", "Oct", "Nov", "Déc",
]

PALETTE_AVATAR = [
    ('#ede9fe', '#6d28d9'), ('#e0f2fe', '#0284c7'),
    ('#ecfdf5', '#059669'), ('#fff7ed', '#ea580c'),
    ('#fdf2f8', '#db2777'), ('#eef2ff', '#4f46e5'),
]

COULEURS_CHARGE = {
    'LIBRE':     ('#ecfdf5', '#059669', 'Disponible'),
    'NORMAL':    ('#eff6ff', '#0284c7', 'Charge normale'),
    'CHARGE':    ('#fffbeb', '#d97706', 'Bien chargé'),
    'SURCHARGE': ('#fef2f2', '#e11d48', 'Surchargé'),
}


# ==========================================
# HELPERS GÉNÉRAUX
# ==========================================
def get_user_atelier(user):
    profil = getattr(user, 'profil', None)
    return profil.atelier if profil else None


def _est_admin(user):
    """Administrateur (propriétaire) de l'atelier."""
    profil = getattr(user, 'profil', None)
    return bool(profil and profil.role == 'ADMIN')


def _to_decimal(valeur, defaut='0'):
    try:
        return Decimal(str(valeur if valeur not in (None, '') else defaut))
    except (InvalidOperation, TypeError, ValueError):
        return Decimal(defaut)


def _to_int(valeur, defaut=1):
    try:
        return int(valeur)
    except (TypeError, ValueError):
        return defaut


def _to_date(valeur, defaut=None):
    """Convertit 'AAAA-MM-JJ' en date, sinon renvoie le défaut."""
    if isinstance(valeur, date):
        return valeur
    if not valeur:
        return defaut
    try:
        a, m, j = (int(x) for x in str(valeur).split('-'))
        return date(a, m, j)
    except (TypeError, ValueError):
        return defaut


def _style_avatar(pk):
    bg, fg = PALETTE_AVATAR[(pk or 0) % len(PALETTE_AVATAR)]
    return f"background:{bg}; color:{fg};"


def _ventes_directes_ids(atelier):
    """IDs des commandes sans aucune ligne de couture (= ventes directes)."""
    return Commande.objects.filter(atelier=atelier).exclude(
        lignes__type_ligne='COUTURE'
    ).filter(lignes__isnull=False).distinct().values_list('id', flat=True)


# ==========================================
# HELPERS EMPLOYÉS
# ==========================================
def _employes_json(atelier):
    """Données JSON des employés actifs pour les selects dynamiques."""
    data = []
    for emp in Employe.objects.filter(
        atelier=atelier, statut='ACTIF'
    ).order_by('nom', 'prenom'):
        data.append({
            'id': emp.id,
            'nom_complet': emp.nom_complet,
            'matricule': emp.matricule,
            'poste_label': emp.get_poste_display(),
            'specialites': emp.specialites or '',
            'en_cours': emp.nb_en_cours,
            'charge': emp.niveau_charge,
            'libelle_charge': COULEURS_CHARGE[emp.niveau_charge][2],
        })
    return json.dumps(data, default=str)


# ==========================================
# HELPERS STOCK
# ==========================================
def _modele_pour_genre(genre):
    """'PAP' -> CatalogueModele | 'ACC' -> Accessoire"""
    return CatalogueModele if genre == 'PAP' else Accessoire


def _stock_actuel(obj, genre):
    return obj.stock_pret_a_porter if genre == 'PAP' else obj.stock_disponible


def _besoins_depuis_post(lignes_data):
    """Agrège les quantités demandées. Retourne {('PAP'|'ACC', id): qte}"""
    besoins = {}
    for data in lignes_data:
        qte = _to_int(data.get('quantite'), 1)
        type_ligne = data.get('type_ligne')

        if type_ligne == 'PRET_A_PORTER' and data.get('modele_id'):
            cle = ('PAP', _to_int(data['modele_id'], 0))
        elif type_ligne == 'ACCESSOIRE' and data.get('accessoire_id'):
            cle = ('ACC', _to_int(data['accessoire_id'], 0))
        else:
            continue

        if cle[1]:
            besoins[cle] = besoins.get(cle, 0) + qte
    return besoins


def _verifier_stock(atelier, besoins):
    """Vérifie la disponibilité. Retourne (ok: bool, erreurs: list[str])."""
    erreurs = []
    for (genre, obj_id), qte in besoins.items():
        obj = _modele_pour_genre(genre).objects.filter(
            pk=obj_id, atelier=atelier).first()
        if not obj:
            erreurs.append("Un article sélectionné n'existe plus dans le catalogue.")
            continue
        if not obj.stock_suffisant(qte):
            dispo = _stock_actuel(obj, genre)
            erreurs.append(
                f"Stock insuffisant pour « {obj.nom} » : "
                f"{dispo} disponible(s) pour {qte} demandé(s)."
            )
    return (len(erreurs) == 0), erreurs


def _appliquer_stock(atelier, besoins, sens, commande=None,
                     auteur=None, type_mvt='VENTE', commentaire=''):
    """
    Applique le mouvement de stock et journalise chaque opération.
    sens = -1 (sortie / vente) | sens = +1 (entrée / annulation)
    """
    for (genre, obj_id), qte in besoins.items():
        obj = _modele_pour_genre(genre).objects.select_for_update().filter(
            pk=obj_id, atelier=atelier).first()
        if not obj:
            continue

        avant = _stock_actuel(obj, genre)
        if sens < 0:
            obj.retirer_stock(qte)
        else:
            obj.remettre_stock(qte)
        apres = _stock_actuel(obj, genre)

        MouvementStock.objects.create(
            atelier=atelier,
            type_mouvement=type_mvt,
            modele=obj if genre == 'PAP' else None,
            accessoire=obj if genre == 'ACC' else None,
            commande=commande,
            quantite=sens * qte,
            stock_avant=avant,
            stock_apres=apres,
            auteur=auteur if auteur and auteur.is_authenticated else None,
            commentaire=commentaire,
        )


def _alerter_stock(request, atelier, besoins):
    """Messages d'alerte après un mouvement de sortie."""
    for (genre, obj_id) in besoins:
        obj = _modele_pour_genre(genre).objects.filter(
            pk=obj_id, atelier=atelier).first()
        if not obj:
            continue
        statut = obj.statut_stock
        reste = _stock_actuel(obj, genre)
        if statut == 'RUPTURE':
            messages.warning(
                request, f"« {obj.nom} » est maintenant en rupture de stock.")
        elif statut == 'FAIBLE':
            messages.info(
                request, f"Stock faible : « {obj.nom} » — {reste} restant(s).")


# ==========================================
# 1. AUTHENTIFICATION & SAAS ONBOARDING
# ==========================================
def inscription_saas(request):
    if request.user.is_authenticated:
        return redirect('core:dashboard')
    if request.method == 'POST':
        form = InscriptionSaaSForm(request.POST)
        if form.is_valid():
            user, atelier = form.save()
            login(request, user)
            messages.success(
                request, f"Bienvenue chez {atelier.nom} ! Votre espace est prêt.")
            return redirect('core:dashboard')
    else:
        form = InscriptionSaaSForm()
    return render(request, 'core/inscription_saas.html', {'form': form})


def connexion(request):
    if request.user.is_authenticated:
        return redirect('core:dashboard')
    if request.method == 'POST':
        form = AuthenticationForm(request, data=request.POST)
        if form.is_valid():
            user = form.get_user()
            login(request, user)
            messages.success(
                request,
                f"Ravi de vous revoir, {user.first_name or user.username} !")
            return redirect('core:dashboard')
        messages.error(request, "Nom d'utilisateur ou mot de passe incorrect.")
    else:
        form = AuthenticationForm()
    return render(request, 'core/connexion.html', {'form': form})


@login_required
def deconnexion(request):
    logout(request)
    messages.info(request, "Vous avez été déconnecté avec succès.")
    return redirect('core:connexion')


# ==========================================
# 2. PROFIL PERSONNEL
# ==========================================
@login_required
def mon_profil(request):
    atelier = get_user_atelier(request.user)
    profil = getattr(request.user, 'profil', None)
    return render(request, 'core/mon_profil.html', {
        'profil': profil,
        'atelier': atelier,
        'style_avatar': _style_avatar(profil.pk) if profil else '',
    })


@login_required
def modifier_profil(request):
    profil = getattr(request.user, 'profil', None)
    if request.method == 'POST':
        form = ProfilForm(request.POST, request.FILES,
                          instance=profil, user=request.user)
        if form.is_valid():
            form.save()
            messages.success(request, "Votre profil a été mis à jour.")
        else:
            for field, errors in form.errors.items():
                label = form.fields[field].label if field in form.fields else field
                for err in errors:
                    messages.error(request, f"{label} : {err}")
    return redirect('core:mon_profil')


@login_required
def changer_mot_de_passe(request):
    if request.method == 'POST':
        form = PasswordChangeForm(request.user, request.POST)
        if form.is_valid():
            user = form.save()
            update_session_auth_hash(request, user)
            messages.success(request, "Votre mot de passe a été modifié avec succès.")
        else:
            for error in form.errors.values():
                messages.error(request, error)
    return redirect('core:mon_profil')


# ==========================================
# 3. DASHBOARD
# ==========================================
@login_required
def dashboard(request):
    atelier = get_user_atelier(request.user)
    if not atelier:
        messages.error(request, "Aucun atelier n'est associé à votre compte.")
        return redirect('core:connexion')

    aujourdhui = timezone.now().date()

    # ---------- Sélecteur de mois ----------
    mois_options = []
    for i in range(12):
        annee, mois_num = aujourdhui.year, aujourdhui.month - i
        while mois_num <= 0:
            mois_num += 12
            annee -= 1
        mois_options.append({
            "valeur": f"{annee}-{mois_num:02d}",
            "label": f"{MOIS_FR[mois_num - 1]} {annee}",
        })

    mois_selectionne = request.GET.get('mois') or mois_options[0]['valeur']
    try:
        annee_sel, mois_sel = (int(x) for x in mois_selectionne.split('-'))
        if not 1 <= mois_sel <= 12:
            raise ValueError
    except (ValueError, TypeError):
        annee_sel, mois_sel = aujourdhui.year, aujourdhui.month
        mois_selectionne = f"{annee_sel}-{mois_sel:02d}"
    mois_annee_fr = f"{MOIS_FR[mois_sel - 1]} {annee_sel}"

    commandes = Commande.objects.filter(atelier=atelier).select_related(
        'client'
    ).prefetch_related(
        'lignes__accessoires_ligne', 'lignes__modele',
        'lignes__employe', 'paiements'
    )

    # ---------- KPI globaux ----------
    chiffre_affaires = sum((c.prix_net for c in commandes), Decimal('0'))
    total_encaisse = Paiement.objects.filter(atelier=atelier).aggregate(
        Sum('montant'))['montant__sum'] or Decimal('0')
    reste_a_recouvrer = max(Decimal('0'), chiffre_affaires - total_encaisse)
    pct_encaisse = int(total_encaisse * 100 / chiffre_affaires) if chiffre_affaires > 0 else 0

    total_clients = Client.objects.filter(atelier=atelier).count()
    nb_commandes = commandes.count()
    commandes_en_cours = commandes.filter(statut='EN_COURS').count()
    commandes_livrees = commandes.filter(statut='LIVRE').count()
    nb_en_retard = sum(1 for c in commandes if c.est_en_retard())

    livraisons_semaine = commandes.filter(
        statut__in=['EN_ATTENTE', 'EN_COURS', 'PRET'],
        date_livraison_prevue__gte=aujourdhui,
        date_livraison_prevue__lte=aujourdhui + timedelta(days=7),
    ).count()

    # ---------- Alertes stock ----------
    pap_rupture = CatalogueModele.objects.filter(
        atelier=atelier, type_modele='PRET_A_PORTER', stock_pret_a_porter=0
    ).count()
    acc_rupture = Accessoire.objects.filter(
        atelier=atelier, stock_disponible=0).count()
    pap_faible = CatalogueModele.objects.filter(
        atelier=atelier, type_modele='PRET_A_PORTER',
        stock_pret_a_porter__gt=0,
        stock_pret_a_porter__lte=F('seuil_alerte'),
    ).count()
    acc_faible = Accessoire.objects.filter(
        atelier=atelier,
        stock_disponible__gt=0,
        stock_disponible__lte=F('seuil_alerte'),
    ).count()
    alertes_stock = pap_rupture + acc_rupture + pap_faible + acc_faible

    # ---------- Équipe ----------
    nb_employes_actifs = Employe.objects.filter(
        atelier=atelier, statut='ACTIF').count()
    coutures_non_attribuees = LigneCommande.objects.filter(
        atelier=atelier,
        type_ligne='COUTURE',
        employe__isnull=True,
        commande__statut__in=['EN_ATTENTE', 'EN_COURS', 'PRET'],
    ).count()

    # ---------- Résultat du mois ----------
    revenus_mois = Paiement.objects.filter(
        atelier=atelier,
        date_paiement__year=annee_sel,
        date_paiement__month=mois_sel,
    ).aggregate(Sum('montant'))['montant__sum'] or Decimal('0')

    depenses_mois = Depense.objects.filter(
        atelier=atelier,
        date__year=annee_sel,
        date__month=mois_sel,
    ).aggregate(Sum('montant'))['montant__sum'] or Decimal('0')

    resultat_mois = revenus_mois - depenses_mois

    # ---------- Graphique 6 derniers mois ----------
    chart_data = []
    for i in range(5, -1, -1):
        a, m = annee_sel, mois_sel - i
        while m <= 0:
            m += 12
            a -= 1
        rev = Paiement.objects.filter(
            atelier=atelier, date_paiement__year=a, date_paiement__month=m
        ).aggregate(Sum('montant'))['montant__sum'] or Decimal('0')
        dep = Depense.objects.filter(
            atelier=atelier, date__year=a, date__month=m
        ).aggregate(Sum('montant'))['montant__sum'] or Decimal('0')
        chart_data.append({
            'label': MOIS_COURT[m - 1], 'revenus': rev, 'depenses': dep})

    valeurs = [max(d['revenus'], d['depenses']) for d in chart_data]
    max_val = max(valeurs) if valeurs else Decimal('0')
    for d in chart_data:
        h_rev = int(d['revenus'] * 100 / max_val) if max_val > 0 else 0
        h_dep = int(d['depenses'] * 100 / max_val) if max_val > 0 else 0
        d['style_rev'] = f"height: {h_rev}%;"
        d['style_dep'] = f"height: {h_dep}%;"

    # ---------- Répartition par statut ----------
    COULEURS_STATUT = {
        'EN_ATTENTE': '#6366f1', 'EN_COURS': '#f59e0b',
        'PRET': '#10b981', 'LIVRE': '#38bdf8', 'ANNULE': '#ef4444',
    }
    total_stat = max(nb_commandes, 1)
    repartition = []
    for code, label in Commande.STATUTS:
        n = commandes.filter(statut=code).count()
        pct = int(n * 100 / total_stat)
        couleur = COULEURS_STATUT.get(code, '#6b7280')
        repartition.append({
            'label': label,
            'count': n,
            'style': f"width: {pct}%; background: {couleur};",
        })

    # ---------- Commandes récentes ----------
    commandes_recentes = []
    for c in commandes.order_by('-date_commande', '-id')[:6]:
        commandes_recentes.append({
            'obj': c,
            'est_vente': c.est_vente_directe,
            'nb_lignes': c.nb_lignes,
            'prix_net': c.prix_net,
            'reste': c.reste_a_payer,
            'soldee': c.est_soldee,
        })

    # ---------- Prochaines livraisons ----------
    livraisons_proches = []
    qs_liv = commandes.filter(
        statut__in=['EN_ATTENTE', 'EN_COURS', 'PRET']
    ).order_by('date_livraison_prevue')[:6]
    for c in qs_liv:
        delta = (c.date_livraison_prevue - aujourdhui).days
        premiere = c.lignes.first()
        livraisons_proches.append({
            'obj': c,
            'jour': c.date_livraison_prevue.day,
            'mois': MOIS_COURT[c.date_livraison_prevue.month - 1].upper(),
            'libelle': premiere.libelle if premiere else "—",
            'employe': premiere.nom_employe if premiere else "—",
            'delta': delta,
            'retard': delta < 0,
            'retard_jours': abs(delta),
        })

    return render(request, 'core/accueil.html', {
        'atelier': atelier,
        'mois_annee_fr': mois_annee_fr,
        'mois_options': mois_options,
        'mois_selectionne': mois_selectionne,
        'chiffre_affaires': chiffre_affaires,
        'total_encaisse': total_encaisse,
        'pct_encaisse': pct_encaisse,
        'reste_a_recouvrer': reste_a_recouvrer,
        'revenus_mois': revenus_mois,
        'depenses_mois': depenses_mois,
        'resultat_mois': resultat_mois,
        'net_mois': resultat_mois,
        'total_clients': total_clients,
        'nb_clients': total_clients,
        'nb_commandes': nb_commandes,
        'commandes_en_cours': commandes_en_cours,
        'commandes_encours': commandes_en_cours,
        'commandes_livrees': commandes_livrees,
        'livraisons_semaine': livraisons_semaine,
        'nb_en_retard': nb_en_retard,
        'alertes_stock': alertes_stock,
        'nb_employes_actifs': nb_employes_actifs,
        'coutures_non_attribuees': coutures_non_attribuees,
        'chart_data': chart_data,
        'repartition': repartition,
        'commandes_recentes': commandes_recentes,
        'livraisons_proches': livraisons_proches,
        'est_admin': _est_admin(request.user),
    })


# ==========================================
# 4. CLIENTS
# ==========================================
@login_required
def liste_clients(request):
    atelier = get_user_atelier(request.user)
    query = request.GET.get('q', '').strip()
    genre = request.GET.get('genre', '')
    origine = request.GET.get('origine', '')
    date_debut = request.GET.get('date_debut', '')
    date_fin = request.GET.get('date_fin', '')
    tri = request.GET.get('tri', 'nom')

    clients = Client.objects.filter(atelier=atelier).annotate(
        nb_commandes=Count('commandes', distinct=True),
        nb_mensurations=Count('mensurations', distinct=True),
    )

    if query:
        clients = clients.filter(
            Q(nom__icontains=query) |
            Q(prenom__icontains=query) |
            Q(telephone__icontains=query) |
            Q(email__icontains=query)
        )
    if genre in ['M', 'F']:
        clients = clients.filter(genre=genre)
    if origine:
        clients = clients.filter(origine=origine)
    if date_debut:
        clients = clients.filter(date_creation__date__gte=date_debut)
    if date_fin:
        clients = clients.filter(date_creation__date__lte=date_fin)

    TRIS = {
        'nom': ['nom', 'prenom'],
        'recent': ['-date_creation'],
        'commandes': ['-nb_commandes', 'nom'],
    }
    clients = clients.order_by(*TRIS.get(tri, TRIS['nom']))

    base = Client.objects.filter(atelier=atelier)
    aujourdhui = timezone.now().date()
    debut_mois = aujourdhui.replace(day=1)

    total_clients = base.count()
    nouveaux_mois = base.filter(date_creation__date__gte=debut_mois).count()
    avec_mensurations = base.filter(mensurations__isnull=False).distinct().count()
    actifs = base.filter(
        commandes__statut__in=['EN_ATTENTE', 'EN_COURS', 'PRET']
    ).distinct().count()

    paginator = Paginator(clients, 12)
    page_obj = paginator.get_page(request.GET.get('page'))

    rows = []
    for c in page_obj:
        total_paye = Paiement.objects.filter(
            atelier=atelier, commande__client=c
        ).aggregate(Sum('montant'))['montant__sum'] or Decimal('0')
        derniere = c.commandes.order_by('-date_commande').first()

        rows.append({
            'c': c,
            'initiales': (c.nom[:1] + (c.prenom[:1] if c.prenom else '')).upper() or '?',
            'style_avatar': _style_avatar(c.pk),
            'nb_commandes': c.nb_commandes,
            'nb_mensurations': c.nb_mensurations,
            'total_paye': total_paye,
            'derniere': derniere,
            'actif': c.commandes.filter(
                statut__in=['EN_ATTENTE', 'EN_COURS', 'PRET']).exists(),
        })

    params = request.GET.copy()
    params.pop('page', None)
    querystring = params.urlencode()

    return render(request, 'core/clients_list.html', {
        'rows': rows,
        'clients': page_obj,
        'page_obj': page_obj,
        'paginator': paginator,
        'is_paginated': page_obj.has_other_pages(),
        'query': query,
        'genre_filter': genre,
        'origine_filter': origine,
        'date_debut': date_debut,
        'date_fin': date_fin,
        'tri': tri,
        'total_clients': total_clients,
        'nouveaux_mois': nouveaux_mois,
        'avec_mensurations': avec_mensurations,
        'actifs': actifs,
        'origine_choices': Client.ORIGINE_CHOICES,
        'querystring': querystring,
        'atelier': atelier,
    })


@login_required
def ajouter_client(request):
    atelier = get_user_atelier(request.user)
    if request.method == 'POST':
        form = ClientForm(request.POST)
        if form.is_valid():
            client = form.save(commit=False)
            client.atelier = atelier
            client.save()
            messages.success(request, f"Client {client} ajouté avec succès.")
        else:
            messages.error(request, "Veuillez corriger les erreurs du formulaire.")
    return redirect('core:liste_clients')


@login_required
def detail_client(request, pk):
    """Fiche client : mensurations groupées par personne + commandes."""
    atelier = get_user_atelier(request.user)
    client = get_object_or_404(Client, pk=pk, atelier=atelier)

    mensurations = client.mensurations.all()

    groupes = {}
    for m in mensurations:
        cle = m.nom_personne
        if cle not in groupes:
            groupes[cle] = {
                'nom': m.nom_personne,
                'lien': m.get_lien_parente_display(),
                'est_client': m.est_pour_client,
                'fiches': [],
            }
        groupes[cle]['fiches'].append(m)

    groupes_tries = sorted(
        groupes.values(), key=lambda g: (not g['est_client'], g['nom']))

    commandes = client.commandes.prefetch_related(
        'lignes__accessoires_ligne', 'paiements'
    ).order_by('-date_commande')

    return render(request, 'core/detail_client.html', {
        'client': client,
        'mensurations': mensurations,
        'groupes_mensurations': groupes_tries,
        'commandes': commandes,
        'liens_parente': Mensuration.LIENS,
        'atelier': atelier,
    })


@login_required
def modifier_client(request, pk):
    atelier = get_user_atelier(request.user)
    client = get_object_or_404(Client, pk=pk, atelier=atelier)
    if request.method == 'POST':
        form = ClientForm(request.POST, instance=client)
        if form.is_valid():
            form.save()
            messages.success(request, "Informations du client mises à jour.")
        else:
            messages.error(request, "Erreur lors de la modification du client.")
    return redirect('core:detail_client', pk=client.pk)


@login_required
def supprimer_client(request, pk):
    atelier = get_user_atelier(request.user)
    client = get_object_or_404(Client, pk=pk, atelier=atelier)
    if request.method == 'POST':
        client.delete()
        messages.success(request, "Client supprimé.")
        return redirect('core:liste_clients')
    return render(request, 'core/supprimer_client.html', {
        'client': client, 'atelier': atelier,
    })


# ==========================================
# 4bis. MENSURATIONS
# ==========================================
def _extraire_champs_dynamiques(request):
    noms = request.POST.getlist('champ_nom[]')
    valeurs = request.POST.getlist('champ_valeur[]')
    donnees = {}
    for nom, valeur in zip(noms, valeurs):
        nom = (nom or '').strip()
        valeur = (valeur or '').strip()
        if nom and valeur:
            donnees[nom] = valeur
    return donnees


@login_required
def ajouter_mensuration(request, client_pk):
    atelier = get_user_atelier(request.user)
    client = get_object_or_404(Client, pk=client_pk, atelier=atelier)

    if request.method == 'POST':
        donnees = _extraire_champs_dynamiques(request)
        genre = request.POST.get('genre', 'homme')
        pour = request.POST.get('pour', 'client')

        beneficiaire = ''
        lien = 'MOI'
        if pour == 'proche':
            beneficiaire = (request.POST.get('beneficiaire') or '').strip()
            lien = request.POST.get('lien_parente') or 'AUTRE'
            if not beneficiaire:
                messages.error(request, "Indiquez le nom de la personne concernée.")
                return redirect('core:detail_client', pk=client.pk)

        libelle = (request.POST.get('libelle') or '').strip()
        if not libelle:
            libelle = f"Mesures {'Homme' if genre == 'homme' else 'Femme'}"

        if not donnees:
            messages.error(request, "Ajoutez au moins une mesure.")
            return redirect('core:detail_client', pk=client.pk)

        Mensuration.objects.create(
            atelier=atelier,
            client=client,
            beneficiaire=beneficiaire,
            lien_parente=lien,
            genre_mesure=genre,
            libelle=libelle,
            donnees=donnees,
        )
        cible = beneficiaire or str(client)
        messages.success(request, f"Mensurations enregistrées pour {cible}.")

    return redirect('core:detail_client', pk=client.pk)


@login_required
def modifier_mensuration(request, pk):
    atelier = get_user_atelier(request.user)
    mensuration = get_object_or_404(Mensuration, pk=pk, atelier=atelier)

    if request.method == 'POST':
        donnees = _extraire_champs_dynamiques(request)
        pour = request.POST.get('pour', 'client')

        if pour == 'proche':
            beneficiaire = (request.POST.get('beneficiaire') or '').strip()
            if not beneficiaire:
                messages.error(request, "Indiquez le nom de la personne concernée.")
                return redirect('core:modifier_mensuration', pk=mensuration.pk)
            mensuration.beneficiaire = beneficiaire
            mensuration.lien_parente = request.POST.get('lien_parente') or 'AUTRE'
        else:
            mensuration.beneficiaire = ''
            mensuration.lien_parente = 'MOI'

        libelle = (request.POST.get('libelle') or '').strip()
        if libelle:
            mensuration.libelle = libelle
        mensuration.genre_mesure = request.POST.get('genre', mensuration.genre_mesure)
        if donnees:
            mensuration.donnees = donnees
        mensuration.save()

        messages.success(request, "Mensurations mises à jour.")
        return redirect('core:detail_client', pk=mensuration.client.pk)

    return render(request, 'core/modifier_mensuration.html', {
        'mensuration': mensuration,
        'client': mensuration.client,
        'liens': Mensuration.LIENS,
        'atelier': atelier,
    })


@login_required
def supprimer_mensuration(request, pk):
    atelier = get_user_atelier(request.user)
    mensuration = get_object_or_404(Mensuration, pk=pk, atelier=atelier)
    client_pk = mensuration.client.pk
    if request.method == 'POST':
        mensuration.delete()
        messages.success(request, "Mensuration supprimée.")
    return redirect('core:detail_client', pk=client_pk)


@login_required
def detail_mensuration(request, pk):
    atelier = get_user_atelier(request.user)
    mensuration = get_object_or_404(Mensuration, pk=pk, atelier=atelier)
    return render(request, 'core/detail_mensuration.html', {
        'mensuration': mensuration,
        'client': mensuration.client,
        'atelier': atelier,
    })


@login_required
def mensuration_pdf(request, pk):
    from xhtml2pdf import pisa
    from django.template.loader import render_to_string

    atelier = get_user_atelier(request.user)
    mensuration = get_object_or_404(Mensuration, pk=pk, atelier=atelier)

    html = render_to_string('core/mensuration_pdf.html', {
        'mensuration': mensuration,
        'client': mensuration.client,
        'atelier': atelier,
        'date_edition': timezone.now(),
    }, request=request)

    response = HttpResponse(content_type='application/pdf')
    nom_fichier = f"mensurations_{mensuration.nom_personne}_{mensuration.id}.pdf"
    response['Content-Disposition'] = (
        f'attachment; filename="{nom_fichier.replace(" ", "_")}"')
    if pisa.CreatePDF(html, dest=response).err:
        return HttpResponse("Erreur lors de la génération du PDF.", status=500)
    return response


@login_required
def api_mensurations_client(request, client_pk):
    """API JSON — mensurations d'un client et de ses proches."""
    atelier = get_user_atelier(request.user)
    client = get_object_or_404(Client, pk=client_pk, atelier=atelier)

    mensurations = [{
        'id': m.id,
        'libelle': m.libelle,
        'libelle_complet': m.libelle_complet,
        'nom_personne': m.nom_personne,
        'lien': m.get_lien_parente_display(),
        'est_proche': not m.est_pour_client,
        'genre': m.genre_mesure,
        'nb_mesures': m.nb_mesures,
        'date_prise': m.date_prise.strftime('%d/%m/%Y') if m.date_prise else '',
    } for m in client.mensurations.all()]

    return JsonResponse({'mensurations': mensurations})


# ==========================================
# 5. CATALOGUE & ACCESSOIRES
# ==========================================
@login_required
def liste_modeles(request):
    atelier = get_user_atelier(request.user)

    modeles_couture = CatalogueModele.objects.filter(
        atelier=atelier, type_modele='COUTURE').order_by('nom')
    modeles_pap = CatalogueModele.objects.filter(
        atelier=atelier, type_modele='PRET_A_PORTER').order_by('nom')
    accessoires = Accessoire.objects.filter(
        atelier=atelier).order_by('categorie', 'nom')

    valeur_stock_pap = sum((m.valeur_stock for m in modeles_pap), Decimal('0'))
    valeur_stock_acc = sum((a.valeur_stock for a in accessoires), Decimal('0'))

    pap_rupture = modeles_pap.filter(stock_pret_a_porter=0).count()
    pap_faible = modeles_pap.filter(
        stock_pret_a_porter__gt=0,
        stock_pret_a_porter__lte=F('seuil_alerte'),
    ).count()
    acc_rupture = accessoires.filter(stock_disponible=0).count()
    acc_faible = accessoires.filter(
        stock_disponible__gt=0,
        stock_disponible__lte=F('seuil_alerte'),
    ).count()

    return render(request, 'core/modeles.html', {
        'modeles_couture': modeles_couture,
        'modeles_pap': modeles_pap,
        'accessoires': accessoires,
        'nb_couture': modeles_couture.count(),
        'nb_pap': modeles_pap.count(),
        'nb_accessoires': accessoires.count(),
        'pap_rupture': pap_rupture,
        'pap_faible': pap_faible,
        'acc_rupture': acc_rupture,
        'accessoires_stock_faible': acc_faible,
        'alertes_stock': pap_rupture + pap_faible + acc_rupture + acc_faible,
        'valeur_stock_pap': valeur_stock_pap,
        'valeur_stock_acc': valeur_stock_acc,
        'categories_acc': Accessoire.CATEGORIES,
        'unites_acc': Accessoire.UNITES,
        'atelier': atelier,
    })


@login_required
def ajouter_accessoire(request):
    atelier = get_user_atelier(request.user)
    if request.method == 'POST':
        form = AccessoireForm(request.POST, request.FILES)
        if form.is_valid():
            acc = form.save(commit=False)
            acc.atelier = atelier
            acc.save()
            if acc.stock_disponible > 0:
                MouvementStock.objects.create(
                    atelier=atelier,
                    type_mouvement='REAPPRO',
                    accessoire=acc,
                    quantite=acc.stock_disponible,
                    stock_avant=0,
                    stock_apres=acc.stock_disponible,
                    auteur=request.user,
                    commentaire="Stock initial à la création",
                )
            messages.success(request, f"Accessoire « {acc.nom} » ajouté.")
        else:
            messages.error(request, "Veuillez corriger les erreurs.")
    return redirect('core:liste_modeles')


@login_required
def modifier_accessoire(request, pk):
    atelier = get_user_atelier(request.user)
    acc = get_object_or_404(Accessoire, pk=pk, atelier=atelier)
    if request.method == 'POST':
        stock_avant = acc.stock_disponible
        form = AccessoireForm(request.POST, request.FILES, instance=acc)
        if form.is_valid():
            acc = form.save()
            delta = acc.stock_disponible - stock_avant
            if delta != 0:
                MouvementStock.objects.create(
                    atelier=atelier,
                    type_mouvement='REAPPRO' if delta > 0 else 'INVENTAIRE',
                    accessoire=acc,
                    quantite=delta,
                    stock_avant=stock_avant,
                    stock_apres=acc.stock_disponible,
                    auteur=request.user,
                    commentaire="Ajustement manuel depuis le catalogue",
                )
            messages.success(request, f"Accessoire « {acc.nom} » mis à jour.")
        else:
            messages.error(request, "Erreur lors de la modification.")
    return redirect('core:liste_modeles')


@login_required
def supprimer_accessoire(request, pk):
    atelier = get_user_atelier(request.user)
    acc = get_object_or_404(Accessoire, pk=pk, atelier=atelier)
    if request.method == 'POST':
        acc.delete()
        messages.success(request, "Accessoire supprimé.")
    return redirect('core:liste_modeles')


@login_required
def ajouter_modele(request):
    atelier = get_user_atelier(request.user)
    if request.method == 'POST':
        form = CatalogueModeleForm(request.POST, request.FILES)
        if form.is_valid():
            modele = form.save(commit=False)
            modele.atelier = atelier
            modele.save()
            if modele.est_pap and modele.stock_pret_a_porter > 0:
                MouvementStock.objects.create(
                    atelier=atelier,
                    type_mouvement='REAPPRO',
                    modele=modele,
                    quantite=modele.stock_pret_a_porter,
                    stock_avant=0,
                    stock_apres=modele.stock_pret_a_porter,
                    auteur=request.user,
                    commentaire="Stock initial à la création",
                )
            messages.success(request, f"Modèle « {modele.nom} » ajouté avec succès.")
        else:
            messages.error(request, "Veuillez corriger les erreurs du formulaire.")
    return redirect('core:liste_modeles')


@login_required
def modifier_modele(request, pk):
    atelier = get_user_atelier(request.user)
    modele = get_object_or_404(CatalogueModele, pk=pk, atelier=atelier)
    if request.method == 'POST':
        stock_avant = modele.stock_pret_a_porter
        form = CatalogueModeleForm(request.POST, request.FILES, instance=modele)
        if form.is_valid():
            modele = form.save()
            delta = modele.stock_pret_a_porter - stock_avant
            if modele.est_pap and delta != 0:
                MouvementStock.objects.create(
                    atelier=atelier,
                    type_mouvement='REAPPRO' if delta > 0 else 'INVENTAIRE',
                    modele=modele,
                    quantite=delta,
                    stock_avant=stock_avant,
                    stock_apres=modele.stock_pret_a_porter,
                    auteur=request.user,
                    commentaire="Ajustement manuel depuis le catalogue",
                )
            messages.success(request, "Modèle mis à jour.")
        else:
            messages.error(request, "Erreur lors de la modification du modèle.")
    return redirect('core:liste_modeles')


@login_required
def supprimer_modele(request, pk):
    atelier = get_user_atelier(request.user)
    modele = get_object_or_404(CatalogueModele, pk=pk, atelier=atelier)
    if request.method == 'POST':
        modele.delete()
        messages.success(request, "Modèle supprimé.")
    return redirect('core:liste_modeles')


# ==========================================
# 6. COMMANDES — HELPERS
# ==========================================
def _extraire_lignes_post(post_data, files_data=None):
    """Extrait les lignes depuis le POST (ligne_count + ligne_i_<champ>)."""
    lignes = []
    count = _to_int(post_data.get('ligne_count', 0), 0)

    for i in range(1, count + 1):
        prefix = f'ligne_{i}_'
        lignes.append({
            'index': i,
            'type_ligne': post_data.get(f'{prefix}type', 'COUTURE'),
            'modele_id': post_data.get(f'{prefix}modele_id', ''),
            'description': post_data.get(f'{prefix}description', ''),
            'prix_unitaire': post_data.get(f'{prefix}prix_unitaire', 0),
            'quantite': post_data.get(f'{prefix}quantite', 1),
            'remise_type': post_data.get(f'{prefix}remise_type', ''),
            'remise_valeur': post_data.get(f'{prefix}remise_valeur', 0),
            'client_secondaire_id': post_data.get(f'{prefix}client_secondaire_id', ''),
            'mensuration_id': post_data.get(f'{prefix}mensuration_id', ''),
            'accessoire_id': post_data.get(f'{prefix}accessoire_id', ''),
            'employe_id': post_data.get(f'{prefix}employe_id', ''),
            'accessoires_ids': post_data.getlist(f'{prefix}acc_ids[]'),
            'accessoires_qtes': post_data.getlist(f'{prefix}acc_qtes[]'),
            'accessoires_prix': post_data.getlist(f'{prefix}acc_prix[]'),
        })
    return lignes


def _creer_ligne_couture(atelier, commande, data, ordre, files=None):
    """Crée une LigneCommande de type COUTURE + ses accessoires liés."""
    ligne = LigneCommande(
        atelier=atelier,
        commande=commande,
        type_ligne='COUTURE',
        ordre=ordre,
        prix_unitaire=_to_decimal(data.get('prix_unitaire')),
        quantite=_to_int(data.get('quantite'), 1),
        description=data.get('description', ''),
        remise_type=data.get('remise_type') or None,
        remise_valeur=_to_decimal(data.get('remise_valeur')),
    )

    modele_id = data.get('modele_id')
    if modele_id:
        ligne.modele = CatalogueModele.objects.filter(
            pk=modele_id, atelier=atelier).first()

    client_sec_id = data.get('client_secondaire_id')
    if client_sec_id:
        ligne.client_secondaire = Client.objects.filter(
            pk=client_sec_id, atelier=atelier).first()

    mensuration_id = data.get('mensuration_id')
    if mensuration_id:
        ligne.mensuration = Mensuration.objects.filter(
            pk=mensuration_id, atelier=atelier).first()

    # --- Couturier : spécifique à la ligne, sinon celui de la commande ---
    employe_id = data.get('employe_id')
    if employe_id:
        ligne.employe = Employe.objects.filter(
            pk=employe_id, atelier=atelier).first()
    elif commande.employe_attribue_id:
        ligne.employe_id = commande.employe_attribue_id

    if files:
        idx = data.get('index', ordre)
        cle_tissu = f'ligne_{idx}_photo_tissu'
        cle_modele = f'ligne_{idx}_photo_modele_custom'
        if cle_tissu in files:
            ligne.photo_tissu = files[cle_tissu]
        if cle_modele in files:
            ligne.photo_modele_custom = files[cle_modele]

    ligne.save()

    for acc_id, qte, prix in zip(
        data.get('accessoires_ids', []),
        data.get('accessoires_qtes', []),
        data.get('accessoires_prix', []),
    ):
        if not acc_id:
            continue
        acc = Accessoire.objects.filter(pk=acc_id, atelier=atelier).first()
        if not acc:
            continue
        LigneAccessoire.objects.create(
            atelier=atelier,
            ligne=ligne,
            accessoire=acc,
            quantite=_to_int(qte, 1),
            prix_unitaire=_to_decimal(prix, str(acc.prix_unitaire)),
        )

    return ligne


def _sync_lignes_couture(request, commande, atelier):
    """Ajoute les nouvelles lignes envoyées par le formulaire d'édition."""
    lignes_data = _extraire_lignes_post(request.POST, request.FILES)
    ordre = commande.lignes.count() + 1
    for data in lignes_data:
        _creer_ligne_couture(atelier, commande, data, ordre, request.FILES)
        ordre += 1
    return commande.lignes.count()


# ==========================================
# 6bis. COMMANDES — VUES
# ==========================================
@login_required
def liste_commandes(request):
    atelier = get_user_atelier(request.user)
    statut_filter = request.GET.get('statut', '')
    paiement_filter = request.GET.get('paiement', '')
    employe_filter = request.GET.get('employe', '')
    q = request.GET.get('q', '').strip()
    date_debut = request.GET.get('date_debut', '')
    date_fin = request.GET.get('date_fin', '')

    ventes_ids = _ventes_directes_ids(atelier)

    commandes = Commande.objects.filter(atelier=atelier).exclude(
        id__in=ventes_ids
    ).select_related('client', 'employe_attribue').prefetch_related(
        'lignes__accessoires_ligne', 'lignes__modele',
        'lignes__employe', 'paiements'
    ).order_by('-date_commande', '-id')

    if statut_filter:
        commandes = commandes.filter(statut=statut_filter)
    if employe_filter == 'AUCUN':
        commandes = commandes.filter(
            lignes__type_ligne='COUTURE', lignes__employe__isnull=True
        ).distinct()
    elif employe_filter:
        commandes = commandes.filter(
            Q(employe_attribue_id=employe_filter) |
            Q(lignes__employe_id=employe_filter)
        ).distinct()
    if q:
        commandes = commandes.filter(
            Q(code__icontains=q) |
            Q(client__nom__icontains=q) |
            Q(client__prenom__icontains=q) |
            Q(client__telephone__icontains=q)
        )
    if date_debut:
        commandes = commandes.filter(date_commande__gte=date_debut)
    if date_fin:
        commandes = commandes.filter(date_commande__lte=date_fin)

    if paiement_filter == 'soldee':
        commandes = [c for c in commandes if c.est_soldee]
    elif paiement_filter == 'non_soldee':
        commandes = [c for c in commandes if not c.est_soldee]

    toutes = Commande.objects.filter(atelier=atelier).exclude(
        id__in=ventes_ids
    ).prefetch_related('lignes__accessoires_ligne', 'paiements')

    total_ca = sum((c.prix_net for c in toutes), Decimal('0'))
    total_encaisse = Paiement.objects.filter(
        atelier=atelier, commande__in=toutes
    ).aggregate(Sum('montant'))['montant__sum'] or Decimal('0')
    total_reste = max(Decimal('0'), total_ca - total_encaisse)
    nb_en_retard = sum(1 for c in toutes if c.est_en_retard())

    nb_non_attribuees = LigneCommande.objects.filter(
        atelier=atelier,
        type_ligne='COUTURE',
        employe__isnull=True,
        commande__statut__in=['EN_ATTENTE', 'EN_COURS', 'PRET'],
    ).count()

    paginator = Paginator(commandes, 15)
    page_obj = paginator.get_page(request.GET.get('page'))

    rows = []
    for c in page_obj:
        pct = c.pct_paye
        if c.est_soldee:
            couleur = '#10b981'
        elif pct > 0:
            couleur = '#f59e0b'
        else:
            couleur = '#e11d48'

        employes = c.employes_impliques
        rows.append({
            'c': c,
            'pct': pct,
            'style': f"width: {pct}%; background: {couleur};",
            'premiere_ligne': c.lignes.first(),
            'employes': employes,
            'nom_employes': ', '.join(e.nom_complet for e in employes) or None,
            'manque_attribution': c.nb_lignes_non_attribuees,
            'pct_avancement': c.pct_avancement,
        })

    clients_data = list(
        Client.objects.filter(atelier=atelier).values(
            'id', 'nom', 'prenom', 'telephone'
        ).order_by('nom', 'prenom')
    )
    catalogue = list(
        CatalogueModele.objects.filter(
            atelier=atelier, type_modele='COUTURE'
        ).values('id', 'nom', 'prix_base', 'type_modele')
    )
    accessoires_data = list(
        Accessoire.objects.filter(atelier=atelier).values(
            'id', 'nom', 'prix_unitaire', 'unite', 'stock_disponible'
        )
    )

    return render(request, 'core/commandes.html', {
        'rows': rows,
        'commandes': page_obj,
        'page_obj': page_obj,
        'is_paginated': page_obj.has_other_pages(),
        'statuts': Commande.STATUTS,
        'statut_selected': statut_filter,
        'paiement_filter': paiement_filter,
        'employe_filter': employe_filter,
        'employes': Employe.objects.filter(atelier=atelier, statut='ACTIF'),
        'q': q,
        'date_debut': date_debut,
        'date_fin': date_fin,
        'total_ca': total_ca,
        'total_encaisse': total_encaisse,
        'total_reste': total_reste,
        'nb_en_retard': nb_en_retard,
        'nb_non_attribuees': nb_non_attribuees,
        'form_commande': CommandeForm(atelier=atelier),
        'atelier': atelier,
        'clients_json': json.dumps(clients_data, default=str),
        'catalogue_json': json.dumps(catalogue, default=str),
        'accessoires_json': json.dumps(accessoires_data, default=str),
        'employes_json': _employes_json(atelier),
    })


@login_required
def creer_commande(request):
    """Création d'une commande de COUTURE SUR MESURE uniquement."""
    atelier = get_user_atelier(request.user)

    if request.method != 'POST':
        return redirect('core:liste_commandes')

    form = CommandeForm(request.POST, atelier=atelier)

    if not form.is_valid():
        if request.headers.get('x-requested-with') == 'XMLHttpRequest':
            return JsonResponse({'success': False, 'errors': form.errors}, status=400)
        for field, errors in form.errors.items():
            for error in errors:
                label = form.fields[field].label if field in form.fields else field
                messages.error(request, f"{label} : {error}")
        return redirect('core:liste_commandes')

    lignes_data = _extraire_lignes_post(request.POST, request.FILES)
    if not lignes_data:
        messages.error(request, "Ajoutez au moins une couture à la commande.")
        return redirect('core:liste_commandes')

    with transaction.atomic():
        commande = form.save(commit=False)
        commande.atelier = atelier
        commande.save()

        ordre = 1
        for data in lignes_data:
            _creer_ligne_couture(atelier, commande, data, ordre, request.FILES)
            ordre += 1

        if commande.nb_lignes == 0:
            transaction.set_rollback(True)
            messages.error(request, "Ajoutez au moins une couture à la commande.")
            return redirect('core:liste_commandes')

        acompte = _to_decimal(form.cleaned_data.get('acompte'))
        if acompte > 0:
            acompte = min(acompte, commande.prix_net)
            Paiement.objects.create(
                atelier=atelier,
                commande=commande,
                montant=acompte,
                mode_paiement=form.cleaned_data.get('acompte_mode') or 'ESPECES',
            )
            messages.success(
                request,
                f"Commande {commande.code} créée avec {commande.nb_lignes} "
                f"couture(s) — acompte de {acompte} {atelier.devise} enregistré."
            )
        else:
            messages.success(
                request,
                f"Commande {commande.code} créée avec {commande.nb_lignes} couture(s)."
            )

        if commande.nb_lignes_non_attribuees:
            messages.warning(
                request,
                f"{commande.nb_lignes_non_attribuees} couture(s) sans couturier "
                f"attribué. Pensez à les affecter."
            )

    return redirect('core:recu_paiement', pk=commande.pk)


@login_required
def detail_commande(request, pk):
    atelier = get_user_atelier(request.user)
    commande = get_object_or_404(
        Commande.objects.select_related('client', 'employe_attribue'),
        pk=pk, atelier=atelier)

    lignes = commande.lignes.select_related(
        'modele', 'client_secondaire', 'mensuration', 'employe'
    ).prefetch_related('accessoires_ligne__accessoire').order_by('ordre')

    lignes_data = []
    for l in lignes:
        lignes_data.append({
            'l': l,
            'employe': l.employe,
            'commission': l.commission_due,
            'style_avatar': _style_avatar(l.employe_id) if l.employe_id else '',
        })

    clients_data = list(
        Client.objects.filter(atelier=atelier).values(
            'id', 'nom', 'prenom', 'telephone'
        ).order_by('nom', 'prenom')
    )
    catalogue = list(
        CatalogueModele.objects.filter(
            atelier=atelier, type_modele='COUTURE'
        ).values('id', 'nom', 'prix_base', 'type_modele')
    )
    accessoires_data = list(
        Accessoire.objects.filter(atelier=atelier).values(
            'id', 'nom', 'prix_unitaire', 'unite'
        )
    )

    return render(request, 'core/detail_commande.html', {
        'commande': commande,
        'lignes': lignes,
        'lignes_data': lignes_data,
        'paiements': commande.paiements.all().order_by('date_paiement'),
        'form_paiement': PaiementForm(atelier=atelier),
        'form_commande_modif': CommandeForm(instance=commande, atelier=atelier),
        'modes_paiement': Paiement.MODES_PAIEMENT,
        'etats_travail': LigneCommande.ETATS_TRAVAIL,
        'employes': Employe.objects.filter(atelier=atelier, statut='ACTIF'),
        'total_commissions': commande.total_commissions,
        'marge': commande.marge_apres_commissions,
        'pct_avancement': commande.pct_avancement,
        'reste_int': int(commande.reste_a_payer),
        'prix_net_int': int(commande.prix_net),
        'atelier': atelier,
        'clients_json': json.dumps(clients_data, default=str),
        'catalogue_json': json.dumps(catalogue, default=str),
        'accessoires_json': json.dumps(accessoires_data, default=str),
        'employes_json': _employes_json(atelier),
    })


@login_required
def modifier_commande(request, pk):
    atelier = get_user_atelier(request.user)
    commande = get_object_or_404(Commande, pk=pk, atelier=atelier)

    if request.method != 'POST':
        return redirect('core:detail_commande', pk=commande.pk)

    form = CommandeForm(request.POST, instance=commande, atelier=atelier)
    if not form.is_valid():
        for field, errors in form.errors.items():
            for error in errors:
                label = form.fields[field].label if field in form.fields else field
                messages.error(request, f"{label} : {error}")
        return redirect('core:detail_commande', pk=commande.pk)

    with transaction.atomic():
        commande = form.save(commit=False)
        commande.date_livraison_effective = (
            request.POST.get('date_livraison_effective') or None
        )
        commande.save()

        # Propage le couturier aux lignes non attribuées
        if commande.employe_attribue_id and request.POST.get('propager_employe'):
            commande.lignes.filter(
                type_ligne='COUTURE', employe__isnull=True
            ).update(employe_id=commande.employe_attribue_id)

        _sync_lignes_couture(request, commande, atelier)

    messages.success(request, f"Commande {commande.code} mise à jour.")
    return redirect('core:detail_commande', pk=commande.pk)


@login_required
def supprimer_commande(request, pk):
    """Supprime une commande et restitue le stock si nécessaire."""
    atelier = get_user_atelier(request.user)
    commande = get_object_or_404(Commande, pk=pk, atelier=atelier)

    if request.method == 'POST':
        code = commande.code
        with transaction.atomic():
            if commande.stock_decremente:
                besoins = commande.besoins_stock()
                _appliquer_stock(
                    atelier, besoins, sens=+1,
                    commande=None, auteur=request.user,
                    type_mvt='ANNULATION',
                    commentaire=f"Suppression de la commande {code}",
                )
            commande.delete()
        messages.success(request, f"Commande {code} supprimée — stock restitué.")
        return redirect('core:liste_commandes')

    return render(request, 'core/supprimer_commande.html', {
        'commande': commande, 'atelier': atelier,
    })


@login_required
def ajouter_ligne(request, commande_pk):
    """Ajoute une ou plusieurs coutures à une commande existante."""
    atelier = get_user_atelier(request.user)
    commande = get_object_or_404(Commande, pk=commande_pk, atelier=atelier)

    if request.method != 'POST':
        return redirect('core:detail_commande', pk=commande.pk)

    lignes_data = _extraire_lignes_post(request.POST, request.FILES)
    if not lignes_data:
        messages.error(request, "Aucune couture à ajouter.")
        return redirect('core:detail_commande', pk=commande.pk)

    with transaction.atomic():
        ordre = commande.lignes.count() + 1
        for data in lignes_data:
            _creer_ligne_couture(atelier, commande, data, ordre, request.FILES)
            ordre += 1

    messages.success(
        request, f"{len(lignes_data)} couture(s) ajoutée(s) à la commande.")
    return redirect('core:detail_commande', pk=commande.pk)


@login_required
def supprimer_ligne(request, pk):
    atelier = get_user_atelier(request.user)
    ligne = get_object_or_404(LigneCommande, pk=pk, atelier=atelier)
    commande = ligne.commande

    if request.method == 'POST':
        if commande.nb_lignes <= 1:
            messages.error(
                request,
                "Impossible : la commande doit contenir au moins une ligne. "
                "Supprimez la commande entière si nécessaire."
            )
        else:
            with transaction.atomic():
                if commande.stock_decremente and ligne.impacte_stock:
                    genre, obj_id = ligne.cle_stock
                    _appliquer_stock(
                        atelier, {(genre, obj_id): ligne.quantite}, sens=+1,
                        commande=commande, auteur=request.user,
                        type_mvt='ANNULATION',
                        commentaire="Ligne retirée de la commande",
                    )
                ligne.delete()
                for i, l in enumerate(commande.lignes.order_by('ordre'), start=1):
                    if l.ordre != i:
                        l.ordre = i
                        l.save(update_fields=['ordre'])
            messages.success(request, "Ligne supprimée.")

    return redirect('core:detail_commande', pk=commande.pk)


@login_required
def attribuer_ligne(request, pk):
    """Attribue ou réattribue une couture à un employé + change son état."""
    atelier = get_user_atelier(request.user)
    ligne = get_object_or_404(LigneCommande, pk=pk, atelier=atelier)

    if request.method != 'POST':
        return redirect('core:detail_commande', pk=ligne.commande.pk)

    form = AttributionLigneForm(request.POST, instance=ligne, atelier=atelier)
    if form.is_valid():
        ligne = form.save(commit=False)

        # Horodatage automatique selon l'état
        if ligne.etat_travail == 'EN_COURS' and not ligne.date_debut_travail:
            ligne.date_debut_travail = timezone.now().date()
        if ligne.etat_travail == 'TERMINE' and not ligne.date_fin_travail:
            ligne.date_fin_travail = timezone.now().date()
        if ligne.etat_travail == 'A_FAIRE':
            ligne.date_debut_travail = None
            ligne.date_fin_travail = None

        ligne.save()
        messages.success(
            request,
            f"Couture « {ligne.libelle} » → {ligne.nom_employe} "
            f"({ligne.get_etat_travail_display()})."
        )
    else:
        messages.error(request, "Attribution impossible, vérifiez les champs.")

    return redirect('core:detail_commande', pk=ligne.commande.pk)


@login_required
def ajouter_paiement(request, commande_pk):
    atelier = get_user_atelier(request.user)
    commande = get_object_or_404(Commande, pk=commande_pk, atelier=atelier)

    if request.method == 'POST':
        montant = _to_decimal(request.POST.get('montant'))
        mode_paiement = request.POST.get('mode_paiement', 'ESPECES')
        reference = request.POST.get('reference_transaction', '').strip()

        if montant <= 0:
            messages.error(request, "Montant invalide.")
            return redirect('core:detail_commande', pk=commande.pk)

        if montant > commande.reste_a_payer:
            montant = commande.reste_a_payer
            messages.warning(
                request,
                f"Montant ajusté au reste à payer : {montant} {atelier.devise}."
            )

        Paiement.objects.create(
            atelier=atelier,
            commande=commande,
            montant=montant,
            mode_paiement=mode_paiement,
            reference_transaction=reference or None,
        )

        commande.refresh_from_db()
        reste = commande.reste_a_payer
        if reste == 0:
            messages.success(
                request,
                f"Paiement de {montant} {atelier.devise} enregistré. "
                f"Commande soldée !"
            )
        else:
            messages.success(
                request,
                f"Paiement de {montant} {atelier.devise} enregistré. "
                f"Reste : {reste} {atelier.devise}."
            )

    return redirect('core:detail_commande', pk=commande.pk)


@login_required
def finaliser_commande(request, pk):
    """
    Solde la commande, la marque livrée, termine les coutures
    et consomme les accessoires rattachés.
    """
    atelier = get_user_atelier(request.user)
    commande = get_object_or_404(Commande, pk=pk, atelier=atelier)

    if request.method != 'POST':
        return redirect('core:detail_commande', pk=commande.pk)

    mode_paiement = request.POST.get('mode_paiement', 'ESPECES')
    reference = request.POST.get('reference_transaction', '').strip()
    aujourdhui = timezone.now().date()

    with transaction.atomic():
        if commande.reste_a_payer > 0:
            Paiement.objects.create(
                atelier=atelier,
                commande=commande,
                montant=commande.reste_a_payer,
                mode_paiement=mode_paiement,
                reference_transaction=reference or None,
            )

        # Toutes les coutures passent en terminé
        commande.lignes.filter(
            type_ligne='COUTURE'
        ).exclude(etat_travail='TERMINE').update(
            etat_travail='TERMINE',
            date_fin_travail=aujourdhui,
        )

        # Consommation des accessoires utilisés en atelier
        if not commande.stock_decremente:
            besoins_acc = {}
            for ligne in commande.lignes.prefetch_related('accessoires_ligne'):
                for la in ligne.accessoires_ligne.all():
                    cle = ('ACC', la.accessoire_id)
                    besoins_acc[cle] = besoins_acc.get(cle, 0) + la.quantite
            if besoins_acc:
                _appliquer_stock(
                    atelier, besoins_acc, sens=-1,
                    commande=commande, auteur=request.user,
                    type_mvt='CONSOMMATION',
                    commentaire="Accessoires consommés à la livraison",
                )
                commande.stock_decremente = True

        commande.statut = 'LIVRE'
        commande.date_livraison_effective = aujourdhui
        commande.save()

    total_comm = commande.total_commissions
    if total_comm > 0:
        messages.info(
            request,
            f"Commissions à verser pour cette commande : "
            f"{total_comm} {atelier.devise}."
        )

    messages.success(
        request, f"Commande {commande.code} finalisée et marquée comme livrée !")
    return redirect('core:facture_commande', pk=commande.pk)


# ==========================================
# 6ter. FICHES ATELIER (BON DE TRAVAIL)
# ==========================================
@login_required
def fiche_atelier_pdf(request, pk):
    """Bon de travail : toutes les coutures de la commande avec mensurations."""
    from xhtml2pdf import pisa
    from django.template.loader import render_to_string

    atelier = get_user_atelier(request.user)
    commande = get_object_or_404(Commande, pk=pk, atelier=atelier)

    lignes = commande.lignes.filter(type_ligne='COUTURE').select_related(
        'modele', 'client_secondaire', 'mensuration', 'employe'
    ).prefetch_related('accessoires_ligne__accessoire').order_by('ordre')

    # Filtre optionnel par employé : ?employe=3
    employe_id = request.GET.get('employe')
    employe = None
    if employe_id:
        employe = Employe.objects.filter(pk=employe_id, atelier=atelier).first()
        if employe:
            lignes = lignes.filter(employe=employe)

    html = render_to_string('core/fiche_atelier_pdf.html', {
        'commande': commande,
        'lignes': lignes,
        'employe_filtre': employe,
        'atelier': atelier,
        'date_edition': timezone.now(),
    }, request=request)

    response = HttpResponse(content_type='application/pdf')
    suffixe = f"_{employe.matricule}" if employe else ""
    response['Content-Disposition'] = (
        f'attachment; filename="fiche_atelier_{commande.code}{suffixe}.pdf"'
    )
    if pisa.CreatePDF(html, dest=response).err:
        return HttpResponse("Erreur lors de la génération du PDF.", status=500)
    return response


@login_required
def fiche_ligne_pdf(request, pk):
    """Bon de travail : une seule couture."""
    from xhtml2pdf import pisa
    from django.template.loader import render_to_string

    atelier = get_user_atelier(request.user)
    ligne = get_object_or_404(
        LigneCommande.objects.select_related(
            'commande__client', 'modele', 'mensuration', 'employe'),
        pk=pk, atelier=atelier)

    html = render_to_string('core/fiche_atelier_pdf.html', {
        'commande': ligne.commande,
        'lignes': [ligne],
        'atelier': atelier,
        'date_edition': timezone.now(),
    }, request=request)

    response = HttpResponse(content_type='application/pdf')
    response['Content-Disposition'] = (
        f'attachment; filename="fiche_{ligne.commande.code}_L{ligne.ordre}.pdf"'
    )
    if pisa.CreatePDF(html, dest=response).err:
        return HttpResponse("Erreur lors de la génération du PDF.", status=500)
    return response


# ==========================================
# 7. VENTES DIRECTES
# ==========================================
@login_required
def liste_ventes_directes(request):
    atelier = get_user_atelier(request.user)
    q = request.GET.get('q', '').strip()
    date_debut = request.GET.get('date_debut', '')
    date_fin = request.GET.get('date_fin', '')
    statut_filter = request.GET.get('statut', '')

    ventes = Commande.objects.filter(
        atelier=atelier, id__in=_ventes_directes_ids(atelier)
    ).select_related('client').prefetch_related(
        'lignes__modele', 'lignes__accessoire', 'paiements'
    )

    if q:
        ventes = ventes.filter(
            Q(code__icontains=q) |
            Q(client__nom__icontains=q) |
            Q(client__prenom__icontains=q) |
            Q(client__telephone__icontains=q)
        )
    if date_debut:
        ventes = ventes.filter(date_commande__gte=date_debut)
    if date_fin:
        ventes = ventes.filter(date_commande__lte=date_fin)
    if statut_filter == 'ANNULE':
        ventes = ventes.filter(statut='ANNULE')
    elif statut_filter == 'VALIDE':
        ventes = ventes.exclude(statut='ANNULE')

    ventes = ventes.order_by('-date_commande', '-id')

    toutes = Commande.objects.filter(
        atelier=atelier, id__in=_ventes_directes_ids(atelier)
    ).prefetch_related('lignes', 'paiements')
    valides = [v for v in toutes if v.statut != 'ANNULE']
    annulees = [v for v in toutes if v.statut == 'ANNULE']

    total_ventes = sum((v.prix_net for v in valides), Decimal('0'))
    total_encaisse = Paiement.objects.filter(
        atelier=atelier, commande__in=[v.pk for v in valides]
    ).aggregate(Sum('montant'))['montant__sum'] or Decimal('0')

    aujourdhui = timezone.now().date()
    ventes_jour = [v for v in valides if v.date_commande == aujourdhui]
    total_jour = sum((v.prix_net for v in ventes_jour), Decimal('0'))

    paginator = Paginator(ventes, 15)
    page_obj = paginator.get_page(request.GET.get('page'))

    rows = []
    for v in page_obj:
        articles = [l.libelle for l in v.lignes.all()[:3]]
        rows.append({
            'v': v,
            'resume': ' · '.join(articles),
            'nb_lignes': v.nb_lignes,
            'prix_net': v.prix_net,
            'annulee': v.statut == 'ANNULE',
            'paiement': v.paiements.first(),
        })

    pap_data = list(
        CatalogueModele.objects.filter(
            atelier=atelier, type_modele='PRET_A_PORTER'
        ).values('id', 'nom', 'prix_base', 'couleur',
                 'taille_disponible', 'stock_pret_a_porter').order_by('nom')
    )
    acc_data = list(
        Accessoire.objects.filter(atelier=atelier).values(
            'id', 'nom', 'prix_unitaire', 'unite',
            'categorie', 'stock_disponible'
        ).order_by('nom')
    )

    return render(request, 'core/ventes_directes.html', {
        'rows': rows,
        'ventes': page_obj,
        'page_obj': page_obj,
        'is_paginated': page_obj.has_other_pages(),
        'q': q,
        'date_debut': date_debut,
        'date_fin': date_fin,
        'statut_filter': statut_filter,
        'total_ventes': total_ventes,
        'total_encaisse': total_encaisse,
        'total_jour': total_jour,
        'nb_jour': len(ventes_jour),
        'nb_annulees': len(annulees),
        'total_annulees': sum((v.prix_net for v in annulees), Decimal('0')),
        'nb_total': len(valides),
        'atelier': atelier,
        'form_vente_directe': VenteDirecteForm(),
        'pap_json': json.dumps(pap_data, default=str),
        'acc_json': json.dumps(acc_data, default=str),
    })


@login_required
def creer_vente_directe(request):
    """Encaisse une vente au comptant et décrémente le stock."""
    atelier = get_user_atelier(request.user)

    if request.method != 'POST':
        return redirect('core:liste_ventes_directes')

    form = VenteDirecteForm(request.POST)
    if not form.is_valid():
        for field, errors in form.errors.items():
            for error in errors:
                label = form.fields[field].label if field in form.fields else field
                messages.error(request, f"{label} : {error}")
        return redirect('core:liste_ventes_directes')

    nom_client = (form.cleaned_data.get('nom_client') or '').strip()
    telephone_client = (form.cleaned_data.get('telephone_client') or '').strip()
    mode_paiement = form.cleaned_data['mode_paiement']

    lignes_data = [
        l for l in _extraire_lignes_post(request.POST, request.FILES)
        if l.get('type_ligne') != 'COUTURE'
    ]
    if not lignes_data:
        messages.error(
            request, "Ajoutez au moins un article pour enregistrer la vente.")
        return redirect('core:liste_ventes_directes')

    besoins = _besoins_depuis_post(lignes_data)
    commande = None

    try:
        with transaction.atomic():
            ok, erreurs = _verifier_stock(atelier, besoins)
            if not ok:
                for e in erreurs:
                    messages.error(request, e)
                raise ValueError('stock')

            if nom_client:
                client, _ = Client.objects.get_or_create(
                    atelier=atelier,
                    nom=nom_client,
                    defaults={'telephone': telephone_client or 'N/A'},
                )
            else:
                client, _ = Client.objects.get_or_create(
                    atelier=atelier,
                    nom='Client de passage',
                    defaults={'telephone': 'N/A'},
                )

            commande = Commande(
                atelier=atelier,
                client=client,
                statut='LIVRE',
                date_livraison_prevue=timezone.now().date(),
                date_livraison_effective=timezone.now().date(),
                code=f"VTE-{uuid.uuid4().hex[:6].upper()}",
            )
            commande.save()

            ordre = 1
            for data in lignes_data:
                type_ligne = data.get('type_ligne', 'ACCESSOIRE')
                ligne = LigneCommande(
                    atelier=atelier,
                    commande=commande,
                    type_ligne=type_ligne,
                    ordre=ordre,
                    prix_unitaire=_to_decimal(data.get('prix_unitaire')),
                    quantite=_to_int(data.get('quantite'), 1),
                    remise_type=data.get('remise_type') or None,
                    remise_valeur=_to_decimal(data.get('remise_valeur')),
                )

                modele_id = data.get('modele_id')
                if modele_id:
                    ligne.modele = CatalogueModele.objects.filter(
                        pk=modele_id, atelier=atelier).first()

                accessoire_id = data.get('accessoire_id')
                if accessoire_id and type_ligne == 'ACCESSOIRE':
                    ligne.accessoire = Accessoire.objects.filter(
                        pk=accessoire_id, atelier=atelier).first()

                ligne.save()
                ordre += 1

            if commande.nb_lignes == 0:
                messages.error(request, "Aucun article valide dans cette vente.")
                raise ValueError('vide')

            _appliquer_stock(
                atelier, besoins, sens=-1,
                commande=commande, auteur=request.user,
                type_mvt='VENTE',
                commentaire=f"Vente directe {commande.code}",
            )
            commande.stock_decremente = True
            commande.save(update_fields=['stock_decremente'])

            Paiement.objects.create(
                atelier=atelier,
                commande=commande,
                montant=commande.prix_net,
                mode_paiement=mode_paiement,
            )

    except ValueError:
        return redirect('core:liste_ventes_directes')

    _alerter_stock(request, atelier, besoins)
    messages.success(
        request,
        f"Vente {commande.code} enregistrée — "
        f"{commande.prix_net} {atelier.devise} encaissés."
    )
    return redirect('core:recu_caisse', pk=commande.pk)


@login_required
def annuler_vente_directe(request, pk):
    """Annule une vente et remet les articles en stock."""
    atelier = get_user_atelier(request.user)
    commande = get_object_or_404(Commande, pk=pk, atelier=atelier)

    if request.method != 'POST':
        return redirect('core:liste_ventes_directes')

    if commande.est_annulee:
        messages.info(request, f"La vente {commande.code} est déjà annulée.")
        return redirect('core:liste_ventes_directes')

    with transaction.atomic():
        restitue = False
        if commande.stock_decremente:
            besoins = commande.besoins_stock()
            if besoins:
                _appliquer_stock(
                    atelier, besoins, sens=+1,
                    commande=commande, auteur=request.user,
                    type_mvt='ANNULATION',
                    commentaire=f"Annulation de la vente {commande.code}",
                )
                restitue = True
            commande.stock_decremente = False

        commande.statut = 'ANNULE'
        commande.save(update_fields=['statut', 'stock_decremente'])

    if restitue:
        messages.success(
            request,
            f"Vente {commande.code} annulée — les articles ont été remis en stock."
        )
    else:
        messages.success(request, f"Vente {commande.code} annulée.")
    return redirect('core:liste_ventes_directes')


@login_required
def detail_vente_directe(request, pk):
    atelier = get_user_atelier(request.user)
    commande = get_object_or_404(Commande, pk=pk, atelier=atelier)
    return render(request, 'core/detail_vente_directe.html', {
        'commande': commande,
        'lignes': commande.lignes.select_related(
            'modele', 'accessoire'
        ).prefetch_related('accessoires_ligne__accessoire').all(),
        'paiements': commande.paiements.order_by('date_paiement'),
        'mouvements': commande.mouvements_stock.select_related(
            'modele', 'accessoire', 'auteur').all(),
        'atelier': atelier,
    })


# ==========================================
# 7bis. MOUVEMENTS DE STOCK
# ==========================================
@login_required
def historique_stock(request):
    """Journal complet des entrées / sorties de stock."""
    atelier = get_user_atelier(request.user)
    type_filter = request.GET.get('type', '')
    q = request.GET.get('q', '').strip()

    mouvements = MouvementStock.objects.filter(atelier=atelier).select_related(
        'modele', 'accessoire', 'commande', 'auteur'
    )

    if type_filter:
        mouvements = mouvements.filter(type_mouvement=type_filter)
    if q:
        mouvements = mouvements.filter(
            Q(modele__nom__icontains=q) |
            Q(accessoire__nom__icontains=q) |
            Q(commande__code__icontains=q)
        )

    paginator = Paginator(mouvements, 30)
    page_obj = paginator.get_page(request.GET.get('page'))

    return render(request, 'core/historique_stock.html', {
        'mouvements': page_obj,
        'page_obj': page_obj,
        'is_paginated': page_obj.has_other_pages(),
        'types': MouvementStock.TYPES,
        'type_filter': type_filter,
        'q': q,
        'atelier': atelier,
    })


@login_required
def ajuster_stock(request):
    """Réapprovisionnement ou correction d'inventaire manuelle."""
    atelier = get_user_atelier(request.user)

    if request.method != 'POST':
        return redirect('core:liste_modeles')

    genre = request.POST.get('genre')            # 'PAP' ou 'ACC'
    obj_id = _to_int(request.POST.get('article_id'), 0)
    quantite = _to_int(request.POST.get('quantite'), 0)
    type_mvt = request.POST.get('type_mouvement', 'REAPPRO')
    commentaire = (request.POST.get('commentaire') or '').strip()

    if genre not in ('PAP', 'ACC') or not obj_id or quantite == 0:
        messages.error(request, "Paramètres d'ajustement invalides.")
        return redirect('core:liste_modeles')

    obj = _modele_pour_genre(genre).objects.filter(
        pk=obj_id, atelier=atelier).first()
    if not obj:
        messages.error(request, "Article introuvable.")
        return redirect('core:liste_modeles')

    sens = 1 if quantite > 0 else -1
    qte_abs = abs(quantite)

    if sens < 0 and not obj.stock_suffisant(qte_abs):
        messages.error(
            request,
            f"Impossible de retirer {qte_abs} : stock actuel "
            f"{_stock_actuel(obj, genre)}."
        )
        return redirect('core:liste_modeles')

    with transaction.atomic():
        _appliquer_stock(
            atelier, {(genre, obj_id): qte_abs}, sens=sens,
            auteur=request.user, type_mvt=type_mvt,
            commentaire=commentaire,
        )

    obj.refresh_from_db()
    messages.success(
        request,
        f"Stock de « {obj.nom} » ajusté : "
        f"{_stock_actuel(obj, genre)} unité(s) disponible(s)."
    )
    return redirect('core:liste_modeles')


# ==========================================
# 8. REÇUS & FACTURES
# ==========================================
def _rendre_pdf(request, template, contexte, nom_fichier):
    from xhtml2pdf import pisa
    from django.template.loader import render_to_string

    html = render_to_string(template, contexte, request=request)
    response = HttpResponse(content_type='application/pdf')
    response['Content-Disposition'] = f'attachment; filename="{nom_fichier}"'
    if pisa.CreatePDF(html, dest=response).err:
        return HttpResponse("Erreur lors de la génération du PDF.", status=500)
    return response


@login_required
def recu_caisse(request, pk):
    atelier = get_user_atelier(request.user)
    commande = get_object_or_404(Commande, pk=pk, atelier=atelier)
    return render(request, 'core/recu_caisse.html', {
        'commande': commande,
        'lignes': commande.lignes.prefetch_related(
            'accessoires_ligne__accessoire').all(),
        'paiement': commande.paiements.order_by('date_paiement').first(),
        'atelier': atelier,
        'pdf': False,
    })


@login_required
def recu_caisse_pdf(request, pk):
    atelier = get_user_atelier(request.user)
    commande = get_object_or_404(Commande, pk=pk, atelier=atelier)
    return _rendre_pdf(request, 'core/recu_caisse.html', {
        'commande': commande,
        'lignes': commande.lignes.prefetch_related(
            'accessoires_ligne__accessoire').all(),
        'paiement': commande.paiements.order_by('date_paiement').first(),
        'atelier': atelier,
        'pdf': True,
    }, f"recu_caisse_{commande.code}.pdf")


@login_required
def recu_paiement(request, pk):
    atelier = get_user_atelier(request.user)
    commande = get_object_or_404(Commande, pk=pk, atelier=atelier)
    return render(request, 'core/recu_paiement.html', {
        'commande': commande,
        'paiement': commande.paiements.order_by('date_paiement').first(),
        'lignes': commande.lignes.prefetch_related(
            'accessoires_ligne__accessoire').all(),
        'atelier': atelier,
        'pdf': False,
    })


@login_required
def recu_paiement_pdf(request, pk):
    atelier = get_user_atelier(request.user)
    commande = get_object_or_404(Commande, pk=pk, atelier=atelier)
    return _rendre_pdf(request, 'core/recu_paiement_pdf.html', {
        'commande': commande,
        'paiement': commande.paiements.order_by('date_paiement').first(),
        'lignes': commande.lignes.prefetch_related(
            'accessoires_ligne__accessoire').all(),
        'atelier': atelier,
        'pdf': True,
    }, f"recu_{commande.code}.pdf")


@login_required
def facture_commande(request, pk):
    atelier = get_user_atelier(request.user)
    commande = get_object_or_404(Commande, pk=pk, atelier=atelier)
    return render(request, 'core/facture_commande.html', {
        'commande': commande,
        'paiements': commande.paiements.order_by('date_paiement'),
        'lignes': commande.lignes.prefetch_related(
            'accessoires_ligne__accessoire').all(),
        'atelier': atelier,
        'pdf': False,
    })


@login_required
def facture_commande_pdf(request, pk):
    atelier = get_user_atelier(request.user)
    commande = get_object_or_404(Commande, pk=pk, atelier=atelier)
    return _rendre_pdf(request, 'core/facture_commande_pdf.html', {
        'commande': commande,
        'paiements': commande.paiements.order_by('date_paiement'),
        'lignes': commande.lignes.prefetch_related(
            'accessoires_ligne__accessoire').all(),
        'atelier': atelier,
        'pdf': True,
    }, f"facture_{commande.code}.pdf")


# ==========================================
# 9. PARAMÈTRES & UTILISATEURS
# ==========================================
@login_required
def parametres_view(request):
    """Paramètres de l'atelier + gestion des comptes d'accès."""
    atelier = get_user_atelier(request.user)
    profil = getattr(request.user, 'profil', None)
    est_admin = _est_admin(request.user)

    # Le compte fondateur est masqué : seuls les comptes créés apparaissent
    membres = Profil.objects.filter(
        atelier=atelier, est_fondateur=False
    ).select_related('user', 'cree_par').order_by(
        'role', 'user__first_name', 'user__username')

    if request.method == 'POST' and 'update_atelier' in request.POST:
        if not est_admin:
            messages.error(
                request, "Seul l'administrateur peut modifier les paramètres.")
            return redirect('core:parametres')

        form_atelier = AtelierForm(request.POST, request.FILES, instance=atelier)
        if form_atelier.is_valid():
            form_atelier.save()
            messages.success(request, "Paramètres de l'atelier enregistrés.")
        else:
            for field, errors in form_atelier.errors.items():
                label = form_atelier.fields[field].label
                for err in errors:
                    messages.error(request, f"{label} : {err}")
        return redirect('core:parametres')

    rows = [{'m': m, 'style_avatar': _style_avatar(m.pk)} for m in membres]

    return render(request, 'core/parametres.html', {
        'atelier': atelier,
        'profil': profil,
        'rows': rows,
        'nb_membres': membres.count(),
        'nb_admins': membres.filter(role='ADMIN').count() + 1,
        'roles': Profil.ROLES,
        'descriptions_roles': Profil.DESCRIPTIONS_ROLES,
        'est_admin': est_admin,
        'form_atelier': AtelierForm(instance=atelier),
        'form_user': UtilisateurCreationForm(),
        'devises': atelier.DEVISES,
    })


@login_required
def ajouter_utilisateur(request):
    """Crée un compte d'accès à l'application."""
    atelier = get_user_atelier(request.user)

    if not _est_admin(request.user):
        messages.error(
            request, "Seul l'administrateur peut créer des utilisateurs.")
        return redirect('core:parametres')

    if request.method != 'POST':
        return redirect('core:parametres')

    form = UtilisateurCreationForm(request.POST)
    if form.is_valid():
        with transaction.atomic():
            user = form.save()
            Profil.objects.create(
                user=user,
                atelier=atelier,
                role=form.cleaned_data['role'],
                telephone=form.cleaned_data.get('telephone', ''),
                est_fondateur=False,
                cree_par=request.user,
            )
        libelle_role = dict(Profil.ROLES)[form.cleaned_data['role']]
        messages.success(
            request,
            f"Utilisateur « {user.get_full_name() or user.username} » créé "
            f"avec le rôle {libelle_role}."
        )
    else:
        for field, errors in form.errors.items():
            label = form.fields[field].label if field in form.fields else field
            for err in errors:
                messages.error(request, f"{label} : {err}")

    return redirect('core:parametres')


@login_required
def modifier_utilisateur(request, user_id):
    """GET : données JSON pour le modal. POST : enregistre les modifications."""
    atelier = get_user_atelier(request.user)

    if not _est_admin(request.user):
        if request.method == 'GET':
            return JsonResponse(
                {'error': "Action réservée à l'administrateur."}, status=403)
        messages.error(
            request, "Seul l'administrateur peut modifier les utilisateurs.")
        return redirect('core:parametres')

    profil = get_object_or_404(
        Profil, user_id=user_id, atelier=atelier, est_fondateur=False)

    if request.method != 'POST':
        return JsonResponse({
            'id': profil.user_id,
            'first_name': profil.user.first_name,
            'last_name': profil.user.last_name,
            'username': profil.user.username,
            'email': profil.user.email or '',
            'role': profil.role,
            'telephone': profil.telephone or '',
            'actif': profil.actif,
        })

    form = UtilisateurEditionForm(
        request.POST, instance=profil.user, profil=profil)
    if form.is_valid():
        with transaction.atomic():
            form.save()   # met à jour User + Profil
        messages.success(request, f"Compte « {profil.nom_affiche} » mis à jour.")
    else:
        for field, errors in form.errors.items():
            label = form.fields[field].label if field in form.fields else field
            for err in errors:
                messages.error(request, f"{label} : {err}")

    return redirect('core:parametres')


@login_required
def supprimer_utilisateur(request, user_id):
    """Supprime un compte d'accès."""
    atelier = get_user_atelier(request.user)

    if not _est_admin(request.user):
        messages.error(
            request, "Seul l'administrateur peut supprimer des utilisateurs.")
        return redirect('core:parametres')

    profil = get_object_or_404(Profil, user_id=user_id, atelier=atelier)

    if profil.est_fondateur:
        messages.error(request, "Le compte fondateur ne peut pas être supprimé.")
        return redirect('core:parametres')

    if profil.user == request.user:
        messages.error(request, "Vous ne pouvez pas supprimer votre propre compte.")
        return redirect('core:parametres')

    if request.method == 'POST':
        nom = profil.nom_affiche
        profil.user.delete()
        messages.success(request, f"Utilisateur « {nom} » supprimé.")

    return redirect('core:parametres')


# ==========================================
# 10. COMPTABILITÉ / DÉPENSES
# ==========================================
@login_required
def liste_depenses(request):
    atelier = get_user_atelier(request.user)
    mois_selectionne = request.GET.get('mois', '')
    categorie_filtre = request.GET.get('categorie', '')
    q = request.GET.get('q', '').strip()

    aujourdhui = timezone.now().date()

    # ---------- Période analysée ----------
    if mois_selectionne:
        try:
            annee_sel, mois_sel = (int(x) for x in mois_selectionne.split('-'))
            if not 1 <= mois_sel <= 12:
                raise ValueError
        except (ValueError, TypeError):
            annee_sel, mois_sel = aujourdhui.year, aujourdhui.month
            mois_selectionne = ''
    else:
        annee_sel, mois_sel = aujourdhui.year, aujourdhui.month

    libelle_periode = f"{MOIS_FR[mois_sel - 1]} {annee_sel}"

    # ---------- Liste filtrée ----------
    depenses_qs = Depense.objects.filter(atelier=atelier)
    if mois_selectionne:
        depenses_qs = depenses_qs.filter(
            date__year=annee_sel, date__month=mois_sel)
    if categorie_filtre:
        depenses_qs = depenses_qs.filter(categorie=categorie_filtre)
    if q:
        depenses_qs = depenses_qs.filter(libelle__icontains=q)
    depenses_qs = depenses_qs.order_by('-date', '-id')

    total_filtre = depenses_qs.aggregate(
        Sum('montant'))['montant__sum'] or Decimal('0')

    paginator = Paginator(depenses_qs, 15)
    page_obj = paginator.get_page(request.GET.get('page'))

    # ---------- Chiffres de la période ----------
    periode_qs = Depense.objects.filter(
        atelier=atelier, date__year=annee_sel, date__month=mois_sel)
    total_depenses = periode_qs.aggregate(
        Sum('montant'))['montant__sum'] or Decimal('0')
    revenus_mois = Paiement.objects.filter(
        atelier=atelier,
        date_paiement__year=annee_sel,
        date_paiement__month=mois_sel,
    ).aggregate(Sum('montant'))['montant__sum'] or Decimal('0')
    rentabilite = revenus_mois - total_depenses

    # ---------- Mois précédent (comparaison) ----------
    a_prec, m_prec = (annee_sel - 1, 12) if mois_sel == 1 else (annee_sel, mois_sel - 1)
    dep_prec = Depense.objects.filter(
        atelier=atelier, date__year=a_prec, date__month=m_prec
    ).aggregate(Sum('montant'))['montant__sum'] or Decimal('0')

    if dep_prec > 0:
        variation = int((total_depenses - dep_prec) * 100 / dep_prec)
    else:
        variation = 100 if total_depenses > 0 else 0

    # ---------- Répartition par catégorie ----------
    COULEURS_CAT = {
        'ACHAT_MATERIEL': '#7c3aed',
        'SALAIRE':        '#0284c7',
        'LOYER':          '#ea580c',
        'FACTURES':       '#d97706',
        'AUTRE':          '#6b7280',
    }
    ICONES_CAT = {
        'ACHAT_MATERIEL': 'bi-scissors',
        'SALAIRE':        'bi-people-fill',
        'LOYER':          'bi-house-door-fill',
        'FACTURES':       'bi-lightning-charge-fill',
        'AUTRE':          'bi-three-dots',
    }

    repartition = []
    for code, label in Depense.CATEGORIES:
        montant = periode_qs.filter(categorie=code).aggregate(
            Sum('montant'))['montant__sum'] or Decimal('0')
        if montant <= 0:
            continue
        pct = int(montant * 100 / total_depenses) if total_depenses > 0 else 0
        couleur = COULEURS_CAT.get(code, '#6b7280')
        repartition.append({
            'code': code,
            'label': label,
            'montant': montant,
            'pct': pct,
            'couleur': couleur,
            'icone': ICONES_CAT.get(code, 'bi-tag'),
            'style_barre': f"width:{pct}%; background:{couleur};",
            'style_pastille': f"background:{couleur}1a; color:{couleur};",
        })
    repartition.sort(key=lambda r: r['montant'], reverse=True)

    # ---------- Lignes enrichies ----------
    rows = []
    for d in page_obj:
        couleur = COULEURS_CAT.get(d.categorie, '#6b7280')
        rows.append({
            'd': d,
            'couleur': couleur,
            'icone': ICONES_CAT.get(d.categorie, 'bi-tag'),
            'style_icone': f"background:{couleur}1a; color:{couleur};",
            'montant_int': int(d.montant),
        })

    # ---------- Sélecteur de mois ----------
    mois_options = []
    for i in range(12):
        annee, mois_num = aujourdhui.year, aujourdhui.month - i
        while mois_num <= 0:
            mois_num += 12
            annee -= 1
        mois_options.append(
            (f"{annee}-{mois_num:02d}", f"{MOIS_FR[mois_num - 1]} {annee}"))

    params = request.GET.copy()
    params.pop('page', None)
    querystring = params.urlencode()

    return render(request, 'core/liste_depenses.html', {
        'rows': rows,
        'depenses': page_obj,
        'page_obj': page_obj,
        'paginator': paginator,
        'is_paginated': page_obj.has_other_pages(),
        'mois_options': mois_options,
        'mois_selectionne': mois_selectionne,
        'categorie_filtre': categorie_filtre,
        'q': q,
        'categories': Depense.CATEGORIES,
        'libelle_periode': libelle_periode,
        'revenus_mois': revenus_mois,
        'total_depenses': total_depenses,
        'rentabilite': rentabilite,
        'dep_prec': dep_prec,
        'variation': abs(variation),
        'en_hausse': total_depenses > dep_prec,
        'repartition': repartition,
        'total_filtre': total_filtre,
        'nb_filtre': paginator.count,
        'form': DepenseForm(),
        'querystring': querystring,
        'atelier': atelier,
    })


@login_required
def ajouter_depense(request):
    atelier = get_user_atelier(request.user)
    if request.method == 'POST':
        form = DepenseForm(request.POST)
        if form.is_valid():
            depense = form.save(commit=False)
            depense.atelier = atelier
            depense.save()
            return JsonResponse({'success': True})
        return JsonResponse(
            {'success': False, 'error': 'Veuillez vérifier les champs.'}, status=400)
    return JsonResponse(
        {'success': False, 'error': 'Méthode non autorisée.'}, status=405)


@login_required
def modifier_depense(request, pk):
    atelier = get_user_atelier(request.user)
    depense = get_object_or_404(Depense, pk=pk, atelier=atelier)
    if request.method == 'POST':
        form = DepenseForm(request.POST, instance=depense)
        if form.is_valid():
            form.save()
            return JsonResponse({'success': True})
        return JsonResponse(
            {'success': False, 'error': 'Veuillez vérifier les champs.'}, status=400)
    return JsonResponse({
        'id': depense.id,
        'date': depense.date.isoformat(),
        'categorie': depense.categorie,
        'libelle': depense.libelle,
        'montant': str(depense.montant),
    })


@login_required
def supprimer_depense(request, pk):
    atelier = get_user_atelier(request.user)
    depense = get_object_or_404(Depense, pk=pk, atelier=atelier)
    if request.method == 'POST':
        depense.delete()
        messages.success(request, "Dépense supprimée.")
    return redirect('core:liste_depenses')


# ==========================================
# 11. CALENDRIER & ABONNEMENT
# ==========================================
@login_required
def calendrier(request):
    """Agenda mensuel des livraisons prévues."""
    atelier = get_user_atelier(request.user)
    aujourdhui = timezone.now().date()

    try:
        annee = int(request.GET.get('annee', aujourdhui.year))
        mois = int(request.GET.get('mois', aujourdhui.month))
        if not 1 <= mois <= 12:
            raise ValueError
    except (TypeError, ValueError):
        annee, mois = aujourdhui.year, aujourdhui.month

    mois_precedent = (annee - 1, 12) if mois == 1 else (annee, mois - 1)
    mois_suivant = (annee + 1, 1) if mois == 12 else (annee, mois + 1)

    commandes = Commande.objects.filter(
        atelier=atelier,
        statut__in=['EN_ATTENTE', 'EN_COURS', 'PRET'],
        date_livraison_prevue__isnull=False,
    ).select_related('client', 'employe_attribue').prefetch_related(
        'lignes__modele', 'lignes__employe', 'lignes__accessoires_ligne', 'paiements'
    ).order_by('date_livraison_prevue')

    # Filtre par employé : ?employe=3
    employe_filter = request.GET.get('employe', '')
    if employe_filter:
        commandes = commandes.filter(
            Q(employe_attribue_id=employe_filter) |
            Q(lignes__employe_id=employe_filter)
        ).distinct()

    COULEURS = {
        'EN_ATTENTE': ('#fffbeb', '#d97706', '#fde68a'),
        'EN_COURS':   ('#eef2ff', '#4f46e5', '#c7d2fe'),
        'PRET':       ('#ecfdf5', '#059669', '#a7f3d0'),
    }
    RETARD = ('#fef2f2', '#e11d48', '#fecdd3')

    par_jour = {}
    items = []
    for c in commandes:
        d = c.date_livraison_prevue
        en_retard = c.est_en_retard()
        bg, fg, bd = RETARD if en_retard else COULEURS.get(
            c.statut, ('#f3f4f6', '#4b5563', '#e5e7eb'))
        premiere = c.lignes.first()
        employes = c.employes_impliques

        item = {
            'obj': c,
            'jour': d.day,
            'date': d,
            'client': str(c.client),
            'libelle': premiere.libelle if premiere else '—',
            'employe': ', '.join(e.nom_complet for e in employes) or 'Non attribuée',
            'retard': en_retard,
            'delta': (d - aujourdhui).days,
            'retard_jours': abs((d - aujourdhui).days),
            'style_pastille': f"background:{bg}; color:{fg}; border:1px solid {bd};",
            'style_point': f"background:{fg};",
            'prix_net': c.prix_net,
            'reste': c.reste_a_payer,
            'soldee': c.est_soldee,
            'nb_lignes': c.nb_lignes,
            'pct_avancement': c.pct_avancement,
        }
        items.append(item)
        if d.year == annee and d.month == mois:
            par_jour.setdefault(d.day, []).append(item)

    cal.setfirstweekday(cal.MONDAY)
    semaines = []
    for semaine in cal.monthcalendar(annee, mois):
        ligne = []
        for jour in semaine:
            if jour == 0:
                ligne.append({'vide': True})
                continue
            evts = par_jour.get(jour, [])
            date_jour = date(annee, mois, jour)
            ligne.append({
                'vide': False,
                'num': jour,
                'aujourdhui': date_jour == aujourdhui,
                'passe': date_jour < aujourdhui,
                'events': evts[:3],
                'reste': max(0, len(evts) - 3),
                'total': len(evts),
                'a_retard': any(e['retard'] for e in evts),
            })
        semaines.append(ligne)

    du_mois = [i for i in items
               if i['date'].year == annee and i['date'].month == mois]
    en_retard = [i for i in items if i['retard']]
    cette_semaine = [i for i in items if 0 <= i['delta'] <= 7]
    aujourdhui_liste = [i for i in items if i['delta'] == 0]

    return render(request, 'core/calendrier.html', {
        'atelier': atelier,
        'annee': annee,
        'mois': mois,
        'mois_nom': MOIS_FR[mois - 1],
        'prev_annee': mois_precedent[0],
        'prev_mois': mois_precedent[1],
        'next_annee': mois_suivant[0],
        'next_mois': mois_suivant[1],
        'annee_auj': aujourdhui.year,
        'mois_auj': aujourdhui.month,
        'semaines': semaines,
        'jours_semaine': ['Lun', 'Mar', 'Mer', 'Jeu', 'Ven', 'Sam', 'Dim'],
        'liste': sorted(du_mois, key=lambda i: i['date']),
        'nb_mois': len(du_mois),
        'nb_retard': len(en_retard),
        'nb_semaine': len(cette_semaine),
        'nb_aujourdhui': len(aujourdhui_liste),
        'prochaines': sorted(
            [i for i in items if i['delta'] >= 0], key=lambda i: i['date'])[:8],
        'retards': sorted(en_retard, key=lambda i: i['date']),
        'employes': Employe.objects.filter(atelier=atelier, statut='ACTIF'),
        'employe_filter': employe_filter,
    })


@login_required
def abonnement_expire(request):
    atelier = get_user_atelier(request.user)
    return render(request, 'core/abonnements.html', {
        'atelier': atelier,
        'plans': PlanAbonnement.objects.all(),
    })


# ==========================================
# 12. EMPLOYÉS DE L'ATELIER
# ==========================================
@login_required
def liste_employes(request):
    atelier = get_user_atelier(request.user)
    q = request.GET.get('q', '').strip()
    poste_filter = request.GET.get('poste', '')
    statut_filter = request.GET.get('statut', '')

    employes = Employe.objects.filter(atelier=atelier)

    if q:
        employes = employes.filter(
            Q(nom__icontains=q) | Q(prenom__icontains=q) |
            Q(telephone__icontains=q) | Q(matricule__icontains=q) |
            Q(specialites__icontains=q)
        )
    if poste_filter:
        employes = employes.filter(poste=poste_filter)
    if statut_filter:
        employes = employes.filter(statut=statut_filter)

    aujourdhui = timezone.now().date()
    debut_mois = aujourdhui.replace(day=1)

    rows = []
    masse_fixe = Decimal('0')
    total_commissions = Decimal('0')

    for e in employes:
        livrees_mois = LigneCommande.objects.filter(
            employe=e,
            commande__statut='LIVRE',
            commande__date_livraison_effective__gte=debut_mois,
        ).select_related('commande').prefetch_related('accessoires_ligne')

        commissions = sum(
            (e.commission_pour_ligne(l) for l in livrees_mois), Decimal('0'))

        if e.est_actif:
            if e.a_fixe:
                masse_fixe += e.salaire_mensuel
            total_commissions += commissions

        bg, fg, libelle = COULEURS_CHARGE[e.niveau_charge]

        rows.append({
            'e': e,
            'style_avatar': _style_avatar(e.pk),
            'style_charge': f"background:{bg}; color:{fg};",
            'style_barre': f"width:{e.charge_pct}%; background:{fg};",
            'libelle_charge': libelle,
            'nb_en_cours': e.nb_en_cours,
            'nb_retard': e.nb_en_retard,
            'nb_livrees_mois': livrees_mois.count(),
            'commissions_mois': commissions,
        })

    base = Employe.objects.filter(atelier=atelier)
    non_attribuees = LigneCommande.objects.filter(
        atelier=atelier,
        type_ligne='COUTURE',
        employe__isnull=True,
        commande__statut__in=['EN_ATTENTE', 'EN_COURS', 'PRET'],
    ).count()

    return render(request, 'core/employes.html', {
        'rows': rows,
        'total_employes': base.count(),
        'nb_actifs': base.filter(statut='ACTIF').count(),
        'masse_fixe': masse_fixe,
        'total_commissions': total_commissions,
        'masse_totale': masse_fixe + total_commissions,
        'non_attribuees': non_attribuees,
        'postes': Employe.POSTES,
        'statuts_emp': Employe.STATUTS,
        'q': q,
        'poste_filter': poste_filter,
        'statut_filter': statut_filter,
        'form': EmployeForm(),
        'est_admin': _est_admin(request.user),
        'atelier': atelier,
    })


@login_required
def ajouter_employe(request):
    atelier = get_user_atelier(request.user)
    if request.method == 'POST':
        form = EmployeForm(request.POST, request.FILES)
        if form.is_valid():
            emp = form.save(commit=False)
            emp.atelier = atelier
            emp.save()
            messages.success(
                request,
                f"Employé « {emp.nom_complet} » ajouté — matricule {emp.matricule}.")
        else:
            for field, errors in form.errors.items():
                label = form.fields[field].label if field in form.fields else field
                for err in errors:
                    messages.error(request, f"{label} : {err}")
    return redirect('core:liste_employes')


@login_required
def detail_employe(request, pk):
    atelier = get_user_atelier(request.user)
    emp = get_object_or_404(Employe, pk=pk, atelier=atelier)

    aujourdhui = timezone.now().date()
    debut_mois = aujourdhui.replace(day=1)

    en_cours = emp.lignes_travail.filter(
        commande__statut__in=['EN_ATTENTE', 'EN_COURS', 'PRET']
    ).select_related('commande__client', 'modele').prefetch_related(
        'accessoires_ligne'
    ).order_by('commande__date_livraison_prevue')

    travaux = []
    for l in en_cours:
        delta = (l.commande.date_livraison_prevue - aujourdhui).days
        travaux.append({
            'l': l,
            'retard': delta < 0,
            'delta': delta,
            'retard_jours': abs(delta),
            'commission': emp.commission_pour_ligne(l),
        })

    livrees = emp.lignes_travail.filter(
        commande__statut='LIVRE'
    ).select_related('commande__client', 'modele').prefetch_related(
        'accessoires_ligne'
    ).order_by('-commande__date_livraison_effective')[:20]

    livrees_mois = emp.lignes_travail.filter(
        commande__statut='LIVRE',
        commande__date_livraison_effective__gte=debut_mois,
    ).prefetch_related('accessoires_ligne')

    commissions_mois = sum(
        (emp.commission_pour_ligne(l) for l in livrees_mois), Decimal('0'))

    # Commissions non encore versées
    non_versees = emp.lignes_travail.filter(
        commande__statut='LIVRE', commission_versee=False
    ).prefetch_related('accessoires_ligne')
    commissions_dues = sum(
        (emp.commission_pour_ligne(l) for l in non_versees), Decimal('0'))

    toutes_livrees = emp.lignes_travail.filter(
        commande__statut='LIVRE').prefetch_related('accessoires_ligne')
    ca_genere = sum((l.prix_net for l in toutes_livrees), Decimal('0'))

    bg, fg, libelle_charge = COULEURS_CHARGE[emp.niveau_charge]

    return render(request, 'core/detail_employe.html', {
        'emp': emp,
        'travaux': travaux,
        'livrees': livrees,
        'nb_en_cours': en_cours.count(),
        'nb_livrees_total': toutes_livrees.count(),
        'nb_livrees_mois': livrees_mois.count(),
        'commissions_mois': commissions_mois,
        'commissions_dues': commissions_dues,
        'net_estime': (emp.salaire_mensuel if emp.a_fixe else Decimal('0'))
                      + commissions_mois,
        'ca_genere': ca_genere,
        'style_avatar': _style_avatar(emp.pk),
        'style_charge': f"background:{bg}; color:{fg};",
        'style_barre': f"width:{emp.charge_pct}%; background:{fg};",
        'libelle_charge': libelle_charge,
        'paies': emp.paies.all()[:12],
        'form': EmployeForm(instance=emp),
        'est_admin': _est_admin(request.user),
        'atelier': atelier,
    })


@login_required
def modifier_employe(request, pk):
    atelier = get_user_atelier(request.user)
    emp = get_object_or_404(Employe, pk=pk, atelier=atelier)
    if request.method == 'POST':
        form = EmployeForm(request.POST, request.FILES, instance=emp)
        if form.is_valid():
            form.save()
            messages.success(request, "Fiche employé mise à jour.")
        else:
            for field, errors in form.errors.items():
                label = form.fields[field].label if field in form.fields else field
                for err in errors:
                    messages.error(request, f"{label} : {err}")
    return redirect('core:detail_employe', pk=emp.pk)


@login_required
def supprimer_employe(request, pk):
    atelier = get_user_atelier(request.user)
    emp = get_object_or_404(Employe, pk=pk, atelier=atelier)

    if request.method == 'POST':
        nb_en_cours = emp.nb_en_cours
        if nb_en_cours:
            messages.error(
                request,
                f"Impossible de supprimer : {nb_en_cours} couture(s) en cours. "
                f"Réattribuez-les d'abord ou passez l'employé en « Ne travaille "
                f"plus ici »."
            )
            return redirect('core:detail_employe', pk=emp.pk)

        nom = emp.nom_complet
        emp.delete()
        messages.success(request, f"Employé « {nom} » supprimé.")
        return redirect('core:liste_employes')

    return redirect('core:detail_employe', pk=emp.pk)


@login_required
def creer_paie(request, pk):
    """Génère un versement de salaire + la dépense comptable associée."""
    atelier = get_user_atelier(request.user)
    emp = get_object_or_404(Employe, pk=pk, atelier=atelier)

    if request.method != 'POST':
        return redirect('core:detail_employe', pk=emp.pk)

    aujourdhui = timezone.now().date()
    debut = _to_date(request.POST.get('periode_debut'), aujourdhui.replace(day=1))
    fin = _to_date(request.POST.get('periode_fin'), aujourdhui)

    if fin < debut:
        messages.error(request, "La date de fin précède la date de début.")
        return redirect('core:detail_employe', pk=emp.pk)

    primes = _to_decimal(request.POST.get('primes'))
    avances = _to_decimal(request.POST.get('avances'))
    mode = request.POST.get('mode_paiement', 'ESPECES')

    lignes = emp.lignes_travail.filter(
        commande__statut='LIVRE',
        commande__date_livraison_effective__gte=debut,
        commande__date_livraison_effective__lte=fin,
        commission_versee=False,
    ).prefetch_related('accessoires_ligne')

    commissions = sum(
        (emp.commission_pour_ligne(l) for l in lignes), Decimal('0'))
    fixe = emp.salaire_mensuel if emp.a_fixe else Decimal('0')
    nb_pieces = lignes.count()

    if fixe == 0 and commissions == 0 and primes == 0:
        messages.warning(
            request,
            "Rien à verser sur cette période : aucun fixe, aucune commission "
            "en attente, aucune prime."
        )
        return redirect('core:detail_employe', pk=emp.pk)

    with transaction.atomic():
        paie = Paie.objects.create(
            atelier=atelier,
            employe=emp,
            periode_debut=debut,
            periode_fin=fin,
            salaire_fixe=fixe,
            commissions=commissions,
            primes=primes,
            avances=avances,
            nb_pieces=nb_pieces,
            statut='PAYEE',
            date_paiement=aujourdhui,
            mode_paiement=mode,
        )

        # Marque les commissions comme versées
        if nb_pieces:
            LigneCommande.objects.filter(
                pk__in=[l.pk for l in lignes]
            ).update(commission_versee=True)

        Depense.objects.create(
            atelier=atelier,
            date=aujourdhui,
            categorie='SALAIRE',
            libelle=f"Salaire {emp.nom_complet} — {paie.periode_libelle}",
            montant=paie.net_a_payer,
        )

    messages.success(
        request,
        f"Paie enregistrée : {paie.net_a_payer} {atelier.devise} "
        f"versés à {emp.nom_complet} ({nb_pieces} pièce(s))."
    )
    return redirect('core:detail_employe', pk=emp.pk)


@login_required
def plan_charge(request):
    """Vue d'équipe : répartition des coutures en cours par employé."""
    atelier = get_user_atelier(request.user)
    aujourdhui = timezone.now().date()

    employes = Employe.objects.filter(
        atelier=atelier, statut='ACTIF').order_by('nom', 'prenom')

    colonnes = []
    total_taches = 0
    total_retards = 0

    for e in employes:
        lignes = e.lignes_travail.filter(
            commande__statut__in=['EN_ATTENTE', 'EN_COURS', 'PRET']
        ).select_related('commande__client', 'modele').order_by(
            'commande__date_livraison_prevue')

        taches = []
        for l in lignes:
            delta = (l.commande.date_livraison_prevue - aujourdhui).days
            retard = delta < 0
            if retard:
                total_retards += 1
            taches.append({
                'l': l,
                'retard': retard,
                'delta': delta,
                'retard_jours': abs(delta),
            })

        total_taches += len(taches)
        bg, fg, libelle = COULEURS_CHARGE[e.niveau_charge]
        colonnes.append({
            'e': e,
            'taches': taches,
            'nb': len(taches),
            'style_avatar': _style_avatar(e.pk),
            'style_charge': f"background:{bg}; color:{fg};",
            'libelle_charge': libelle,
        })

    orphelines = LigneCommande.objects.filter(
        atelier=atelier,
        type_ligne='COUTURE',
        employe__isnull=True,
        commande__statut__in=['EN_ATTENTE', 'EN_COURS', 'PRET'],
    ).select_related('commande__client', 'modele').order_by(
        'commande__date_livraison_prevue')

    nb_orphelines = orphelines.count()
    total_retards += sum(1 for l in orphelines if l.commande.est_en_retard())

    return render(request, 'core/plan_charge.html', {
        'colonnes': colonnes,
        'orphelines': orphelines,
        'nb_orphelines': nb_orphelines,
        'total_taches': total_taches + nb_orphelines,
        'total_retards': total_retards,
        'employes': employes,
        'atelier': atelier,
    })


@login_required
def api_employes(request):
    """Liste des employés actifs pour les selects dynamiques."""
    atelier = get_user_atelier(request.user)
    data = [{
        'id': e.id,
        'nom_complet': e.nom_complet,
        'matricule': e.matricule,
        'poste_label': e.get_poste_display(),
        'specialites': e.specialites or '',
        'en_cours': e.nb_en_cours,
        'charge': e.niveau_charge,
        'libelle_charge': COULEURS_CHARGE[e.niveau_charge][2],
    } for e in Employe.objects.filter(
        atelier=atelier, statut='ACTIF').order_by('nom', 'prenom')]
    return JsonResponse({'employes': data})

def _est_admin(user):
    profil = getattr(user, 'profil', None)
    return bool(profil and profil.role == 'ADMIN')


def _peut_comptabilite(user):
    """Admin ou comptable."""
    profil = getattr(user, 'profil', None)
    return bool(profil and profil.role in ('ADMIN', 'COMPTABLE'))


def _peut_production(user):
    """Admin ou gestionnaire : clients, commandes, ventes."""
    profil = getattr(user, 'profil', None)
    return bool(profil and profil.role in ('ADMIN', 'GESTIONNAIRE'))
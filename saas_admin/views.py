from datetime import date, timedelta
from decimal import Decimal, InvalidOperation

from django.contrib import messages
from django.contrib.auth.password_validation import validate_password
from django.core.exceptions import ValidationError
from django.contrib.auth.decorators import user_passes_test
from django.contrib.auth.models import User
from core.validators import generer_mot_de_passe_temporaire
from django.core.paginator import Paginator
from django.db import transaction
from django.db.models import Q, Sum, Count
from core.expiration import infos_expiration
from core.sauvegarde import (
    chemin_sauvegarde_systeme, creer_sauvegarde_systeme,
    lister_sauvegardes_systeme, supprimer_sauvegarde_systeme,
)
from django.http import FileResponse
from django.shortcuts import get_object_or_404, redirect, render

from core.models import (
    Abonnement, Atelier, PlanAbonnement, Profil,
)

from .models import Facture, FormuleAbonnement, PaiementAbonnement


# --- DÉCORATEUR UNIQUE ET STRICT POUR LE SAAS ---
def superadmin_required(view_func):
    """Décorateur restreignant l'accès strictement aux Superadministrateurs."""
    decorated_view_func = user_passes_test(
        lambda u: u.is_authenticated and u.is_superuser,
        login_url='core:connexion'
    )(view_func)
    return decorated_view_func


# ==========================================
# 1. TABLEAU DE BORD PRINCIPAL SUPERADMIN
# ==========================================
@superadmin_required
def superadmin_dashboard(request):
    aujourdhui = date.today()
    dans_7_jours = aujourdhui + timedelta(days=7)

    abonnements = Abonnement.objects.select_related('plan', 'atelier')
    actifs = abonnements.filter(statut='ACTIF', date_fin__gte=aujourdhui)
    total_boutiques = Atelier.objects.count()
    boutiques_actives = actifs.count()
    boutiques_essai = actifs.filter(plan__prix_mensuel=0).count()
    boutiques_suspendues = abonnements.filter(statut='SUSPENDU').count()

    # Revenu Mensuel Récurrent (MRR) des abonnements actifs non expirés
    mrr = actifs.aggregate(total=Sum('plan__prix_mensuel'))['total'] or 0

    # Montant global encaissé (tous les paiements d'abonnements enregistrés)
    from .models import PaiementAbonnement
    montant_global_abonnements = PaiementAbonnement.objects.aggregate(
        total=Sum('montant'))['total'] or 0
    expirations_proches = actifs.filter(
        date_fin__range=[aujourdhui, dans_7_jours]).count()

    taux_conversion = 0
    if total_boutiques > 0:
        taux_conversion = round((boutiques_actives / total_boutiques) * 100, 1)

    context = {
        'total_boutiques': total_boutiques,
        'boutiques_actives': boutiques_actives,
        'boutiques_essai': boutiques_essai,
        'boutiques_suspendues': boutiques_suspendues,
        'mrr': mrr,
        'montant_global_abonnements': montant_global_abonnements,
        'expirations_proches': expirations_proches,
        'taux_conversion': taux_conversion,
        'today': aujourdhui,
    }
    boutiques = list(
        Atelier.objects.select_related('abonnement__plan')
        .annotate(nb_membres=Count('membres'))
        .all().order_by('-date_creation'))
    fondateurs = {
        profil.atelier_id: profil.user
        for profil in Profil.objects.filter(
            atelier__in=[b.id for b in boutiques], est_fondateur=True,
        ).select_related('user')
    }
    for boutique in boutiques:
        boutique.proprietaire_user = fondateurs.get(boutique.id)
    context['boutiques'] = boutiques
    return render(request, 'saas_admin/dashboard.html', context)


# ==========================================
# 2. GESTION DES BOUTIQUES (ateliers réels)
# ==========================================
# Le back-office pilote désormais les vraies boutiques du système :
# core.Atelier (créés à l'inscription), leurs membres (Profil) et leur
# abonnement (core.Abonnement). L'ancien modèle Boutique reste en base
# mais n'est plus utilisé par ces écrans.
@superadmin_required
def superadmin_liste_boutiques(request):
    q = request.GET.get('q', '').strip()
    boutiques = Atelier.objects.select_related('abonnement__plan').annotate(
        nb_membres=Count('membres')).order_by('-date_creation')
    if q:
        boutiques = boutiques.filter(
            Q(nom__icontains=q)
            | Q(membres__user__username__icontains=q)
            | Q(membres__user__first_name__icontains=q)
        ).distinct()
    boutiques = list(boutiques)
    fondateurs = {
        p.atelier_id: p.user
        for p in Profil.objects.filter(
            atelier__in=[b.id for b in boutiques], est_fondateur=True,
        ).select_related('user')
    }
    kpi = {'total': len(boutiques), 'actives': 0, 'expirees': 0, 'supprimables': 0}
    for boutique in boutiques:
        boutique.proprietaire_user = fondateurs.get(boutique.id)
        boutique.infos_exp = infos_expiration(boutique)
        if boutique.infos_exp['fonctionnelle']:
            kpi['actives'] += 1
        elif boutique.infos_exp['supprimable']:
            kpi['supprimables'] += 1
        else:
            kpi['expirees'] += 1
    return render(request, 'saas_admin/liste_boutiques.html', {
        'boutiques': boutiques,
        'q': q,
        'today': date.today(),
        'plans': PlanAbonnement.objects.all().order_by('prix_mensuel'),
        'kpi': kpi,
    })


@superadmin_required
def ajouter_boutique(request):
    """Crée une boutique complète : utilisateur propriétaire (ADMIN
    fondateur), atelier et abonnement au plan choisi."""
    if request.method == 'POST':
        nom = (request.POST.get('nom_atelier') or '').strip()
        username = (request.POST.get('username') or '').strip()
        password = request.POST.get('password') or ''
        plan_id = request.POST.get('plan_id')
        if not nom or not username:
            messages.error(request, "Nom de boutique et identifiant sont obligatoires.")
            return redirect('saas_admin:superadmin_liste_boutiques')
        try:
            validate_password(password)
        except ValidationError as e:
            messages.error(request, "Mot de passe du propriétaire : " + " ".join(e.messages))
            return redirect('saas_admin:superadmin_liste_boutiques')
        if User.objects.filter(username=username).exists():
            messages.error(request, f"L'identifiant « {username} » existe déjà.")
            return redirect('saas_admin:superadmin_liste_boutiques')
        plan = get_object_or_404(PlanAbonnement, id=plan_id) if plan_id else None
        with transaction.atomic():
            user = User.objects.create_user(
                username=username,
                password=password,
                first_name=request.POST.get('first_name', ''),
                last_name=request.POST.get('last_name', ''),
                email=request.POST.get('email', ''),
            )
            atelier = Atelier.objects.create(
                nom=nom,
                telephone=request.POST.get('telephone', ''),
                email=request.POST.get('email', '') or None,
                adresse=request.POST.get('adresse', ''),
            )
            Profil.objects.create(
                user=user, atelier=atelier, role='ADMIN', est_fondateur=True)
            jours = 14 if (plan and plan.prix_mensuel == 0) else 30
            Abonnement.objects.create(
                atelier=atelier, plan=plan, statut='ACTIF',
                date_fin=date.today() + timedelta(days=jours))
        messages.success(
            request,
            f"Boutique « {nom} » créée : compte propriétaire {username}, "
            f"abonnement {plan.nom if plan else '—'} pour {jours} jours.")
    return redirect('saas_admin:superadmin_liste_boutiques')


@superadmin_required
def detail_boutique(request, boutique_id):
    atelier = get_object_or_404(Atelier, id=boutique_id)
    abonnement = getattr(atelier, 'abonnement', None)
    fondateur = atelier.membres.filter(est_fondateur=True).select_related('user').first()
    return render(request, 'saas_admin/detail_boutique.html', {
        'boutique': atelier,
        'fondateur': fondateur.user if fondateur else None,
        'abonnement': abonnement,
        'membres': atelier.membres.select_related('user').order_by('role', 'user__username'),
        'paiements': atelier.paiements_abonnement.select_related('enregistre_par').order_by('-date_paiement'),
        'plans': PlanAbonnement.objects.all().order_by('prix_mensuel'),
        'nb_clients': atelier.clients.count(),
        'nb_commandes': atelier.commandes.count(),
        'nb_depenses': atelier.depenses.count(),
        'today': date.today(),
    })


@superadmin_required
def modifier_boutique(request, boutique_id):
    atelier = get_object_or_404(Atelier, id=boutique_id)
    if request.method == 'POST':
        atelier.nom = request.POST.get('nom') or atelier.nom
        atelier.adresse = request.POST.get('adresse', '')
        atelier.telephone = request.POST.get('telephone', '')
        atelier.email = request.POST.get('email', '') or None
        atelier.devise = request.POST.get('devise') or atelier.devise
        atelier.est_actif = request.POST.get('est_actif') == 'on'
        atelier.save()
        messages.success(request, "Informations de la boutique mises à jour.")
    return redirect('saas_admin:detail_boutique', boutique_id=atelier.id)


def _int_or_none(valeur):
    try:
        return int(valeur)
    except (TypeError, ValueError):
        return None


@superadmin_required
def changer_plan_boutique(request, boutique_id):
    """Attribue (ou change) l'abonnement : nouveau plan, statut actif et
    période de `mois` mois qui repart d'aujourd'hui."""
    atelier = get_object_or_404(Atelier, id=boutique_id)
    if request.method == 'POST':
        plan = get_object_or_404(PlanAbonnement, id=request.POST.get('plan_id'))
        try:
            mois = int(request.POST.get('mois', plan.duree_mois or 3))
            if mois < 0:
                mois = 0
        except ValueError:
            mois = plan.duree_mois or 3
        abonnement, _ = Abonnement.objects.get_or_create(atelier=atelier)
        abonnement.plan = plan
        abonnement.statut = 'ACTIF'
        # Durée 0 = période d'essai (14 jours) ; sinon 30 jours par mois.
        nb_jours = 14 if mois == 0 else 30 * mois
        abonnement.date_fin = date.today() + timedelta(days=nb_jours)
        abonnement.save()
        messages.success(
            request,
            f"Abonnement « {plan.nom} » attribué à {atelier.nom} "
            f"jusqu'au {abonnement.date_fin:%d/%m/%Y}.")
    return redirect('saas_admin:detail_boutique', boutique_id=atelier.id)


@superadmin_required
def suspendre_boutique(request, boutique_id):
    atelier = get_object_or_404(Atelier, id=boutique_id)
    if request.method == 'POST':
        abonnement = getattr(atelier, 'abonnement', None)
        if abonnement:
            abonnement.statut = 'SUSPENDU'
            abonnement.save()
        atelier.est_actif = False
        atelier.save()
        messages.warning(request, f"La boutique {atelier.nom} est suspendue.")
    return redirect('saas_admin:detail_boutique', boutique_id=atelier.id)


@superadmin_required
def reactiver_boutique(request, boutique_id):
    atelier = get_object_or_404(Atelier, id=boutique_id)
    if request.method == 'POST':
        aujourdhui = date.today()
        abonnement = getattr(atelier, 'abonnement', None)
        if abonnement is None:
            jusquau = aujourdhui + timedelta(days=30)
            Abonnement.objects.create(
                atelier=atelier, plan=None, statut='ACTIF', date_fin=jusquau)
        else:
            base = max(abonnement.date_fin, aujourdhui)
            abonnement.date_fin = base + timedelta(days=30)
            abonnement.statut = 'ACTIF'
            abonnement.save()
            jusquau = abonnement.date_fin
        atelier.est_actif = True
        atelier.save()
        messages.success(
            request,
            f"Nouvel abonnement activé : la boutique {atelier.nom} est "
            f"fonctionnelle jusqu'au {jusquau:%d/%m/%Y} avec toutes ses "
            f"anciennes données.")
    return redirect('saas_admin:detail_boutique', boutique_id=atelier.id)


@superadmin_required
def supprimer_boutique(request, boutique_id):
    atelier = get_object_or_404(Atelier, id=boutique_id)
    if request.method == 'POST':
        infos = infos_expiration(atelier)
        if not infos['supprimable']:
            messages.error(
                request,
                f"Suppression refusée : les données de {atelier.nom} sont "
                f"conservées jusqu'au {infos['echeance']:%d/%m/%Y} (3 mois "
                f"sans abonnement). Activez un abonnement pour la "
                f"réactiver, ou revenez après cette date.")
            return redirect('saas_admin:detail_boutique', boutique_id=atelier.id)
        if request.POST.get('confirmation') != 'SUPPRIMER':
            messages.error(request, "Confirmation requise : tapez SUPPRIMER.")
            return redirect('saas_admin:detail_boutique', boutique_id=atelier.id)
        nom = atelier.nom
        users = list(atelier.membres.values_list('user_id', flat=True))
        atelier.delete()
        User.objects.filter(id__in=users, profil__isnull=True).delete()
        messages.success(
            request,
            f"Boutique « {nom} » supprimée totalement (données comprises) "
            f"après la fin du délai de conservation.")
        return redirect('saas_admin:superadmin_liste_boutiques')
    return redirect('saas_admin:detail_boutique', boutique_id=atelier.id)


@superadmin_required
def reinitialiser_pass_boutique(request, boutique_id):
    """Réinitialise le mot de passe d'un membre : le nouveau mot de passe
    temporaire est affiché au super-admin, à transmettre au propriétaire."""
    atelier = get_object_or_404(Atelier, id=boutique_id)
    if request.method == 'POST':
        user = get_object_or_404(User, id=request.POST.get('user_id'))
        if not atelier.membres.filter(user=user).exists():
            messages.error(request, "Cet utilisateur n'appartient pas à cette boutique.")
        else:
            temporaire = generer_mot_de_passe_temporaire()
            user.set_password(temporaire)
            user.save()
            messages.success(
                request,
                f"Mot de passe de {user.username} réinitialisé. "
                f"Temporaire : {temporaire} (à changer à la prochaine connexion).")
    return redirect('saas_admin:detail_boutique', boutique_id=atelier.id)


@superadmin_required
def impersonner_boutique(request, boutique_id):
    atelier = get_object_or_404(Atelier, id=boutique_id)
    messages.warning(
        request,
        f"Accès refusé : la connexion directe à l'espace de la boutique "
        f"'{atelier.nom}' est désactivée pour les Super Admins.")
    return redirect('saas_admin:detail_boutique', boutique_id=atelier.id)


@superadmin_required
def enregistrer_paiement(request, boutique_id):
    """Encaissement manuel d'un abonnement (espèces, Orange Money, Wave…).

    Si « prolonger » est coché, l'abonnement gagne `mois_couverts` mois à
    partir de sa date de fin actuelle (ou d'aujourd'hui si expiré)."""
    atelier = get_object_or_404(Atelier, id=boutique_id)
    if request.method == 'POST':
        try:
            montant = Decimal(str(request.POST.get('montant') or 0))
            mois = max(1, int(request.POST.get('mois_couverts') or 1))
        except (ValueError, InvalidOperation):
            messages.error(request, "Montant ou nombre de mois invalide.")
            return redirect('saas_admin:detail_boutique', boutique_id=atelier.id)
        prolonge = request.POST.get('prolonger') == 'on'
        PaiementAbonnement.objects.create(
            atelier=atelier,
            montant=montant,
            mode=request.POST.get('mode') or 'ESPECES',
            reference=request.POST.get('reference', ''),
            note=request.POST.get('note', ''),
            mois_couverts=mois,
            prolonge=prolonge,
            enregistre_par=request.user,
        )
        if prolonge:
            abonnement, _ = Abonnement.objects.get_or_create(atelier=atelier)
            base = max(abonnement.date_fin, date.today())
            abonnement.date_fin = base + timedelta(days=30 * mois)
            abonnement.statut = 'ACTIF'
            abonnement.save()
            messages.success(
                request,
                f"Paiement de {montant:,.0f} FCFA encaissé pour {atelier.nom} ; "
                f"abonnement prolongé jusqu'au {abonnement.date_fin:%d/%m/%Y}."
                .replace(',', ' '))
        else:
            messages.success(
                request,
                f"Paiement de {montant:,.0f} FCFA encaissé pour {atelier.nom} "
                f"(sans prolongation).".replace(',', ' '))
    return redirect('saas_admin:detail_boutique', boutique_id=atelier.id)


# ==========================================
# 4. GESTION DES FORMULES D'ABONNEMENT
# ==========================================
# Le back-office pilote `core.PlanAbonnement`, le modèle réellement consommé
# par la page « Abonnements & Offres » de l'application et par la landing
# publique. L'ancien modèle FormuleAbonnement reste en base (clé étrangère
# de Boutique) mais n'est plus édité ici.
@superadmin_required
def liste_abonnements(request):
    formules = PlanAbonnement.objects.all().order_by('prix_mensuel').annotate(
        nb_abonnes=Count('abonnement'))
    return render(request, 'saas_admin/abonnements.html', {'formules': formules})


@superadmin_required
def ajouter_abonnement(request):
    if request.method == 'POST':
        try:
            duree = int(request.POST.get('duree_mois') or 3)
        except ValueError:
            duree = 3
        if duree not in dict(PlanAbonnement.DUREE_CHOICES):
            duree = 3
        PlanAbonnement.objects.create(
            nom=request.POST.get('nom') or 'Nouvelle offre',
            description=request.POST.get('description', ''),
            prix_mensuel=request.POST.get('prix_mensuel') or 0,
            max_commandes_mois=int(request.POST.get('max_commandes_mois') or 50),
            max_utilisateurs=int(request.POST.get('max_utilisateurs') or 3),
            support_prioritaire=request.POST.get('support_prioritaire') == 'on',
            est_populaire=request.POST.get('est_populaire') == 'on',
            actif=request.POST.get('actif') == 'on',
            duree_mois=duree,
            fonctionnalites_incluses=request.POST.get('fonctionnalites_incluses', ''),
            fonctionnalites_exclues=request.POST.get('fonctionnalites_exclues', ''),
        )
        messages.success(request, "L'offre d'abonnement a été créée.")
    return redirect('saas_admin:abonnements')


@superadmin_required
def modifier_abonnement(request, formule_id):
    formule = get_object_or_404(PlanAbonnement, id=formule_id)
    if request.method == 'POST':
        formule.nom = request.POST.get('nom') or formule.nom
        formule.description = request.POST.get('description', '')
        formule.prix_mensuel = request.POST.get('prix_mensuel') or formule.prix_mensuel
        formule.max_commandes_mois = int(
            request.POST.get('max_commandes_mois') or formule.max_commandes_mois)
        formule.max_utilisateurs = int(
            request.POST.get('max_utilisateurs') or formule.max_utilisateurs)
        formule.support_prioritaire = request.POST.get('support_prioritaire') == 'on'
        formule.est_populaire = request.POST.get('est_populaire') == 'on'
        formule.actif = request.POST.get('actif') == 'on'
        try:
            duree = int(request.POST.get('duree_mois') or formule.duree_mois)
        except ValueError:
            duree = formule.duree_mois
        if duree in dict(PlanAbonnementDuree := PlanAbonnement.DUREE_CHOICES):
            formule.duree_mois = duree
        formule.fonctionnalites_incluses = request.POST.get(
            'fonctionnalites_incluses', formule.fonctionnalites_incluses)
        formule.fonctionnalites_exclues = request.POST.get(
            'fonctionnalites_exclues', formule.fonctionnalites_exclues)
        formule.save()
        messages.success(request, "L'offre d'abonnement a été mise à jour.")
    return redirect('saas_admin:abonnements')


@superadmin_required
def supprimer_abonnement(request, formule_id):
    formule = get_object_or_404(PlanAbonnement, id=formule_id)
    if request.method == 'POST':
        nb = Abonnement.objects.filter(plan=formule).count()
        if nb:
            messages.error(
                request,
                "Impossible de supprimer « %s » : %d atelier(s) y sont "
                "abonnés. Désactivez plutôt l'offre (case « actif ») pour la "
                "masquer sans casser les abonnements en cours."
                % (formule.nom, nb),
            )
        else:
            formule.delete()
            messages.success(request, "L'offre d'abonnement a été supprimée.")
    return redirect('saas_admin:abonnements')


# ==========================================
# 5. GESTION EXCLUSIVE DES SUPER ADMINS
# ==========================================
@superadmin_required
def superadmin_liste_utilisateurs(request):
    search_query = request.GET.get('q', '').strip()

    utilisateurs_list = User.objects.filter(is_superuser=True).order_by('-date_joined')

    if search_query:
        utilisateurs_list = utilisateurs_list.filter(
            Q(username__icontains=search_query) |
            Q(first_name__icontains=search_query) |
            Q(last_name__icontains=search_query) |
            Q(email__icontains=search_query)
        )

    paginator = Paginator(utilisateurs_list, 15)
    page_number = request.GET.get('page')
    page_obj = paginator.get_page(page_number)

    context = {
        'page_obj': page_obj,
        'search_query': search_query,
    }
    return render(request, 'saas_admin/liste_utilisateurs.html', context)


@superadmin_required
def ajouter_utilisateur(request):
    if request.method == 'POST':
        username = request.POST.get('username')
        first_name = request.POST.get('first_name', '')
        last_name = request.POST.get('last_name', '')
        email = request.POST.get('email', '')
        password = request.POST.get('password')

        if User.objects.filter(username=username).exists():
            messages.error(request, f"L'identifiant '{username}' est déjà pris.")
            return redirect('saas_admin:superadmin_liste_utilisateurs')
        try:
            validate_password(password or '')
        except ValidationError as e:
            messages.error(request, "Mot de passe : " + " ".join(e.messages))
            return redirect('saas_admin:superadmin_liste_utilisateurs')

        User.objects.create_user(
            username=username,
            email=email,
            password=password,
            first_name=first_name,
            last_name=last_name,
            is_staff=True,
            is_superuser=True
        )

        messages.success(request, f"Le Super Admin '{username}' a été créé avec succès.")

    return redirect('saas_admin:superadmin_liste_utilisateurs')


@superadmin_required
def modifier_utilisateur(request, user_id):
    user = get_object_or_404(User, id=user_id, is_superuser=True)
    if request.method == 'POST':
        username = request.POST.get('username')
        
        if User.objects.filter(username=username).exclude(id=user.id).exists():
            messages.error(request, f"L'identifiant '{username}' est déjà utilisé par un autre compte.")
            return redirect('saas_admin:superadmin_liste_utilisateurs')

        user.username = username
        user.first_name = request.POST.get('first_name', '')
        user.last_name = request.POST.get('last_name', '')
        user.email = request.POST.get('email', '')

        password = request.POST.get('password')
        if password:
            user.set_password(password)

        user.save()
        messages.success(request, f"Le profil de '{user.username}' a été mis à jour.")

    return redirect('saas_admin:superadmin_liste_utilisateurs')


@superadmin_required
def supprimer_utilisateur(request, user_id):
    user = get_object_or_404(User, id=user_id, is_superuser=True)
    if request.method == 'POST':
        if user == request.user:
            messages.error(request, "Vous ne pouvez pas supprimer votre propre compte Super Admin.")
        else:
            username = user.username
            user.delete()
            messages.success(request, f"Le Super Admin '{username}' a été supprimé avec succès.")

    return redirect('saas_admin:superadmin_liste_utilisateurs')


@superadmin_required
def changer_statut_utilisateur(request, user_id):
    user = get_object_or_404(User, id=user_id, is_superuser=True)
    if request.method == 'POST':
        if user != request.user:
            user.is_active = not user.is_active
            user.save()
            statut_txt = "activé" if user.is_active else "désactivé"
            messages.success(request, f"Le compte de {user.username} a été {statut_txt}.")
        else:
            messages.error(request, "Vous ne pouvez pas désactiver votre propre compte.")
    return redirect('saas_admin:superadmin_liste_utilisateurs')


@superadmin_required
def superadmin_parametres(request):
    if request.method == 'POST':
        if request.POST.get('action') == 'lomopay':
            _enregistrer_cles_lomopay(request)
        else:
            messages.success(request, "Les paramètres globaux ont été mis à jour avec succès.")
        return redirect('saas_admin:superadmin_parametres')

    from core.models import ConfigurationLomopay
    context = {
        'active_tab': 'parametres',
        'lomopay_config': ConfigurationLomopay.objects.first(),
    }
    return render(request, 'saas_admin/parametres.html', context)


def _enregistrer_cles_lomopay(request):
    """Crée ou met à jour la configuration LomoPay de la plateforme.

    Si une clé publique est déjà enregistrée et que les champs sont laissés
    vides, on ne touche à rien (les clés sont masquées à l'écran) ; la case
    « actif » seule est appliquée."""
    from core.models import ConfigurationLomopay
    cle_publique = (request.POST.get('cle_publique') or '').strip()
    cle_secrete = (request.POST.get('cle_secrete') or '').strip()
    actif = request.POST.get('lomopay_actif') == 'on'
    cfg = ConfigurationLomopay.objects.first()
    if cfg is None:
        if not cle_publique or not cle_secrete:
            messages.error(request, "Renseignez la clé publique ET la clé secrète pour activer LomoPay.")
            return
        ConfigurationLomopay.objects.create(
            cle_publique=cle_publique, cle_secrete=cle_secrete, actif=actif)
        messages.success(request, "Clés LomoPay enregistrées — paiement en ligne désormais disponible.")
        return
    # Mise à jour : champs vides = conserver la valeur en place
    if cle_publique:
        cfg.cle_publique = cle_publique
    if cle_secrete:
        cfg.cle_secrete = cle_secrete
    cfg.actif = actif
    cfg.save()
    messages.success(
        request,
        "Configuration LomoPay mise à jour "
        f"(paiement en ligne {'activé' if actif else 'désactivé'}).")

# ==========================================
# SAUVEGARDES SYSTÈME (super-admin)
# ==========================================
@superadmin_required
def sauvegardes_systeme(request):
    if request.method == 'POST':
        choix = (request.POST.get('boutique') or 'TOUTES').strip()
        if choix and choix != 'TOUTES':
            atelier = get_object_or_404(Atelier, id=_int_or_none(choix))
            nom = creer_sauvegarde_systeme(atelier=atelier)
            messages.success(
                request, f"Sauvegarde de la boutique « {atelier.nom} » créée : {nom}")
            return redirect('saas_admin:sauvegardes_systeme')
        nom = creer_sauvegarde_systeme()
        messages.success(request, f"Sauvegarde système (toutes boutiques) créée : {nom}")
        return redirect('saas_admin:sauvegardes_systeme')
    return render(request, 'saas_admin/sauvegardes_systeme.html', {
        'sauvegardes': lister_sauvegardes_systeme(),
        'boutiques': Atelier.objects.all().order_by('nom'),
    })


@superadmin_required
def sauvegarde_systeme_telecharger(request, nom):
    chemin = chemin_sauvegarde_systeme(nom)
    if chemin is None:
        messages.error(request, "Sauvegarde système introuvable.")
        return redirect('saas_admin:sauvegardes_systeme')
    return FileResponse(chemin.open('rb'), as_attachment=True, filename=nom)


@superadmin_required
def sauvegarde_systeme_supprimer(request):
    if request.method == 'POST':
        if supprimer_sauvegarde_systeme(request.POST.get('nom', '')):
            messages.success(request, "Sauvegarde système supprimée.")
        else:
            messages.error(request, "Sauvegarde système introuvable.")
    return redirect('saas_admin:sauvegardes_systeme')

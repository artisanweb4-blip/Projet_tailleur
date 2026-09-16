from datetime import date, timedelta

from django.contrib import messages
from django.contrib.auth.decorators import user_passes_test
from django.contrib.auth.models import User
from django.core.paginator import Paginator
from django.db import transaction
from django.db.models import Q, Sum
from django.shortcuts import get_object_or_404, redirect, render

from .models import Boutique, Facture, FormuleAbonnement


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
    total_boutiques = Boutique.objects.count()
    boutiques_actives = Boutique.objects.filter(statut='ACTIF').count()
    boutiques_essai = Boutique.objects.filter(statut='ESSAI').count()
    boutiques_suspendues = Boutique.objects.filter(statut='SUSPENDU').count()

    # Revenu Mensuel Récurrent (MRR) des boutiques actives
    mrr = Boutique.objects.filter(statut='ACTIF').aggregate(
        total=Sum('formule_abonnement__prix')
    )['total'] or 0

    # Abonnements arrivant à expiration dans les 7 prochains jours
    dans_7_jours = date.today() + timedelta(days=7)
    expirations_proches = Boutique.objects.filter(
        statut='ACTIF',
        date_expiration_abonnement__range=[date.today(), dans_7_jours]
    ).count()

    # Calcul du taux de conversion
    taux_conversion = 0
    if total_boutiques > 0:
        taux_conversion = round((boutiques_actives / total_boutiques) * 100, 1)

    context = {
        'total_boutiques': total_boutiques,
        'boutiques_actives': boutiques_actives,
        'boutiques_essai': boutiques_essai,
        'boutiques_suspendues': boutiques_suspendues,
        'mrr': mrr,
        'expirations_proches': expirations_proches,
        'taux_conversion': taux_conversion,
        'boutiques': Boutique.objects.select_related('formule_abonnement', 'proprietaire').all().order_by('-date_creation'),
    }
    return render(request, 'saas_admin/dashboard.html', context)


# ==========================================
# 2. GESTION DES BOUTIQUES
# ==========================================
@superadmin_required
def superadmin_liste_boutiques(request):
    search_query = request.GET.get('q', '').strip()
    paginate_by = request.GET.get('paginate_by', 10)

    boutiques_list = Boutique.objects.select_related('formule_abonnement', 'proprietaire').all().order_by('-date_creation')

    if search_query:
        boutiques_list = boutiques_list.filter(
            Q(nom_boutique__icontains=search_query) |
            Q(telephone__icontains=search_query)
        )

    try:
        paginate_by = int(paginate_by)
    except ValueError:
        paginate_by = 10

    paginator = Paginator(boutiques_list, paginate_by)
    page_number = request.GET.get('page')
    page_obj = paginator.get_page(page_number)

    formules = FormuleAbonnement.objects.all()

    context = {
        'page_obj': page_obj,
        'formules': formules,
        'search_query': search_query,
        'paginate_by': paginate_by,
    }
    return render(request, 'saas_admin/liste_boutiques.html', context)


@superadmin_required
def ajouter_boutique(request):
    if request.method == 'POST':
        nom_boutique = request.POST.get('nom_boutique')
        email = request.POST.get('email')
        telephone = request.POST.get('telephone')
        formule_id = request.POST.get('formule_id')

        nom_proprietaire = request.POST.get('nom_proprietaire')
        username = request.POST.get('username')
        password = request.POST.get('password')

        if User.objects.filter(username=username).exists():
            messages.error(request, f"L'identifiant '{username}' est déjà utilisé. Veuillez en choisir un autre.")
            return redirect('saas_admin:superadmin_liste_boutiques')

        try:
            with transaction.atomic():
                first_name = nom_proprietaire.split(' ')[0] if nom_proprietaire else ''
                last_name = ' '.join(nom_proprietaire.split(' ')[1:]) if nom_proprietaire and len(nom_proprietaire.split(' ')) > 1 else ''
                
                user = User.objects.create_user(
                    username=username,
                    email=email,
                    password=password,
                    first_name=first_name,
                    last_name=last_name
                )

                formule = FormuleAbonnement.objects.filter(id=formule_id).first() if formule_id else None

                Boutique.objects.create(
                    nom_boutique=nom_boutique,
                    email=email,
                    telephone=telephone,
                    proprietaire=user,
                    formule_abonnement=formule,
                    statut='ESSAI'
                )

                messages.success(request, f"La boutique '{nom_boutique}' et le compte propriétaire '{username}' ont été créés avec succès.")
        
        except Exception as e:
            messages.error(request, f"Une erreur s'est produite lors de la création : {e}")

    return redirect('saas_admin:superadmin_liste_boutiques')


@superadmin_required
def detail_boutique(request, boutique_id):
    boutique = get_object_or_404(Boutique, id=boutique_id)
    formules = FormuleAbonnement.objects.all()
    factures = boutique.factures.all().order_by('-date_paiement')

    context = {
        'boutique': boutique,
        'formules': formules,
        'factures': factures,
    }
    return render(request, 'saas_admin/detail_boutique.html', context)


@superadmin_required
def modifier_boutique(request, boutique_id):
    boutique = get_object_or_404(Boutique, id=boutique_id)
    if request.method == 'POST':
        boutique.nom_boutique = request.POST.get('nom_boutique')
        boutique.slug = request.POST.get('slug')
        boutique.email = request.POST.get('email')
        boutique.telephone = request.POST.get('telephone')
        boutique.save()
        messages.success(request, "Informations de la boutique mises à jour avec succès.")
    return redirect('saas_admin:detail_boutique', boutique_id=boutique.id)


@superadmin_required
def changer_plan_boutique(request, boutique_id):
    boutique = get_object_or_404(Boutique, id=boutique_id)
    if request.method == 'POST':
        formule_id = request.POST.get('formule_id')
        formule = get_object_or_404(FormuleAbonnement, id=formule_id)
        boutique.formule_abonnement = formule
        boutique.save()
        messages.success(request, f"Plan mis à jour vers : {formule.nom}")
    return redirect('saas_admin:detail_boutique', boutique_id=boutique.id)


@superadmin_required
def suspendre_boutique(request, boutique_id):
    boutique = get_object_or_404(Boutique, id=boutique_id)
    if request.method == 'POST':
        boutique.statut = 'SUSPENDU'
        boutique.save()
        messages.warning(request, f"La boutique {boutique.nom_boutique} a été suspendue.")
    return redirect('saas_admin:detail_boutique', boutique_id=boutique.id)


@superadmin_required
def reactiver_boutique(request, boutique_id):
    boutique = get_object_or_404(Boutique, id=boutique_id)
    if request.method == 'POST':
        boutique.statut = 'ACTIF'
        boutique.save()
        messages.success(request, f"La boutique {boutique.nom_boutique} est à nouveau active.")
    return redirect('saas_admin:detail_boutique', boutique_id=boutique.id)


@superadmin_required
def supprimer_boutique(request, boutique_id):
    boutique = get_object_or_404(Boutique, id=boutique_id)
    if request.method == 'POST':
        nom = boutique.nom_boutique
        boutique.delete()
        messages.error(request, f"La boutique {nom} a été supprimée définitivement.")
        return redirect('saas_admin:superadmin_dashboard')
    return redirect('saas_admin:detail_boutique', boutique_id=boutique.id)


# ==========================================
# 3. ACTIONS DE SÉCURITÉ & IMPERSONNALISATION
# ==========================================
@superadmin_required
def reinitialiser_pass_boutique(request, boutique_id):
    boutique = get_object_or_404(Boutique, id=boutique_id)
    if request.method == 'POST':
        # Logique d'envoi de mail ici
        messages.info(request, "Un e-mail de réinitialisation a été envoyé au propriétaire.")
    return redirect('saas_admin:detail_boutique', boutique_id=boutique.id)


@superadmin_required
def impersonner_boutique(request, boutique_id):
    boutique = get_object_or_404(Boutique, id=boutique_id)
    messages.warning(
        request, 
        f"Accès refusé : La connexion directe à l'espace de la boutique '{boutique.nom_boutique}' est désactivée pour les Super Admins."
    )
    return redirect('saas_admin:detail_boutique', boutique_id=boutique.id)


# ==========================================
# 4. GESTION DES FORMULES D'ABONNEMENT
# ==========================================
@superadmin_required
def liste_abonnements(request):
    formules = FormuleAbonnement.objects.all().order_by('prix')
    return render(request, 'saas_admin/abonnements.html', {'formules': formules})


@superadmin_required
def ajouter_abonnement(request):
    if request.method == 'POST':
        duree_mois = request.POST.get('duree_mois', 1)
        try:
            duree_mois = int(duree_mois)
        except ValueError:
            duree_mois = 1

        FormuleAbonnement.objects.create(
            nom=request.POST.get('nom'),
            description=request.POST.get('description'),
            prix=request.POST.get('prix'),
            duree_mois=duree_mois,
            fonctionnalites_incluses=request.POST.get('fonctionnalites_incluses'),
            fonctionnalites_exclues=request.POST.get('fonctionnalites_exclues'),
            est_populaire=request.POST.get('est_populaire') == 'on'
        )
        messages.success(request, "L'abonnement a été créé avec succès.")
    return redirect('saas_admin:abonnements')


@superadmin_required
def modifier_abonnement(request, formule_id):
    formule = get_object_or_404(FormuleAbonnement, id=formule_id)
    if request.method == 'POST':
        duree_mois = request.POST.get('duree_mois', 1)
        try:
            duree_mois = int(duree_mois)
        except ValueError:
            duree_mois = 1

        formule.nom = request.POST.get('nom')
        formule.description = request.POST.get('description')
        formule.prix = request.POST.get('prix')
        formule.duree_mois = duree_mois
        formule.fonctionnalites_incluses = request.POST.get('fonctionnalites_incluses')
        formule.fonctionnalites_exclues = request.POST.get('fonctionnalites_exclues')
        formule.est_populaire = request.POST.get('est_populaire') == 'on'
        formule.save()

        messages.success(request, "L'abonnement a été mis à jour.")
    return redirect('saas_admin:abonnements')


@superadmin_required
def supprimer_abonnement(request, formule_id):
    formule = get_object_or_404(FormuleAbonnement, id=formule_id)
    if request.method == 'POST':
        formule.delete()
        messages.success(request, "L'abonnement a été supprimé.")
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
        messages.success(request, "Les paramètres globaux ont été mis à jour avec succès.")
        return redirect('saas_admin:superadmin_parametres')

    context = {
        'active_tab': 'parametres',
    }
    return render(request, 'saas_admin/parametres.html', context)
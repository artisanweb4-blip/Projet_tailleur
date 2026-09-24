"""
Crée un atelier de démonstration et quatre comptes prêts à l'emploi.

À utiliser quand `python manage.py setup_demo` n'est pas disponible
(c'est-à-dire tant que le 4e patch n'est pas appliqué).

    python crees_comptes.py

Idempotent : relançable sans rien dupliquer. Ne supprime jamais de données.
"""
import os
import sys
from datetime import date, timedelta
from decimal import Decimal

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'tailleur_gestion.settings')

import django  # noqa: E402

django.setup()

from django.contrib.auth.models import User  # noqa: E402

from core.models import (  # noqa: E402
    Abonnement, Atelier, PlanAbonnement, Profil,
)

MOT_DE_PASSE = 'test12345!'
NOM_ATELIER = 'Atelier Kora Couture'

COMPTES = [
    # (identifiant, rôle, prénom, nom, fondateur)
    ('aminata', 'ADMIN', 'Aminata', 'Traoré', True),
    ('mousso', 'GESTIONNAIRE', 'Mousso', 'Diallo', False),
    ('ibra', 'COMPTABLE', 'Ibrahim', 'Sangaré', False),
]


def main():
    # --- Atelier -------------------------------------------------------
    atelier = Atelier.objects.filter(nom=NOM_ATELIER).first()
    if atelier:
        print('Atelier    : %s (existant)' % atelier.nom)
    else:
        atelier = Atelier.objects.create(
            nom=NOM_ATELIER,
            telephone='+223 70 00 00 00',
            email='contact@kora.ml',
            adresse='Hamdallaye ACI 2000, Bamako',
            devise='FCFA',
            seuil_stock_faible=5,
        )
        print('Atelier    : %s (créé)' % atelier.nom)

    plan = PlanAbonnement.objects.filter(nom='Pro').first() or \
        PlanAbonnement.objects.create(nom='Pro', prix_mensuel=Decimal(15000))
    if not Abonnement.objects.filter(atelier=atelier).exists():
        Abonnement.objects.create(
            atelier=atelier, statut='ACTIF', plan=plan,
            date_fin=date.today() + timedelta(days=30),
        )

    # --- Comptes métier ------------------------------------------------
    for login, role, prenom, nom, fondateur in COMPTES:
        user = User.objects.filter(username=login).first()
        if user:
            user.set_password(MOT_DE_PASSE)
            user.first_name = user.first_name or prenom
            user.last_name = user.last_name or nom
            user.save()
            etat = 'existant, mot de passe réinitialisé'
        else:
            user = User.objects.create_user(
                login, password=MOT_DE_PASSE, first_name=prenom, last_name=nom)
            etat = 'créé'

        profil = Profil.objects.filter(user=user).first()
        if profil:
            profil.atelier = atelier
            profil.role = role
            profil.actif = True
            profil.save()
        else:
            Profil.objects.create(
                user=user, atelier=atelier, role=role,
                est_fondateur=fondateur, actif=True,
                telephone='+223 70 00 00 00',
            )
        print('Compte     : %-11s %-13s %s' % (login, role, etat))

    # --- Super-admin plateforme ---------------------------------------
    sa = User.objects.filter(username='superadmin').first()
    if sa:
        sa.set_password(MOT_DE_PASSE)
        sa.is_superuser = True
        sa.is_staff = True
        sa.save()
        etat = 'existant, mot de passe réinitialisé'
    else:
        sa = User.objects.create_superuser(
            'superadmin', 'sa@plateforme.ml', MOT_DE_PASSE)
        etat = 'créé'
    print('Superadmin : %-11s %-13s %s' % ('superadmin', 'plateforme', etat))

    # --- Récapitulatif -------------------------------------------------
    print('')
    print('✅ Terminé. Mot de passe commun : %s' % MOT_DE_PASSE)
    print('')
    print('   Identifiants : aminata (ADMIN) · mousso (GESTIONNAIRE)')
    print('                  ibra (COMPTABLE) · superadmin (back-office)')
    print('')
    total = User.objects.count()
    sans_atelier = Profil.objects.filter(atelier__isnull=True).count()
    print('   Vérification : %d utilisateur(s) en base, %d profil(s) sans atelier'
          % (total, sans_atelier))
    print('')
    print('   Lancez : python manage.py runserver')
    print('   Ouvrez : http://127.0.0.1:8000/')


if __name__ == '__main__':
    main()

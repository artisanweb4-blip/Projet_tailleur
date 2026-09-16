# Migration de données : garantit l'existence des trois plans d'abonnement.
#
# La page « Abonnements & Offres » (core/abonnements.html) restait vide sur
# toute base n'ayant jamais exécuté setup_demo ni une inscription : aucun
# PlanAbonnement n'était créé par défaut. Les valeurs sont idempotentes
# (get_or_create) et alignées sur setup_demo (Pro à 15 000 FCFA) et sur le
# plan d'essai créé par le formulaire d'inscription (Starter, 0 FCFA).
from decimal import Decimal

from django.db import migrations

PLANS = [
    # (nom, prix_mensuel, max_commandes_mois, max_utilisateurs, support_prioritaire)
    ('Starter — essai gratuit', Decimal('0'), 50, 3, False),
    ('Pro', Decimal('15000'), 200, 10, True),
    ('Business', Decimal('30000'), 999999, 25, True),
]


def creer_plans(apps, schema_editor):
    PlanAbonnement = apps.get_model('core', 'PlanAbonnement')
    for nom, prix, commandes, utilisateurs, support in PLANS:
        PlanAbonnement.objects.get_or_create(
            nom=nom,
            defaults={
                'prix_mensuel': prix,
                'max_commandes_mois': commandes,
                'max_utilisateurs': utilisateurs,
                'support_prioritaire': support,
            },
        )


class Migration(migrations.Migration):

    dependencies = [
        ('core', '0012_alter_profil_options_profil_actif_profil_cree_par_and_more'),
    ]

    operations = [
        migrations.RunPython(creer_plans, migrations.RunPython.noop),
    ]

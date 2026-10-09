# 0047 — Mois bonus (offerts) dans les formules d'abonnement.
#
# Passage de la représentation « prix/mois réduit » (grille v2, 12 500 F)
# à la représentation demandée : PRIX PLEIN (15 000 F/mois) + MOIS OFFERTS
# qui ne sont pas facturés :
#
#   Pro 3 mois  : 3 payés + 0 offert   → 45 000 F
#   Pro 6 mois  : 5 payés + 1 offert   → 75 000 F
#   Pro 12 mois : 10 payés + 2 offerts → 150 000 F
#
# Les totaux facturés restent EXACTS ; seule la présentation change.
from django.db import migrations, models


def appliquer_bonus_standard(apps, schema_editor):
    PlanAbonnement = apps.get_model('core', 'PlanAbonnement')

    mappings = {
        3:  dict(mois_bonus=0, prix=15000,
                 description="Tarif plein — jusqu'à 100 commandes par mois."),
        6:  dict(mois_bonus=1, prix=15000,
                 description="Payez 5 mois, le 6e est offert — commandes illimitées."),
        12: dict(mois_bonus=2, prix=15000,
                 description="Payez 10 mois, les 2 derniers sont offerts — commandes illimitées."),
    }
    for duree, cfg in mappings.items():
        plan = (PlanAbonnement.objects
                .filter(duree_mois=duree, prix_mensuel__gt=0, actif=True)
                .order_by('pk').first())
        if plan is None:
            continue
        plan.prix_mensuel = cfg['prix']
        plan.mois_bonus = cfg['mois_bonus']
        plan.description = cfg['description']
        plan.save()


class Migration(migrations.Migration):

    dependencies = [
        ('core', '0018_grille_v2'),
    ]

    operations = [
        migrations.AddField(
            model_name='planabonnement',
            name='mois_bonus',
            field=models.PositiveSmallIntegerField(
                default=0,
                help_text=("Mois offerts (non facturés) au sein de la durée totale. "
                           "Grille standard : 0 (3 mois), 1 (6 mois), 2 (12 mois)."),
            ),
        ),
        migrations.RunPython(appliquer_bonus_standard, migrations.RunPython.noop),
    ]

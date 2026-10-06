# Ajustement de la grille tarifaire (suite à la v2 demandée) :
#  - Pro 3 mois  : 15 000 F/mois, commandes limitées à 100/mois.
#  - Pro 6 mois  : 75 000 F au total (payez 5 mois, le 6e offert), illimité.
#  - Pro 12 mois : 150 000 F au total (payez 10 mois, 2 offerts), illimité.
from django.db import migrations


def nouvelle_grille(apps, schema_editor):
    PlanAbonnement = apps.get_model('core', 'PlanAbonnement')

    # 3 mois : inchangé sur prix, commandes plafonnées à 100/mois
    # 6 mois : prix_mensuel 12 500 → total 75 000 (5 mois tarif plein + 1 offert)
    # 12 mois : prix_mensuel 12 500 → total 150 000 (10 mois tarif plein + 2 offerts)
    conf = {
        3:  dict(prix=15000, max_cmd=100,
                 description="Tarif plein — jusqu'à 100 commandes par mois."),
        6:  dict(prix=12500, max_cmd=999999,
                 description="Payez 5 mois, le 6e mois est offert — commandes illimitées."),
        12: dict(prix=12500, max_cmd=999999,
                 description="Payez 10 mois, les 2 derniers mois sont offerts — commandes illimitées."),
    }
    for duree, cfg in conf.items():
        plan = (PlanAbonnement.objects
                .filter(duree_mois=duree, prix_mensuel__gt=0, actif=True)
                .order_by('pk').first())
        if plan is None:
            continue
        plan.prix_mensuel = cfg['prix']
        plan.max_commandes_mois = cfg['max_cmd']
        plan.description = cfg['description']
        plan.save()


class Migration(migrations.Migration):

    dependencies = [
        ('core', '0017_grille_tarifaire_pro'),
    ]

    operations = [
        migrations.RunPython(nouvelle_grille, migrations.RunPython.noop),
    ]

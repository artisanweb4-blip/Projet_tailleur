# Migration de schéma + données : le catalogue d'offres devient configurable.
#
# Avant : le back-office saas_admin éditait `FormuleAbonnement` (modèle
# parallèle, jamais consommé par l'application), tandis que la page
# « Abonnements & Offres » et la future landing lisaient `PlanAbonnement`,
# dont les trois lignes avaient été créées par la migration 0013 avec des
# valeurs fixes. Les offres affichées n'étaient donc pilotables nulle part.
#
# Maintenant : `PlanAbonnement` porte aussi les champs éditoriaux
# (description, est_populaire, actif) et c'est lui que saas_admin édite.
# L'ancien catalogue FormuleAbonnement est repris uniquement si aucun plan
# n'existe encore (base antérieure à la migration 0013), pour ne perdre
# aucune configuration saisie dans le back-office.
from django.db import migrations, models


def enrichir(apps, schema_editor):
    Plan = apps.get_model('core', 'PlanAbonnement')

    descriptions = {
        'Starter — essai gratuit':
            "Idéal pour découvrir la gestion d'atelier : 14 jours offerts.",
        'Pro':
            "Pour les ateliers avec employés : commandes, paies et paiements.",
        'Business':
            "Pour les grandes maisons : volume illimité et support prioritaire.",
    }
    for nom, texte in descriptions.items():
        Plan.objects.filter(nom=nom, description='').update(description=texte)
    Plan.objects.filter(nom='Pro').update(est_populaire=True)

    if not Plan.objects.exists():
        Formule = apps.get_model('saas_admin', 'FormuleAbonnement')
        for formule in Formule.objects.all():
            Plan.objects.create(
                nom=formule.nom,
                prix_mensuel=formule.prix,
                description=formule.description or '',
                est_populaire=formule.est_populaire,
            )


class Migration(migrations.Migration):

    dependencies = [
        ('core', '0013_seed_plans_abonnement'),
        ('saas_admin', '0002_formuleabonnement_est_populaire_and_more'),
    ]

    operations = [
        migrations.AddField(
            model_name='planabonnement',
            name='description',
            field=models.TextField(blank=True, default=''),
        ),
        migrations.AddField(
            model_name='planabonnement',
            name='est_populaire',
            field=models.BooleanField(default=False),
        ),
        migrations.AddField(
            model_name='planabonnement',
            name='actif',
            field=models.BooleanField(
                default=True,
                help_text="Décocher pour masquer l'offre de la landing et de l'application.",
            ),
        ),
        migrations.RunPython(enrichir, migrations.RunPython.noop),
    ]

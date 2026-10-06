# Généré pour la grille tarifaire 0045 : Essai 14 j + Pro 3/6/12 mois.
from django.db import migrations


FONCTIONNALITES_PRO = (
    "Tableau de bord & statistiques\n"
    "Clients & mensurations illimités\n"
    "Commandes, calendrier & plan de charge\n"
    "Comptabilité — dépenses & recettes\n"
    "Employés & paies\n"
    "Catalogue modèles & accessoires\n"
    "Export Excel & sauvegardes"
)


def forcer_grille_tarifaire(apps, schema_editor):
    PlanAbonnement = apps.get_model('core', 'PlanAbonnement')

    # ---------- 1) Essai gratuit (Starter) ----------
    essai = PlanAbonnement.objects.filter(
        duree_mois=0, prix_mensuel=0
    ).order_by('pk').first()
    if essai is None:
        essai = PlanAbonnement.objects.filter(prix_mensuel=0).order_by('pk').first()
    if essai is None:
        essai = PlanAbonnement(nom="Starter — essai gratuit", prix_mensuel=0, duree_mois=0)
    essai.nom = "Starter — essai gratuit"
    essai.duree_mois = 0
    essai.max_commandes_mois = 50
    essai.max_utilisateurs = 4
    essai.support_prioritaire = False
    essai.description = "Idéal pour découvrir la gestion d'atelier : 14 jours offerts."
    essai.est_populaire = False
    essai.actif = True
    essai.save()

    # ---------- 2) Plans payants 3 / 6 / 12 mois ----------
    # Mêmes fonctionnalités ; remise -10 % (6 mois), -20 % (12 mois).
    grille = {
        3:  dict(nom="Pro 3 mois",  prix=15000,
                 description="Le meilleur de TailleurPro, tarif mensuel de base."),
        6:  dict(nom="Pro 6 mois",  prix=13500,
                 description="Mêmes fonctions — 10 % de remise (13 500 FCFA / mois)."),
        12: dict(nom="Pro 12 mois", prix=12000,
                 description="Mêmes fonctions — 20 % de remise (12 000 FCFA / mois)."),
    }
    plans_valides = []
    for duree, cfg in grille.items():
        # Un seul plan payant par durée ; les autres (doublons, anciens) sont coupés.
        qs = (PlanAbonnement.objects
              .filter(duree_mois=duree, prix_mensuel__gt=0)
              .order_by('pk'))
        plan = qs.first()
        if plan is None:
            plan = PlanAbonnement(nom=cfg['nom'], prix_mensuel=cfg['prix'], duree_mois=duree)
        plan.nom = cfg['nom']
        plan.prix_mensuel = cfg['prix']
        plan.max_commandes_mois = 50
        plan.max_utilisateurs = 3
        plan.support_prioritaire = True
        plan.description = cfg['description']
        plan.fonctionnalites_incluses = FONCTIONNALITES_PRO
        plan.actif = True
        plan.save()
        plans_valides.append(plan.pk)
        qs.exclude(pk=plan.pk).update(actif=False)

    # On célèbre la formule la plus courte (engagement faible) comme populaire :
    PlanAbonnement.objects.filter(pk__in=plans_valides, duree_mois=3).update(est_populaire=True)
    PlanAbonnement.objects.filter(pk__in=plans_valides).exclude(duree_mois=3).update(est_populaire=False)

    # ---------- 3) Tout autre plan payant actif (ancienne grille) → coupé ----------
    PlanAbonnement.objects.filter(prix_mensuel__gt=0, actif=True).exclude(
        duree_mois__in=(3, 6, 12)
    ).update(actif=False)


class Migration(migrations.Migration):

    dependencies = [
        ('core', '0016_lomopay'),
    ]

    # Pas d'opération inverse : la grille précédente est spécifique à chaque
    # instance client (données). On laisse Django redescendre sans rien faire.
    operations = [
        migrations.RunPython(forcer_grille_tarifaire, migrations.RunPython.noop),
    ]

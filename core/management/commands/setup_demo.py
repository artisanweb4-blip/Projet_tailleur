"""
Commande de démonstration : crée un atelier et les comptes associés.

    python manage.py setup_demo

Crée un atelier « Atelier Kora Couture » et quatre comptes, tous avec le
mot de passe `test12345!` :

    aminata     ADMIN           accès complet
    mousso      GESTIONNAIRE    production (clients, commandes, ventes)
    ibra        COMPTABLE       dépenses, paiements, factures
    superadmin  —               back-office plateforme (/saas-admin/)

Plus quelques données métier (client, mensuration, modèle, accessoire,
employé, commande, dépense, mouvements de stock) pour que chaque page ait
quelque chose à afficher.

La commande est idempotente : relancée, elle met à jour les comptes existants
au lieu de les dupliquer. Elle ne supprime jamais de données.
"""

from datetime import date, timedelta
from decimal import Decimal

from django.contrib.auth.models import User
from django.core.management.base import BaseCommand
from django.db import transaction

from core.models import (
    Abonnement, Accessoire, Atelier, CatalogueModele, Client, Commande,
    Depense, Employe, LigneCommande, Mensuration, MouvementStock,
    PlanAbonnement, Profil,
)
from saas_admin.models import Boutique, FormuleAbonnement

MOT_DE_PASSE = 'test12345!'
NOM_ATELIER = 'Atelier Kora Couture'


class Command(BaseCommand):
    help = "Crée un atelier de démonstration et quatre comptes prêts à l'emploi."

    def add_arguments(self, parser):
        parser.add_argument(
            '--mot-de-passe', default=MOT_DE_PASSE,
            help='Mot de passe des comptes créés (défaut : %(default)s)',
        )
        parser.add_argument(
            '--vide', action='store_true',
            help="Réinitialise d'abord les données de démonstration "
                 "(supprime l'atelier de démo et ses comptes).",
        )

    @transaction.atomic
    def handle(self, *args, **options):
        mot_de_passe = options['mot_de_passe']

        if options['vide']:
            self._nettoyer()

        atelier = self._atelier()
        comptes = self._comptes(atelier, mot_de_passe)
        self._superadmin(mot_de_passe)
        self._backoffice(atelier, comptes['aminata'])
        created = self._donnees_metier(atelier)

        self.stdout.write('')
        self.stdout.write(self.style.SUCCESS('✅ Démonstration prête.'))
        self.stdout.write('')
        self.stdout.write('   Atelier        : %s' % atelier.nom)
        self.stdout.write('   Mot de passe   : %s  (tous les comptes)' % mot_de_passe)
        self.stdout.write('')
        self.stdout.write('   %-12s %-14s %s' % ('IDENTIFIANT', 'RÔLE', 'PÉRIMÈTRE'))
        for login, role, perimetre in (
            ('aminata', 'ADMIN', 'accès complet'),
            ('mousso', 'GESTIONNAIRE', 'clients, commandes, ventes'),
            ('ibra', 'COMPTABLE', 'dépenses, paiements, factures'),
            ('superadmin', 'plateforme', '/saas-admin/dashboard/'),
        ):
            self.stdout.write('   %-12s %-14s %s' % (login, role, perimetre))
        self.stdout.write('')
        if created:
            self.stdout.write('   Données métier : %s' % ', '.join(created))
        else:
            self.stdout.write('   Données métier : déjà présentes, rien ajouté.')
        self.stdout.write('')
        self.stdout.write('   Lancez ensuite : python manage.py runserver')
        self.stdout.write('   Puis ouvrez    : http://127.0.0.1:8000/')
        self.stdout.write('')

    # ------------------------------------------------------------------

    def _nettoyer(self):
        atelier = Atelier.objects.filter(nom=NOM_ATELIER).first()
        if atelier:
            atelier.delete()
            self.stdout.write('   Atelier de démo supprimé.')
        for login in ('aminata', 'mousso', 'ibra', 'superadmin'):
            User.objects.filter(username=login).delete()
        Boutique.objects.filter(nom_boutique=NOM_ATELIER).delete()

    def _atelier(self):
        atelier, cree = Atelier.objects.get_or_create(
            nom=NOM_ATELIER,
            defaults={
                'telephone': '+223 70 00 00 00',
                'email': 'contact@kora.ml',
                'adresse': 'Hamdallaye ACI 2000, Bamako',
                'devise': 'FCFA',
                'seuil_stock_faible': 5,
            },
        )
        plan, _ = PlanAbonnement.objects.get_or_create(
            nom='Pro', defaults={'prix_mensuel': Decimal(15000)})
        Abonnement.objects.get_or_create(
            atelier=atelier,
            defaults={'statut': 'ACTIF', 'plan': plan,
                      'date_fin': date.today() + timedelta(days=30)},
        )
        self.stdout.write('   Atelier   : %s (%s)' % (
            atelier.nom, 'créé' if cree else 'existant'))
        return atelier

    def _compte(self, atelier, login, role, prenom, nom, fondateur=False):
        user, cree = User.objects.get_or_create(
            username=login,
            defaults={'first_name': prenom, 'last_name': nom},
        )
        if cree:
            user.set_password(MOT_DE_PASSE)
            user.save()
        profil, _ = Profil.objects.get_or_create(
            user=user,
            defaults={'atelier': atelier, 'role': role,
                      'est_fondateur': fondateur, 'actif': True},
        )
        # Un compte préexistant peut ne pas être rattaché à l'atelier : on répare.
        if profil.atelier != atelier or profil.role != role:
            profil.atelier = atelier
            profil.role = role
            profil.actif = True
            profil.save()
        return user

    def _comptes(self, atelier, mot_de_passe):
        comptes = {}
        for login, role, prenom, nom, fondateur in (
            ('aminata', 'ADMIN', 'Aminata', 'Traoré', True),
            ('mousso', 'GESTIONNAIRE', 'Mousso', 'Diallo', False),
            ('ibra', 'COMPTABLE', 'Ibrahim', 'Sangaré', False),
        ):
            comptes[login] = self._compte(atelier, login, role, prenom, nom, fondateur)
        # Le mot de passe demandé en ligne de commande prime.
        for user in comptes.values():
            user.set_password(mot_de_passe)
            user.save()
        self.stdout.write('   Comptes   : %d rattachés à l\'atelier' % len(comptes))
        return comptes

    def _superadmin(self, mot_de_passe):
        user, cree = User.objects.get_or_create(
            username='superadmin',
            defaults={'email': 'sa@plateforme.ml', 'is_superuser': True,
                      'is_staff': True},
        )
        if cree:
            user.is_superuser = True
            user.is_staff = True
        user.set_password(mot_de_passe)
        user.save()
        self.stdout.write('   Superadmin: %s' % ('créé' if cree else 'existant'))

    def _backoffice(self, atelier, proprietaire):
        formule, _ = FormuleAbonnement.objects.get_or_create(
            nom='Débutant',
            defaults={'prix': Decimal(5000), 'duree_mois': 1, 'est_populaire': True,
                      'fonctionnalites_incluses':
                          "Jusqu'à 50 commandes/mois\n1 utilisateur"},
        )
        Boutique.objects.get_or_create(
            nom_boutique=atelier.nom,
            defaults={'proprietaire': proprietaire, 'formule_abonnement': formule,
                      'statut': 'ACTIF',
                      'date_expiration_abonnement': date.today() + timedelta(days=30)},
        )

    def _donnees_metier(self, atelier):
        """N'ajoute des données que si l'atelier est vide. Ne supprime jamais."""
        if Client.objects.filter(atelier=atelier).exists():
            return []

        faits = []
        client = Client.objects.create(
            atelier=atelier, nom='Fatoumata', prenom='Coulibaly', genre='F',
            telephone='+223 66 55 44 33')
        Mensuration.objects.create(
            atelier=atelier, client=client, beneficiaire='', libelle='Boubou brodé',
            donnees={'Tour de poitrine': '96', 'Longueur totale': '135',
                     'Épaules': '40'})
        faits.append('1 client + mensuration')

        modele = CatalogueModele.objects.create(
            atelier=atelier, nom='Boubou brodé', type_modele='COUTURE',
            prix_base=Decimal(25000))
        pap = CatalogueModele.objects.create(
            atelier=atelier, nom='Chemise bazin prête-à-porter',
            type_modele='PRET_A_PORTER', prix_base=Decimal(12000),
            stock_pret_a_porter=20, taille_disponible='M, L, XL')
        accessoire = Accessoire.objects.create(
            atelier=atelier, nom='Bouton doré', categorie='BOUTON',
            prix_unitaire=Decimal(250), stock_disponible=40, unite='PIECE')
        faits.append('2 modèles + 1 accessoire')

        employe = Employe.objects.create(
            atelier=atelier, nom='Seydou', prenom='Keita',
            telephone='+223 79 88 77 66', poste='COUTURIER',
            type_remuneration='MIXTE', salaire_mensuel=Decimal(75000))
        faits.append('1 employé')

        commande = Commande.objects.create(
            atelier=atelier, client=client, statut='EN_COURS',
            date_livraison_prevue=date.today() + timedelta(days=7),
            employe_attribue=employe)
        LigneCommande.objects.create(
            atelier=atelier, commande=commande, modele=modele, quantite=1,
            prix_unitaire=Decimal(25000), type_ligne='COUTURE')
        faits.append('1 commande + ligne')

        auteur = User.objects.filter(username='aminata').first()
        Depense.objects.create(
            atelier=atelier, libelle='Achat tissu bazin',
            montant=Decimal(45000), date=date.today())
        faits.append('1 dépense')

        MouvementStock.objects.create(
            atelier=atelier, type_mouvement='REAPPRO', modele=pap, quantite=20,
            stock_avant=0, stock_apres=20, auteur=auteur,
            commentaire='Réception commande fournisseur')
        MouvementStock.objects.create(
            atelier=atelier, type_mouvement='VENTE', accessoire=accessoire,
            quantite=-4, stock_avant=44, stock_apres=40, auteur=auteur,
            commande=commande)
        MouvementStock.objects.create(
            atelier=atelier, type_mouvement='PERTE', modele=pap, quantite=-1,
            stock_avant=21, stock_apres=20, auteur=auteur,
            commentaire='Tache de teinture, invendable')
        MouvementStock.objects.create(
            atelier=atelier, type_mouvement='INVENTAIRE', accessoire=accessoire,
            quantite=-2, stock_avant=42, stock_apres=40, auteur=auteur,
            commentaire='Écart constaté lors du comptage mensuel')
        faits.append('4 mouvements de stock')

        return faits

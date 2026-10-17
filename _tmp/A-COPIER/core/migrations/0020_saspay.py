from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ('core', '0019_plan_mois_bonus'),
    ]

    operations = [
        migrations.DeleteModel(name='LomoPayTransaction'),
        migrations.DeleteModel(name='ConfigurationLomopay'),
        migrations.CreateModel(
            name='ConfigurationSaspay',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True,
                                           serialize=False, verbose_name='ID')),
                ('cle_secrete', models.CharField(max_length=120)),
                ('secret_webhook', models.CharField(blank=True, default='',
                    help_text=("Secret de signature du webhook SasPay (signing_secret), "
                               "visible UNE SEULE FOIS lors de la création du webhook "
                               "dans le tableau de bord SasPay. Optionnel : sans lui, "
                               "l'activation repose sur le retour client + la re-vérification API."),
                    max_length=120)),
                ('actif', models.BooleanField(default=True,
                    help_text="Décocher pour désactiver le paiement en ligne sans effacer les clés.")),
                ('cree_le', models.DateTimeField(auto_now_add=True)),
                ('modifie_le', models.DateTimeField(auto_now=True)),
            ],
            options={'verbose_name': 'Configuration SasPay'},
        ),
        migrations.CreateModel(
            name='SasPayTransaction',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True,
                                           serialize=False, verbose_name='ID')),
                ('montant', models.PositiveIntegerField()),
                ('devise', models.CharField(default='XOF', max_length=3)),
                ('description', models.CharField(blank=True, default='', max_length=200)),
                ('external_reference', models.CharField(max_length=64, unique=True)),
                ('id_saspay', models.CharField(blank=True, default='', max_length=64)),
                ('checkout_url', models.URLField(blank=True, default='', max_length=500)),
                ('methode', models.CharField(blank=True, default='', max_length=40)),
                ('statut', models.CharField(
                    choices=[('PENDING', 'En attente'), ('COMPLETED', 'Payé'),
                             ('FAILED', 'Échoué / annulé')],
                    default='PENDING', max_length=10)),
                ('evenement_id', models.CharField(blank=True, default='',
                    help_text="Dernier traitement de webhook (anti-doublon).",
                    max_length=64)),
                ('cree_le', models.DateTimeField(auto_now_add=True)),
                ('maj_le', models.DateTimeField(auto_now=True)),
                ('atelier', models.ForeignKey(
                    on_delete=django.db.models.deletion.CASCADE,
                    related_name='transactions_saspay', to='core.atelier')),
                ('plan', models.ForeignKey(
                    blank=True, null=True,
                    on_delete=django.db.models.deletion.SET_NULL,
                    related_name='+', to='core.planabonnement')),
            ],
            options={'verbose_name': 'Transaction SasPay',
                     'ordering': ['-cree_le']},
        ),
    ]

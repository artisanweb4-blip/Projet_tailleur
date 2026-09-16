# Projet_tailleur

SaaS multi-tenant de gestion pour **ateliers de couture et tailleurs**, en français.

Clients et mensurations · commandes sur mesure et ventes directes · catalogue de modèles ·
accessoires et stock avec seuils d'alerte · dépenses et comptabilité · employés, paie à la
pièce et plan de charge · calendrier des échéances · factures, reçus et fiches atelier en PDF ·
abonnements et back-office super-admin.

| | |
|---|---|
| Framework | Django 6.1 (monolithe, rendu serveur) |
| Base de données | PostgreSQL (SQLite possible en local) |
| Front | Bootstrap 5.3 + Bootstrap Icons (chargés depuis le CDN jsDelivr) |
| PDF | xhtml2pdf (reportlab) |
| Multi-tenancy | Base partagée, colonne `atelier_id` sur chaque table métier |

---

## Démarrage rapide

### 1. Prérequis

- Python **3.11 ou plus récent** (vérifié avec 3.13)
- PostgreSQL 13+ — *ou rien du tout si vous démarrez en SQLite*

### 2. Installation

```bash
git clone https://github.com/artisanweb4-blip/Projet_tailleur.git
cd Projet_tailleur

python -m venv .venv
source .venv/bin/activate          # Windows : .venv\Scripts\activate

pip install -r requirements.txt
```

### 3. Configuration

`.env` **n'est pas fourni** (il est dans `.gitignore`, pour ne jamais committer de secret).
Il faut donc le créer :

```bash
cp .env.example .env          # Windows : copy .env.example .env
```

Puis éditer `.env`. Pour un **démarrage immédiat sans PostgreSQL** :

```ini
DJANGO_DEBUG=True
DJANGO_ALLOWED_HOSTS=localhost,127.0.0.1
DB_ENGINE=sqlite3
DB_NAME=db.sqlite3
```

Pour **PostgreSQL**, renseigner `DB_NAME`, `DB_USER`, `DB_PASSWORD`, `DB_HOST`, `DB_PORT`.

> ⚠️ `.env` est dans `.gitignore` et ne doit **jamais** être commité.
> Le mot de passe PostgreSQL qui était codé en dur dans `settings.py` a été retiré du dépôt :
> il est considéré comme compromis et doit être changé sur toutes les bases où il a servi.
>
> Sans `.env`, l'application démarre quand même — mais sur PostgreSQL par défaut, avec un
> mot de passe vide. Si vous voyez `OperationalError` ou `FATAL: password authentication
> failed`, c'est que `.env` manque ou est mal renseigné.

### 4. Base de données et premier lancement

```bash
python manage.py migrate
```

> **`migrate` est obligatoire avant le premier `runserver`.** Sans lui, la base est vide et
> la première requête échoue sur `no such table: django_session` — Django l'annonce par
> `You have NN unapplied migration(s)` au démarrage.

Puis créer un atelier de démonstration avec ses comptes :

```bash
python manage.py setup_demo
```

Cette commande crée l'atelier « Atelier Kora Couture » et quatre comptes, tous avec le mot
de passe `test12345!` :

| Identifiant | Rôle | Périmètre |
|---|---|---|
| `aminata` | `ADMIN` | accès complet |
| `mousso` | `GESTIONNAIRE` | clients, commandes, ventes |
| `ibra` | `COMPTABLE` | dépenses, paiements, factures |
| `superadmin` | plateforme | `/saas-admin/dashboard/` |

Elle ajoute aussi de quoi remplir chaque page : un client et sa mensuration, deux modèles,
un accessoire, un employé, une commande avec sa ligne, une dépense et quatre mouvements de
stock. Elle est **idempotente** (relançable sans dupliquer) et ne supprime jamais de données.

Options : `--mot-de-passe <valeur>` pour choisir un autre mot de passe, `--vide` pour
repartir de zéro.

> `python manage.py createsuperuser` crée bien un compte `is_superuser`, mais **sans atelier** :
> il donne accès au back-office `/saas-admin/` et à `/admin/`, pas à l'application métier.
> Pour utiliser l'application, il faut un compte rattaché à un atelier — d'où `setup_demo`.

Enfin :

```bash
python manage.py runserver
```

Ouvrir http://127.0.0.1:8000/ — la racine redirige vers la page de connexion.

Le back-office de la plateforme est sur http://127.0.0.1:8000/saas-admin/dashboard/
(réservé aux comptes `is_superuser`).

---

## Variables d'environnement

Toutes documentées dans [`.env.example`](.env.example). Les principales :

| Variable | Défaut | Rôle |
|---|---|---|
| `DJANGO_SECRET_KEY` | clé de développement | **Obligatoire en production.** L'app refuse de démarrer si `DEBUG=False` et que la clé vaut encore la valeur de développement. |
| `DJANGO_DEBUG` | `True` | À passer à `False` dès que le site est accessible depuis Internet. |
| `DJANGO_ALLOWED_HOSTS` | `localhost,127.0.0.1` | Liste séparée par des virgules. |
| `DB_ENGINE` | `postgresql` | `postgresql` ou `sqlite3`. |
| `DB_NAME` `DB_USER` `DB_PASSWORD` `DB_HOST` `DB_PORT` | — | Connexion PostgreSQL. |
| `SECURE_SSL_REDIRECT` | `True` | Appliqué uniquement quand `DEBUG=False`. |
| `SECURE_HSTS_SECONDS` | `3600` | Augmenter à `31536000` une fois le HTTPS validé. |

Une variable déjà présente dans l'environnement du système a toujours priorité sur `.env`
(comportement attendu sous Docker, systemd ou un PaaS).

Générer une clé secrète :

```bash
python -c "from django.core.management.utils import get_random_secret_key as k; print(k())"
```

---

## Architecture

```
tailleur_gestion/      settings, urls racine, wsgi, asgi
core/                  le métier — models, views, forms, templates, middleware
saas_admin/            la plateforme — boutiques, formules d'abonnement, super-admin
```

### Les trois rôles métier

Définis dans `core/models.py` (`Profil.ROLES`), décrits dans `Profil.DESCRIPTIONS_ROLES` :

| Rôle | Périmètre annoncé |
|---|---|
| `ADMIN` | Accès complet : paramètres, utilisateurs, employés, catalogue, commandes, comptabilité. |
| `GESTIONNAIRE` | Clients, mensurations, commandes, ventes directes, livraisons. Pas de comptabilité ni de paramètres. |
| `COMPTABLE` | Dépenses, paiements, factures, reçus, rapports financiers. Consultation seule des commandes. |

### Isolation entre ateliers

Chaque modèle métier hérite de `TenantAwareModel`, qui porte une clé étrangère `atelier`.
Les vues résolvent l'atelier courant via `get_user_atelier(request.user)` puis filtrent
systématiquement (`get_object_or_404(Client, pk=pk, atelier=atelier)`).

> **Il n'y a pas de filtrage automatique au niveau de l'ORM.** `core/middleware.py` alimente
> un `threading.local()` que rien ne consomme : le `TenantManager` annoncé dans sa docstring
> n'a jamais été implémenté. L'isolation repose donc entièrement sur le filtrage manuel dans
> chaque vue — toute nouvelle vue doit le reprendre.

---

## Développement

### Vérifications

```bash
python manage.py check                          # doit renvoyer « no issues »
python manage.py makemigrations --check --dry-run   # doit renvoyer « No changes detected »
python manage.py test
```

### Outils de diagnostic

Les trois scripts de diagnostic ci-dessous vivent hors du dépôt (dossier `dev/` de l'espace
de travail de l'audit) et s'appuient sur une base SQLite, sans jamais toucher à PostgreSQL.

```bash
export PYTHONPATH=$PWD:/chemin/vers/dev
export DJANGO_SETTINGS_MODULE=dev_settings

python manage.py migrate
python manage.py setup_demo        # jeu de données — fourni par le dépôt
python /chemin/vers/dev/rbac.py            # matrice page × rôle : qui voit quoi
python /chemin/vers/dev/escalade.py        # écritures croisées entre rôles
python /chemin/vers/dev/audit_templates.py # {% url %} cassées + templates orphelins
```

`dev/rbac.py` affiche les 14 pages principales croisées avec les 4 rôles et signale tout
crash. `dev/escalade.py` exécute 8 écritures interdites et compte celles qui passent quand
même — **3/8 actuellement**, ce qui mesure le défaut d'autorisation décrit dans `AUDIT.md` §7.
Quand le contrôle par rôle sera branché, ce script doit afficher 8/8.

Pour un jeu de données plus riche, `dev/seed.py` fait la même chose que `setup_demo` en
recréant la base de zéro.

---

## Déploiement

1. `DJANGO_DEBUG=False`, `DJANGO_SECRET_KEY` générée, `DJANGO_ALLOWED_HOSTS` renseigné.
2. Servir derrière un reverse proxy TLS (nginx, Caddy, Traefik). Décommenter
   `SECURE_PROXY_SSL_HEADER` dans `settings.py`, sinon `SECURE_SSL_REDIRECT` provoque une
   boucle de redirections.
3. `python manage.py collectstatic` puis servir `staticfiles/` par le proxy.
4. `MEDIA_ROOT` (`media/`) doit être sur un volume persistant : logos, photos d'employés,
   photos de tissus y sont téléversés.
5. Servir l'app avec gunicorn (WSGI) ou uvicorn (ASGI, voir `tailleur_gestion/asgi.py`).

---

## État connu

Un audit complet figure dans [`AUDIT.md`](AUDIT.md) : anomalies corrigées, anomalies restantes,
et plan d'action en 5 étapes.

À retenir avant toute mise en ligne :

- 🔴 **Le contrôle par rôle n'est pas encore appliqué** : toutes les vues sont protégées par
  `@login_required` et par le filtrage d'atelier, mais pas par le rôle. Un COMPTABLE peut
  actuellement supprimer un client, un GESTIONNAIRE peut créer une dépense.
  Suivi dans `AUDIT.md` §7, correctif à l'étape 3 du plan d'action.
- 🟠 **Aucun test automatisé** (`core/tests.py` est vide).
- 🟠 **Deux systèmes d'abonnement parallèles** non reliés : `core.Atelier`/`PlanAbonnement`
  et `saas_admin.Boutique`/`FormuleAbonnement`.
- 🟢 **Bootstrap est chargé depuis un CDN** : l'interface perd sa mise en forme hors-ligne.

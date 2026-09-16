# Audit — Projet_tailleur

**Dépôt** : https://github.com/artisanweb4-blip/Projet_tailleur (public, branche `main`)
**Commits** : 2 (`d6b6a33` premier commit, `a190097` nettoyage)
**Date de l'audit** : 16 septembre 2026
**Méthode** : lecture du code + exécution réelle (Django 6.1.1 / SQLite de test, migrations, seed de données, visite automatisée de toutes les routes GET avec 4 rôles, tests d'écriture POST croisés entre rôles).

---

## 0. Suivi des corrections

Branche : `fix/audit-securite-500` (commits locaux, rien n'a été poussé sur GitHub).

| # | Anomalie | État |
|---|---|---|
| 2 | Mot de passe PostgreSQL commité en clair | ✅ **Retiré du code** — ⚠️ *reste à changer le mot de passe sur vos bases* |
| 3 | `DEBUG=True`, `ALLOWED_HOSTS=[]`, `SECRET_KEY` en dur | ✅ Corrigé (`.env` + garde au démarrage) |
| 4 | `/stock/historique/` → 500 | ✅ Corrigé (template créé) |
| 5 | `/parametres/` → 500 pour le super-admin | ✅ Corrigé (garde `atelier is None`) |
| 6 | Aucun `requirements.txt` | ✅ Créé |
| 9 | `boutique_context` renvoie toujours `None` | ✅ Corrigé |
| — | Zéro README | ✅ Créé |
| — | Avertissement `staticfiles.W004` | ✅ Corrigé (`static/` créé) — `manage.py check` renvoie désormais **0 problème** |
| — | 12 références `{% url %}` cassées | ✅ 11 corrigées — reste `'recherche_clients'` (vue inexistante, voir §10) |
| — | `export_data.py` inutilisable | ✅ Corrigé (module de settings erroné, export UTF-8, modèles système exclus) |
| 1 | **Contrôle par rôle non appliqué** | ⏳ **À faire** — harnais de test livré, voir §7 |
| 16 | **`POST /inscription/` ne créait aucun compte** | ✅ Corrigé (commit `3eaacdd`), voir §6ter |
| 17 | `MESSAGE_TAGS` absent → 42 messages d'erreur sans style | ✅ Corrigé |
| 18 | Messages flash jamais affichés sur le tableau de bord | ✅ Corrigé |
| 19 | Essai gratuit de 14 jours promis mais jamais accordé | ✅ Corrigé |
| 7 | Deux systèmes d'abonnement parallèles | ⏳ À faire (décision produit nécessaire) |
| 8 | `TenantMiddleware` mort | ⏳ À faire (supprimer ou implémenter) |
| 10 | 107 lignes de décorateurs morts et cassés | ⏳ À faire |
| 11 | 8 routes dupliquées dans `core/urls.py` | ⏳ À faire |
| 12 | Zéro test dans le dépôt, zéro CI | ⏳ À faire |
| 13 | Bootstrap via CDN | ⏳ À faire |
| 14 | 6 templates orphelins | ⏳ À faire (décision : les câbler ou les supprimer) |
| 15 | Fichiers de données inutiles | ⏳ À faire |

### Outils de vérification livrés

Quatre scripts reproductibles, hors dépôt (dossier `dev/` de l'espace de travail), sur base SQLite jetable — ils ne touchent jamais à votre PostgreSQL :

| Script | Rôle |
|---|---|
| `dev/dev_settings.py` | Settings de test : SQLite, `DEBUG_PROPAGATE_EXCEPTIONS=True` |
| `dev/seed.py` | Jeu de données de démo : 1 atelier, 4 comptes, clients, commande, mouvements de stock |
| `dev/rbac.py` | Matrice page × rôle — détecte les crashes et les accès anormaux |
| `dev/escalade.py` | Écritures croisées entre rôles — 8 contrôles attendus/bloqués |
| `dev/audit_templates.py` | Références `{% url %}` cassées + templates orphelins |

Ils sont décrits dans le README, section « Développement ».

---

## 1. Ce que c'est

SaaS de gestion pour **ateliers de couture / tailleurs**, multi-tenant, en français, orienté marché ouest-africain (devises FCFA, GNF, MAD…).

| | |
|---|---|
| Stack | Django 6.x (monolithe, rendu serveur), PostgreSQL, Bootstrap 5 via CDN, xhtml2pdf pour les PDF |
| Taille | 7 570 lignes de Python, 44 templates HTML, 91 fichiers, 1,5 Mo |
| Apps | `core` (le métier), `saas_admin` (la plateforme / super-admin) |
| Multi-tenancy | Base de données partagée, une colonne `atelier_id` sur chaque table métier |

### Modules fonctionnels couverts

Clients & mensurations (fiches de mesures en JSON, plusieurs bénéficiaires par client) · Commandes sur mesure et ventes directes · Catalogue de modèles · Accessoires & stock avec seuils d'alerte · Dépenses / comptabilité · Employés, paie à la pièce ou au fixe, plan de charge · Calendrier & échéances · Factures, reçus de caisse, fiches atelier (PDF) · Abonnements SaaS et back-office super-admin avec impersonation.

**Verdict global : le périmètre fonctionnel est large et cohérent, le code est lisible, bien commenté en français, et les requêtes sont correctement optimisées (`select_related` / `prefetch_related` présents, y compris sur les listes lourdes). Le problème n'est pas la qualité d'écriture — c'est que la couche d'autorisation annoncée n'est pas branchée, et que la configuration de production est absente.**

---

## 2. Synthèse des anomalies

| # | Sévérité | Anomalie | Preuve |
|---|---|---|---|
| 1 | 🔴 **Critique** | Le contrôle par rôle n'est appliqué **nulle part** : n'importe quel membre peut tout faire | Tests POST croisés §3 |
| 2 | 🔴 **Critique** | Mots de passe de production commités en clair dans `settings.py` | §4.1 |
| 3 | 🔴 **Critique** | `DEBUG = True`, `ALLOWED_HOSTS = []`, `SECRET_KEY` en dur | §4.2 |
| 4 | 🟠 Majeur | `/stock/historique/` → **erreur 500** pour tous les rôles (template manquant) | §3.1 |
| 5 | 🟠 Majeur | `/parametres/` → **erreur 500** pour le super-admin (`atelier.DEVISES` sur `None`) | §3.2 |
| 6 | 🟠 Majeur | Aucun `requirements.txt`, aucune dépendance figée ; `xhtml2pdf` nécessaire mais jamais déclaré | §4.3 |
| 7 | 🟠 Majeur | Deux systèmes d'abonnement parallèles et non connectés (`Atelier`/`Abonnement` vs `Boutique`/`FormuleAbonnement`) | §5.1 |
| 8 | 🟡 Moyen | `TenantMiddleware` + `threading.local()` : code mort, inutilisable en ASGI | §5.2 |
| 9 | 🟡 Moyen | `context_processors.boutique_context` ne renvoie jamais rien (`request.user.profile`, `profil.boutique` n'existent pas) | §5.3 |
| 10 | 🟡 Moyen | 107 lignes de décorateurs morts qui, s'ils étaient branchés, **casseraient tout** (`redirect('login')` introuvable) | §5.4 |
| 11 | 🟡 Moyen | 8 routes dupliquées dans `core/urls.py` — la 2ᵉ occurrence est du code mort | §5.5 |
| 12 | 🟡 Moyen | Zéro test (`core/tests.py` = 3 lignes vides), zéro README, zéro CI | §6 |
| 13 | 🟢 Mineur | Bootstrap chargé depuis un CDN → l'app ne s'affiche plus hors-ligne | §6 |
| 14 | 🟢 Mineur | 12 références `{% url %}` cassées + 6 templates orphelins | §5.6 |
| 15 | 🟢 Mineur | Fichiers de données inutiles commités (`data.json`, `data_utf8.json` = `[]`, `export_data.py` pointe vers un module inexistant) | §6 |

---

## 3. Les deux bugs bloquants (vérifiés à l'exécution)

### 3.1 `/stock/historique/` → 500 pour tout le monde

`core/views.py:2056` fait `render(request, 'core/historique_stock.html', …)` mais **ce template n'existe pas**. Le dossier `core/templates/core/` contient 36 fichiers, aucun ne porte ce nom.

```
TemplateDoesNotExist: core/historique_stock.html
  @ core/views.py:2056 in historique_stock
```

Reproduit avec les 4 rôles (ADMIN, GESTIONNAIRE, COMPTABLE, SUPERADMIN). La vue est complète et fonctionnelle (filtres, pagination, `select_related`) — il ne manque que le gabarit. Le lien est probablement présent dans la navigation, donc un utilisateur qui clique dessus tombe sur une page d'erreur Django.

### 3.2 `/parametres/` → 500 pour le super-admin

`core/views.py:2263` passe `'devises': atelier.DEVISES` au contexte. Quand l'utilisateur n'a pas d'atelier (cas du super-admin, ou d'un compte dont le profil est incomplet), `get_user_atelier()` renvoie `None` → `AttributeError: 'NoneType' object has no attribute 'DEVISES'`.

```
AttributeError: 'NoneType' object has no attribute 'DEVISES'
  @ core/views.py:2263 in parametres_view
```

C'est un cas général : **aucune vue du module `core` ne vérifie que `atelier` est non nul** après `get_user_atelier()`. Partout ailleurs cela produit un 404 silencieux (`get_object_or_404(Client, pk=…, atelier=None)` ne matche rien) — acceptable mais trompeur pour l'utilisateur ; ici cela produit un crash.

---

## 4. Configuration : trois fuites à corriger avant toute mise en ligne

### 4.1 Identifiants de base de données en clair dans le dépôt

```python
# tailleur_gestion/settings.py:69
DATABASES = {'default': {
    'NAME': 'tailleur_db', 'USER': 'postgres',
    'PASSWORD': 'MAIGA@123',        # ← commité sur un dépôt public
    'HOST': 'localhost', 'PORT': '5432',
}}
```

Le dépôt est public : ce mot de passe est donc exposé. **À faire immédiatement**, dans cet ordre :

1. Changer le mot de passe `postgres` sur toutes les machines où il a été utilisé.
2. Vérifier qu'aucune instance en ligne n'utilise ces identifiants.
3. Passer par `.env` + `python-decouple` ou `os.environ`, et retirer la valeur du fichier.

> Note : purger l'historique git (`git filter-repo`) ne dispense pas de l'étape 1 — le secret est déjà sorti.

### 4.2 Configuration de développement laissée telle quelle

```python
SECRET_KEY = 'django-insecure-s@i68aj-pfg@e3pj6p(#2o65age(brg@f8-h_%ub(eb90n84o6'
DEBUG = True
ALLOWED_HOSTS = []
```

Conséquences en production : `DEBUG = True` affiche la **page d'erreur Django complète** (source des vues, variables locales, `settings`) au premier incident — c'est une fuite d'information majeure. `ALLOWED_HOSTS = []` rejette toutes les requêtes dès que `DEBUG = False`. Le préfixe `django-insecure-` de la clé indique que Django lui-même la considère comme compromise.

Manquent aussi : `SECURE_SSL_REDIRECT`, `SESSION_COOKIE_SECURE`, `CSRF_COOKIE_SECURE`, `SECURE_HSTS_SECONDS`, `X_FRAME_OPTIONS` explicite.

### 4.3 Aucune dépendance déclarée

Il n'y a ni `requirements.txt`, ni `pyproject.toml`, ni `Pipfile`, ni lock. Pour lancer le projet j'ai dû deviner : `django`, `pillow` (champs `ImageField`), `xhtml2pdf` (importé dans 6 vues PDF), `psycopg2-binary` (moteur PostgreSQL).

Le détail qui compte : **`xhtml2pdf` est importé à l'intérieur des fonctions**, donc l'erreur n'apparaît qu'au moment où l'utilisateur clique sur « Télécharger le PDF » — pas au démarrage. Six routes sont concernées :

| Route | Vue |
|---|---|
| `/mensurations/<pk>/pdf/` | `mensuration_pdf` (views.py:824) |
| `/commandes/<pk>/recu/pdf/` | `recu_paiement_pdf` |
| `/commandes/<pk>/recu-caisse/pdf/` | `recu_caisse_pdf` (views.py:2122) |
| `/commandes/<pk>/facture/pdf/` | `facture_commande_pdf` |
| `/commandes/<pk>/fiche-atelier/` | `fiche_atelier_pdf` (views.py:1687) |
| `/lignes/<pk>/fiche/` | `fiche_ligne_pdf` (views.py:1726) |

Sans `requirements.txt`, toute réinstallation ou tout déploiement reproduira ce bug.

---

## 5. Architecture : les incohérences structurelles

### 5.1 Deux modèles de « tenant » qui s'ignorent

C'est le problème de conception le plus important.

| `core` | `saas_admin` |
|---|---|
| `Atelier` (nom, slug, adresse, devise, seuil stock) | `Boutique` (nom_boutique, slug, email, téléphone) |
| `PlanAbonnement` (prix_mensuel, max_commandes_mois, max_utilisateurs) | `FormuleAbonnement` (prix, duree_mois, fonctionnalités incluses/exclues) |
| `Abonnement` → `Atelier` (statut, date_debut, date_fin) | `Boutique.date_expiration_abonnement`, `Facture` → `Boutique` |

Aucune clé étrangère ne relie `Boutique` à `Atelier`. Le super-admin pilote des `Boutique` ; l'application métier tourne sur des `Atelier`. Concrètement :

- **Suspendre une boutique dans le back-office ne bloque rien** dans l'application — les deux tables sont indépendantes.
- Les quotas de `PlanAbonnement` (`max_commandes_mois`, `max_utilisateurs`) ne sont **jamais vérifiés** : aucune occurrence dans `core/views.py`.
- Le décorateur `subscription_active_required` cherche `atelier.is_subscription_active`, attribut qui **n'existe sur aucun modèle**.

Il faut choisir un seul tenant. Recommandation : garder `Atelier` (c'est lui qui porte toutes les données métier), transformer `Boutique` en vue ou en extension 1-1 d'`Atelier`, et supprimer `PlanAbonnement` au profit de `FormuleAbonnement` qui est le plus complet des deux.

### 5.2 `TenantMiddleware` : un filtrage automatique annoncé, jamais implémenté

`core/middleware.py` documente : *« Utilisé par le TenantManager dans models.py pour filtrer l'ORM. »*

**Il n'y a aucun `TenantManager`, ni aucun `objects = …` personnalisé dans `core/models.py`.** Le middleware alimente donc un `threading.local()` que personne ne lit. Deux conséquences :

1. C'est du code mort (~50 lignes) qui donne un faux sentiment de sécurité — on pourrait croire que l'isolation entre ateliers est automatique alors qu'elle repose entièrement sur le filtrage manuel dans chaque vue.
2. `threading.local()` est **incorrect en ASGI** (`asgi.py` est présent) : plusieurs requêtes peuvent partager un thread. Si ce filtrage automatique était un jour branché, il y aurait un risque réel de fuite de données entre ateliers.

**Point positif à signaler** : le filtrage manuel, lui, est fait sérieusement. On trouve 191 occurrences de `atelier=atelier` dans `core/views.py`, systématiquement via `get_object_or_404(…, atelier=atelier)`. L'isolation tient — à condition qu'aucune vue ne l'oublie, ce qui n'est garanti par aucun test.

### 5.3 `boutique_context` renvoie toujours `None`

```python
# core/context_processors.py
profil = request.user.profile              # ← la relation s'appelle 'profil'
boutique = profil.boutique if profil else None   # ← le champ s'appelle 'atelier'
```

`Profil` est déclaré avec `related_name='profil'` et un champ `atelier`. Les deux attributs utilisés ici n'existent donc pas, l'`except Exception` avale l'erreur, et **`profil` et `boutique` valent toujours `None` dans tous les templates**. Les 3 occurrences de `.boutique` côté templates sont silencieusement vides.

### 5.4 107 lignes de décorateurs morts — et cassés

`core/decorators.py` définit `boutique_user_required`, `role_requis`, `subscription_active_required`. **Aucun n'est importé ni utilisé nulle part dans le projet** (vérifié par grep sur l'ensemble des `.py`).

S'ils étaient branchés tels quels, ils provoqueraient des erreurs 500 :

```python
return redirect('login')              # NoReverseMatch — la route s'appelle 'core:connexion'
return redirect('mon_profil')         # NoReverseMatch — c'est 'core:mon_profil'
return redirect('abonnement_expire')  # NoReverseMatch — c'est 'core:abonnement_expire'
```

J'ai vérifié par `reverse()` : ces trois noms **n'existent pas**. Par ailleurs `role_requis` et `boutique_user_required` cherchent `request.user.profilutilisateur` ou `.profile` — **0 occurrence** de ces noms dans le projet, la relation s'appelle `.profil`. Ces décorateurs ne reconnaîtraient donc jamais personne.

Enfin, `superadmin_required` est défini **deux fois** : dans `saas_admin/decorators.py` (version complète, gère `profil.role == 'SUPERADMIN'`) et dans `saas_admin/views.py:15` (version réduite à `is_superuser`). C'est la version réduite, locale au fichier, qui est utilisée — `saas_admin/decorators.py` est entièrement mort.

### 5.5 Routes dupliquées dans `core/urls.py`

Django prend la **première** correspondance : les doublons en fin de fichier sont inaccessibles.

| Route dupliquée | Lignes |
|---|---|
| `stock/historique/` | déclarée 2× |
| `stock/ajuster/` | déclarée 2× |
| `employes/<int:pk>/` (`detail_employe`) | déclarée 2× |

S'y ajoutent des incohérences de nommage : la section « 10. ÉQUIPE / UTILISATEURS » de `core/urls.py` définit `ajouter_utilisateur` / `modifier_utilisateur` / `supprimer_utilisateur`, **exactement les mêmes noms** que dans `saas_admin/urls.py`. Les deux sont dans des namespaces distincts donc cela fonctionne, mais c'est une source d'erreur permanente.

### 5.6 Templates : références cassées et fichiers orphelins

**12 références `{% url %}` qui ne résolvent pas**, dont :

| Fichier | Référence | Statut |
|---|---|---|
| `core/supprimer_client.html:19` | `'detail_client'` | **Template actif** → lien cassé visible |
| `core/landing.html:174` | `'core:landing_page'` | La vue n'existe pas |
| `core/landing.html:188` | `'core:inscription'` | La route s'appelle `core:inscription_saas` |
| `core/ajouter_mensuration.html:12` | `'recherche_clients'` | Aucune vue correspondante |
| `core/ajouter_mensuration.html:136` | `'ajouter_commande'` | La route s'appelle `creer_commande` |

Les autres sont dans des templates eux-mêmes orphelins, donc sans impact immédiat.

**6 templates jamais rendus par aucune vue et jamais inclus** : `core/landing.html`, `core/inscription.html`, `core/clients.html`, `core/ajouter_mensuration.html`, `core/supprimer_depense.html`, `core/supprimer_mensuration.html`.

À noter : `core/urls.py` fait `path('', RedirectView.as_view(pattern_name='core:connexion'))` — **la racine du site redirige vers la page de connexion**. La landing page publique et la page d'inscription sont donc inaccessibles en navigation directe, ce qui est contradictoire avec un produit SaaS qui doit acquérir des clients.

---

## 6. Dettes secondaires

**Zéro test.** `core/tests.py` contient 3 lignes (`from django.test import TestCase` + un commentaire). Aucun test sur le multi-tenant, alors que c'est précisément le risque principal du produit : une seule vue qui oublie `atelier=atelier` et un atelier lit les clients d'un autre.

**Zéro documentation.** Pas de README. Un nouveau développeur doit deviner les dépendances, la base de données, et la commande de lancement.

**Pas de CI.** Aucun workflow GitHub Actions.

**Dépendance au CDN.** `base.html` charge Bootstrap 5.3 et Bootstrap Icons depuis `cdn.jsdelivr.net`, et la ligne `{% load static %}` est commentée. Hors-ligne (ou si le CDN tombe), toute l'interface perd sa mise en forme. Le dossier `static/` référencé par `STATICFILES_DIRS` **n'existe pas** (d'où l'avertissement `staticfiles.W004` au `manage.py check`).

**Fichiers à supprimer du dépôt.** `data.json` (14 octets, UTF-16, contient `[]`), `data_utf8.json` (7 octets, `[]`), `data_final.json` (30 enregistrements, uniquement `auth.permission` et `contenttypes.contenttype` — aucune donnée client, donc pas de problème RGPD). `export_data.py` référence `DJANGO_SETTINGS_MODULE = 'projet_tailleur.settings'` alors que le module s'appelle `tailleur_gestion` : **le script est inutilisable en l'état**.

**Doublons de fonctions.** `_est_admin` est défini deux fois dans `core/views.py` (lignes 63 et 3100), à l'identique — la seconde définition écrase la première sans conséquence, mais c'est le signe d'un fichier de 3 113 lignes qui a grossi par ajouts successifs.

**Helpers d'autorisation écrits puis abandonnés.** `_peut_comptabilite` (ligne 3105) et `_peut_production` (ligne 3111) sont définis tout à la fin du fichier et **jamais appelés**. Ils correspondent exactement aux règles décrites dans `Profil.DESCRIPTIONS_ROLES`. Tout indique que le contrôle par rôle a été démarré puis interrompu.

**`core/views.py` fait 3 113 lignes** pour ~60 vues. À découper par domaine (`views/clients.py`, `views/commandes.py`, `views/stock.py`, `views/pdf.py`…).

---

## 6bis. Découvertes supplémentaires (2ᵉ passe)

Ces points sont apparus en construisant le harnais de test ; ils n'étaient pas dans la première passe.

### Le journal de stock est contourné par la saisie directe

`MouvementStock` est conçu pour tracer chaque entrée/sortie et « justifier un écart d'inventaire ». Or :

- **`ajuster_stock` est inatteignable** : la route `/stock/ajuster/` existe, la vue est complète et correcte (`_appliquer_stock` écrit bien dans le journal), mais **aucun template n'y fait référence** — vérifié par grep sur les 44 fichiers HTML. Depuis l'interface, on ne peut donc ni réapprovisionner proprement, ni corriger un inventaire.
- **Le catalogue permet de modifier le stock directement** : `modeles.html` contient des champs `stock_pret_a_porter` (lignes 544 et 616) et `stock_disponible` (ligne 712), soumis via `modifier_modele` / `modifier_accessoire`. Ces vues écrivent la nouvelle valeur en base **sans créer de `MouvementStock`**.

Conséquence : un utilisateur qui ajuste un stock depuis le catalogue produit un écart d'inventaire invisible — exactement ce que le journal est censé empêcher. `/stock/historique/` ne reflète alors que les ventes directes.

Deux options : (a) rendre ces champs en lecture seule dans le catalogue et faire passer toute modification par `ajuster_stock`, ou (b) créer un mouvement d'inventaire automatique dans `modifier_modele` / `modifier_accessoire` quand la valeur change. L'option (a) est plus saine.

### `historique_stock` n'était lié nulle part

Au-delà du template manquant, **aucun lien de navigation ne pointait vers `/stock/historique/`**. La fonctionnalité était doublement inaccessible : elle plantait, et personne ne pouvait l'atteindre en cliquant. Le template créé contient un bouton de retour vers le catalogue ; reste à ajouter l'entrée de navigation.

### Une référence `{% url %}` sans vue correspondante

`core/ajouter_mensuration.html:12` appelle `'recherche_clients'`. Aucune route de ce nom n'existe, et aucune vue ne ressemble à une recherche de clients (`liste_clients` accepte déjà un paramètre `?q=`). Ce template étant par ailleurs orphelin (§5.6), la référence est sans impact immédiat — mais elle indique qu'une fonctionnalité de recherche a été prévue puis abandonnée. À trancher avec les 6 templates orphelins.

### Les 6 templates orphelins représentent des fonctionnalités entières

Il ne s'agit pas de fichiers résiduels anodins :

| Template | Ce qu'il contient |
|---|---|
| `core/landing.html` | Page d'accueil commerciale complète : navbar, sections « Fonctionnalités », « Tarifs », témoignages, CTA d'inscription |
| `core/inscription.html` | Formulaire d'inscription |
| `core/clients.html` | Une seconde vue de la liste clients |
| `core/ajouter_mensuration.html` | Formulaire de saisie des mesures |
| `core/supprimer_depense.html` | Confirmation de suppression (la vue `supprimer_depense` existe, ligne 2590, mais ne rend aucun template) |
| `core/supprimer_mensuration.html` | Confirmation de suppression |

Le point le plus marquant : `core/urls.py` fait `path('', RedirectView.as_view(pattern_name='core:connexion'))` — **la racine du site envoie directement sur la page de connexion**. Pour un SaaS qui doit acquérir des clients, la landing page existe, est terminée, et est inaccessible. Il suffit probablement de créer une vue `landing_page` qui rend `core/landing.html` et de l'affecter à la racine.

---

## 6ter. L'inscription SaaS était cassée depuis l'origine

Découvert en intégrant une nouvelle maquette de la page d'inscription : le bug était
**antérieur** et présent depuis le premier commit. Corrigé par `3eaacdd`.

### Le parcours d'acquisition ne fonctionnait pas

```
POST /inscription/  ->  200  (au lieu de 302)
                        aucun compte créé
                        aucun atelier créé
                        aucune erreur affichée
```

Cause : `InscriptionSaaSForm` déclare `first_name` et `last_name` comme **obligatoires**,
mais aucun template ne les affiche. La vérification mesurée sur le code d'origine :

```
champs présents dans le HTML : ['confirm_password', 'csrfmiddlewaretoken', 'devise',
                                'email', 'nom_atelier', 'password',
                                'telephone_atelier', 'username']
formulaire valide ? False
erreurs : {'first_name': ['Ce champ est obligatoire.'],
           'last_name':  ['Ce champ est obligatoire.']}
```

Les deux erreurs restaient invisibles : la vue ré-affiche le formulaire, et le template
ne rend ni ces champs ni `form.non_field_errors`. Un visiteur remplissait tout, cliquait sur
« Créer mon compte et mon atelier », et la page se rechargeait **sans aucun message**.

C'est le point le plus coûteux de l'audit en termes produit : pour un SaaS, la page
d'inscription est le haut de l'entonnoir. Elle était intégralement non fonctionnelle.

### L'essai gratuit n'était jamais accordé

`InscriptionSaaSForm.save()` ne créait l'abonnement que si un `PlanAbonnement` existait déjà :

```python
plan_starter = (PlanAbonnement.objects.filter(nom__icontains='Starter').first()
                or PlanAbonnement.objects.first())
if plan_starter:                       # ← faux sur une base neuve
    Abonnement.objects.create(...)
```

Sur une base neuve il n'y a aucun plan, donc l'atelier était créé **sans abonnement** —
alors que la page promet « 14 jours d'essai gratuit ». Combiné au §5.1 (deux systèmes
d'abonnement parallèles), un nouvel inscrit n'entrait dans aucun des deux.

### Les messages d'erreur n'étaient pas stylés

`MESSAGE_TAGS` n'était pas défini. Les templates écrivent `class="alert alert-{{ message.tags }}"`,
et Django produit par défaut le tag `error` — donc `alert-error`, **classe inexistante dans
Bootstrap**. Les **42 appels à `messages.error`** de `core/views.py` s'affichaient en texte
nu, sans fond rouge ni icône. Répartition mesurée :

| Appel | Occurrences | Classe produite avant | Après |
|---|---|---|---|
| `messages.error` | 42 | `alert-error` ❌ | `alert-danger` ✅ |
| `messages.success` | 39 | `alert-success` ✅ | inchangé |
| `messages.info` | 5 | `alert-info` ✅ | inchangé |
| `messages.warning` | 4 | `alert-warning` ✅ | inchangé |

### Les messages n'étaient pas affichés sur le tableau de bord

Ni `base.html` ni `accueil.html` (le template du dashboard) ne contenaient le moindre
`{% if messages %}`. Vérifié par `grep -c` : **0 occurrence** dans les deux fichiers.
Seize templates les affichent individuellement, mais pas ceux-là.

Conséquence directe : le `messages.success("Bienvenue chez … ! Votre espace est prêt.")`
envoyé par `inscription_saas` était **consommé puis perdu**. Le correctif a été placé dans
`accueil.html` et non dans `base.html` : ce dernier est hérité par les 16 templates qui
affichent déjà les messages, et un rendu global aurait doublé chaque bandeau.

### État après correctif

Vérifié sur base neuve, en HTTP réel (pas seulement via le client de test Django) :

```
POST /inscription/  ->  302 vers /dashboard/
  compte            : créé, mot de passe haché et vérifiable
  profil            : role=ADMIN, est_fondateur=True, actif=True, telephone renseigné
  atelier           : créé, slug généré, devise FCFA
  abonnement        : ACTIF, plan « Starter — essai gratuit », fin à J+14
  /dashboard/       : 200, « Bienvenue chez … » rendu en alert-success

Cas d'erreur (aucun ne crée de compte) :
  mots de passe différents   -> 200 + « Les mots de passe ne correspondent pas. »
  mot de passe trop court    -> 200 + « …au moins 6 caractères (actuellement 3). »
  identifiant déjà pris      -> 200 + « Ce nom d'utilisateur est déjà pris. »
```

Restent deux points non corrigés, volontairement :

- **`form.non_field_errors` n'est rendu par aucun template du projet** (0 occurrence).
  Aujourd'hui sans impact — `clean()` utilise `add_error()` sur des champs précis — mais
  toute future validation globale serait invisible.
- **Deux ateliers peuvent porter le même nom** : `Atelier.slug` est `unique` et se
  déduplique automatiquement (`chez-awa-couture`, `chez-awa-couture-1`), mais `nom` ne
  l'est pas. Mesure : deux ateliers « Chez Awa Couture » créés sans erreur. À trancher
  selon l'intention produit.

---



## 7. Le problème n°1 en détail : l'autorisation par rôle

`Profil.ROLES` définit trois rôles et `Profil.DESCRIPTIONS_ROLES` documente précisément qui peut faire quoi :

| Rôle | Ce qui est écrit dans le code |
|---|---|
| `ADMIN` | « Accès complet : paramètres, utilisateurs, employés, catalogue, commandes et comptabilité. » |
| `GESTIONNAIRE` | « Clients, mensurations, commandes, ventes directes et suivi des livraisons. **Pas d'accès à la comptabilité ni aux paramètres.** » |
| `COMPTABLE` | « Dépenses, paiements, factures, reçus et rapports financiers. **Consultation seule des commandes.** » |

**Réalité mesurée.** J'ai créé un atelier avec un compte de chaque rôle, puis visité toutes les routes :

| Page | ADMIN | GESTIONNAIRE | COMPTABLE |
|---|---|---|---|
| `/depenses/` (comptabilité) | 200 | **200** ❌ | 200 |
| `/employes/` + plan de charge | 200 | **200** ❌ | **200** ❌ |
| `/parametres/` | 200 | **200** ❌ | **200** ❌ |
| `/commandes/` | 200 | 200 | **200** ❌ (devrait être lecture seule) |

Puis j'ai testé les écritures :

| Action | Rôle testé | Résultat |
|---|---|---|
| `POST /depenses/ajouter/` | GESTIONNAIRE | ✅ **Créée** — 1 → 2 dépenses en base |
| `POST /clients/<pk>/supprimer/` | COMPTABLE | ✅ **Client supprimé définitivement** |
| `POST /modeles/<pk>/supprimer/` | GESTIONNAIRE | ✅ **Modèle supprimé** |
| `POST /employes/<pk>/supprimer/` | COMPTABLE | ✅ **Employé supprimé** |
| `POST /parametres/` (modifier l'atelier) | COMPTABLE | ⛔ Bloqué — garde `_est_admin` présente |
| `POST /utilisateurs/ajouter/` avec `role=ADMIN` | GESTIONNAIRE | ⛔ Bloqué — garde `_est_admin` présente |

**Ce qui est protégé** : les 4 vues qui contiennent un `if not _est_admin(request.user)` explicite (lignes 2272, 2312, 2355 + `parametres_view`). Soit la modification des paramètres et la gestion des comptes.

**Ce qui ne l'est pas** : tout le reste. Seule la vérification d'appartenance à l'atelier (`atelier=atelier`) est appliquée — elle empêche de toucher aux données d'un *autre* atelier, mais pas de toucher à *toutes* les données de son propre atelier quel que soit son rôle.

**Impact concret** : un comptable peut effacer le fichier clients ; un gestionnaire peut créer de fausses dépenses et supprimer le catalogue. Dans une PME où ces comptes sont partagés ou peu surveillés, c'est un risque réel de perte de données.

### Résultat du harnais `dev/escalade.py` (état actuel du code)

```
=== ÉCRITURES CROISÉES ENTRE RÔLES ===
Règles de référence : Profil.DESCRIPTIONS_ROLES

❌ POST /depenses/ajouter/                GESTIONNAIRE  attendu=bloque  obtenu=AUTORISÉ
❌ POST /clients/<pk>/supprimer/          COMPTABLE     attendu=bloque  obtenu=AUTORISÉ
❌ POST /employes/<pk>/supprimer/         COMPTABLE     attendu=bloque  obtenu=AUTORISÉ
❌ POST /modeles/<pk>/supprimer/          GESTIONNAIRE  attendu=bloque  obtenu=AUTORISÉ
❌ POST /accessoires/<pk>/supprimer/      GESTIONNAIRE  attendu=bloque  obtenu=AUTORISÉ
✅ POST /employes/ajouter/                COMPTABLE     attendu=bloque  obtenu=bloqué
✅ POST /utilisateurs/ajouter/ (role=ADMIN) GESTIONNAIRE attendu=bloque  obtenu=bloqué
✅ POST /parametres/ (update_atelier)     COMPTABLE     attendu=bloque  obtenu=bloqué

3/8 contrôles conformes.
⚠️  5 action(s) réellement exécutée(s) par un rôle qui ne le devrait pas.
```

Ce script est **réexécutable en l'état** : c'est lui qui validera le correctif.
Quand les 8 lignes passeront à ✅, l'autorisation par rôle sera branchée.

> Les trois ✅ proviennent des gardes `_est_admin` déjà présentes dans les vues
> `parametres_view`, `ajouter_utilisateur` et `ajouter_employe`. Le reste du code
> n'a aucune garde de rôle.

**Bonne nouvelle** : le correctif est court. Les helpers existent déjà (`_est_admin`, `_peut_comptabilite`, `_peut_production`), la table de rôles est propre, et les décorateurs sont écrits. Il « suffit » de les réparer et de les appliquer aux ~60 vues.

---

## 8. Ce qui est bien fait

Pour être équitable — plusieurs choses sont solides :

- **Le filtrage multi-tenant manuel est systématique** : 191 occurrences de `atelier=atelier`, toujours via `get_object_or_404`. Aucune fuite inter-ateliers détectée pendant les tests.
- **Les requêtes sont optimisées** : `select_related` et `prefetch_related` sont utilisés correctement sur les listes lourdes (`liste_commandes` précharge `client`, `employe_attribue`, `lignes__modele`, `lignes__employe`, `lignes__accessoires_ligne`, `paiements`). Ce n'est pas le cas dans la plupart des projets de cette taille.
- **Les migrations sont propres et à jour** : `makemigrations --check` ne détecte rien, les 12 migrations `core` + 2 `saas_admin` s'appliquent sans erreur, y compris sur SQLite.
- **Le code est lisible** : noms en français cohérents, docstrings sur les modèles, helpers factorisés (`_to_decimal`, `_verifier_stock`, `_appliquer_stock`), sections numérotées.
- **La modélisation métier est réfléchie** : `Mensuration.donnees` en `JSONField` pour des mesures variables selon le vêtement, le concept de bénéficiaire (mesurer un enfant sur la fiche du parent), la distinction couture sur mesure / prêt-à-porter, la paie à la pièce avec commission.
- **Les montants sont en `Decimal`**, jamais en `float`.
- **64 routes redirigent correctement les anonymes** (302 vers la connexion) — `@login_required` est bien appliqué partout.
- **Le super-admin est bien isolé** du back-office SaaS (`/saas-admin/*` renvoie 302 pour les trois rôles métier).

---

## 9. Plan d'action proposé

### Étape 1 — Sécuriser (½ journée, à faire avant tout le reste)

1. **Changer le mot de passe PostgreSQL exposé** sur toutes les machines concernées.
2. Créer `.env` + installer `python-decouple`, externaliser `SECRET_KEY`, `DEBUG`, `ALLOWED_HOSTS`, et les 5 variables de base de données.
3. Ajouter les en-têtes de sécurité (`SECURE_SSL_REDIRECT`, cookies `Secure`, HSTS).
4. Écrire `requirements.txt` avec versions figées — inclure `xhtml2pdf`.

### Étape 2 — Débloquer les 500 (1 heure)

5. Créer `core/templates/core/historique_stock.html`.
6. Garder `parametres_view` (et idéalement toutes les vues `core`) contre `atelier is None` — rediriger le super-admin vers `/saas-admin/dashboard/`.

### Étape 3 — Brancher l'autorisation (1 à 2 jours)

7. Corriger `core/decorators.py` : remplacer `profilutilisateur`/`profile` par `profil`, et les trois `redirect()` par leurs noms namespacés (`core:connexion`, `core:mon_profil`, `core:abonnement_expire`).
8. Supprimer le `superadmin_required` dupliqué dans `saas_admin/views.py` et importer celui de `saas_admin/decorators.py`.
9. Appliquer `@role_requis(…)` aux ~60 vues selon `Profil.DESCRIPTIONS_ROLES`.
10. **Écrire les tests RBAC en même temps** — une matrice rôle × route qui échoue si une permission dérive. C'est le seul moyen de garantir que ça ne casse pas à nouveau.

### Étape 4 — Clarifier l'architecture (1 jour)

11. Fusionner `Boutique` dans `Atelier` (ou relier les deux en 1-1), supprimer `PlanAbonnement` au profit de `FormuleAbonnement`.
12. Supprimer `TenantMiddleware` + `threading.local()` **ou** implémenter réellement le `TenantManager` — mais dans ce cas utiliser `contextvars`, pas `threading.local()`, à cause de `asgi.py`.
13. Corriger `context_processors.boutique_context` (`request.user.profil`, `profil.atelier`).
14. Dédoublonner `core/urls.py`, supprimer les 6 templates orphelins et les 12 références `{% url %}` cassées, corriger les noms de routes en double avec `saas_admin`.

### Étape 5 — Rendre le projet transmissible (½ journée)

15. `README.md` : prérequis, installation, `.env.example`, lancement, comptes de démonstration.
16. Télécharger Bootstrap en local dans `static/` (et créer ce dossier) pour ne plus dépendre du CDN.
17. Supprimer `data.json`, `data_utf8.json`, `data_final.json`, et corriger ou supprimer `export_data.py`.
18. GitHub Actions : `manage.py check` + `manage.py test` + `makemigrations --check` à chaque push.
19. Découper `core/views.py` (3 113 lignes) en modules par domaine.

---

## Annexe — environnement de reproduction

L'audit a été mené dans une sandbox isolée, sur SQLite, sans jamais toucher à votre base PostgreSQL :

```bash
git clone https://github.com/artisanweb4-blip/Projet_tailleur.git
cd Projet_tailleur
pip install -r requirements.txt

export PYTHONPATH=$PWD:/chemin/vers/dev
export DJANGO_SETTINGS_MODULE=dev_settings     # SQLite + DEBUG_PROPAGATE_EXCEPTIONS

python manage.py migrate                        # 12 migrations core + 2 saas_admin : OK
python manage.py check                          # avant correctifs : staticfiles.W004
                                                # après correctifs  : no issues
python manage.py makemigrations --check --dry-run   # No changes detected

python /chemin/vers/dev/seed.py                 # jeu de données de démo
python /chemin/vers/dev/rbac.py                 # matrice page × rôle
python /chemin/vers/dev/escalade.py             # écritures croisées entre rôles
python /chemin/vers/dev/audit_templates.py      # {% url %} cassés + templates orphelins
```

Les cinq scripts sont décrits au §0 et dans le README, section « Développement ».

"""
Django settings for tailleur_gestion project.

Les valeurs sensibles (clé secrète, base de données, DEBUG, hôtes autorisés)
sont lues depuis l'environnement, avec un fichier `.env` optionnel à la racine
du projet pour le développement. Voir `.env.example` et le README.
"""

import os
from pathlib import Path

from django.contrib import messages
from django.core.exceptions import ImproperlyConfigured

# Build paths inside the project like this: BASE_DIR / 'subdir'.
BASE_DIR = Path(__file__).resolve().parent.parent


# ==========================================
# CHARGEMENT DU FICHIER .env (sans dépendance externe)
# Les variables déjà présentes dans l'environnement ont toujours priorité,
# ce qui permet d'écraser .env en production (Docker, systemd, PaaS…).
# ==========================================
def _charger_env(chemin):
    """Charge un fichier .env minimaliste (KEY=VALUE) dans os.environ.

    Gère les commentaires (#), les lignes vides, et les valeurs entre
    guillemets simples ou doubles. Ne dépend d'aucune librairie tierce.
    """
    try:
        with open(chemin, encoding='utf-8') as f:
            lignes = f.readlines()
    except FileNotFoundError:
        return

    for ligne in lignes:
        ligne = ligne.strip()
        if not ligne or ligne.startswith('#') or '=' not in ligne:
            continue
        cle, _, valeur = ligne.partition('=')
        cle = cle.strip()
        valeur = valeur.strip()
        if len(valeur) >= 2 and valeur[0] == valeur[-1] and valeur[0] in ('"', "'"):
            valeur = valeur[1:-1]
        os.environ.setdefault(cle, valeur)


_charger_env(BASE_DIR / '.env')


def _env_bool(nom, defaut=False):
    """Interprète une variable d'environnement comme un booléen."""
    return os.environ.get(nom, str(defaut)).strip().lower() in ('1', 'true', 'yes', 'oui', 'on')


def _env_liste(nom, defaut=''):
    """Interprète une variable d'environnement comme une liste séparée par des virgules."""
    brut = os.environ.get(nom, defaut)
    return [v.strip() for v in brut.split(',') if v.strip()]


# SECURITY WARNING: keep the secret key used in production secret!
# `or` plutôt que la valeur par défaut de .get() : une variable présente mais
# vide (cas fréquent dans un .env fraîchement copié) doit aussi déclencher le
# repli, puis l'erreur de configuration en production.
SECRET_KEY = os.environ.get('DJANGO_SECRET_KEY') or (
    # Clé de repli uniquement pour le développement local.
    'django-insecure-s@i68aj-pfg@e3pj6p(#2o65age(brg@f8-h_%ub(eb90n84o6'
)

# SECURITY WARNING: don't run with debug turned on in production!
DEBUG = _env_bool('DJANGO_DEBUG', True)

# En production (DEBUG=False), ALLOWED_HOSTS doit être renseigné explicitement.
ALLOWED_HOSTS = _env_liste('DJANGO_ALLOWED_HOSTS', 'localhost,127.0.0.1')



# Application definition

INSTALLED_APPS = [
    'django.contrib.admin',
    'django.contrib.auth',
    'django.contrib.contenttypes',
    'django.contrib.sessions',
    'django.contrib.messages',
    'django.contrib.staticfiles',
    
    # Vos applications
    'core',
    'saas_admin.apps.SaasAdminConfig', 
]

MIDDLEWARE = [
    'django.middleware.security.SecurityMiddleware',
    'django.contrib.sessions.middleware.SessionMiddleware',
    'django.middleware.common.CommonMiddleware',
    'django.middleware.csrf.CsrfViewMiddleware',
    'django.contrib.auth.middleware.AuthenticationMiddleware',
    'django.contrib.messages.middleware.MessageMiddleware',
    'django.middleware.clickjacking.XFrameOptionsMiddleware',
    'core.middleware.TenantMiddleware',
]

ROOT_URLCONF = 'tailleur_gestion.urls'

TEMPLATES = [
    {
        'BACKEND': 'django.template.backends.django.DjangoTemplates',
        'DIRS': [BASE_DIR / 'templates'],
        'APP_DIRS': True,
        'OPTIONS': {
            'context_processors': [
                'django.template.context_processors.debug',
                'django.template.context_processors.request',
                'django.contrib.auth.context_processors.auth',
                'django.contrib.messages.context_processors.messages',
                
                # Context processor personnalisé
                'core.context_processors.boutique_context',
            ],
        },
    },
]

WSGI_APPLICATION = 'tailleur_gestion.wsgi.application'


# Database
# PostgreSQL par défaut ; basculer sur SQLite en local avec DB_ENGINE=sqlite3
# (utile pour les tests et pour démarrer sans serveur PostgreSQL).
_DB_ENGINE = os.environ.get('DB_ENGINE', 'postgresql').strip().lower()

if _DB_ENGINE in ('sqlite3', 'sqlite'):
    DATABASES = {
        'default': {
            'ENGINE': 'django.db.backends.sqlite3',
            'NAME': BASE_DIR / os.environ.get('DB_NAME', 'db.sqlite3'),
        }
    }
else:
    DATABASES = {
        'default': {
            'ENGINE': 'django.db.backends.postgresql',
            'NAME': os.environ.get('DB_NAME', 'tailleur_db'),
            'USER': os.environ.get('DB_USER', 'postgres'),
            'PASSWORD': os.environ.get('DB_PASSWORD', ''),
            'HOST': os.environ.get('DB_HOST', 'localhost'),
            'PORT': os.environ.get('DB_PORT', '5432'),
            # Nécessaire avec PgBouncer en mode « transaction pooling ».
            'DISABLE_SERVER_SIDE_CURSORS': True,
            'OPTIONS': {},
        }
    }


# Password validation
AUTH_PASSWORD_VALIDATORS = [
    {'NAME': 'core.validators.MotDePasseFortValidator'},
    {'NAME': 'django.contrib.auth.password_validation.UserAttributeSimilarityValidator'},
    {'NAME': 'django.contrib.auth.password_validation.MinimumLengthValidator'},
    {'NAME': 'django.contrib.auth.password_validation.CommonPasswordValidator'},
    {'NAME': 'django.contrib.auth.password_validation.NumericPasswordValidator'},
]


# Internationalization (Passé en français)
LANGUAGE_CODE = 'fr-fr'
TIME_ZONE = 'UTC'
USE_I18N = True
USE_TZ = True


# Static files (CSS, JavaScript, Images)
STATIC_URL = 'static/'
STATICFILES_DIRS = [BASE_DIR / 'static']
STATIC_ROOT = BASE_DIR / 'staticfiles'

# Media files (Téléversement d'images pour les commandes / modèles)
MEDIA_URL = '/media/'
MEDIA_ROOT = BASE_DIR / 'media'

# Default primary key field type
DEFAULT_AUTO_FIELD = 'django.db.models.BigAutoField'


# --- REDIRECTIONS AUTHENTIFICATION ---
LOGIN_URL = 'core:connexion'
LOGIN_REDIRECT_URL = 'core:dashboard'
LOGOUT_REDIRECT_URL = 'core:connexion'


# --- MESSAGES FLASH ---
# Les templates écrivent `class="alert alert-{{ message.tags }}"`. Sans cette
# correspondance, `messages.error` produit `alert-error`, qui n'existe pas dans
# Bootstrap : le bandeau s'affiche sans aucun style. 42 appels à messages.error
# étaient concernés dans l'application.
MESSAGE_TAGS = {
    messages.DEBUG: 'secondary',
    messages.INFO: 'info',
    messages.SUCCESS: 'success',
    messages.WARNING: 'warning',
    messages.ERROR: 'danger',
}


# ==========================================
# SÉCURITÉ HTTP
# Actifs uniquement hors DEBUG : en développement, la redirection HTTPS
# permanente et le HSTS rendraient le serveur local inutilisable.
# ==========================================
if not DEBUG:
    # Toute requête HTTP est redirigée vers HTTPS.
    SECURE_SSL_REDIRECT = _env_bool('SECURE_SSL_REDIRECT', True)
    SESSION_COOKIE_SECURE = True
    CSRF_COOKIE_SECURE = True
    CSRF_COOKIE_SAMESITE = 'Lax'
    SESSION_COOKIE_SAMESITE = 'Lax'
    SESSION_COOKIE_HTTPONLY = True

    # HSTS : 1 an, sous-domaines inclus. Augmenter après validation en prod.
    SECURE_HSTS_SECONDS = int(os.environ.get('SECURE_HSTS_SECONDS', 3600))
    SECURE_HSTS_INCLUDE_SUBDOMAINS = True
    SECURE_HSTS_PRELOAD = _env_bool('SECURE_HSTS_PRELOAD', False)

    SECURE_CONTENT_TYPE_NOSNIFF = True
    SECURE_REFERRER_POLICY = 'same-origin'
    X_FRAME_OPTIONS = 'DENY'

    # Derrière un reverse proxy TLS (nginx, Caddy, Traefik…), décommenter :
    # SECURE_PROXY_SSL_HEADER = ('HTTP_X_FORWARDED_PROTO', 'https')
    # USE_X_FORWARDED_HOST = True

# En production, refuser de démarrer sans clé secrète explicite.
if not DEBUG and SECRET_KEY.startswith('django-insecure-'):
    raise ImproperlyConfigured(
        "DJANGO_SECRET_KEY doit être défini dans l'environnement (ou .env) "
        "lorsque DEBUG=False. Générez-en une avec : "
        "python -c \"from django.core.management.utils import "
        "get_random_secret_key as k; print(k())\""
    )
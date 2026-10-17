"""
Client API SasPay (v1) — paiements Mobile Money / carte bancaire.

Documentation : https://docs.saspay.me  (base : https://api.saspay.me/api/v1)

Flux d'abonnement câblé dans core/views.py ::
    1. L'atelier clique « Payer … » sur son offre d'abonnement ;
    2. on crée une SasPayTransaction locale (PENDING) avec notre
       `external_reference` unique (ABO-… / ABOINIT-…) ;
    3. POST /checkout-sessions/ → on redirige vers `checkout_url`
       (page hébergée SasPay : Mobile Money du pays, carte bancaire…) ;
    4. le client revient sur /saspay/retour/ -> statut lu en direct sur
       GET /checkout-sessions/{id}/status/  (transaction_status = SUCCESS) ;
    5. en parallèle, SasPay notifie /saspay/webhook/ (signé HMAC-SHA256,
       événement `transaction.success`) — filet de sécurité côté serveur.

Points clés de l'API SasPay (vérifiés sur la doc) :
    - authentification :  Authorization: Bearer sk_test_… / sk_live_…
    - la référence marchande se propage via `metadata` de la session et
      `external_reference` de la transaction ;
    - le webhook est créé depuis le DASHBOARD SasPay (pas par API) ; son
      secret de signature (`signing_secret`) se copie une seule fois ;
    - signature : HMAC-SHA256(signing_secret, f"{timestamp}.{corps brut}"),
      rejet si timestamp écarté de plus de 5 minutes (anti-rejeu).

Configuration (dans cet ordre de priorité) :
    - base : ligne ConfigurationSaspay (paramétrable depuis le back-office
      superadmin → Paramètres) ;
    - secours : variables d'environnement SASPAY_SECRET_KEY /
      SASPAY_WEBHOOK_SECRET (utile pour les tests).

⚠️ La clé secrète ne quitte JAMAIS le serveur (pas de JS client).
"""
import hashlib
import hmac
import json
import os
import time
import urllib.error
import urllib.request

BASE = 'https://api.saspay.me/api/v1'
TIMEOUT = 25
# User-Agent déclaré : certains WAF jettent l'agent urllib par défaut.
USER_AGENT = 'TailleurPro/1.0 (+https://saspay.me)'
# Tolérance anti-rejeu des webhooks (doc SasPay : 5 minutes).
TOLERANCE_WEBHOOK = 300


class SasPayError(Exception):
    """Erreur côté SasPay ou réseau (message affichable à l'utilisateur)."""


# ------------------------------------------------------------------
# Configuration
# ------------------------------------------------------------------
def get_config():
    """Renvoie la ConfigurationSaspay active ou None si non configurée."""
    from .models import ConfigurationSaspay
    cfg = ConfigurationSaspay.objects.filter(actif=True).first()
    if cfg is not None:
        return cfg
    # Secours : variables d'environnement (tests / dev local).
    sk = os.environ.get('SASPAY_SECRET_KEY', '').strip()
    wh = os.environ.get('SASPAY_WEBHOOK_SECRET', '').strip()
    if sk:
        class _Cfg:  # simple adaptateur
            cle_secrete, secret_webhook, actif = sk, wh, True
        return _Cfg()
    return None


def est_actif():
    return get_config() is not None


# ------------------------------------------------------------------
# Appel HTTP (regroupé ici pour être facile à mocker dans les tests)
# ------------------------------------------------------------------
def appel_api(chemin, methode='GET', payload=None, idempotency_key=None):
    """Invoque l'API. Exceptions → SasPayError. Renvoie le JSON décodé."""
    cfg = get_config()
    if cfg is None:
        raise SasPayError("SasPay n'est pas configuré (clé secrète absente).")
    url = f"{BASE}{chemin}"
    donnees = None if payload is None else json.dumps(payload).encode('utf-8')
    req = urllib.request.Request(url, data=donnees, method=methode)
    req.add_header('Authorization', f'Bearer {cfg.cle_secrete}')
    req.add_header('Accept', 'application/json')
    req.add_header('User-Agent', USER_AGENT)
    if donnees is not None:
        req.add_header('Content-Type', 'application/json')
    if idempotency_key:
        # Recommandé par la doc pour toute route qui déplace de l'argent :
        # un retry réseau ne recrée PAS un second paiement.
        req.add_header('Idempotency-Key', idempotency_key)
    try:
        with urllib.request.urlopen(req, timeout=TIMEOUT) as reponse:
            corps = reponse.read().decode('utf-8', errors='replace')
    except urllib.error.HTTPError as e:
        try:
            detail = json.loads(e.read().decode('utf-8', errors='replace'))
            msg = detail.get('message') or detail.get('error') or str(e)
        except Exception:
            msg = str(e)
        raise SasPayError(f"SasPay a refusé la demande ({e.code}) : {msg}")
    except (urllib.error.URLError, TimeoutError) as e:
        raise SasPayError(f"Impossible de joindre SasPay : {e}")
    try:
        retour = json.loads(corps)
    except ValueError:
        raise SasPayError("Réponse SasPay illisible.")
    # Toutes les réponses de l'API portent leur contenu utile dans `data`.
    if retour.get('success') is False:
        raise SasPayError(retour.get('message', 'SasPay a refusé la demande.'))
    return retour


# ------------------------------------------------------------------
# Paiements (checkout hébergé)
# ------------------------------------------------------------------
def creer_checkout(amount, currency, description, external_reference,
                   return_url, customer_email='', customer_name=''):
    """Crée une session de checkout hébergé. Renvoie le champ `data`
    (id de session + checkout_url)."""
    payload = {
        'amount': f"{int(amount)}.00",
        'currency': currency,
        'description': description,
        'customer_email': customer_email or '',
        'customer_name': customer_name or 'Client',
        # Notre référence unique propage jusqu'à la transaction finale.
        'metadata': {'external_reference': external_reference},
    }
    # La return_url est une redirection côté NAVIGATEUR du client : en dev
    # local, localhost fonctionne (le pare-feu de SasPay ne la rappelle pas).
    if return_url:
        payload['return_url'] = return_url
    rep = appel_api('/checkout-sessions/', methode='POST', payload=payload,
                    idempotency_key=external_reference)
    return rep.get('data', rep)


def statut_session(id_session):
    """GET /checkout-sessions/{id}/status/ → status / transaction_status."""
    from urllib.parse import quote
    return appel_api(f"/checkout-sessions/{quote(str(id_session))}/status/")
    # Renvoie ex. : {status: "PAID", transaction_status: "SUCCESS",
    #                transaction_id: "…", transaction_reference: "…"}


def verifier_paiement(id_paiement):
    """GET /payments/{id}/verify/ → transaction complète (statut réel)."""
    from urllib.parse import quote
    return appel_api(f"/payments/{quote(str(id_paiement))}/verify/")


# ------------------------------------------------------------------
# Webhook (signature HMAC-SHA256 sur « timestamp.corps »)
# ------------------------------------------------------------------
def signature_valide(corps_brut, signature_header, timestamp_header):
    """Vérifie les en-têtes X-Webhook-Signature / X-Webhook-Timestamp.

    Deux contrôles (doc SasPay) :
      1. l'horodatage ne doit pas s'écarter de plus de 5 minutes ;
      2. HMAC-SHA256(f"{timestamp}.{corps brut}") == signature reçue.
    """
    cfg = get_config()
    if cfg is None:
        return False
    secret = (getattr(cfg, 'secret_webhook', '') or '').strip()
    if not secret:
        # Sans secret configuré, impossible de vérifier : on refuse —
        # la validation réelle repose toujours sur la re-vérification API.
        return False
    try:
        ts = int(timestamp_header or 0)
    except (TypeError, ValueError):
        return False
    if abs(int(time.time()) - ts) > TOLERANCE_WEBHOOK:
        return False
    body = corps_brut.decode('utf-8', errors='replace') \
        if isinstance(corps_brut, bytes) else str(corps_brut)
    attendue = hmac.new(
        secret.encode('utf-8'),
        f"{timestamp_header}.{body}".encode('utf-8'),
        hashlib.sha256,
    ).hexdigest()
    return hmac.compare_digest(attendue, signature_header or '')


# ------------------------------------------------------------------
# Utilitaires métier
# ------------------------------------------------------------------
_HOTES_LOCAUX = {'localhost', '127.0.0.1', '::1', '0.0.0.0'}


def url_publique(url):
    """True si `url` est joignable publiquement (webhook depuis Internet),
    False en dev local (localhost, 127.0.0.1, IP privées…).

    En SasPay le webhook se configure au dashboard : cette fonction sert
    uniquement à INFORMER si l'URL affichée dans les paramètres a un sens.
    """
    from urllib.parse import urlparse
    import re
    hote = (urlparse(url or '').hostname or '').lower()
    if (not hote or '.' not in hote or hote in _HOTES_LOCAUX
            or hote.endswith(('.local', '.test', '.invalid'))):
        return False
    if hote.startswith(('10.', '192.168.', '169.254.')):
        return False
    m = re.match(r'^172\.(\d+)\.', hote)
    if m and 16 <= int(m.group(1)) <= 31:
        return False
    return True


DEVISES_API = {'XOF', 'XAF', 'EUR', 'USD'}


def devise_pour_api(devise_atelier):
    """La devise de l'atelier → devise admise par l'API (XOF par défaut)."""
    d = (devise_atelier or '').upper()
    if d == 'FCFA':
        return 'XOF'
    return d if d in DEVISES_API else 'XOF'


def mode_journal_pour_methode(methode):
    """Code réseau SasPay (ex. orange_ml, moov_bf, wave_ci, card…)
    → code du journal manuel des paiements."""
    m = (methode or '').lower()
    if 'orange' in m:
        return 'ORANGE_MONEY'
    if 'wave' in m:
        return 'WAVE'
    if m == 'card' or 'carte' in m or 'visa' in m or 'master' in m:
        return 'CARTE'
    if 'virement' in m or 'transfert' in m:
        return 'VIREMENT'
    if m:  # mobile money autre (Moov, MTN, Airtel, M-Pesa…)
        return 'MOBILE_MONEY'
    return 'AUTRE'

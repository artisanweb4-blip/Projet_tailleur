"""
Client API LomoPay (v1) — paiements Mobile Money / carte bancaire.

Résumé du flux d'abonnement câblé dans core/views.py ::
    1. L'atelier clique « Payer … » sur son offre d'abonnement ;
    2. on crée une LomoPayTransaction locale (PENDING) ;
    3. POST /api/v1/payments.php → on redirige vers checkout_url ;
    4. LomoPay notifie notre /lomopay/webhook/ (signé HMAC-SHA256) ;
    5. la transaction passe COMPLETED → abonnement prolongé + encaissement
       journalisé (PaiementAbonnement, mode LOMOPAY).

Configuration (dans cet ordre de priorité) :
    - base : ligne ConfigurationLomopay (paramétrable depuis le back-office
      superadmin → Paramètres) ;
    - secours : variables d'environnement LOMOPAY_PUBLIC_KEY /
      LOMOPAY_SECRET_KEY (utile pour les tests).

⚠️ La clé secrète ne quitte JAMAIS le serveur (pas de JS client).
"""
import hashlib
import hmac
import json
import os
import urllib.error
import urllib.request

BASE = 'https://lomopay.net/api/v1'
TIMEOUT = 25
# User-Agent déclaré : sans lui, le pare-feu (Cloudflare err. 1010) rejette
# l'agent urllib par défaut de Python — mesuré en test live 2026-09-29.
USER_AGENT = 'TailleurGestionSaaS/1.0 (+https://lomopay.net)'


class LomoPayError(Exception):
    """Erreur côté LomoPay ou réseau (message affichable à l'utilisateur)."""


# ------------------------------------------------------------------
# Configuration
# ------------------------------------------------------------------
def get_config():
    """Renvoie la ConfigurationLomopay active ou None si non configurée."""
    from .models import ConfigurationLomopay
    cfg = ConfigurationLomopay.objects.filter(actif=True).first()
    if cfg is not None:
        return cfg
    # Secours : variables d'environnement. La clé publique est facultative :
    # l'API accepte X-Secret-Key seule (mesuré en test live 2026-09-29).
    pk = os.environ.get('LOMOPAY_PUBLIC_KEY', '').strip()
    sk = os.environ.get('LOMOPAY_SECRET_KEY', '').strip()
    if sk:
        class _Cfg:  # simple adaptateur
            cle_publique, cle_secrete, actif = pk, sk, True
        return _Cfg()
    return None


def est_actif():
    return get_config() is not None


# ------------------------------------------------------------------
# Appel HTTP (regroupé ici pour être facile à mocker dans les tests)
# ------------------------------------------------------------------
def appel_api(chemin, methode='GET', payload=None):
    """Invoque l'API. Exceptions → LomoPayError. Renvoie le JSON décodé."""
    cfg = get_config()
    if cfg is None:
        raise LomoPayError("LomoPay n'est pas configuré (clés absentes).")
    url = f"{BASE}{chemin}"
    donnees = None if payload is None else json.dumps(payload).encode('utf-8')
    req = urllib.request.Request(url, data=donnees, method=methode)
    req.add_header('X-Public-Key', cfg.cle_publique)
    req.add_header('X-Secret-Key', cfg.cle_secrete)
    req.add_header('Accept', 'application/json')
    # Sans User-Agent explicite, le pare-feu de lomopay.net (Cloudflare,
    # erreur 1010) bloque l'agent urllib par défaut de Python. Mesuré en
    # test live 2026-09-29 : 403 sans UA, 200 avec UA identifié.
    req.add_header('User-Agent', USER_AGENT)
    if donnees is not None:
        req.add_header('Content-Type', 'application/json')
    try:
        with urllib.request.urlopen(req, timeout=TIMEOUT) as reponse:
            corps = reponse.read().decode('utf-8', errors='replace')
    except urllib.error.HTTPError as e:
        try:
            detail = json.loads(e.read().decode('utf-8', errors='replace'))
            msg = detail.get('message') or detail.get('error') or str(e)
        except Exception:
            msg = str(e)
        raise LomoPayError(f"LomoPay a refusé la demande ({e.code}) : {msg}")
    except (urllib.error.URLError, TimeoutError) as e:
        raise LomoPayError(f"Impossible de joindre LomoPay : {e}")
    try:
        return json.loads(corps)
    except ValueError:
        raise LomoPayError("Réponse LomoPay illisible.")


# ------------------------------------------------------------------
# Paiements
# ------------------------------------------------------------------
def creer_paiement(amount, currency, description, external_reference,
                   return_url, webhook_url, customer_email='', customer_name=''):
    """Initie un paiement et renvoie le champ `data` (avec checkout_url)."""
    rep = appel_api('/payments.php', methode='POST', payload={
        'amount': amount,
        'currency': currency,
        'description': description,
        'external_reference': external_reference,
        'return_url': return_url,
        'webhook_url': webhook_url,
        'customer_email': customer_email,
        'customer_name': customer_name,
    })
    if not rep.get('success'):
        raise LomoPayError(rep.get('message', 'Échec de création du paiement.'))
    return rep['data']


def infos_paiement(id_lomopay_ou_ref):
    """Re-synchronise le statut d'un paiement (par id lpx_… ou notre ref)."""
    from urllib.parse import quote
    return appel_api(f"/payments.php?id={quote(str(id_lomopay_ou_ref))}")


def methodes_disponibles():
    """GET /methods.php — utilisé par le bouton « Tester la connexion »."""
    return appel_api('/methods.php')


# ------------------------------------------------------------------
# Webhook (signature)
# ------------------------------------------------------------------
def signature_valide(corps_brut, signature_header):
    """Vérifie l'en-tête X-LomoPay-Signature (HMAC-SHA256 du corps)."""
    cfg = get_config()
    if cfg is None:
        return False
    attendue = ('sha256=' + hmac.new(
        cfg.cle_secrete.encode('utf-8'), corps_brut, hashlib.sha256
    ).hexdigest())
    return hmac.compare_digest(attendue, signature_header or '')


# ------------------------------------------------------------------
# Utilitaires métier
# ------------------------------------------------------------------
DEVISES_API = {'XOF', 'XAF', 'EUR', 'USD'}


def devise_pour_api(devise_atelier):
    """La devise de l'atelier → devise admise par l'API (XOF par défaut)."""
    d = (devise_atelier or '').upper()
    if d == 'FCFA':
        return 'XOF'
    return d if d in DEVISES_API else 'XOF'


def mode_journal_pour_methode(methode):
    """Méthode LomoPay (ex. sebpay, carte…) → code du journal manuel."""
    m = (methode or '').lower()
    if 'orange' in m:
        return 'ORANGE_MONEY'
    if 'wave' in m:
        return 'WAVE'
    if 'carte' in m or 'card' in m or 'visa' in m or 'master' in m:
        return 'CARTE'
    if 'virement' in m or 'transfert' in m:
        return 'VIREMENT'
    return 'AUTRE'

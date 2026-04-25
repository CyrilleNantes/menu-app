"""
google_auth.py — Flux OAuth 2.0 Google (Calendar + Tasks)

Utilise httpx conformément à la stack imposée.
Les tokens sont stockés dans le modèle TokenOAuth.
"""

import logging
import os
from datetime import timedelta
from urllib.parse import urlencode

import httpx
from django.utils import timezone

logger = logging.getLogger("menu")

GOOGLE_AUTH_URL  = "https://accounts.google.com/o/oauth2/v2/auth"
GOOGLE_TOKEN_URL = "https://oauth2.googleapis.com/token"

GOOGLE_SCOPES = [
    "openid",
    "email",
    "profile",
    "https://www.googleapis.com/auth/calendar",
    "https://www.googleapis.com/auth/tasks",
]


# ─── Étape 1 : construction de l'URL d'autorisation ──────────────────────────

def google_build_auth_url(redirect_uri: str, state: str) -> str:
    """Retourne l'URL vers laquelle rediriger l'utilisateur pour l'autoriser."""
    params = {
        "client_id":     os.environ["GOOGLE_CLIENT_ID"],
        "redirect_uri":  redirect_uri,
        "response_type": "code",
        "scope":         " ".join(GOOGLE_SCOPES),
        "access_type":   "offline",   # pour obtenir un refresh_token
        "prompt":        "consent",   # force l'affichage du consentement (garantit refresh_token)
        "state":         state,
    }
    return f"{GOOGLE_AUTH_URL}?{urlencode(params)}"


# ─── Étape 2 : échange du code contre des tokens ─────────────────────────────

def google_exchange_code(code: str, redirect_uri: str) -> dict:
    """
    Échange le code d'autorisation contre access_token + refresh_token.
    Retourne le dict JSON brut de Google.
    Lève httpx.HTTPError en cas d'échec.
    """
    try:
        resp = httpx.post(
            GOOGLE_TOKEN_URL,
            data={
                "code":          code,
                "client_id":     os.environ["GOOGLE_CLIENT_ID"],
                "client_secret": os.environ["GOOGLE_CLIENT_SECRET"],
                "redirect_uri":  redirect_uri,
                "grant_type":    "authorization_code",
            },
            timeout=10,
        )
        resp.raise_for_status()
        return resp.json()
    except httpx.HTTPError as exc:
        logger.error("google_exchange_code : erreur HTTP %s", exc)
        raise


# ─── Rafraîchissement d'un access_token expiré ───────────────────────────────

def google_refresh_access_token(refresh_token: str) -> dict:
    """
    Rafraîchit un access_token via le refresh_token.
    Retourne le dict JSON brut de Google.
    Lève httpx.HTTPError en cas d'échec.
    """
    try:
        resp = httpx.post(
            GOOGLE_TOKEN_URL,
            data={
                "client_id":     os.environ["GOOGLE_CLIENT_ID"],
                "client_secret": os.environ["GOOGLE_CLIENT_SECRET"],
                "refresh_token": refresh_token,
                "grant_type":    "refresh_token",
            },
            timeout=10,
        )
        resp.raise_for_status()
        return resp.json()
    except httpx.HTTPError as exc:
        logger.error("google_refresh_access_token : erreur HTTP %s", exc)
        raise


# ─── Point d'entrée principal : obtenir un token valide ──────────────────────

def google_get_valid_token(user) -> str:
    """
    Retourne un access_token Google valide pour l'utilisateur.

    - Rafraîchit automatiquement si le token expire dans moins de 60 secondes.
    - Lève TokenOAuth.DoesNotExist si l'utilisateur n'a pas connecté Google.
    - Lève httpx.HTTPError si le rafraîchissement échoue.
    """
    from menu.models import TokenOAuth  # import local pour éviter la circularité

    token = TokenOAuth.objects.get(user=user, service="google")

    # Rafraîchir si expiré (avec marge de 60s)
    if token.expires_at and timezone.now() >= token.expires_at - timedelta(seconds=60):
        logger.debug("google_get_valid_token : rafraîchissement pour user %s", user.id)
        data = google_refresh_access_token(token.refresh_token)

        token.access_token = data["access_token"]
        if "expires_in" in data:
            token.expires_at = timezone.now() + timedelta(seconds=int(data["expires_in"]))
        # Google peut renvoyer un nouveau refresh_token (rare mais possible)
        if "refresh_token" in data:
            token.refresh_token = data["refresh_token"]

        token.save(update_fields=["access_token", "expires_at", "refresh_token", "updated_at"])
        logger.info("google_get_valid_token : token rafraîchi pour user %s", user.id)

    return token.access_token

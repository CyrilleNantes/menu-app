"""
google_calendar.py — Export du planning vers Google Calendar

Utilise httpx conformément à la stack imposée.
Chaque repas planifié (avec recette) devient un événement dans le calendrier Google
de l'utilisateur connecté.
"""

import logging
from datetime import datetime

import httpx

logger = logging.getLogger("menu")

CALENDAR_BASE = "https://www.googleapis.com/calendar/v3"


# ─── Construction du corps d'un événement ────────────────────────────────────

def _event_body(meal, profile) -> dict:
    """
    Construit le dict JSON d'un événement Google Calendar pour un repas.
    Utilise les créneaux horaires configurés sur le profil.
    """
    recipe_title = meal.recipe.title if meal.recipe else "Repas"

    if meal.meal_time == "lunch":
        start_t = profile.lunch_start    # datetime.time
        end_t   = profile.lunch_end
        emoji   = "🍽️"
    else:
        start_t = profile.dinner_start
        end_t   = profile.dinner_end
        emoji   = "🌙"

    tz = "Europe/Paris"
    # Format ISO 8601 sans timezone offset (Google accepte le timeZone séparé)
    start_iso = datetime.combine(meal.date, start_t).strftime("%Y-%m-%dT%H:%M:%S")
    end_iso   = datetime.combine(meal.date, end_t).strftime("%Y-%m-%dT%H:%M:%S")

    # Description enrichie
    lines = [f"Recette : {recipe_title}"]
    if meal.servings_count:
        lines.append(f"Nombre de personnes : {meal.servings_count}")
    if meal.is_leftovers:
        lines.append("(Restes du repas précédent)")

    return {
        "summary":     f"{emoji} {recipe_title}",
        "description": "\n".join(lines),
        "start": {"dateTime": start_iso, "timeZone": tz},
        "end":   {"dateTime": end_iso,   "timeZone": tz},
    }


# ─── Export principal ─────────────────────────────────────────────────────────

def google_calendar_export_planning(user, plan) -> dict:
    """
    Exporte tous les repas du planning vers Google Calendar.

    - Crée un événement pour chaque repas ayant une recette.
    - Met à jour l'événement existant si `meal.google_event_id` est défini.
    - Recrée si l'événement a été supprimé côté Google (404).
    - Stocke l'ID de l'événement dans `Meal.google_event_id`.

    Retourne : {"created": N, "updated": N, "skipped": N}
    Lève     : httpx.HTTPError en cas d'échec réseau
               TokenOAuth.DoesNotExist si pas connecté Google
    """
    from menu.integrations.google_auth import google_get_valid_token  # import local

    access_token = google_get_valid_token(user)
    headers = {
        "Authorization": f"Bearer {access_token}",
        "Content-Type":  "application/json",
    }

    try:
        profile = user.profile
    except Exception as exc:
        raise ValueError("Profil utilisateur introuvable.") from exc

    calendar_id = profile.google_calendar_id or "primary"

    meals = plan.meals.select_related("recipe").filter(recipe__isnull=False)
    created = updated = skipped = 0

    for meal in meals:
        if not meal.recipe:
            skipped += 1
            continue

        body = _event_body(meal, profile)

        # ── Mise à jour d'un événement existant ───────────────────
        if meal.google_event_id:
            url = f"{CALENDAR_BASE}/calendars/{calendar_id}/events/{meal.google_event_id}"
            try:
                resp = httpx.patch(url, headers=headers, json=body, timeout=10)
                if resp.status_code == 404:
                    # Événement supprimé côté Google → on va le recréer ci-dessous
                    meal.google_event_id = ""
                elif resp.status_code == 410:
                    # Événement annulé (cancelled) → recréer
                    meal.google_event_id = ""
                else:
                    resp.raise_for_status()
                    updated += 1
                    continue
            except httpx.HTTPStatusError as exc:
                logger.warning(
                    "google_calendar_export : PATCH échoué (%s) pour meal %s — recréation",
                    exc.response.status_code, meal.id,
                )
                meal.google_event_id = ""

        # ── Création d'un nouvel événement ────────────────────────
        url = f"{CALENDAR_BASE}/calendars/{calendar_id}/events"
        try:
            resp = httpx.post(url, headers=headers, json=body, timeout=10)
            resp.raise_for_status()
        except httpx.HTTPError as exc:
            logger.error(
                "google_calendar_export : POST échoué pour meal %s : %s", meal.id, exc
            )
            raise

        event_id = resp.json().get("id", "")
        meal.google_event_id = event_id
        meal.save(update_fields=["google_event_id"])
        created += 1

    logger.info(
        "google_calendar_export_planning : %d créés, %d mis à jour, %d ignorés — user %s plan %s",
        created, updated, skipped, user.id, plan.id,
    )
    return {"created": created, "updated": updated, "skipped": skipped}

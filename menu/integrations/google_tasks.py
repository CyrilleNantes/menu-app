"""
google_tasks.py — Export de la liste de courses vers Google Tasks

Utilise httpx conformément à la stack imposée.
Chaque article non coché de la ShoppingList devient une tâche Google Tasks.
Format : "{quantité} {unité} {nom}" ou "{nom}" si pas de quantité.
"""

import logging

import httpx

logger = logging.getLogger("menu")

TASKS_BASE = "https://tasks.googleapis.com/tasks/v1"


# ─── Titre formaté d'une tâche ────────────────────────────────────────────────

def _task_title(item) -> str:
    """
    Construit le titre de la tâche selon le format : "{quantité} {unité} {nom}".
    Exemples :
      - "2 kg pommes de terre"
      - "3 œufs"
      - "sel"
    """
    parts = []
    if item.quantity is not None:
        # Affiche sans décimale si entier (ex: 2 au lieu de 2.0)
        qty_str = (
            str(int(item.quantity))
            if item.quantity == int(item.quantity)
            else f"{item.quantity:g}"
        )
        parts.append(qty_str)
    if item.unit:
        parts.append(item.unit)
    parts.append(item.name)
    return " ".join(parts)


# ─── Export principal ─────────────────────────────────────────────────────────

def google_tasks_export_courses(user, shopping_list) -> dict:
    """
    Exporte les articles non cochés de la liste de courses vers Google Tasks.

    - Cible : liste Google Tasks définie dans `UserProfile.google_tasklist_id`
      (ou "@default" si non défini).
    - Crée une tâche par article non coché avec note "Menu Familial".
    - Ne met pas à jour les tâches existantes (export one-shot).

    Retourne : {"created": N, "skipped": N}
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

    tasklist_id = profile.google_tasklist_id or "@default"

    # Note commune à toutes les tâches
    plan = shopping_list.week_plan
    note = (
        f"Menu Familial — Semaine {plan.period_start.isocalendar()[1]} "
        f"({plan.period_start.strftime('%d/%m')} – {plan.period_end.strftime('%d/%m/%Y')})"
    )

    items = shopping_list.items.filter(checked=False).order_by("category", "name")

    created = skipped = 0
    url = f"{TASKS_BASE}/lists/{tasklist_id}/tasks"

    for item in items:
        title = _task_title(item)
        body = {
            "title": title,
            "notes": note,
        }
        try:
            resp = httpx.post(url, headers=headers, json=body, timeout=10)
            resp.raise_for_status()
            created += 1
        except httpx.HTTPError as exc:
            logger.error(
                "google_tasks_export : POST échoué pour item '%s' : %s", title, exc
            )
            skipped += 1
            # On continue les autres articles même si un échoue
            continue

    logger.info(
        "google_tasks_export_courses : %d créées, %d ignorées — user %s liste %s",
        created, skipped, user.id, shopping_list.id,
    )
    return {"created": created, "skipped": skipped}

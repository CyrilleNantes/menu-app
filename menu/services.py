import io
import json
import logging
import zipfile as zf_lib

from django.contrib.auth.models import User as DjangoUser
from django.db import connection, transaction

from .models import Ingredient, IngredientGroup, Recipe, RecipeSection, RecipeStep

logger = logging.getLogger("menu")


def calculer_macros_recette(recipe: Recipe) -> None:
    """Recalcule et sauvegarde les macros par portion à partir des ingrédients."""
    ingredients = list(recipe.ingredients.all())
    if not ingredients:
        recipe.calories_per_serving = None
        recipe.proteins_per_serving = None
        recipe.carbs_per_serving = None
        recipe.fats_per_serving = None
        recipe.save(update_fields=["calories_per_serving", "proteins_per_serving", "carbs_per_serving", "fats_per_serving"])
        return

    total_cal = sum(i.calories or 0 for i in ingredients)
    total_prot = sum(i.proteins or 0 for i in ingredients)
    total_carbs = sum(i.carbs or 0 for i in ingredients)
    total_fats = sum(i.fats or 0 for i in ingredients)

    n = max(recipe.base_servings or 1, 1)
    recipe.calories_per_serving = round(total_cal / n, 1) if total_cal else None
    recipe.proteins_per_serving = round(total_prot / n, 1) if total_prot else None
    recipe.carbs_per_serving = round(total_carbs / n, 1) if total_carbs else None
    recipe.fats_per_serving = round(total_fats / n, 1) if total_fats else None
    recipe.save(update_fields=["calories_per_serving", "proteins_per_serving", "carbs_per_serving", "fats_per_serving"])


def _parse_float(val: str):
    try:
        return float(val) if val and val.strip() else None
    except (ValueError, TypeError):
        return None


def _parse_int(val: str):
    try:
        return int(val) if val and val.strip() else None
    except (ValueError, TypeError):
        return None


@transaction.atomic
def sauvegarder_recette_depuis_post(recipe: Recipe, post_data: dict) -> None:
    """
    Parse les données POST du formulaire recette et sauvegarde groupes, ingrédients,
    étapes et sections. Supprime les anciens objets et recrée tout.
    Appelé après la sauvegarde du modèle Recipe lui-même.
    """
    # ── Ingrédients ──────────────────────────────────────────────────────────
    recipe.ingredient_groups.all().delete()  # cascade sur Ingredient

    group_count = _parse_int(post_data.get("group_count", "0")) or 0
    for g in range(group_count):
        group_name = post_data.get(f"group_name_{g}", "").strip()
        if not group_name:
            continue
        group = IngredientGroup.objects.create(recipe=recipe, name=group_name, order=g)

        ing_count = _parse_int(post_data.get(f"group_ing_count_{g}", "0")) or 0
        for i in range(ing_count):
            name = post_data.get(f"ing_name_{g}_{i}", "").strip()
            if not name:
                continue
            Ingredient.objects.create(
                recipe=recipe,
                group=group,
                name=name,
                quantity=_parse_float(post_data.get(f"ing_qty_{g}_{i}")),
                quantity_note=post_data.get(f"ing_qty_note_{g}_{i}", "").strip() or None,
                unit=post_data.get(f"ing_unit_{g}_{i}", "").strip() or None,
                is_optional=post_data.get(f"ing_optional_{g}_{i}") == "on",
                category=post_data.get(f"ing_category_{g}_{i}", "").strip() or None,
                calories=_parse_float(post_data.get(f"ing_calories_{g}_{i}")),
                proteins=_parse_float(post_data.get(f"ing_proteins_{g}_{i}")),
                carbs=_parse_float(post_data.get(f"ing_carbs_{g}_{i}")),
                fats=_parse_float(post_data.get(f"ing_fats_{g}_{i}")),
                openfoodfacts_id=post_data.get(f"ing_off_id_{g}_{i}", "").strip() or None,
                order=i,
            )

    # ── Étapes ───────────────────────────────────────────────────────────────
    recipe.steps.all().delete()

    step_count = _parse_int(post_data.get("step_count", "0")) or 0
    for s in range(step_count):
        instruction = post_data.get(f"step_instruction_{s}", "").strip()
        if not instruction:
            continue
        RecipeStep.objects.create(
            recipe=recipe,
            order=s + 1,
            instruction=instruction,
            chef_note=post_data.get(f"step_chef_note_{s}", "").strip() or None,
            timer_seconds=_parse_int(post_data.get(f"step_timer_{s}")),
        )

    # ── Sections libres ───────────────────────────────────────────────────────
    recipe.sections.all().delete()

    section_count = _parse_int(post_data.get("section_count", "0")) or 0
    for s in range(section_count):
        content = post_data.get(f"section_content_{s}", "").strip()
        section_type = post_data.get(f"section_type_{s}", "").strip()
        if not content or not section_type:
            continue
        RecipeSection.objects.create(
            recipe=recipe,
            section_type=section_type,
            title=post_data.get(f"section_title_{s}", "").strip() or None,
            content=content,
            order=s,
        )

    calculer_macros_recette(recipe)
    logger.info(
        "Recette '%s' sauvegardée : %d groupes, %d ingrédients, %d étapes, %d sections.",
        recipe.title,
        recipe.ingredient_groups.count(),
        recipe.ingredients.count(),
        recipe.steps.count(),
        recipe.sections.count(),
    )


# ─── Backup / Restore ────────────────────────────────────────────────────────

# Ordre de restauration (parents avant enfants). Suppression = ordre inverse.
# Respecte les contraintes PROTECT : Family/Recipe/WeekPlan avant User.
_BACKUP_APP_MODELS = [
    "Family",
    "UserProfile",
    "TokenOAuth",
    "NotificationPreference",
    "Recipe",
    "IngredientGroup",
    "Ingredient",
    "RecipeStep",
    "RecipeSection",
    "Review",
    "WeekPlan",
    "Meal",
    "ShoppingList",
    "ShoppingItem",
    "MealProposal",
]


def _get_app_model(name):
    from . import models as m
    return getattr(m, name)


def exporter_backup() -> bytes:
    """
    Sérialise tous les objets de l'application (+ Users Django) en JSON
    compressé dans un fichier zip.
    """
    from django.core import serializers as djser

    data = {"__auth_user": json.loads(djser.serialize("json", DjangoUser.objects.all()))}
    for name in _BACKUP_APP_MODELS:
        data[name] = json.loads(djser.serialize("json", _get_app_model(name).objects.all()))

    buf = io.BytesIO()
    with zf_lib.ZipFile(buf, "w", zf_lib.ZIP_DEFLATED) as zf:
        zf.writestr("backup.json", json.dumps(data, indent=2, ensure_ascii=False))
    buf.seek(0)
    return buf.read()


def restaurer_backup(zip_bytes: bytes) -> dict:
    """
    Efface toutes les données et restaure depuis un zip de backup.
    Réinitialise les séquences PostgreSQL après restore.
    Retourne {'total': <nb objets restaurés>}.
    """
    from django.core import serializers as djser

    buf = io.BytesIO(zip_bytes)
    with zf_lib.ZipFile(buf, "r") as zf:
        data = json.loads(zf.read("backup.json").decode("utf-8"))

    with transaction.atomic():
        # Suppression dans l'ordre inverse (feuilles d'abord, respecte PROTECT)
        for name in reversed(_BACKUP_APP_MODELS):
            _get_app_model(name).objects.all().delete()
        DjangoUser.objects.all().delete()

        # Restauration dans l'ordre (parents d'abord)
        total = 0
        if "__auth_user" in data:
            for obj in djser.deserialize("json", json.dumps(data["__auth_user"])):
                obj.save()
                total += 1

        for name in _BACKUP_APP_MODELS:
            if name not in data:
                continue
            for obj in djser.deserialize("json", json.dumps(data[name])):
                try:
                    obj.save()
                    total += 1
                except Exception as exc:
                    logger.warning("Objet ignoré lors de la restauration (%s) : %s", name, exc)

    # Réinitialisation des séquences hors transaction (setval est non-transactionnel)
    _reset_postgres_sequences()
    logger.info("Backup restauré : %d objets.", total)
    return {"total": total}


def _reset_postgres_sequences():
    """Réinitialise les séquences auto-increment PostgreSQL après restauration."""
    tables = [DjangoUser._meta.db_table]
    for name in _BACKUP_APP_MODELS:
        tables.append(_get_app_model(name)._meta.db_table)

    with connection.cursor() as cursor:
        for table in tables:
            try:
                cursor.execute(
                    f"SELECT setval("
                    f"pg_get_serial_sequence('{table}', 'id'), "
                    f"coalesce(max(id), 1), max(id) IS NOT NULL"
                    f") FROM \"{table}\""
                )
            except Exception as exc:
                logger.warning("Sequence reset ignorée pour %s : %s", table, exc)


# ─── Import recettes depuis JSON ──────────────────────────────────────────────

@transaction.atomic
def importer_recette_depuis_json(data: dict, user) -> tuple:
    """
    Importe une recette depuis un dict (format {recipe: {...}} ou directement {...}).
    Idempotent : si une recette active avec le même titre existe, retourne (recipe, False).
    Retourne (recipe, True) si créée.
    """
    recipe_data = data.get("recipe", data)
    title = (recipe_data.get("title") or "").strip()
    if not title:
        raise ValueError("Titre de recette manquant")

    existing = Recipe.objects.filter(title=title, actif=True).first()
    if existing:
        return existing, False

    recipe = Recipe.objects.create(
        title=title,
        description=recipe_data.get("description") or None,
        base_servings=int(recipe_data.get("base_servings") or 4),
        prep_time=recipe_data.get("prep_time") or None,
        cook_time=recipe_data.get("cook_time") or None,
        category=recipe_data.get("category") or "plat",
        cuisine_type=recipe_data.get("cuisine_type") or None,
        seasons=recipe_data.get("seasons") or [],
        health_tags=recipe_data.get("health_tags") or [],
        complexity=recipe_data.get("complexity") or "intermediaire",
        calories_per_serving=recipe_data.get("calories_per_serving") or None,
        proteins_per_serving=recipe_data.get("proteins_per_serving") or None,
        carbs_per_serving=recipe_data.get("carbs_per_serving") or None,
        fats_per_serving=recipe_data.get("fats_per_serving") or None,
        created_by=user,
    )

    for g_idx, g_data in enumerate(recipe_data.get("ingredient_groups") or []):
        group = IngredientGroup.objects.create(
            recipe=recipe,
            name=g_data.get("name") or "Ingrédients",
            order=g_data.get("order", g_idx),
        )
        for i_idx, i_data in enumerate(g_data.get("ingredients") or []):
            name_ing = (i_data.get("name") or "").strip()
            if not name_ing:
                continue
            Ingredient.objects.create(
                recipe=recipe,
                group=group,
                name=name_ing,
                quantity=i_data.get("quantity") or None,
                quantity_note=i_data.get("quantity_note") or None,
                unit=i_data.get("unit") or None,
                is_optional=bool(i_data.get("is_optional", False)),
                category=i_data.get("category") or None,
                calories=i_data.get("calories") or None,
                proteins=i_data.get("proteins") or None,
                carbs=i_data.get("carbs") or None,
                fats=i_data.get("fats") or None,
                openfoodfacts_id=i_data.get("openfoodfacts_id") or None,
                order=i_data.get("order", i_idx),
            )

    for s_data in recipe_data.get("steps") or []:
        instruction = (s_data.get("instruction") or "").strip()
        if not instruction:
            continue
        RecipeStep.objects.create(
            recipe=recipe,
            order=s_data.get("order", 1),
            instruction=instruction,
            chef_note=s_data.get("chef_note") or None,
            timer_seconds=s_data.get("timer_seconds") or None,
        )

    for sec_data in recipe_data.get("sections") or []:
        content = (sec_data.get("content") or "").strip()
        if not content:
            continue
        RecipeSection.objects.create(
            recipe=recipe,
            section_type=sec_data.get("section_type") or "libre",
            title=sec_data.get("title") or None,
            content=content,
            order=sec_data.get("order", 0),
        )

    logger.info("Recette importée : '%s' (%d groupes, %d étapes).",
                recipe.title, recipe.ingredient_groups.count(), recipe.steps.count())
    return recipe, True

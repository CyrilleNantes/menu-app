import logging

from django.db import transaction

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

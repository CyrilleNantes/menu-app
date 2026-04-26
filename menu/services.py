import io
import json
import logging
import zipfile as zf_lib
from datetime import date as date_type

from django.contrib.auth.models import User as DjangoUser
from django.db import connection, transaction

from .models import (
    Ingredient, IngredientGroup, Meal, NutritionConfig, Recipe,
    RecipeSection, RecipeStep, Review, ShoppingItem, ShoppingList,
    UserProfile, WeekPlan,
)

logger = logging.getLogger("menu")


@transaction.atomic
def generer_liste_courses(plan: WeekPlan) -> ShoppingList:
    """
    Génère (ou recrée) la liste de courses d'un WeekPlan.

    Règles :
    - Seuls les repas avec recette et is_leftovers=False sont pris en compte.
    - Les quantités sont proratisées : quantité × (servings_count / base_servings).
    - Les ingrédients identiques (même nom, même unité, insensible à la casse) sont agrégés.
    - Les articles sont triés par catégorie puis par nom.
    """
    # Supprimer l'ancienne liste si elle existe
    ShoppingList.objects.filter(week_plan=plan).delete()

    meals = (
        Meal.objects
        .filter(week_plan=plan, is_leftovers=False, recipe__isnull=False)
        .select_related("recipe")
        .prefetch_related("recipe__ingredients")
    )

    # Clé d'agrégation : (nom_normalisé, unité_normalisée)
    aggregated: dict[tuple, dict] = {}

    for meal in meals:
        recipe = meal.recipe
        base = max(recipe.base_servings or 1, 1)
        ratio = (meal.servings_count or base) / base

        for ing in recipe.ingredients.all():
            norm_name = ing.name.strip()
            norm_unit = (ing.unit or "").strip()
            key = (norm_name.lower(), norm_unit.lower())

            if key not in aggregated:
                aggregated[key] = {
                    "name": norm_name,
                    "unit": norm_unit or None,
                    "category": ing.category or None,
                    "quantity": None,
                }

            entry = aggregated[key]
            if ing.quantity is not None:
                adj = ing.quantity * ratio
                entry["quantity"] = (entry["quantity"] or 0.0) + adj

    # Créer la nouvelle liste
    shopping_list = ShoppingList.objects.create(
        family=plan.family,
        week_plan=plan,
    )

    # Trier : catégorie (vide en dernier) puis nom
    sorted_items = sorted(
        aggregated.values(),
        key=lambda x: (x["category"] or "zzz", x["name"].lower()),
    )

    ShoppingItem.objects.bulk_create([
        ShoppingItem(
            shopping_list=shopping_list,
            name=item["name"],
            quantity=round(item["quantity"], 2) if item["quantity"] is not None else None,
            unit=item["unit"],
            category=item["category"],
            checked=False,
        )
        for item in sorted_items
    ])

    logger.info("Liste de courses générée : %d articles pour plan %s", len(sorted_items), plan.pk)
    return shopping_list


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


def calculer_alertes_planning(week_plan, family) -> list[dict]:
    """
    Analyse le WeekPlan et retourne les alertes d'équilibre nutritionnel (nudges).
    Jamais bloquantes — uniquement affichées au Cuisinier dans le planning.
    Retourne une liste de dicts {type, message, dismissable}.
    """
    config = NutritionConfig.get()

    meals = list(
        Meal.objects
        .filter(week_plan=week_plan, recipe__isnull=False, is_leftovers=False)
        .select_related("recipe")
    )

    protein_types = [m.recipe.protein_type for m in meals if m.recipe.protein_type]
    red_meat_count = protein_types.count("boeuf") + protein_types.count("porc")
    fish_count     = protein_types.count("poisson")
    veg_count      = sum(1 for pt in protein_types if pt in ("aucune", "legumineuses"))

    # Totaux nutritionnels (référence : 1 portion par repas)
    total_cal  = sum(m.recipe.calories_per_serving  or 0 for m in meals)
    total_prot = sum(m.recipe.proteins_per_serving or 0 for m in meals)

    cal_week_target  = config.calories_dinner_target  * 14
    prot_week_target = config.proteins_dinner_target  * 14

    alertes = []

    if fish_count == 0:
        alertes.append({
            "type": "poisson",
            "message": "🐟 Pensez à intégrer un repas poisson cette semaine",
            "dismissable": True,
        })

    if red_meat_count >= config.max_red_meat_per_week:
        alertes.append({
            "type": "viande_rouge",
            "message": f"🥩 Vous avez déjà {red_meat_count} repas de viande rouge cette semaine",
            "dismissable": True,
        })

    if veg_count == 0:
        alertes.append({
            "type": "vegetarien",
            "message": "🥦 Un repas végétarien serait bienvenu",
            "dismissable": True,
        })

    if cal_week_target > 0 and total_cal > cal_week_target * 1.3:
        alertes.append({
            "type": "calories_hautes",
            "message": "⚠️ La semaine semble chargée en calories",
            "dismissable": True,
        })

    if prot_week_target > 0 and total_prot > 0 and total_prot < prot_week_target * 0.6:
        alertes.append({
            "type": "proteines_basses",
            "message": "💪 Les protéines sont un peu faibles cette semaine",
            "dismissable": True,
        })

    logger.debug("calculer_alertes_planning : plan=%s → %d alerte(s)", week_plan.pk, len(alertes))
    return alertes


def _saison_courante() -> str:
    """Retourne la saison courante : printemps / ete / automne / hiver."""
    mois = date_type.today().month
    if mois in (3, 4, 5):  return "printemps"
    if mois in (6, 7, 8):  return "ete"
    if mois in (9, 10, 11): return "automne"
    return "hiver"


def suggerer_recettes(family, week_plan, target_date, meal_time: str) -> list[dict]:
    """
    Retourne les 5 meilleures recettes candidates pour un créneau (date + meal_time).

    Score composite 0.0–1.0 sur 5 dimensions pondérées :
      30% fraîcheur/rotation · 30% appréciation famille · 20% variété protéines
      10% saisonnalité · 10% équilibre nutritionnel semaine

    Chaque résultat : {'recipe': Recipe, 'score': float, 'reasons': dict}
    """
    config = NutritionConfig.get()
    saison = _saison_courante()

    # ── Candidats ─────────────────────────────────────────────────────────────
    all_recipes = list(Recipe.objects.filter(actif=True))
    if not all_recipes:
        return []

    # ── Membres de la famille ──────────────────────────────────────────────────
    family_user_ids = set(
        UserProfile.objects.filter(family=family).values_list("user_id", flat=True)
    )

    # ── Dernière utilisation de chaque recette pour cette famille ──────────────
    # Parcours trié par date → la dernière écriture pour chaque recipe_id gagne
    last_used: dict[int, date_type] = {}
    for m in (
        Meal.objects
        .filter(week_plan__family=family, recipe__isnull=False)
        .order_by("date")
        .values("recipe_id", "date")
    ):
        last_used[m["recipe_id"]] = m["date"]

    # ── Avis famille par recette ───────────────────────────────────────────────
    family_stars: dict[int, list[int]] = {}
    for r in Review.objects.filter(user_id__in=family_user_ids).values("recipe_id", "stars"):
        family_stars.setdefault(r["recipe_id"], []).append(r["stars"])

    def _family_avg(recipe_id: int):
        stars = family_stars.get(recipe_id, [])
        return sum(stars) / len(stars) if stars else None

    # ── Repas déjà planifiés dans ce WeekPlan ─────────────────────────────────
    week_meals = list(
        Meal.objects.filter(week_plan=week_plan, recipe__isnull=False)
        .select_related("recipe")
    )
    day_meals = [m for m in week_meals if m.date == target_date]

    day_protein_types   = [m.recipe.protein_type for m in day_meals  if m.recipe.protein_type]
    week_protein_types  = [m.recipe.protein_type for m in week_meals if m.recipe.protein_type]
    red_meat_count      = week_protein_types.count("boeuf") + week_protein_types.count("porc")

    # Calories/protéines déjà planifiées (référence : 1 portion par repas)
    week_calories = sum(m.recipe.calories_per_serving or 0 for m in week_meals)
    week_proteins = sum(m.recipe.proteins_per_serving or 0 for m in week_meals)

    # Cibles hebdomadaires (14 créneaux × cible dîner)
    cal_week_target  = config.calories_dinner_target * 14
    prot_week_target = config.proteins_dinner_target * 14

    # ── Scoring ───────────────────────────────────────────────────────────────
    results = []

    for recipe in all_recipes:
        avg_fam  = _family_avg(recipe.id)
        last     = last_used.get(recipe.id)

        # ── Dim 1 : Fraîcheur / rotation (30%) ────────────────────────────────
        if last is None:
            rotation_score = 1.0
        else:
            days_since = (target_date - last).days
            if avg_fam is not None and avg_fam < 2 and days_since < config.min_days_low_rated_repeat:
                rotation_score = 0.0
            elif days_since < config.min_days_before_repeat:
                rotation_score = 0.0
            else:
                span = max(config.min_days_low_rated_repeat - config.min_days_before_repeat, 1)
                rotation_score = min(1.0, 0.3 + 0.7 * (days_since - config.min_days_before_repeat) / span)

        # ── Dim 2 : Appréciation famille (30%) ────────────────────────────────
        famille_score = 0.5 if avg_fam is None else avg_fam / 5.0

        # ── Dim 3 : Variété protéines (20%) ───────────────────────────────────
        pt = recipe.protein_type
        if not pt:
            variete_score = 0.5  # neutre si non renseigné
        elif day_protein_types.count(pt) >= 2:
            variete_score = 0.0  # règle dure : 2× même protéine dans la journée
        elif pt in ("boeuf", "porc") and red_meat_count >= config.max_red_meat_per_week:
            variete_score = 0.0  # règle dure : quota viande rouge atteint
        else:
            variete_score = 0.5
            if pt not in week_protein_types:
                variete_score += 0.3   # bonus : absent de la semaine
            elif week_protein_types.count(pt) >= 2:
                variete_score -= 0.2   # malus : déjà 2× cette semaine
            variete_score = max(0.0, min(1.0, variete_score))

        # ── Dim 4 : Saisonnalité (10%) ────────────────────────────────────────
        seasons = recipe.seasons or []
        if not seasons:
            saison_score = 0.7
        elif saison in seasons:
            saison_score = 1.0
        else:
            saison_score = 0.2

        # ── Dim 5 : Équilibre nutritionnel semaine (10%) ──────────────────────
        equilibre_score = 0.5
        if cal_week_target > 0 and week_calories > cal_week_target * 1.1:
            if "leger" in (recipe.health_tags or []):
                equilibre_score += 0.2
        if prot_week_target > 0 and week_proteins < prot_week_target * 0.7:
            if "proteine" in (recipe.health_tags or []):
                equilibre_score += 0.2
        equilibre_score = min(1.0, equilibre_score)

        # ── Score final ────────────────────────────────────────────────────────
        score = (
            rotation_score  * 0.30 +
            famille_score   * 0.30 +
            variete_score   * 0.20 +
            saison_score    * 0.10 +
            equilibre_score * 0.10
        )

        results.append({
            "recipe": recipe,
            "score": round(score, 3),
            "reasons": {
                "rotation":  round(rotation_score,  2),
                "famille":   round(famille_score,   2),
                "variete":   round(variete_score,   2),
                "saison":    round(saison_score,    2),
                "equilibre": round(equilibre_score, 2),
            },
        })

    results.sort(key=lambda x: x["score"], reverse=True)
    logger.debug(
        "suggerer_recettes : famille=%s date=%s %s → %d candidats, top score=%.3f",
        family.pk, target_date, meal_time,
        len(results), results[0]["score"] if results else 0,
    )
    return results[:5]


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

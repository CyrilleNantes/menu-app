import io
import json
import logging
import math
import zipfile as zf_lib
from datetime import date as date_type

from django.contrib.auth.models import User as DjangoUser
from django.db import connection, transaction

from .models import (
    Ingredient, IngredientGroup, IngredientRef, KnownIngredient,
    Meal, MealProposal, NutritionConfig, NotificationPreference,
    Recipe, RecipeSection, RecipeStep, Review, ShoppingItem, ShoppingList,
    UserProfile, WeekPlan,
)

logger = logging.getLogger("menu")


@transaction.atomic
def generer_liste_courses(plan: WeekPlan) -> ShoppingList:
    """
    Génère (ou recrée) la liste de courses d'un WeekPlan.

    Règles :
    - Tous les repas avec recette (non absents) sont pris en compte.
    - Les quantités sont proratisées : quantité × (servings_count / base_servings).
    - Les ingrédients identiques (même nom, même unité, insensible à la casse) sont agrégés.
    - Les quantités sont arrondies au plafond (math.ceil) pour ne jamais manquer.
    - Les articles sont triés par catégorie puis par nom.
    """
    ShoppingList.objects.filter(week_plan=plan).delete()

    meals = (
        Meal.objects
        .filter(week_plan=plan, absent=False, recipe__isnull=False)
        .select_related("recipe")
        .prefetch_related("recipe__ingredients")
    )

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
                entry["quantity"] = (entry["quantity"] or 0.0) + ing.quantity * ratio

    shopping_list = ShoppingList.objects.create(family=plan.family, week_plan=plan)

    sorted_items = sorted(
        aggregated.values(),
        key=lambda x: (x["category"] or "zzz", x["name"].lower()),
    )

    ShoppingItem.objects.bulk_create([
        ShoppingItem(
            shopping_list=shopping_list,
            name=item["name"],
            quantity=math.ceil(item["quantity"]) if item["quantity"] is not None else None,
            unit=item["unit"],
            category=item["category"],
            checked=False,
        )
        for item in sorted_items
    ])

    logger.info("Liste de courses générée : %d articles pour plan %s", len(sorted_items), plan.pk)
    return shopping_list


# ─── Conversions Ciqual ────────────────────────────────────────────────────────

_UNIT_TO_GRAMS: dict[str | None, float | None] = {
    'g':          1.0,
    'kg':         1000.0,
    'ml':         1.0,
    'cl':         10.0,
    'L':          1000.0,
    'l':          1000.0,
    'c. à soupe': 15.0,
    'càs':        15.0,
    'cs':         15.0,
    'c. à café':  5.0,
    'càc':        5.0,
    'cc':         5.0,
}


def _quantity_to_grams(quantity: float | None, unit: str | None,
                       default_weight_g: float | None) -> float | None:
    """Convertit une quantité dans l'unité donnée en grammes."""
    if quantity is None:
        return None
    if unit in _UNIT_TO_GRAMS:
        return quantity * _UNIT_TO_GRAMS[unit]
    if unit is None and default_weight_g is not None:
        return quantity * default_weight_g
    return None


def compute_ingredient_macros_from_ciqual(ingr: Ingredient) -> dict | None:
    """
    Calcule les macros d'un ingrédient à partir de son ciqual_ref.
    Retourne None si le calcul est impossible (pas de ref ou qté non convertible).
    Un kcal_100g NULL (sel, eau…) est traité comme 0 — l'ingrédient est mappé.
    """
    ref = ingr.ciqual_ref
    if ref is None:
        return None
    qty_g = _quantity_to_grams(ingr.quantity, ingr.unit, ref.default_weight_g)
    if qty_g is None or qty_g <= 0:
        return None
    factor = qty_g / 100.0
    return {
        'calories': round((ref.kcal_100g or 0) * factor, 2),
        'proteins': round((ref.proteines_100g or 0) * factor, 2),
        'carbs':    round((ref.glucides_100g or 0) * factor, 2),
        'sugars':   round((ref.sucres_100g or 0) * factor, 2),
        'fats':     round((ref.lipides_100g or 0) * factor, 2),
    }


def rechercher_connus(q: str, limit: int = 10) -> list[dict]:
    """
    Recherche dans la base de connaissance ingrédients (KnownIngredient).
    Insensible à la casse et aux accents. Priorité aux correspondances synonymes.
    """
    from .models import _normaliser_nom
    if not q or len(q) < 2:
        return []
    q_norm = _normaliser_nom(q)
    from django.db.models import Q, Case, When, IntegerField, Count
    qs = (
        KnownIngredient.objects
        .select_related('ciqual_ref')
        .annotate(nb_recettes=Count('ciqual_ref__ingredients__recipe', distinct=True))
        .filter(Q(nom_normalise__icontains=q_norm) | Q(synonymes__icontains=q_norm))
        .annotate(
            pertinence=Case(
                When(nom_normalise__startswith=q_norm, then=0),
                When(nom_normalise__icontains=q_norm, then=1),
                default=2,
                output_field=IntegerField(),
            )
        )
        .order_by('pertinence', 'name')[:limit]
    )
    results = []
    for ki in qs:
        ref = ki.ciqual_ref
        results.append({
            'id':             ki.pk,
            'name':           ki.name,
            'ciqual_ref_id':  ref.pk if ref else None,
            'nom_ciqual':     ref.nom_fr if ref else None,
            'kcal_100g':      ref.kcal_100g if ref else None,
            'proteines_100g': ref.proteines_100g if ref else None,
            'glucides_100g':  ref.glucides_100g if ref else None,
            'lipides_100g':   ref.lipides_100g if ref else None,
            'default_weight_g': ref.default_weight_g if ref else None,
            'default_unit':   ki.default_unit or 'g',
        })
    return results


def rechercher_ciqual(q: str, limit: int = 8) -> list[dict]:
    """
    Recherche dans IngredientRef par nom normalisé.
    Retourne une liste de dicts pour le JSON de l'autocomplete.
    """
    from .models import _normaliser_nom
    if not q or len(q) < 2:
        return []
    q_norm = _normaliser_nom(q)
    from django.db.models import Q, Case, When, IntegerField
    refs = (
        IngredientRef.objects
        .filter(Q(nom_normalise__icontains=q_norm) | Q(synonymes__icontains=q_norm))
        .annotate(
            # Priorité : correspond au synonyme (nom courant) > correspond au nom Ciqual
            pertinence=Case(
                When(synonymes__icontains=q_norm, then=0),
                default=1,
                output_field=IntegerField(),
            )
        )
        .order_by('pertinence', 'nom_fr')
        .distinct()[:limit]
    )
    return [
        {
            'id': r.pk,
            'ciqual_code': r.ciqual_code,
            'nom_fr': r.nom_fr,
            'kcal_100g': r.kcal_100g,
            'proteines_100g': r.proteines_100g,
            'glucides_100g': r.glucides_100g,
            'lipides_100g': r.lipides_100g,
            'default_weight_g': r.default_weight_g,
        }
        for r in refs
    ]


def calculer_macros_recette(recipe: Recipe) -> None:
    """
    Recalcule et sauvegarde les macros par portion + nutrition_status.
    Calcule directement depuis ciqual_ref (pas les calories stockées).
    Tous les ingrédients (y compris optionnels) contribuent au calcul.
    Le nutrition_status est déterminé sur les non-optionnels uniquement.
    """
    all_ingrs = list(
        recipe.ingredients
        .select_related('ciqual_ref')
        .all()
    )
    non_optional = [i for i in all_ingrs if not i.is_optional]

    # ── Statut nutritionnel (basé sur les non-optionnels) ────────────────────
    mapped = [i for i in non_optional if i.ciqual_ref_id is not None]
    if not non_optional:
        status = 'missing'
    elif len(mapped) == len(non_optional):
        status = 'ok'
    elif mapped:
        status = 'partial'
    else:
        status = 'missing'

    if not all_ingrs:
        recipe.calories_per_serving = None
        recipe.kcal_per_100g_raw    = None
        recipe.proteins_per_serving = None
        recipe.carbs_per_serving    = None
        recipe.sugars_per_serving   = None
        recipe.fats_per_serving     = None
        recipe.nutrition_status     = 'missing'
        recipe.save(update_fields=[
            "calories_per_serving", "kcal_per_100g_raw", "proteins_per_serving",
            "carbs_per_serving", "sugars_per_serving", "fats_per_serving", "nutrition_status",
        ])
        return

    total_cal = total_prot = total_carbs = total_sugars = total_fats = 0.0
    total_weight_g = 0.0
    has_any = False
    for ingr in all_ingrs:
        macros = compute_ingredient_macros_from_ciqual(ingr)
        if macros:
            total_cal    += macros['calories']
            total_prot   += macros['proteins']
            total_carbs  += macros['carbs']
            total_sugars += macros['sugars']
            total_fats   += macros['fats']
            ref = ingr.ciqual_ref
            qty_g = _quantity_to_grams(ingr.quantity, ingr.unit, ref.default_weight_g if ref else None)
            if qty_g:
                total_weight_g += qty_g
            has_any = True

    n = max(recipe.base_servings or 1, 1)
    recipe.calories_per_serving = round(total_cal    / n, 1) if has_any else None
    recipe.kcal_per_100g_raw    = round(total_cal / total_weight_g * 100, 1) if has_any and total_weight_g > 0 else None
    recipe.proteins_per_serving = round(total_prot   / n, 1) if has_any else None
    recipe.carbs_per_serving    = round(total_carbs  / n, 1) if has_any else None
    recipe.sugars_per_serving   = round(total_sugars / n, 1) if has_any else None
    recipe.fats_per_serving     = round(total_fats   / n, 1) if has_any else None
    recipe.nutrition_status     = status
    recipe.save(update_fields=[
        "calories_per_serving", "kcal_per_100g_raw", "proteins_per_serving",
        "carbs_per_serving", "sugars_per_serving", "fats_per_serving", "nutrition_status",
    ])


def calculer_alertes_planning(week_plan, family) -> list[dict]:
    """
    Analyse le WeekPlan et retourne les alertes d'équilibre nutritionnel (nudges).
    Jamais bloquantes — uniquement affichées au Cuisinier dans le planning.
    Retourne une liste de dicts {type, message, dismissable}.
    """
    config = NutritionConfig.get()

    meals = list(
        Meal.objects
        .filter(week_plan=week_plan, absent=False, recipe__isnull=False)
        .select_related("recipe")
    )

    nb_jours = len(week_plan.get_active_dates()) or 7

    protein_types = [m.recipe.protein_type for m in meals if m.recipe.protein_type]
    red_meat_count = protein_types.count("boeuf") + protein_types.count("porc")
    fish_count     = protein_types.count("poisson")
    veg_count      = sum(1 for pt in protein_types if pt in ("aucune", "legumineuses"))

    total_cal  = sum(m.recipe.calories_per_serving  or 0 for m in meals)
    total_prot = sum(m.recipe.proteins_per_serving or 0 for m in meals)

    # Cibles proportionnelles au nombre de jours (référence : 14 créneaux/semaine)
    cal_target  = config.calories_dinner_target  * nb_jours * 2
    prot_target = config.proteins_dinner_target  * nb_jours * 2

    alertes = []

    if fish_count == 0:
        alertes.append({
            "type": "poisson",
            "message": "🐟 Pensez à intégrer un repas poisson sur cette période",
            "dismissable": True,
        })

    if red_meat_count >= config.max_red_meat_per_week:
        alertes.append({
            "type": "viande_rouge",
            "message": f"🥩 Vous avez déjà {red_meat_count} repas de viande rouge",
            "dismissable": True,
        })

    if veg_count == 0:
        alertes.append({
            "type": "vegetarien",
            "message": "🥦 Un repas végétarien serait bienvenu",
            "dismissable": True,
        })

    if cal_target > 0 and total_cal > cal_target * 1.3:
        alertes.append({
            "type": "calories_hautes",
            "message": "⚠️ La période semble chargée en calories",
            "dismissable": True,
        })

    if prot_target > 0 and total_prot > 0 and total_prot < prot_target * 0.6:
        alertes.append({
            "type": "proteines_basses",
            "message": "💪 Les protéines sont un peu faibles sur cette période",
            "dismissable": True,
        })

    logger.debug("calculer_alertes_planning : plan=%s → %d alerte(s)", week_plan.pk, len(alertes))
    return alertes


def bilan_planning(week_plan) -> dict:
    """
    Calcule le bilan équilibre de la période pour l'affichage dynamique.
    Retourne un dict avec les compteurs variété, totaux nutritionnels et statuts.
    Les créneaux `absent=True` sont exclus de tous les calculs.
    """
    config = NutritionConfig.get()

    meals = list(
        Meal.objects
        .filter(week_plan=week_plan, absent=False, recipe__isnull=False)
        .select_related("recipe")
    )

    absent_count = Meal.objects.filter(week_plan=week_plan, absent=True).count()
    nb_jours = len(week_plan.get_active_dates()) or 7
    total_slots = nb_jours * 2  # midi + soir par jour

    protein_types    = [m.recipe.protein_type for m in meals if m.recipe.protein_type]
    fish_count       = protein_types.count("poisson")
    red_meat_count   = protein_types.count("boeuf") + protein_types.count("porc")
    white_meat_count = protein_types.count("volaille")
    veg_count        = sum(1 for pt in protein_types if pt in ("aucune", "legumineuses"))

    total_cal    = sum((m.recipe.calories_per_serving  or 0) for m in meals)
    total_prot   = sum((m.recipe.proteins_per_serving or 0) for m in meals)
    total_sugars = sum((m.recipe.sugars_per_serving   or 0) for m in meals)

    cal_target  = config.calories_dinner_target  * (total_slots - absent_count)
    prot_target = config.proteins_dinner_target  * (total_slots - absent_count)

    def _pct(actual, target):
        if not target or not actual:
            return 0
        return round(actual / target * 100)

    def _status(actual, target):
        if not target or not actual:
            return "neutral"
        pct = actual / target * 100
        if pct < 60 or pct > 130:
            return "alert"
        if pct < 80 or pct > 110:
            return "warning"
        return "ok"

    return {
        "repas_avec_recette": len(meals),
        "absent_count":       absent_count,
        "fish_count":         fish_count,
        "red_meat_count":     red_meat_count,
        "white_meat_count":   white_meat_count,
        "veg_count":          veg_count,
        "fish_ok":            fish_count >= 1,
        "red_meat_ok":        red_meat_count <= config.max_red_meat_per_week,
        "white_meat_ok":      white_meat_count >= 1,
        "veg_ok":             veg_count >= 1,
        "cal_total":          round(total_cal),
        "prot_total":         round(total_prot, 1),
        "sugars_total":       round(total_sugars, 1),
        "cal_target":         round(cal_target),
        "prot_target":        round(prot_target, 1),
        "cal_pct":            _pct(total_cal, cal_target),
        "prot_pct":           _pct(total_prot, prot_target),
        "cal_status":         _status(total_cal, cal_target),
        "prot_status":        _status(total_prot, prot_target),
        "max_red_meat":       config.max_red_meat_per_week,
    }


def bilan_par_membre(plan) -> list[dict]:
    """
    Calcule les kcal/prot de la période par membre présent.

    Par jour :
    - Repas hors planning (petit-dej, collation, autres) → valeurs fixes du profil, ajoutées chaque jour
    - Repas planifié avec recette + membre présent → kcal/prot de la recette × portions_factor
    - Repas absent → cible du profil pour ce créneau (lunch ou dinner) × portions_factor
    - Créneau sans repas ou membre non présent → 0

    Cible totale = daily_kcal_total (profil) × nb_jours
    """
    config = NutritionConfig.get()
    active_dates = plan.get_active_dates()

    present_users = list(
        plan.present_members
        .select_related('profile')
        .all()
    )
    if not present_users:
        return []

    meals = list(
        Meal.objects
        .filter(week_plan=plan)
        .select_related('recipe')
        .prefetch_related('meal_members')
    )
    meal_by_slot = {(m.date, m.meal_time): m for m in meals}

    result = []
    for user in present_users:
        try:
            factor  = user.profile.portions_factor
            profile = user.profile
            # Créneaux planifiés — kcal
            lunch_kcal    = (profile.lunch_kcal_target  or 650) * factor
            dinner_kcal   = (profile.dinner_kcal_target or 650) * factor
            # Créneaux planifiés — protéines
            lunch_prot    = (profile.lunch_prot_target  or 25) * factor
            dinner_prot   = (profile.dinner_prot_target or 25) * factor
            # Hors planning — kcal et protéines par jour
            fixed_kcal    = ((profile.breakfast_kcal or 0) + (profile.snack_kcal or 0) + (profile.other_kcal or 0)) * factor
            fixed_prot    = ((profile.breakfast_prot  or 0) + (profile.snack_prot  or 0) + (profile.other_prot  or 0)) * factor
            # Cibles journalières complètes
            daily_kcal_target = (profile.daily_kcal_total or 2000) * factor
            daily_prot_target = (profile.daily_prot_total or 75)   * factor
        except Exception:
            factor = 1.0
            lunch_kcal  = dinner_kcal  = (config.calories_dinner_target or 650) * factor
            lunch_prot  = dinner_prot  = (config.proteins_dinner_target  or 27)  * factor
            fixed_kcal  = fixed_prot   = 0.0
            daily_kcal_target = (config.calories_dinner_target or 650) * 2 * factor
            daily_prot_target = (config.proteins_dinner_target  or 27)  * 2 * factor

        kcal_total = 0.0
        prot_total = 0.0
        member_ids_in_meals = {}

        nb_jours = len(active_dates)
        for d in active_dates:
            # Hors planning : ajoutés chaque jour sans condition
            kcal_total += fixed_kcal
            prot_total += fixed_prot

            for mt in ('lunch', 'dinner'):
                slot_kcal = lunch_kcal if mt == 'lunch' else dinner_kcal
                slot_prot = lunch_prot if mt == 'lunch' else dinner_prot
                meal = meal_by_slot.get((d, mt))
                if meal is None:
                    continue
                if meal.absent:
                    kcal_total += slot_kcal
                    prot_total += slot_prot
                elif meal.recipe:
                    slot = (meal.pk,)
                    if slot not in member_ids_in_meals:
                        member_ids_in_meals[slot] = frozenset(
                            meal.meal_members.values_list('id', flat=True)
                        )
                    if user.pk in member_ids_in_meals[slot]:
                        kcal_total += (meal.recipe.calories_per_serving or 0) * factor
                        prot_total += (meal.recipe.proteins_per_serving or 0) * factor

        kcal_target = daily_kcal_target * nb_jours
        prot_target = daily_prot_target * nb_jours

        def _pct_membre(actual, target):
            return min(round(actual / target * 100) if target else 0, 100)

        def _status_membre(actual, target):
            if not target:
                return 'neutral'
            p = actual / target * 100
            if p < 60 or p > 130:
                return 'alert'
            if p < 80 or p > 110:
                return 'warning'
            return 'ok'

        result.append({
            'user_id':     user.pk,
            'name':        user.first_name or user.email.split('@')[0],
            'kcal':        round(kcal_total),
            'prot':        round(prot_total, 1),
            'kcal_target': round(kcal_target),
            'prot_target': round(prot_target, 1),
            'kcal_pct':    _pct_membre(kcal_total, kcal_target),
            'prot_pct':    _pct_membre(prot_total, prot_target),
            'kcal_status': _status_membre(kcal_total, kcal_target),
            'prot_status': _status_membre(prot_total, prot_target),
        })

    return result


def _saison_courante() -> str:
    """Retourne la saison courante : printemps / ete / automne / hiver."""
    mois = date_type.today().month
    if mois in (3, 4, 5):  return "printemps"
    if mois in (6, 7, 8):  return "ete"
    if mois in (9, 10, 11): return "automne"
    return "hiver"


def calculer_protein_score(recipe) -> float:
    """Score protéines 0.3–1.0 basé sur proteins_per_serving réel."""
    p = recipe.proteins_per_serving
    if p is None: return 0.5   # inconnu → neutre
    if p < 15:    return 0.3   # faible
    if p < 25:    return 0.6   # correct
    return 1.0                 # élevé


def _protein_level(ps: float) -> str:
    """Libellé humain du Protein Score."""
    if ps == 0.3: return "faible"
    if ps == 0.6: return "correct"
    if ps == 1.0: return "élevé"
    return "inconnu"


def calculer_wpd(week_plan, config) -> float:
    """
    Weekly Protein Deficit factor (WPD).
    Compare les protéines déjà planifiées vs la cible des créneaux encore vides.
    Retourne 1.0 (nominal) · 1.2 (déficit modéré) · 1.5 (déficit fort).
    Les créneaux absent=True sont exclus du total et des cibles.
    """
    repas_planifies = list(
        Meal.objects
        .filter(week_plan=week_plan, absent=False, is_leftovers=False, recipe__isnull=False)
        .select_related("recipe")
    )
    repas_avec_prot = [m for m in repas_planifies if m.recipe.proteins_per_serving]

    proteins_planned = sum(
        m.recipe.proteins_per_serving
        * (m.servings_count or m.recipe.base_servings or 1)
        / max(m.recipe.base_servings or 1, 1)
        for m in repas_avec_prot
    )

    total_slots  = 14   # 7 jours × 2 créneaux
    filled_count = len(repas_planifies)
    absent_count = Meal.objects.filter(week_plan=week_plan, absent=True).count()
    repas_restants = max(0, total_slots - filled_count - absent_count)

    proteins_target = config.proteins_dinner_target * repas_restants
    if proteins_target == 0:
        return 1.0

    deficit_ratio = proteins_planned / proteins_target
    if deficit_ratio < 0.6:   return 1.5
    elif deficit_ratio < 0.8: return 1.2
    else:                      return 1.0


def _calculer_poids(wpd: float) -> dict:
    """
    Poids dynamiques normalisés selon le WPD.
    Le poids nutrition augmente proportionnellement à WPD ;
    les autres dimensions sont réduites pour que Σ = 1.0.
    """
    base = {
        "fraicheur":    0.30,
        "appreciation": 0.30,
        "variete":      0.20,
        "saison":       0.10,
        "nutrition":    0.10,
    }
    nutrition_weight = base["nutrition"] * wpd          # 0.10 → 0.12 → 0.15
    autres_base  = 1.0 - base["nutrition"]              # 0.90
    autres_cible = 1.0 - nutrition_weight
    ratio = autres_cible / autres_base
    return {
        "fraicheur":    round(base["fraicheur"]    * ratio, 4),
        "appreciation": round(base["appreciation"] * ratio, 4),
        "variete":      round(base["variete"]      * ratio, 4),
        "saison":       round(base["saison"]       * ratio, 4),
        "nutrition":    round(nutrition_weight,            4),
    }


def suggerer_recettes(family, week_plan, target_date, meal_time: str) -> list[dict]:
    """
    Retourne les 5 meilleures recettes candidates pour un créneau (date + meal_time).

    Score composite 0.0–1.0 sur 5 dimensions — poids dynamiques normalisés selon WPD :
      fraîcheur/rotation · appréciation famille · variété protéines
      saisonnalité · adéquation protéique (PS × WPD)

    Chaque résultat : {recipe, score, protein_score, protein_level,
                       proteins_per_serving, reasons{…nutrition…}}
    """
    config = NutritionConfig.get()
    saison = _saison_courante()

    # ── Candidats ─────────────────────────────────────────────────────────────
    all_recipes = list(Recipe.objects.filter(actif=True))
    if not all_recipes:
        return []

    # ── WPD et poids dynamiques ────────────────────────────────────────────────
    wpd   = calculer_wpd(week_plan, config)
    poids = _calculer_poids(wpd)

    # ── Membres de la famille ──────────────────────────────────────────────────
    family_user_ids = set(
        UserProfile.objects.filter(family=family).values_list("user_id", flat=True)
    )

    # ── Dernière utilisation de chaque recette pour cette famille ──────────────
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
        Meal.objects
        .filter(week_plan=week_plan, absent=False, recipe__isnull=False)
        .select_related("recipe")
    )
    day_meals = [m for m in week_meals if m.date == target_date]

    day_protein_types  = [m.recipe.protein_type for m in day_meals  if m.recipe.protein_type]
    week_protein_types = [m.recipe.protein_type for m in week_meals if m.recipe.protein_type]
    red_meat_count     = week_protein_types.count("boeuf") + week_protein_types.count("porc")

    # ── Scoring ───────────────────────────────────────────────────────────────
    results = []

    for recipe in all_recipes:
        avg_fam = _family_avg(recipe.id)
        last    = last_used.get(recipe.id)

        # ── Dim 1 : Fraîcheur / rotation ──────────────────────────────────────
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

        # ── Dim 2 : Appréciation famille ──────────────────────────────────────
        famille_score = 0.5 if avg_fam is None else avg_fam / 5.0

        # ── Dim 3 : Variété protéines + bonus adéquation ──────────────────────
        pt = recipe.protein_type
        if not pt:
            variete_score = 0.5   # neutre si type non renseigné
        elif day_protein_types.count(pt) >= 2:
            variete_score = 0.0   # règle dure : 2× même protéine dans la journée
        elif pt in ("boeuf", "porc") and red_meat_count >= config.max_red_meat_per_week:
            variete_score = 0.0   # règle dure : quota viande rouge atteint
        else:
            variete_score = 0.5
            if pt not in week_protein_types:
                variete_score += 0.3   # bonus : absent de la semaine
            elif week_protein_types.count(pt) >= 2:
                variete_score -= 0.2   # malus : déjà 2× cette semaine
            # Bonus adéquation protéique : récompense les plats très protéinés
            if recipe.proteins_per_serving and recipe.proteins_per_serving > 25:
                variete_score += 0.1
            variete_score = max(0.0, min(1.0, variete_score))

        # ── Dim 4 : Saisonnalité ──────────────────────────────────────────────
        seasons = recipe.seasons or []
        if not seasons:
            saison_score = 0.7
        elif saison in seasons:
            saison_score = 1.0
        else:
            saison_score = 0.2

        # ── Dim 5 : Adéquation protéique (PS × WPD, normalisé à 1.0) ─────────
        ps = calculer_protein_score(recipe)
        nutrition_score = min(ps * wpd, 1.0)

        # ── Score final avec poids dynamiques normalisés ───────────────────────
        score = (
            rotation_score   * poids["fraicheur"]    +
            famille_score    * poids["appreciation"] +
            variete_score    * poids["variete"]      +
            saison_score     * poids["saison"]       +
            nutrition_score  * poids["nutrition"]
        )

        results.append({
            "recipe":              recipe,
            "score":               round(score, 3),
            "protein_score":       ps,
            "protein_level":       _protein_level(ps),
            "proteins_per_serving": recipe.proteins_per_serving,
            "reasons": {
                "rotation":   round(rotation_score,  2),
                "famille":    round(famille_score,   2),
                "variete":    round(variete_score,   2),
                "saison":     round(saison_score,    2),
                "nutrition":  round(nutrition_score, 2),
            },
        })

    results.sort(key=lambda x: x["score"], reverse=True)
    logger.debug(
        "suggerer_recettes : famille=%s date=%s %s → %d candidats, top=%.3f, wpd=%.1f",
        family.pk, target_date, meal_time,
        len(results), results[0]["score"] if results else 0, wpd,
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


def _sync_known_ingredient(name: str, ciqual_ref) -> None:
    """Ajoute ou enrichit la base de connaissance lors de la sauvegarde d'une recette."""
    from .models import _normaliser_nom
    nom_norm = _normaliser_nom(name)
    try:
        ki = KnownIngredient.objects.get(nom_normalise=nom_norm)
        if ciqual_ref and ki.ciqual_ref is None:
            ki.ciqual_ref = ciqual_ref
            ki.save(update_fields=['ciqual_ref'])
    except KnownIngredient.DoesNotExist:
        KnownIngredient.objects.create(name=name, ciqual_ref=ciqual_ref)


@transaction.atomic
def sauvegarder_recette_depuis_post(recipe: Recipe, post_data: dict) -> None:
    """
    Parse les données POST du formulaire recette et sauvegarde groupes, ingrédients,
    étapes et sections. Supprime les anciens objets et recrée tout.
    Appelé après la sauvegarde du modèle Recipe lui-même.
    """
    # ── Ingrédients ──────────────────────────────────────────────────────────
    # Ingredient.group a on_delete=SET_NULL → supprimer les ingrédients en premier
    recipe.ingredients.all().delete()
    recipe.ingredient_groups.all().delete()

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
            qty  = _parse_float(post_data.get(f"ing_qty_{g}_{i}"))
            unit = post_data.get(f"ing_unit_{g}_{i}", "").strip() or None

            # ── Résolution KnownIngredient (source primaire) ────────────────
            # Le formulaire envoie ing_known_id (nouveau) OU ing_ciqual_ref_id
            # (ancien, rétrocompat pour les recettes déjà en base).
            known_ingr = None
            ciqual_ref = None
            known_id_raw = post_data.get(f"ing_known_id_{g}_{i}", "").strip()
            if known_id_raw:
                try:
                    known_ingr = KnownIngredient.objects.select_related('ciqual_ref').get(
                        pk=int(known_id_raw)
                    )
                    ciqual_ref = known_ingr.ciqual_ref  # dérivé de la base de connaissance
                except (KnownIngredient.DoesNotExist, ValueError):
                    pass
            # Fallback rétrocompat : champ ing_ciqual_ref_id encore présent en base
            if ciqual_ref is None:
                ciqual_id_raw = post_data.get(f"ing_ciqual_ref_id_{g}_{i}", "").strip()
                if ciqual_id_raw:
                    try:
                        ciqual_ref = IngredientRef.objects.get(pk=int(ciqual_id_raw))
                    except (IngredientRef.DoesNotExist, ValueError):
                        pass

            ingr = Ingredient(
                recipe=recipe,
                group=group,
                name=name,
                quantity=qty,
                quantity_note=post_data.get(f"ing_qty_note_{g}_{i}", "").strip() or None,
                unit=unit,
                is_optional=post_data.get(f"ing_optional_{g}_{i}") == "on",
                category=post_data.get(f"ing_category_{g}_{i}", "").strip() or None,
                known_ingredient=known_ingr,
                ciqual_ref=ciqual_ref,
                order=i,
            )
            # Macros : calculées depuis Ciqual (dérivé de KnownIngredient).
            # Jamais depuis des champs cachés pour éviter les valeurs obsolètes.
            macros = compute_ingredient_macros_from_ciqual(ingr) if ciqual_ref else None
            if macros:
                ingr.calories = macros['calories']
                ingr.proteins = macros['proteins']
                ingr.carbs    = macros['carbs']
                ingr.fats     = macros['fats']
            else:
                ingr.calories = None
                ingr.proteins = None
                ingr.carbs    = None
                ingr.fats     = None
            ingr.save()
            # Enrichissement base de connaissance si ingrédient non encore référencé
            if known_ingr is None:
                _sync_known_ingredient(name, ciqual_ref)

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


# ─── Notifications email ─────────────────────────────────────────────────────

def _destinataires_email(profiles) -> list:
    """
    Filtre une queryset de UserProfile pour ne garder que les utilisateurs
    qui n'ont PAS explicitement désactivé les notifications email.
    """
    result = []
    for profile in profiles:
        if not profile.user.email:
            continue
        a_desactive = NotificationPreference.objects.filter(
            user=profile.user, channel="email", enabled=False
        ).exists()
        if not a_desactive:
            result.append(profile.user.email)
    return result


def notifier_planning_publie(plan: WeekPlan) -> None:
    """
    Envoie un récapitulatif de la semaine à tous les membres de la famille
    qui n'ont pas désactivé les notifications email.
    """
    from .integrations.email import envoyer_email

    membres = plan.family.members.select_related("user").all()
    recipients = _destinataires_email(membres)
    if not recipients:
        return

    meals = (
        plan.meals
        .filter(recipe__isnull=False)
        .select_related("recipe")
        .order_by("date", "meal_time")
    )

    context = {
        "plan": plan,
        "meals": meals,
        "family_name": plan.family.name,
        "period_start": plan.period_start,
        "period_end": plan.period_end,
        "published_by": plan.created_by.first_name or plan.created_by.email,
    }

    envoyer_email(
        subject=f"🍽️ Menu du {plan.period_start.strftime('%d/%m')} — {plan.family.name}",
        template_txt="menu/email/planning_publie.txt",
        template_html="menu/email/planning_publie.html",
        context=context,
        recipients=recipients,
    )


def notifier_nouvelle_proposition(proposal: MealProposal) -> None:
    """
    Envoie un email aux Cuisiniers de la famille quand un Convive propose une recette.
    N'envoie pas à la personne qui vient de proposer.
    """
    from .integrations.email import envoyer_email

    cuisiniers = (
        proposal.family.members
        .filter(role__in=["cuisinier", "chef_etoile"])
        .exclude(user=proposal.proposed_by)
        .select_related("user")
    )
    recipients = _destinataires_email(cuisiniers)
    if not recipients:
        return

    context = {
        "proposal": proposal,
        "recipe": proposal.recipe,
        "proposed_by": proposal.proposed_by.first_name or proposal.proposed_by.email,
        "plan": proposal.week_plan,
        "family_name": proposal.family.name,
        "message": proposal.message,
    }

    envoyer_email(
        subject=f"💡 {proposal.proposed_by.first_name or 'Quelqu\'un'} propose « {proposal.recipe.title} »",
        template_txt="menu/email/nouvelle_proposition.txt",
        template_html="menu/email/nouvelle_proposition.html",
        context=context,
        recipients=recipients,
    )

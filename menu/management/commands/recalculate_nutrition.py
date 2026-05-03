"""
Management command: recalculate_nutrition
==========================================
Usage:
    python manage.py recalculate_nutrition
    python manage.py recalculate_nutrition --dry-run
    python manage.py recalculate_nutrition --recipe-id 42

Recalcule les macros (calories, protéines, glucides, lipides) sur :
1. Chaque Ingredient ayant un ciqual_ref ET une quantité convertible en grammes
2. Chaque Recipe, en agrégeant ses ingrédients et en divisant par base_servings

Conversions d'unités supportées :
  g, kg, ml, cl, L → grammes directs
  c. à soupe, càs, cs → 15 g
  c. à café, càc, cc → 5 g
  (aucune unité + default_weight_g sur ciqual_ref) → dénombrable
"""

from django.core.management.base import BaseCommand
from django.db import transaction

from menu.models import Ingredient, Recipe, KnownIngredient


# ─── Conversions vers grammes ────────────────────────────────────────────────

UNIT_TO_GRAMS: dict[str | None, float | None] = {
    'g':         1.0,
    'kg':        1000.0,
    'ml':        1.0,     # densité ≈ 1 pour liquides cuisiniers
    'cl':        10.0,
    'L':         1000.0,
    'l':         1000.0,
    'c. à soupe': 15.0,
    'càs':       15.0,
    'cs':        15.0,
    'c. à café': 5.0,
    'càc':       5.0,
    'cc':        5.0,
}


def quantity_to_grams(quantity: float | None, unit: str | None,
                      default_weight_g: float | None) -> float | None:
    """Convertit une quantité dans l'unité donnée en grammes."""
    if quantity is None:
        return None

    if unit in UNIT_TO_GRAMS:
        factor = UNIT_TO_GRAMS[unit]
        return quantity * factor

    # Unité nulle = élément dénombrable (ex: 2 oignons)
    if unit is None and default_weight_g is not None:
        return quantity * default_weight_g

    return None  # Unité inconnue ou manque de données


def compute_ingredient_macros(ingr: Ingredient) -> dict | None:
    """
    Calcule les macros d'un ingrédient à partir de son ciqual_ref.
    Retourne None UNIQUEMENT si ciqual_ref est absent (non mappé) ou quantité invalide.
    Un kcal_100g NULL (sel, eau…) est traité comme 0 — l'ingrédient est mappé et correct.
    """
    ref = ingr.ciqual_ref
    if ref is None:
        return None  # Pas de mapping Ciqual → non calculable

    qty_g = quantity_to_grams(ingr.quantity, ingr.unit, ref.default_weight_g)
    if qty_g is None or qty_g <= 0:
        return None  # Quantité manquante ou unité inconnue

    factor = qty_g / 100.0
    return {
        'calories': round((ref.kcal_100g or 0) * factor, 2),
        'proteins': round((ref.proteines_100g or 0) * factor, 2),
        'carbs':    round((ref.glucides_100g or 0) * factor, 2),
        'fats':     round((ref.lipides_100g or 0) * factor, 2),
    }


# ─── Command ────────────────────────────────────────────────────────────────

class Command(BaseCommand):
    help = 'Recalcule les macros sur tous les Ingredient et Recipe'

    def add_arguments(self, parser):
        parser.add_argument('--dry-run', action='store_true')
        parser.add_argument('--recipe-id', type=int, default=None,
                            help='Limiter à une seule recette')

    @transaction.atomic
    def handle(self, *args, **options):
        dry_run   = options['dry_run']
        recipe_id = options['recipe_id']

        # ── Purge des ingrédients orphelins (group=NULL, résidu d'un bug d'accumulation) ──
        orphan_qs = Ingredient.objects.filter(group__isnull=True)
        if recipe_id:
            orphan_qs = orphan_qs.filter(recipe_id=recipe_id)
        orphan_count = orphan_qs.count()
        if orphan_count:
            if not dry_run:
                orphan_qs.delete()
            self.stdout.write(
                f'{"[DRY] " if dry_run else ""}Ingrédients orphelins supprimés : {orphan_count}'
            )

        recipe_qs = Recipe.objects.filter(actif=True)
        if recipe_id:
            recipe_qs = recipe_qs.filter(pk=recipe_id)

        ingr_updated = 0
        ingr_no_ref  = 0
        ingr_no_qty  = 0
        recipe_updated = 0
        recipe_partial = 0

        for recipe in recipe_qs:
            recipe_kcal = recipe_prot = recipe_gluc = recipe_lip = 0.0
            has_any = False
            all_calculable = True

            # ── 1. Recalculer chaque ingrédient ──────────────────────────
            all_ingrs = Ingredient.objects.filter(recipe=recipe).select_related(
                'ciqual_ref', 'known_ingredient__ciqual_ref'
            )

            for ingr in all_ingrs:
                if ingr.is_optional:
                    continue

                # Priorité : ciqual_ref dérivé de known_ingredient, sinon ciqual_ref direct
                if ingr.known_ingredient and ingr.known_ingredient.ciqual_ref:
                    if ingr.ciqual_ref_id != ingr.known_ingredient.ciqual_ref_id:
                        ingr.ciqual_ref = ingr.known_ingredient.ciqual_ref
                        if not dry_run:
                            ingr.save(update_fields=['ciqual_ref'])

                macros = compute_ingredient_macros(ingr) if ingr.ciqual_ref else None

                if macros is None:
                    # Pas de ref ou quantité non convertible → on efface les valeurs
                    # obsolètes plutôt que de les laisser polluer le calcul.
                    if ingr.ciqual_ref is None:
                        ingr_no_ref += 1
                    else:
                        ingr_no_qty += 1
                    all_calculable = False
                    if not dry_run and (ingr.calories is not None or ingr.proteins is not None):
                        ingr.calories = None
                        ingr.proteins = None
                        ingr.carbs    = None
                        ingr.fats     = None
                        ingr.save(update_fields=['calories', 'proteins', 'carbs', 'fats'])
                    continue

                if not dry_run:
                    ingr.calories = macros['calories']
                    ingr.proteins = macros['proteins']
                    ingr.carbs    = macros['carbs']
                    ingr.fats     = macros['fats']
                    ingr.save(update_fields=['calories', 'proteins', 'carbs', 'fats'])

                recipe_kcal += macros['calories']
                recipe_prot += macros['proteins']
                recipe_gluc += macros['carbs']
                recipe_lip  += macros['fats']
                has_any = True
                ingr_updated += 1

            # ── 2. Agréger sur la recette — toujours écrire (même None) ──────
            bs = recipe.base_servings or 1
            if has_any:
                kcal_per = round(recipe_kcal / bs, 1)
                prot_per = round(recipe_prot / bs, 2)
                gluc_per = round(recipe_gluc / bs, 2)
                lip_per  = round(recipe_lip  / bs, 2)
                status   = 'ok' if all_calculable else 'partial'
                if dry_run:
                    self.stdout.write(
                        f'  [DRY] {recipe.title[:40]:40s} | '
                        f'{kcal_per:>6.0f} kcal | {prot_per:>5.1f} g prot | '
                        f'{"OK" if all_calculable else "partiel"}'
                    )
                else:
                    recipe.calories_per_serving = kcal_per
                    recipe.proteins_per_serving  = prot_per
                    recipe.carbs_per_serving     = gluc_per
                    recipe.fats_per_serving      = lip_per
                    recipe.nutrition_status      = status
                    recipe.save(update_fields=[
                        'calories_per_serving', 'proteins_per_serving',
                        'carbs_per_serving', 'fats_per_serving',
                        'nutrition_status',
                    ])
                recipe_updated += 1
                if not all_calculable:
                    recipe_partial += 1
            else:
                # Aucun ingrédient calculable → effacer les macros de la recette
                if not dry_run:
                    recipe.calories_per_serving = None
                    recipe.proteins_per_serving  = None
                    recipe.carbs_per_serving     = None
                    recipe.fats_per_serving      = None
                    recipe.nutrition_status      = 'missing'
                    recipe.save(update_fields=[
                        'calories_per_serving', 'proteins_per_serving',
                        'carbs_per_serving', 'fats_per_serving',
                        'nutrition_status',
                    ])

        self.stdout.write(self.style.SUCCESS(
            f'Recalcul termine :\n'
            f'   Ingredients mis a jour  : {ingr_updated}\n'
            f'   Ingredients sans ref    : {ingr_no_ref}\n'
            f'   Ingredients sans qte   : {ingr_no_qty}\n'
            f'   Recettes mises a jour   : {recipe_updated}\n'
            f'   Recettes partielles     : {recipe_partial}\n'
            + ('   [MODE DRY-RUN - rien n\'a ete sauvegarde]' if dry_run else '')
        ))

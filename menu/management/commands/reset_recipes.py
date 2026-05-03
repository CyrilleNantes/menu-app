"""
reset_recipes
=============
Supprime les recettes et données associées.

Modes :
  --full          Recettes + KnownIngredient + WeekPlan  (reset complet, recommandé)
  --also-planning Recettes + WeekPlan (garde KnownIngredient)
  (aucun flag)    Recettes uniquement

Toujours conservés :
  - IngredientRef (table Ciqual ANSES — ne jamais supprimer)
  - Utilisateurs et familles

Usage :
    python manage.py reset_recipes --full
    python manage.py reset_recipes --dry-run --full
"""

from django.core.management.base import BaseCommand
from django.db import transaction

from menu.models import Recipe, WeekPlan, KnownIngredient


class Command(BaseCommand):
    help = "Supprime les recettes et données associées (voir --full pour reset complet)"

    def add_arguments(self, parser):
        parser.add_argument('--dry-run', action='store_true',
                            help='Affiche les comptages sans supprimer')
        parser.add_argument('--full', action='store_true',
                            help='Reset complet : recettes + KnownIngredient + WeekPlan')
        parser.add_argument('--also-planning', action='store_true',
                            help='Supprime aussi WeekPlan (sans toucher KnownIngredient)')

    @transaction.atomic
    def handle(self, *args, **options):
        dry_run       = options['dry_run']
        full          = options['full']
        also_planning = options['also_planning'] or full

        recipe_count = Recipe.objects.count()
        wp_count     = WeekPlan.objects.count()
        ki_count     = KnownIngredient.objects.count()

        if dry_run:
            self.stdout.write(f"[DRY-RUN] {recipe_count} recette(s) à supprimer")
            if also_planning:
                self.stdout.write(f"[DRY-RUN] {wp_count} planning(s) à supprimer")
            if full:
                self.stdout.write(f"[DRY-RUN] {ki_count} KnownIngredient à supprimer")
            self.stdout.write("IngredientRef (Ciqual) conservé.")
            return

        total_deleted = 0

        if also_planning:
            n, _ = WeekPlan.objects.all().delete()
            total_deleted += n
            self.stdout.write(f"  Plannings supprimés : {n}")

        n, _ = Recipe.objects.all().delete()
        total_deleted += n
        self.stdout.write(f"  Recettes (+ cascade) supprimées : {n}")

        if full:
            n, _ = KnownIngredient.objects.all().delete()
            total_deleted += n
            self.stdout.write(f"  KnownIngredient supprimés : {n}")

        self.stdout.write(self.style.SUCCESS(
            f"\nReset terminé — {total_deleted} objets supprimés au total.\n"
            f"IngredientRef (Ciqual) conservé."
        ))

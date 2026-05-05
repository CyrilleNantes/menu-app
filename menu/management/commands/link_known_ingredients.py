"""
link_known_ingredients
======================
Relie automatiquement les Ingredient existants (sans known_ingredient)
à leur KnownIngredient correspondant.

Stratégie de correspondance (dans l'ordre) :
  1. ciqual_ref identique : même IngredientRef FK → KnownIngredient le plus fréquent
  2. nom normalisé identique : _normaliser_nom(ingredient.name) == KnownIngredient.nom_normalise

Usage :
    python manage.py link_known_ingredients
    python manage.py link_known_ingredients --dry-run
"""

from django.core.management.base import BaseCommand
from django.db import transaction

from menu.models import Ingredient, KnownIngredient, _normaliser_nom


class Command(BaseCommand):
    help = "Relie les Ingredient existants à leur KnownIngredient (migration one-shot)"

    def add_arguments(self, parser):
        parser.add_argument('--dry-run', action='store_true',
                            help='Affiche les liaisons sans sauvegarder')

    @transaction.atomic
    def handle(self, *args, **options):
        dry_run = options['dry_run']

        # Ingrédients sans known_ingredient (tous les existants après migration)
        qs = (Ingredient.objects
              .filter(known_ingredient__isnull=True)
              .select_related('ciqual_ref'))

        total = qs.count()
        self.stdout.write(f"Ingrédients sans lien known_ingredient : {total}")

        # Index 1 : ciqual_ref_id → KnownIngredient PK (le premier trouvé)
        ciqual_to_ki: dict[int, KnownIngredient] = {}
        for ki in KnownIngredient.objects.filter(ciqual_ref__isnull=False).select_related('ciqual_ref'):
            if ki.ciqual_ref_id not in ciqual_to_ki:
                ciqual_to_ki[ki.ciqual_ref_id] = ki

        # Index 2 : nom_normalise → KnownIngredient
        name_to_ki: dict[str, KnownIngredient] = {
            ki.nom_normalise: ki
            for ki in KnownIngredient.objects.all()
        }

        linked_ciqual = linked_name = skipped = 0

        to_update: list[Ingredient] = []
        for ingr in qs.iterator(chunk_size=500):
            ki = None

            # Stratégie 1 : ciqual_ref
            if ingr.ciqual_ref_id and ingr.ciqual_ref_id in ciqual_to_ki:
                ki = ciqual_to_ki[ingr.ciqual_ref_id]
                linked_ciqual += 1

            # Stratégie 2 : nom normalisé
            if ki is None:
                norm = _normaliser_nom(ingr.name)
                if norm in name_to_ki:
                    ki = name_to_ki[norm]
                    linked_name += 1

            if ki is None:
                skipped += 1
                continue

            if dry_run:
                self.stdout.write(
                    f"  [DRY] {ingr.name[:40]:40s} → {ki.name} "
                    f"({'ciqual' if ingr.ciqual_ref_id and ingr.ciqual_ref_id in ciqual_to_ki else 'nom'})"
                )
            else:
                ingr.known_ingredient = ki
                to_update.append(ingr)

        if not dry_run and to_update:
            CHUNK = 500
            for i in range(0, len(to_update), CHUNK):
                Ingredient.objects.bulk_update(to_update[i:i + CHUNK], ['known_ingredient'])

        self.stdout.write(self.style.SUCCESS(
            f"\nTerminé :\n"
            f"   Via ciqual_ref   : {linked_ciqual}\n"
            f"   Via nom normalisé : {linked_name}\n"
            f"   Sans correspondance : {skipped}\n"
            + ("   [DRY-RUN — rien sauvegardé]" if dry_run else
               f"   Total liés       : {linked_ciqual + linked_name}")
        ))

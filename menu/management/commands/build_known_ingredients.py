from collections import Counter
from django.core.management.base import BaseCommand
from menu.models import Ingredient, KnownIngredient, _normaliser_nom


class Command(BaseCommand):
    help = "Construit la base de connaissance ingrédients depuis les recettes existantes."

    def handle(self, *args, **options):
        qs = (Ingredient.objects
              .filter(recipe__actif=True)
              .select_related('ciqual_ref')
              .values_list('name', 'ciqual_ref_id'))

        # Regroupe par nom normalisé : choisit le ciqual_ref le plus fréquent
        grouped = {}  # nom_norm → {name_original, counter_ciqual}
        for name, ciqual_id in qs:
            name = name.strip()
            if not name:
                continue
            norm = _normaliser_nom(name)
            if norm not in grouped:
                grouped[norm] = {'name': name, 'ciqual_counter': Counter()}
            if ciqual_id:
                grouped[norm]['ciqual_counter'][ciqual_id] += 1

        created = updated = skipped = 0
        for nom_norm, data in grouped.items():
            best_ciqual_id = (data['ciqual_counter'].most_common(1)[0][0]
                              if data['ciqual_counter'] else None)
            try:
                ki = KnownIngredient.objects.get(nom_normalise=nom_norm)
                # Met à jour le ciqual_ref seulement s'il manque
                if best_ciqual_id and ki.ciqual_ref_id is None:
                    ki.ciqual_ref_id = best_ciqual_id
                    ki.save(update_fields=['ciqual_ref'])
                    updated += 1
                else:
                    skipped += 1
            except KnownIngredient.DoesNotExist:
                KnownIngredient.objects.create(
                    name=data['name'],
                    ciqual_ref_id=best_ciqual_id,
                )
                created += 1

        self.stdout.write(self.style.SUCCESS(
            f"Terminé : {created} créés, {updated} mis à jour, {skipped} inchangés."
        ))

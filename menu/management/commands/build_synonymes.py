import unicodedata
import re
from collections import defaultdict
from django.core.management.base import BaseCommand
from menu.models import Ingredient, IngredientRef


def _normalize(s: str) -> str:
    s = s.lower().strip()
    s = unicodedata.normalize('NFD', s)
    s = ''.join(c for c in s if unicodedata.category(c) != 'Mn')
    s = re.sub(r'[^\w\s]', ' ', s)
    return re.sub(r'\s+', ' ', s).strip()


class Command(BaseCommand):
    help = "Construit les synonymes Ciqual à partir des noms d'ingrédients existants dans les recettes."

    def add_arguments(self, parser):
        parser.add_argument(
            '--reset', action='store_true',
            help="Écrase les synonymes existants (par défaut : fusionne sans supprimer les manuels)."
        )

    def handle(self, *args, **options):
        reset = options['reset']

        # Collecte : pour chaque ciqual_ref, tous les noms d'ingrédients utilisés
        raw = defaultdict(set)
        qs = Ingredient.objects.filter(ciqual_ref__isnull=False).values_list('name', 'ciqual_ref_id')
        for name, ref_id in qs:
            nom = name.strip()
            if nom:
                raw[ref_id].add(nom)

        self.stdout.write(f"{len(raw)} IngredientRef avec des ingrédients mappés.")

        updated = 0
        for ref in IngredientRef.objects.filter(pk__in=raw.keys()):
            nouveaux = raw[ref.pk]

            # Exclure les noms trop proches du nom officiel Ciqual (inutiles comme synonyme)
            nom_norm = _normalize(ref.nom_fr)
            candidats = {n for n in nouveaux if _normalize(n) not in (nom_norm, nom_norm[:20])}

            if reset:
                synonymes_finaux = candidats
            else:
                # Fusion : garde les manuels existants + ajoute les nouveaux
                existants = {s.strip() for s in ref.synonymes.split(',') if s.strip()}
                synonymes_finaux = existants | candidats

            nouvelle_valeur = ', '.join(sorted(synonymes_finaux))
            if nouvelle_valeur != ref.synonymes:
                ref.synonymes = nouvelle_valeur
                ref.save(update_fields=['synonymes'])
                updated += 1

        self.stdout.write(self.style.SUCCESS(f"{updated} IngredientRef mis à jour avec des synonymes."))

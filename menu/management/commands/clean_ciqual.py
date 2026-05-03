"""
clean_ciqual
============
Nettoie la table IngredientRef en supprimant :
  1. Les entrées du groupe "entrées et plats composés"
  2. Les entrées sans donnée calorique (kcal_100g IS NULL)
     → Exception : eaux, bouillons, vinaigres (kcal réellement 0 ou non pertinent)

Si un KnownIngredient référençait une entrée supprimée, son ciqual_ref
passe automatiquement à NULL (on_delete=SET_NULL) — à re-mapper manuellement.

Usage :
    python manage.py clean_ciqual --dry-run   ← voir ce qui serait supprimé
    python manage.py clean_ciqual             ← supprimer pour de vrai
"""

from django.core.management.base import BaseCommand
from django.db import transaction

from menu.models import IngredientRef

# Groupes à supprimer entièrement (peu importe les données nutritionnelles)
GROUPES_A_SUPPRIMER = {
    'entrées et plats composés',
}

# Mots-clés dans le nom qui justifient de garder une entrée même sans kcal
# (eau, bouillon, vinaigre… ont légitimement 0 ou pas de calorie utile)
EXCEPTIONS_SANS_KCAL = [
    'eau', 'bouillon', 'vinaigre', 'levure chimique', 'gelatine',
    'agar', 'pectine', 'sel ', 'sel,', 'bicarbonate',
]


def est_exception(nom: str) -> bool:
    n = nom.lower()
    return any(kw in n for kw in EXCEPTIONS_SANS_KCAL)


class Command(BaseCommand):
    help = "Nettoie la table Ciqual (plats composés + entrées sans calorie)"

    def add_arguments(self, parser):
        parser.add_argument('--dry-run', action='store_true',
                            help='Affiche ce qui serait supprimé sans toucher la base')

    @transaction.atomic
    def handle(self, *args, **options):
        dry_run = options['dry_run']

        # ── 1. Plats composés ────────────────────────────────────────────────
        qs_plats = IngredientRef.objects.filter(groupe__in=GROUPES_A_SUPPRIMER)
        n_plats = qs_plats.count()

        # ── 2. Sans kcal (hors exceptions) ──────────────────────────────────
        qs_sans_kcal_all = IngredientRef.objects.filter(
            kcal_100g__isnull=True
        ).exclude(
            groupe__in=GROUPES_A_SUPPRIMER  # déjà comptés ci-dessus
        )

        sans_kcal_gardes   = []
        sans_kcal_a_suppr  = []
        for ref in qs_sans_kcal_all.values('id', 'nom_fr', 'groupe'):
            if est_exception(ref['nom_fr']):
                sans_kcal_gardes.append(ref)
            else:
                sans_kcal_a_suppr.append(ref)

        n_sans_kcal = len(sans_kcal_a_suppr)
        ids_sans_kcal = [r['id'] for r in sans_kcal_a_suppr]

        # ── Affichage dry-run ────────────────────────────────────────────────
        if dry_run:
            self.stdout.write(f"\n{'─'*60}")
            self.stdout.write(f"Plats composés à supprimer : {n_plats}")
            self.stdout.write(f"Entrées sans kcal à supprimer : {n_sans_kcal}")
            self.stdout.write(f"Entrées sans kcal conservées (exceptions) : {len(sans_kcal_gardes)}")

            self.stdout.write(f"\n── Exemples plats composés (10 premiers) ──")
            for ref in qs_plats.values('nom_fr', 'groupe')[:10]:
                self.stdout.write(f"  {ref['nom_fr'][:60]}")

            self.stdout.write(f"\n── Exemples sans kcal supprimés (10 premiers) ──")
            for ref in sans_kcal_a_suppr[:10]:
                self.stdout.write(f"  {ref['nom_fr'][:60]}")

            self.stdout.write(f"\n── Exceptions conservées ──")
            for ref in sans_kcal_gardes:
                self.stdout.write(f"  ✓ {ref['nom_fr'][:60]}")

            self.stdout.write(
                f"\n[DRY-RUN] Total à supprimer : {n_plats + n_sans_kcal} entrées\n"
                f"Relancer sans --dry-run pour appliquer."
            )
            return

        # ── Suppression ──────────────────────────────────────────────────────
        deleted_plats, _ = qs_plats.delete()
        deleted_sans_kcal = 0
        if ids_sans_kcal:
            deleted_sans_kcal, _ = IngredientRef.objects.filter(id__in=ids_sans_kcal).delete()

        self.stdout.write(self.style.SUCCESS(
            f"\nNettoyage terminé :\n"
            f"   Plats composés supprimés       : {deleted_plats}\n"
            f"   Entrées sans kcal supprimées   : {deleted_sans_kcal}\n"
            f"   Exceptions conservées          : {len(sans_kcal_gardes)}\n"
            f"   Total supprimé                 : {deleted_plats + deleted_sans_kcal}\n"
            f"\n⚠ Les KnownIngredient mappés sur ces entrées ont leur ciqual_ref mis à NULL.\n"
            f"  Relancez 'Recalculer les macros' pour mettre à jour les recettes."
        ))

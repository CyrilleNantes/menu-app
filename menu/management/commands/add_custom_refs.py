"""
add_custom_refs — Injecte les références nutritionnelles personnalisées
(eau, sel, épices, aromates…) dans la table IngredientRef.

Ces entrées n'existent pas dans le référentiel ANSES Ciqual 2020 mais sont
présentes dans les recettes. Toutes les valeurs nutritionnelles sont fixées
à 0 (quantités utilisées négligeables ou ingrédient sans apport calorique).

Usage :
    python manage.py add_custom_refs
    python manage.py add_custom_refs --force   # recrée les entrées existantes
"""
import unicodedata
import re

from django.core.management.base import BaseCommand

from menu.models import IngredientRef


# (code, nom_fr, groupe)
CUSTOM_REFS = [
    ("CUST001", "Eau",                               "Eau / boissons"),
    ("CUST002", "Sel",                               "Condiments / épices"),
    ("CUST003", "Poivre",                            "Condiments / épices"),
    ("CUST004", "Herbes de Provence",                "Herbes aromatiques"),
    ("CUST005", "Basilic frais",                     "Herbes aromatiques"),
    ("CUST006", "Menthe fraîche",                    "Herbes aromatiques"),
    ("CUST007", "Sauge",                             "Herbes aromatiques"),
    ("CUST008", "Laurier",                           "Herbes aromatiques"),
    ("CUST009", "Bouquet garni",                     "Herbes aromatiques"),
    ("CUST010", "Coriandre",                         "Herbes aromatiques"),
    ("CUST011", "Cumin",                             "Condiments / épices"),
    ("CUST012", "Cannelle",                          "Condiments / épices"),
    ("CUST013", "Curry en poudre",                   "Condiments / épices"),
    ("CUST014", "Muscade",                           "Condiments / épices"),
    ("CUST015", "Gingembre",                         "Condiments / épices"),
    ("CUST016", "Ras el hanout",                     "Condiments / épices"),
    ("CUST017", "Épices mélangées",                  "Condiments / épices"),
    ("CUST018", "Vinaigrette",                       "Condiments / épices"),
    ("CUST019", "Sauce Worcestershire",              "Condiments / épices"),
    ("CUST020", "Sauce sucrée",                      "Condiments / épices"),
    ("CUST021", "Baies roses",                       "Condiments / épices"),
    ("CUST022", "Levure sèche",                      "Condiments / épices"),
    ("CUST023", "Radis roses",                       "Légumes"),
    ("CUST024", "Jus de cuisson",                    "Condiments / épices"),
    ("CUST025", "Mélange de légumes",                "Légumes"),
    ("CUST026", "Sauce confit d'oignon",             "Condiments / épices"),
    ("CUST027", "Céleri branche",                    "Légumes"),
    ("CUST028", "Mélange d'épices du Moyen-Orient",  "Condiments / épices"),
]


def _normalize(s: str) -> str:
    s = s.lower().strip()
    s = unicodedata.normalize("NFD", s)
    s = "".join(c for c in s if unicodedata.category(c) != "Mn")
    s = re.sub(r"[^\w\s]", " ", s)
    s = re.sub(r"\s+", " ", s).strip()
    return s


class Command(BaseCommand):
    help = "Ajoute les references Ciqual personnalisees (eau, sel, epices…) avec valeurs nutritionnelles a 0."

    def add_arguments(self, parser):
        parser.add_argument(
            "--force",
            action="store_true",
            help="Met a jour les entrees existantes (sinon elles sont ignorees).",
        )

    def handle(self, *args, **options):
        force   = options["force"]
        created = 0
        updated = 0
        skipped = 0

        for code, nom_fr, groupe in CUSTOM_REFS:
            nom_n = _normalize(nom_fr)
            defaults = dict(
                nom_fr=nom_fr,
                nom_normalise=nom_n,
                groupe=groupe,
                sous_groupe="Personnalise",
                kcal_100g=0.0,
                proteines_100g=0.0,
                glucides_100g=0.0,
                lipides_100g=0.0,
            )
            try:
                obj = IngredientRef.objects.get(ciqual_code=code)
                if force:
                    for k, v in defaults.items():
                        setattr(obj, k, v)
                    obj.save()
                    updated += 1
                    self.stdout.write(f"  MAJ  {code} — {nom_fr}")
                else:
                    skipped += 1
            except IngredientRef.DoesNotExist:
                IngredientRef.objects.create(ciqual_code=code, **defaults)
                created += 1
                self.stdout.write(f"  CREE {code} — {nom_fr}")

        self.stdout.write(
            f"\nTermine : {created} crees, {updated} mis a jour, {skipped} deja presents (--force pour forcer)."
        )

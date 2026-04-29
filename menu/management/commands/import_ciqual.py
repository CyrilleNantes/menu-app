"""
Management command: import_ciqual
==================================
Usage:
    python manage.py import_ciqual --file /path/to/Table_Ciqual_2020_FR_2020_07_07.xls

Importe la table Ciqual 2020 dans le modèle IngredientRef.
Opération idempotente : upsert basé sur ciqual_code.
Optimisé : bulk_create + bulk_update (3 requêtes au lieu de 3186).
"""

import unicodedata
import re

import xlrd
from django.core.management.base import BaseCommand, CommandError

from menu.models import IngredientRef


# ─── Helpers ────────────────────────────────────────────────────────────────

def normalize(s: str) -> str:
    """Normalise un nom d'ingrédient pour la recherche floue."""
    s = s.lower().strip()
    s = unicodedata.normalize('NFD', s)
    s = ''.join(c for c in s if unicodedata.category(c) != 'Mn')
    s = s.replace('œ', 'oe').replace('æ', 'ae')
    s = re.sub(r'[^\w\s]', ' ', s)
    s = re.sub(r'\s+', ' ', s).strip()
    return s


def parse_float(cell_value) -> float | None:
    s = str(cell_value).strip().replace(',', '.')
    if s in ('-', '', 'traces', 'tr.', 'nan', 'none'):
        return None
    try:
        return float(s)
    except ValueError:
        return None


GROUP_TO_SHOPPING = {
    'viandes, œufs, poissons et assimilés': 'viandes_poissons',
    'fruits, légumes, légumineuses et oléagineux': 'legumes_fruits',
    'produits laitiers et assimilés': 'cremerie',
    'produits céréaliers': 'epicerie',
    'aides culinaires et ingrédients divers': 'epicerie',
    'matières grasses': 'epicerie',
    'eaux et autres boissons': 'boissons',
    'produits sucrés': 'epicerie',
    'entrées et plats composés': 'epicerie',
}

# Poids par défaut pour les unités dénombrables (g par unité)
DEFAULT_WEIGHTS = {
    # Fruits & légumes
    'oignon': 80, 'echalote': 30, 'ail': 5,   # gousse
    'carotte': 100, 'courgette': 200, 'aubergine': 300,
    'tomate': 120, 'citron': 100, 'concombre': 300,
    'poivron': 150, 'navet': 150, 'poireau': 150,
    'avocat': 150,
    # Protéines
    'oeuf': 60, 'magret de canard': 350,
    # Condiments
    'bouquet garni': 10,
}


def guess_protein_type(nom: str, groupe: str) -> str | None:
    n = nom.lower()
    if any(x in n for x in ['boeuf', 'veau', 'agneau', 'entrecote', 'rumsteck', 'faux-filet',
                              'gite', 'paleron', 'hampe', 'joue', 'jarret', 'bourguignon']):
        return 'boeuf'
    if any(x in n for x in ['porc', 'lard', 'jambon', 'chorizo', 'saucisse', 'saucisson',
                              'coppa', 'guanciale', 'pancetta', 'andouille']):
        return 'porc'
    if any(x in n for x in ['poulet', 'dinde', 'pintade', 'canard', 'oie', 'volaille',
                              'lapin', 'caille', 'pigeon']):
        return 'volaille'
    if any(x in n for x in ['saumon', 'thon', 'cabillaud', 'sole', 'dorade', 'bar,', 'colin',
                              'crevette', 'moule', 'coquille', 'anchois', 'sardine', 'merlan',
                              'truite', 'rouget', 'poisson', 'fruits de mer']):
        return 'poisson'
    if any(x in n for x in ['oeuf', 'oeufs']):
        return 'oeufs'
    if any(x in n for x in ['lentille', 'haricot', 'pois chiche', 'feve', 'soja', 'tofu',
                              'edamame', 'flageolet', 'pois casse']):
        return 'legumineuses'
    if groupe == 'viandes, œufs, poissons et assimilés':
        return 'autre'
    return None


def guess_default_weight(nom: str) -> float | None:
    """Essaie de trouver un poids par défaut pour les aliments dénombrables."""
    n = normalize(nom).split(',')[0]
    for keyword, weight in DEFAULT_WEIGHTS.items():
        if keyword in n:
            return weight
    return None


# ─── Command ────────────────────────────────────────────────────────────────

BULK_FIELDS = [
    'nom_fr', 'nom_normalise', 'groupe', 'sous_groupe',
    'kcal_100g', 'proteines_100g', 'glucides_100g', 'lipides_100g',
    'protein_type', 'shopping_category', 'default_weight_g',
]


class Command(BaseCommand):
    help = 'Importe la table Ciqual 2020 dans IngredientRef'

    def add_arguments(self, parser):
        parser.add_argument(
            '--file',
            type=str,
            default='data/Table_Ciqual_2020_FR_2020_07_07.xls',
            help='Chemin vers le fichier XLS Ciqual'
        )
        parser.add_argument(
            '--dry-run',
            action='store_true',
            help='Affiche les données sans importer'
        )

    def handle(self, *args, **options):
        filepath = options['file']
        dry_run = options['dry_run']

        # ── 1. Lire le fichier XLS ───────────────────────────────────────────
        self.stdout.write(f'Ouverture de {filepath}…')
        self.stdout.flush()
        try:
            wb = xlrd.open_workbook(filepath)
        except FileNotFoundError:
            raise CommandError(f'Fichier introuvable : {filepath}')

        ws = wb.sheet_by_index(0)
        total_rows = ws.nrows - 1
        self.stdout.write(f'Ciqual : {total_rows} entrées à traiter…')
        self.stdout.flush()

        # ── 2. Parser toutes les lignes ──────────────────────────────────────
        rows_by_code: dict[str, dict] = {}
        skipped = 0

        for row in range(1, ws.nrows):
            code = str(ws.cell_value(row, 6)).replace('.0', '').strip()
            nom  = str(ws.cell_value(row, 7)).strip()
            grp  = str(ws.cell_value(row, 3)).strip()
            sgrp = str(ws.cell_value(row, 4)).strip()

            if not code or not nom:
                skipped += 1
                continue

            rows_by_code[code] = {
                'nom_fr':            nom,
                'nom_normalise':     normalize(nom),
                'groupe':            grp,
                'sous_groupe':       sgrp,
                'kcal_100g':         parse_float(ws.cell_value(row, 10)),
                'proteines_100g':    parse_float(ws.cell_value(row, 14)),
                'glucides_100g':     parse_float(ws.cell_value(row, 16)),
                'lipides_100g':      parse_float(ws.cell_value(row, 17)),
                'protein_type':      guess_protein_type(nom, grp),
                'shopping_category': GROUP_TO_SHOPPING.get(grp, 'epicerie'),
                'default_weight_g':  guess_default_weight(nom),
            }

        self.stdout.write(f'Parsé : {len(rows_by_code)} lignes valides, {skipped} ignorées.')
        self.stdout.flush()

        if dry_run:
            for code, data in list(rows_by_code.items())[:20]:
                self.stdout.write(
                    f"[DRY] {code} | {data['nom_fr'][:40]:40s} | "
                    f"{data['kcal_100g'] or '?':>6} kcal | {data['proteines_100g'] or '?':>5} g prot"
                )
            self.stdout.write(f'… (dry-run, {len(rows_by_code)} entrées au total)')
            return

        # ── 3. Récupérer les codes existants (1 requête) ────────────────────
        existing_qs = IngredientRef.objects.filter(ciqual_code__in=rows_by_code.keys())
        existing_map: dict[str, IngredientRef] = {obj.ciqual_code: obj for obj in existing_qs}
        self.stdout.write(f'En base : {len(existing_map)} existants.')
        self.stdout.flush()

        # ── 4. Séparer créations / mises à jour ─────────────────────────────
        to_create: list[IngredientRef] = []
        to_update: list[IngredientRef] = []

        for code, data in rows_by_code.items():
            if code in existing_map:
                obj = existing_map[code]
                for field, value in data.items():
                    setattr(obj, field, value)
                to_update.append(obj)
            else:
                to_create.append(IngredientRef(ciqual_code=code, **data))

        self.stdout.write(f'À créer : {len(to_create)}, à mettre à jour : {len(to_update)}')
        self.stdout.flush()

        # ── 5. bulk_create + bulk_update (2 requêtes) ───────────────────────
        CHUNK = 500
        created_count = 0
        for i in range(0, len(to_create), CHUNK):
            chunk = to_create[i:i + CHUNK]
            IngredientRef.objects.bulk_create(chunk, ignore_conflicts=False)
            created_count += len(chunk)
            self.stdout.write(f'  Créés : {created_count}/{len(to_create)}…')
            self.stdout.flush()

        updated_count = 0
        for i in range(0, len(to_update), CHUNK):
            chunk = to_update[i:i + CHUNK]
            IngredientRef.objects.bulk_update(chunk, BULK_FIELDS)
            updated_count += len(chunk)
            self.stdout.write(f'  Mis à jour : {updated_count}/{len(to_update)}…')
            self.stdout.flush()

        self.stdout.write(self.style.SUCCESS(
            f'Import termine : {created_count} crees, {updated_count} mis a jour, {skipped} ignores'
        ))

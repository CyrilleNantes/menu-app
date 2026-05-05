"""
Management command: import_ciqual
==================================
Usage:
    python manage.py import_ciqual
    python manage.py import_ciqual --file data/CIRQUAL_MENU_APP.xls
    python manage.py import_ciqual --wipe          # vide la table avant import
    python manage.py import_ciqual --dry-run

Colonnes importées depuis le fichier Ciqual :
  col 3  : groupe alimentaire
  col 4  : sous-groupe
  col 6  : code Ciqual
  col 7  : nom français
  col 10 : kcal/100g
  col 14 : protéines/100g
  col 16 : glucides/100g
  col 17 : lipides/100g
  col 18 : sucres/100g
  col 26 : fibres/100g
  col 31 : AG saturés/100g
  col 49 : sel/100g
"""

import unicodedata
import re

import xlrd
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction

from menu.models import IngredientRef


# ─── Helpers ────────────────────────────────────────────────────────────────

def normalize(s: str) -> str:
    s = s.lower().strip()
    s = unicodedata.normalize('NFD', s)
    s = ''.join(c for c in s if unicodedata.category(c) != 'Mn')
    s = s.replace('œ', 'oe').replace('æ', 'ae')
    s = re.sub(r'[^\w\s]', ' ', s)
    return re.sub(r'\s+', ' ', s).strip()


def parse_float(cell_value) -> float | None:
    """Convertit une valeur cellule en float.
    Gère : '-', 'traces', '< 0,5', '0,16', etc.
    Les valeurs '< X' sont traitées comme 0 (quantité négligeable).
    """
    s = str(cell_value).strip()
    if s in ('-', '', 'traces', 'tr.', 'nan', 'none', 'None'):
        return None
    s = s.replace(',', '.')
    # Valeur "< X" → 0 (trace)
    if s.startswith('<'):
        return 0.0
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

DEFAULT_WEIGHTS = {
    'oignon': 80, 'echalote': 30, 'ail': 5,
    'carotte': 100, 'courgette': 200, 'aubergine': 300,
    'tomate': 120, 'citron': 100, 'concombre': 300,
    'poivron': 150, 'navet': 150, 'poireau': 150,
    'avocat': 150,
    'oeuf': 60, 'magret de canard': 350,
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
    n = normalize(nom).split(',')[0]
    for keyword, weight in DEFAULT_WEIGHTS.items():
        if keyword in n:
            return weight
    return None


# ─── Command ────────────────────────────────────────────────────────────────

BULK_FIELDS = [
    'nom_fr', 'nom_normalise', 'groupe', 'sous_groupe',
    'kcal_100g', 'proteines_100g', 'glucides_100g', 'lipides_100g',
    'sucres_100g', 'fibres_100g', 'ag_satures_100g', 'sel_100g',
    'protein_type', 'shopping_category', 'default_weight_g',
]


class Command(BaseCommand):
    help = 'Importe la table Ciqual dans IngredientRef'

    def add_arguments(self, parser):
        parser.add_argument(
            '--file', type=str,
            default='data/CIRQUAL_MENU_APP.xls',
            help='Chemin vers le fichier XLS Ciqual (défaut: data/CIRQUAL_MENU_APP.xls)',
        )
        parser.add_argument('--dry-run', action='store_true')
        parser.add_argument(
            '--wipe', action='store_true',
            help='Vide la table IngredientRef avant import (repart de zéro)',
        )

    @transaction.atomic
    def handle(self, *args, **options):
        filepath = options['file']
        dry_run  = options['dry_run']
        wipe     = options['wipe']

        # ── 1. Lire le fichier XLS ───────────────────────────────────────────
        self.stdout.write(f'Ouverture de {filepath}…')
        try:
            wb = xlrd.open_workbook(filepath)
        except FileNotFoundError:
            raise CommandError(f'Fichier introuvable : {filepath}')

        ws = wb.sheet_by_index(0)
        self.stdout.write(f'Ciqual : {ws.nrows - 1} entrées à traiter…')

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
                'nom_fr':          nom,
                'nom_normalise':   normalize(nom),
                'groupe':          grp,
                'sous_groupe':     sgrp,
                'kcal_100g':       parse_float(ws.cell_value(row, 10)),
                'proteines_100g':  parse_float(ws.cell_value(row, 14)),
                'glucides_100g':   parse_float(ws.cell_value(row, 16)),
                'lipides_100g':    parse_float(ws.cell_value(row, 17)),
                'sucres_100g':     parse_float(ws.cell_value(row, 18)),
                'fibres_100g':     parse_float(ws.cell_value(row, 26)),
                'ag_satures_100g': parse_float(ws.cell_value(row, 31)),
                'sel_100g':        parse_float(ws.cell_value(row, 49)),
                'protein_type':    guess_protein_type(nom, grp),
                'shopping_category': GROUP_TO_SHOPPING.get(grp, 'epicerie'),
                'default_weight_g':  guess_default_weight(nom),
            }

        self.stdout.write(f'Parsé : {len(rows_by_code)} lignes valides, {skipped} ignorées.')

        if dry_run:
            for code, data in list(rows_by_code.items())[:20]:
                self.stdout.write(
                    f"[DRY] {code} | {data['nom_fr'][:40]:40s} | "
                    f"{data['kcal_100g'] or '?':>6} kcal | "
                    f"fibres={data['fibres_100g']} | sel={data['sel_100g']}"
                )
            self.stdout.write(f'… (dry-run, {len(rows_by_code)} entrées au total)')
            return

        # ── 3. Vider la table si demandé ─────────────────────────────────────
        if wipe:
            deleted, _ = IngredientRef.objects.all().delete()
            self.stdout.write(f'Table vidée : {deleted} entrées supprimées.')

        # ── 4. Upsert ────────────────────────────────────────────────────────
        existing_qs  = IngredientRef.objects.filter(ciqual_code__in=rows_by_code.keys())
        existing_map = {obj.ciqual_code: obj for obj in existing_qs}
        self.stdout.write(f'En base : {len(existing_map)} existants.')

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

        CHUNK = 500
        created_count = 0
        for i in range(0, len(to_create), CHUNK):
            IngredientRef.objects.bulk_create(to_create[i:i + CHUNK])
            created_count += len(to_create[i:i + CHUNK])
            self.stdout.write(f'  Créés : {created_count}/{len(to_create)}…')

        updated_count = 0
        for i in range(0, len(to_update), CHUNK):
            IngredientRef.objects.bulk_update(to_update[i:i + CHUNK], BULK_FIELDS)
            updated_count += len(to_update[i:i + CHUNK])
            self.stdout.write(f'  Mis à jour : {updated_count}/{len(to_update)}…')

        self.stdout.write(self.style.SUCCESS(
            f'Import terminé : {created_count} créés, {updated_count} mis à jour, {skipped} ignorés.'
        ))

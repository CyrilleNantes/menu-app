"""
Management command: match_ingredients
======================================
Usage:
    python manage.py match_ingredients
    python manage.py match_ingredients --dry-run
    python manage.py match_ingredients --export-unmatched unmatched.csv

Associe automatiquement chaque Ingredient à un IngredientRef Ciqual
en utilisant :
  1. La table de synonymes manuels (SYNONYMS ci-dessous)
  2. La correspondance exacte sur le nom normalisé
  3. La correspondance par premier mot (fallback)

Les ingrédients non matchés sont listés et exportables en CSV.
"""

import csv
import re
import sys
import unicodedata

from django.core.management.base import BaseCommand

from menu.models import Ingredient, IngredientRef


# ─── Table de synonymes ─────────────────────────────────────────────────────
#
# Format : "nom_normalisé_de_mon_ingredient" → "code_ciqual"
# None = ingrédient non calculable (eau, sel, épices sans valeur nutritionnelle)
#
SYNONYMS = {
    # ── Œufs ──
    'oeuf':                       '22000',
    'oeufs':                      '22000',
    'oeuf entier':                '22000',
    'jaune d oeuf':               '22002',
    'jaunes d oeufs':             '22002',
    'blanc d oeuf':               '22001',
    'blancs d oeufs':             '22001',

    # ── Bœuf ──
    'boeuf':                      '6255',
    'boeuf hache':                '6255',
    'steak hache':                '6255',
    'steaks haches':              '6255',
    'steaks de boeuf':            '6110',
    'boeuf a braiser':            '6101',
    'boeuf paleron':              '6141',
    'entrecote':                  '6100',
    'entrecotes':                 '6100',
    'pave de boeuf marine':       '6110',
    'boeuf rumsteck tende de tranche faux filet': '6110',
    'boeuf filet ou rumsteck':    '6110',
    'boeuf rumsteck ou equivalent': '6110',

    # ── Porc / charcuterie ──
    'porc':                       '28101',
    'ribs travers de porc':       '28101',
    'tranches de carre de porc':  '28105',
    'lardons':                    '28501',
    'lardons fumes':              '28720',
    'lardon nature':              '28501',
    'des de chorizo':             '30315',   # Chorizo
    'saucisses de montbelliard ou toulouse': '30011',
    'saucisses de montbeliard ou toulouse': '30011',  # variante sans double L
    'saucisse de toulouse':           '30011',
    'saucisses fumees':           '30105',
    'jambon blanc':               '28900',
    'jambon':                     '28900',
    'tranches de jambon':         '28900',
    'tranches de jambon cru':     '28804',
    'guanciale':                  '28501',

    # ── Veau ──
    'veau':                       '6520',
    'escalopes de veau':          '6520',
    'escalopes poulet ou veau':   '6520',
    'jarret de veau':             '6550',
    'veau hache':                 '6536',

    # ── Volaille ──
    'poulet':                     '36018',
    'cuisses de poulet':          '36004',
    'filets de poulet':           '36018',
    'hauts de cuisse desosse':    '36004',
    'escalopes de dinde':         '36020',
    'paupiettes de dinde':        '36020',
    'dinde':                      '36020',
    'magret de canard':           '36300',
    'cuisses de confit de canard':'36300',
    'filets de canette':          '36900',
    'gesiers confits':            '36900',

    # ── Poisson / fruits de mer ──
    'saumon':                     '25996',
    'paves de saumon':            '26037',
    'saumon fume':                '26037',
    'emiette de saumon fume aux baies roses': '26037',
    'filets de poisson':          '25996',
    'crevettes':                  '26090',

    # ── Légumes ──
    'ail':                        '11000',
    'gousse d ail':               '11000',
    'gousses d ail':              '11000',
    'ail en poudre':              '11001',
    'echalote':                   '20012',
    'echalotes':                  '20012',
    'oignon':                     '20034',
    'oignons':                    '20034',
    'oignon jaune':               '20034',
    'oignon rouge':               '20036',
    'oignons rouges':             '20036',
    'oignon au vinaigre':         '20034',
    'oignons au vinaigre':        '20034',
    'oignons nouveaux ciboule':   '20035',
    'poireau':                    '20040',
    'poireaux':                   '20040',
    'blancs de poireaux':         '20040',
    'poireaux blanc vert clair':  '20040',
    'carotte':                    '20009',
    'carottes':                   '20009',
    'courgette':                  '20020',
    'courgettes':                 '20020',
    'aubergine':                  '20005',
    'aubergines':                 '20005',
    'poivron':                    '20041',
    'poivrons':                   '20041',
    'poivrons grilles':           '20041',
    'tomate':                     '20047',
    'tomates':                    '20047',
    'tomates mures':              '20047',
    'tomates cerises':            '20049',
    'tomates concassees':         '20049',
    'tomates pelees':             '20049',
    'tomates semi sechees':       '20049',
    'tomates ou crudites':        '20047',
    'pulpe de tomate':            '20049',
    'passata':                    '20049',
    'concentre de tomate':        '20290',
    'concentre de tomates':       '20290',
    'concombre':                  '20210',   # Concombre, pulpe, cru
    'concombres':                 '20210',
    'cornichons':                 '20210',
    'chou fleur':                 '20016',   # Chou-fleur, cru
    'chou blanc':                 '20116',
    'chou rouge':                 '20014',
    'chou':                       '20116',   # chou blanc par défaut
    'navet':                      '20064',
    'navets':                     '20064',
    'champignon':                 '20008',
    'champignons':                '20008',
    'champignons de paris':       '20008',
    'choux de bruxelles':         '20013',
    'epinard':                    '20015',
    'epinards':                   '20015',
    'pomme de terre':             '4008',
    'pommes de terre':            '4008',
    'pommes de terre jaunes':     '4008',
    'pommes de terre roses':      '4008',
    'pommes de terre type charlotte': '4008',
    'pommes de terre type ferme': '4008',
    'pommes de terre grenaille':  '4008',
    'grenailles':                 '4008',
    'pommes de terre deja cuites':'4003',
    'citron':                     '20055',
    'citrons':                    '20055',
    'jus de citron':              '20056',
    'citrons jus':                '20056',
    'avocat':                     '20003',
    'avocats':                    '20003',
    'citronnelle':                '11060',
    'ciboulette':                 '11003',   # Ciboule ou Ciboulette, fraîche
    'ciboulette ou persil':       '11003',
    'persil':                     '11014',   # Persil, frais
    'persil plat':                '11014',
    'aneth':                      '11093',   # Aneth, frais
    'aneth ou ciboulette':        '11093',
    'thym':                       '11070',
    'branche de thym':            '11070',
    'feuilles de laurier':        None,      # non calculable (quantité trop faible)
    'feuilles de sauge':          None,
    'bouquet garni thym laurier': None,
    'mini bouquet garni':         None,
    'cube bouquet garni':         None,
    'pruneaux avec noyau':        '20068',
    'pruneaux':                   '20068',
    'prunes':                     '20067',
    'raisins secs':               '20072',
    'amandes effilees':           '15000',   # Amande (avec peau)
    'amandes':                    '15000',
    'graines de sesame':          '15010',   # Sésame, graine
    'gomasio':                    '15010',
    'baies roses':                None,      # quantité négligeable
    'lentilles':                  '20587',
    'lentilles vertes':           '20587',

    # ── Salades & légumes supplémentaires ──
    'salade':                     '20031',   # Laitue, crue
    'salade verte':               '20031',
    'laitue':                     '20031',
    'endive':                     '20026',
    'endives':                    '20026',
    'haricots verts':             '20061',   # Haricot vert, cru
    'haricot vert':               '20061',
    'haricots verts surgeles':    '20061',
    'haricots verts frais':       '20061',
    'haricots rouges':            '20503',   # Haricot rouge, bouilli/cuit
    'haricot rouge':              '20503',
    'haricots blancs':            '20501',   # Haricot blanc, bouilli/cuit
    'pois chiches':               '20541',   # Pois chiche, appertisé
    'pois casse':                 '20506',   # Pois cassé, bouilli/cuit
    'epinards':                   '20015',
    'epinard':                    '20015',

    # ── Produits laitiers ──
    'beurre':                     '16400',
    'creme fraiche':              '19410',
    'creme fraiche epaisse':      '19410',
    'creme liquide':              '19415',
    'creme':                      '19410',
    'mascarpone':                 '12060',
    'gruyere':                    '12113',
    'gruyere rape':               '12113',
    'fromage rape':               '12113',   # Gruyère IGP France (par défaut)
    'comte':                      '12110',
    'emmental':                   '12100',
    'parmesan':                   '12120',
    'parmesan rape':              '12120',
    'pecorino romano dop':        '12120',
    'raclette fromage':           '12749',
    'fromage a raclette':         '12749',
    'cheddar rape ou fromage a burger': '12040',
    'munster aop':                '12039',
    'munster':                    '12039',
    'camembert':                  '12001',   # Camembert, sans précision
    'fromage':                    '12320',
    'yaourt nature':              '19860',   # Yaourt à la grecque, nature
    'yaourt':                     '19860',
    'yaourts nature':             '19860',

    # ── Céréales / pâtes / riz ──
    'riz':                        '9100',
    'riz blanc':                  '9100',
    'riz blanc cru':              '9100',
    'riz long basmati ou equivalent': '9100',
    'riz long etuve':             '9104',
    'riz arborio ou carnaroli':   '9103',
    'riz casse':                  '9100',
    'spaghetti':                  '9811',
    'linguine':                   '9811',
    'linguine fraiches':          '9816',
    'farfalle':                   '9811',
    'conchiglie':                 '9811',
    'fettuccine':                 '9811',
    'tagliatelle':                '9816',
    'macaroni':                   '9811',
    'pates':                      '9811',
    'pates alimentaires':         '9811',
    'couscous':                   '9200',
    'graines de couscous':        '9200',
    'semoule':                    '9610',   # Semoule de blé dur, crue
    'semoule moyenne':            '9610',
    'semoule fine':               '9610',
    'crozets':                    '9811',
    'crozets au sarrasin':        '9871',
    'galettes de sarrasin':       '9871',
    'feuilles de brick':          '25557',   # Brick à l'oeuf, fait maison
    'chapelure fine':             '7500',
    'chapelure':                  '7500',
    'sachets de puree mousseline':'4020',
    'pain':                       '7200',
    'tranches de pain':           '7200',
    'pain de mie':                '7111',   # Pain de mie
    'baguette ou pain rustique':  '7001',   # Pain, baguette, courante
    'farine':                     '9436',   # Farine T55
    'farine de ble':              '9436',
    'farine de ble t55':          '9436',
    'farine de ble t45':          '9440',
    'gnocchi':                    '26264',  # Gnocchi à la pomme de terre, cru

    # ── Viandes supplémentaires ──
    'viande hachee':              '6260',   # Haché à base de boeuf
    'viande hachee de boeuf':     '6255',
    'chair a saucisse':           '30050',  # Chair à saucisse, crue
    'jambon italien':             '28800',  # Jambon cru

    # ── Matières grasses / condiments ──
    'huile d olive':              '17270',
    'huile olive':                '17270',
    'vinaigre':                   '11220',
    'vinaigre de vin':            '11220',
    'vinaigrette':                '11230',
    'nuoc mam':                   '11104',
    'sauce nuoc mam':             '11104',
    'sauce soja':                 '11104',
    'miel ou sucre':              '31100',
    'miel':                       '31100',
    'vin blanc':                  '5215',

    # ── Bouillons / épices ──
    'bouillon':                   '25948',
    'bouillon de volaille':       '25948',
    'bouillon de boeuf':          '25948',
    'cube bouillon':              '25948',
    'cube de bouillon':           '25948',
    'cube de bouillon de volaille': '25948',
    'cube kubor':                 '25948',
    'bouillon de legumes':        '25948',
    'paprika fume en poudre':     '11040',
    'paprika':                    '11040',
    'ras el hanout':              None,
    'epices italiennes':          None,
    'epices mexicaines':          None,
    'epices calabraises':         None,
    'epices ramen':               None,

    # ── Nouveaux — protéines / viandes ──
    'poitrine de porc':           '28105',  # Porc, côte de porc
    'filets de saumon':           '26037',
    'saumon frais':               '25996',
    'thon':                       '26039',  # Thon, au naturel, appertisé
    'thon egoutte':               '26039',
    'thon en boite':              '26039',
    'poulet entier':              '36018',

    # ── Nouveaux — féculents / divers ──
    'boulgour':                   '9690',   # Boulgour de blé, cru
    'boulgour fin':               '9690',
    'nouilles ramen':             '9811',
    'noix':                       '15005',  # Noix, séchée, cerneaux
    'noix de cajou':              '15055',  # Noix de cajou, grillée à sec
    'lait de coco':               '18041',  # Lait de coco ou Crème de coco
    'sucre':                      '31016',  # Sucre blanc
    'sucre en poudre':            '31016',
    'coriandre':                  None,     # aromate — quantité négligeable
    'huile':                      '17270',  # huile sans précision → huile d'olive
    'ketchup':                    '11073',  # Ketchup allégé en sucres
    'moutarde':                   '11101',  # Sauce béchamel (approximation) → None?
    'concentre de tomates':       '20290',
    'vinaigrette':                None,     # sauce préparée — non calculable directement
    'lait':                       '19042',  # Lait demi-écrémé, pasteurisé
    'lait entier':                '19024',
    'lait demi ecreme':           '19042',
    'mais en conserve':           '20066',  # Maïs doux, appertisé
    'mais doux':                  '20066',
    'mais':                       '20066',
    'chevre':                     '12830',  # Chabichou (fromage de chèvre)
    'fromage de chevre':          '12830',
    'buche de chevre':            '12830',
    'chevre frais':               '12847',
    'cacahuetes':                 '15037',  # Cacahuète, grillée à sec, salée
    'cacahuetes grillees':        '15037',
    'pate d arachide':            None,     # non calculable (beurre de cacahuète)
    'pate feuilletee':            None,     # pâte préparée — non calculable
    'pate a pizza':               None,
    'ravioli':                    '9811',   # approximation pâtes
    'raviolis':                   '9811',
    'mozzarella':                 '19590',  # Mozzarella au lait de vache
    'merguez':                    '30156',  # Merguez, boeuf et mouton, crue
    'patate douce':               '4101',   # Patate douce, crue
    'pomme':                      '13050',  # Pomme, pulpe, crue
    'pommes':                     '13050',
    'celeri':                     None,     # très faible valeur nutritionnelle
    'branches de celeri':         None,
    'branche de celeri':          None,
    'manioc':                     '54031',  # Manioc, racine crue
    'petits pains':               '7001',   # Pain, baguette (approximation)
    'sucrine':                    '20031',  # Laitue, crue (salade sucrine)
    'crottin de chevre':          '12834',  # Crottin de Chavignol
    'cantal':                     '12722',  # Cantal entre-deux
    'poitrine fumee':             '28858',  # Pancetta ou Poitrine roulée sèche
    'mayonnaise':                 '11054',  # Mayonnaise 70% MG
    'radis':                      None,     # faible valeur nutritionnelle
    'radis roses':                None,

    # ── Non calculables (eau, sel, aromates discrets) ──
    'eau':                        None,
    'eau cocotte':                None,
    'eau chaude':                 None,
    'eau ou bouillon':            None,
    'eau tiede':                  None,
    'sel':                        None,
    'sel et poivre':              None,
    'sel fin':                    None,
    'sel poivre':                 None,
    'poivre':                     None,
    'poivre noir':                None,
    'poivre du moulin':           None,
    'muscade':                    None,
    'noix de muscade':            None,
    'jus de cuisson du porc':     None,
    'herbes de provence':         None,
    'herbes':                     None,
    'herbes fraiches':            None,
    'feuille de laurier':         None,
    'melange nordique':           None,
    'melange de legumes':         None,
    'legumes':                    None,
    'sauce sucree':               None,
    'nems ou rouleaux imperiaux': None,
    'bouillon ou eau':            None,
    'menthe':                     None,
    'basilic':                    None,
    'levure seche':               None,
    'levure de boulanger':        None,
    'matiere grasse':             None,
    'puree de gingembre':         None,
    'sauce worcestershire':       None,
    'sauce confit d oignon':      None,
    'pate brisee':                None,
    'melange marocain':           None,
    'melange epices':             None,
    'melange d epices du moyen orient': None,
    'spatzle frais':              '9811',   # approximation pâtes fraîches
    'fond de veau':               '25948',  # approximation bouillon
    'foie gras':                  '8331',   # Foie gras, canard, bloc (aliment moyen)
    'curry':                      None,
    'cumin':                      None,
    'gingembre':                  None,
    'cannelle':                   None,
    'laurier':                    None,
    'sauge':                      None,
}


# ─── Normalisation ──────────────────────────────────────────────────────────

def normalize(s: str) -> str:
    s = s.lower().strip()
    s = unicodedata.normalize('NFD', s)
    s = ''.join(c for c in s if unicodedata.category(c) != 'Mn')
    s = s.replace('œ', 'oe').replace('æ', 'ae')
    s = re.sub(r'[^\w\s]', ' ', s)
    s = re.sub(r'\s+', ' ', s).strip()
    return s


# ─── Command ────────────────────────────────────────────────────────────────

class Command(BaseCommand):
    help = 'Associe les Ingredient existants aux IngredientRef Ciqual'

    def add_arguments(self, parser):
        parser.add_argument('--dry-run', action='store_true')
        parser.add_argument('--export-unmatched', type=str, default='',
                            help='Exporte les non-matchés dans ce fichier CSV')
        parser.add_argument('--recipe-id', type=int, default=None,
                            help='Limiter à une seule recette (debug)')

    def handle(self, *args, **options):
        dry_run          = options['dry_run']
        export_unmatched = options['export_unmatched']
        recipe_id        = options['recipe_id']

        # Charger tous les IngredientRef en mémoire pour la recherche
        refs = list(IngredientRef.objects.all())
        if not refs:
            self.stderr.write(self.style.ERROR(
                'Aucun IngredientRef en base. Lance d\'abord : python manage.py import_ciqual'
            ))
            return

        ref_by_code = {r.ciqual_code: r for r in refs}
        ref_by_norm = {r.nom_normalise: r for r in refs}

        # Construire un index "premier mot → refs" pour le fallback
        ref_by_first_word: dict[str, list[IngredientRef]] = {}
        for r in refs:
            first = r.nom_normalise.split(',')[0].split(' ')[0]
            ref_by_first_word.setdefault(first, []).append(r)

        qs = Ingredient.objects.select_related('ciqual_ref')
        if recipe_id:
            qs = qs.filter(recipe_id=recipe_id)

        matched = updated = skipped = 0
        unmatched_list = []

        for ingr in qs:
            name_n = normalize(ingr.name)

            # ── Étape 1 : synonymes manuels (exact ou variante courte) ────
            synonym_found = False
            code = None

            if name_n in SYNONYMS:
                code = SYNONYMS[name_n]
                synonym_found = True
            else:
                # Variantes courtes : "boeuf (paleron)" → "boeuf", etc.
                for length in [3, 2, 1]:
                    short = ' '.join(name_n.split()[:length])
                    if short in SYNONYMS:
                        code = SYNONYMS[short]
                        synonym_found = True
                        break

            if synonym_found:
                if code is None:
                    # Ingrédient non calculable — on ne cherche pas plus loin
                    if ingr.ciqual_ref is not None and not dry_run:
                        ingr.ciqual_ref = None
                        ingr.save(update_fields=['ciqual_ref'])
                    skipped += 1
                    continue

                ref = ref_by_code.get(code)
                if ref:
                    if ingr.ciqual_ref != ref:
                        if not dry_run:
                            ingr.ciqual_ref = ref
                            ingr.save(update_fields=['ciqual_ref'])
                        updated += 1
                    matched += 1
                    continue

            # ── Étape 2 : correspondance exacte sur nom normalisé ─────────
            ref = ref_by_norm.get(name_n)
            if ref:
                if ingr.ciqual_ref != ref:
                    if not dry_run:
                        ingr.ciqual_ref = ref
                        ingr.save(update_fields=['ciqual_ref'])
                    updated += 1
                matched += 1
                continue

            # ── Étape 3 : fallback premier mot ───────────────────────────
            first_word = name_n.split(' ')[0]
            candidates = ref_by_first_word.get(first_word, [])
            if len(candidates) == 1:
                ref = candidates[0]
                if ingr.ciqual_ref != ref:
                    if not dry_run:
                        ingr.ciqual_ref = ref
                        ingr.save(update_fields=['ciqual_ref'])
                    updated += 1
                matched += 1
                continue

            # ── Pas de match ──────────────────────────────────────────────
            unmatched_list.append({
                'ingredient_pk':  ingr.pk,
                'recipe_id':      ingr.recipe_id,
                'name':           ingr.name,
                'name_normalise': name_n,
                'unit':           ingr.unit or '',
                'quantity':       ingr.quantity or '',
            })

        total = qs.count()
        self.stdout.write(self.style.SUCCESS(
            f'Resultat : {matched} matches, {updated} mis a jour, '
            f'{skipped} non calculables, {len(unmatched_list)} non matches / {total} total'
        ))
        self.stdout.write(
            f'   Couverture : {(matched/total*100):.1f}%'
        )

        if unmatched_list:
            self.stdout.write(f'\nNon matches ({len(unmatched_list)}) :')
            for u in unmatched_list[:30]:
                self.stdout.write(f'   [{u["ingredient_pk"]}] {u["name"]}')
            if len(unmatched_list) > 30:
                self.stdout.write(f'   ... et {len(unmatched_list)-30} autres')

        if export_unmatched and unmatched_list:
            with open(export_unmatched, 'w', newline='', encoding='utf-8') as f:
                writer = csv.DictWriter(f, fieldnames=list(unmatched_list[0].keys()))
                writer.writeheader()
                writer.writerows(unmatched_list)
            self.stdout.write(f'Non-matches exportes : {export_unmatched}')

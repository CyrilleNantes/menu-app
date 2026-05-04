# Spécifications Fonctionnelles — Menu Familial

> Document vivant — mis à jour par l'IA après chaque implémentation validée.
> Version courante : **v4.0** — affichée dans le footer de l'application.
> Dernière mise à jour : 2026-05-03

---

## 1. Contexte, Objectifs et Limites

### 1.1 Objectif principal

Permettre à des familles de planifier leurs menus hebdomadaires, gérer un catalogue de recettes communautaire, générer automatiquement leurs listes de courses, et synchroniser le tout avec Google Calendar et Google Tasks.

### 1.2 Périmètre inclus

- Gestion des familles et invitation des membres
- Catalogue de recettes partagé (communauté globale)
- Fiche recette enrichie : ingrédients groupés, étapes avec timers, notes de chef, sections libres
- Référentiel nutritionnel local ANSES Ciqual 2020 (3185 ingrédients, calcul hors-ligne)
- Système de notation par étoiles (1–5) avec historique par utilisateur
- Propositions de repas par les Convives
- Planning hebdomadaire par famille (période paramétrable)
- Gestion des repas avec restes
- Génération automatique de la liste de courses
- Mode Cuisine mobile (cochage ingrédients/étapes, timers)
- Export vers Google Calendar (menus) et Google Tasks (courses)
- Gamification : rangs progressifs pour Cuisiniers et Convives
- Gestion légère des allergies/régimes par profil utilisateur
- PWA installable sur mobile (service worker, cache offline)
- Algorithme de suggestions de menu (rotation, préférences famille, variété protéines, saisonnalité, équilibre nutritionnel)
- Cadre nutritionnel de référence PNNS (configurable, indicatif — pas médical)
- Dashboard nutritionnel individuel par utilisateur (portions personnalisées via `portions_factor`)
- Alertes équilibre non bloquantes dans la vue planning
- Galerie photos par recette (upload par tout utilisateur connecté)

### 1.3 Hors périmètre (Anti-Scope)

> ⚠️ CRITIQUE — L'IA ne doit jamais implémenter ce qui suit sans accord explicite.

- Ne PAS utiliser React, Vue ou tout framework JS — vanilla JS uniquement
- Ne PAS utiliser Supabase — Railway PostgreSQL uniquement
- Ne PAS utiliser SQLite — PostgreSQL en dev comme en prod
- Ne PAS exposer d'API REST publique (pas de DRF)
- Ne PAS implémenter Docker
- Ne PAS ajouter de système de messagerie entre utilisateurs
- Ne PAS implémenter de notifications push — email uniquement, implémentation ultérieure
- Ne PAS gérer des allergies avec un moteur de règles complexe — tags simples uniquement
- Ne PAS afficher de recommandations médicales — les données nutritionnelles sont des repères indicatifs PNNS uniquement
- Ne PAS suggérer d'alternatives à la stack sans demande explicite

### 1.4 Vue d'ensemble fonctionnelle (User Stories)

| En tant que... | Je veux... | Afin de... |
|----------------|------------|------------|
| Chef Étoilé | Gérer les utilisateurs et familles | Administrer la plateforme |
| Cuisinier | Créer des recettes enrichies | Constituer le catalogue commun |
| Cuisinier | Planifier le menu de la semaine | Organiser les repas de ma famille |
| Cuisinier | Générer la liste de courses | Préparer mes achats automatiquement |
| Cuisinier | Exporter vers Google Calendar / Tasks | Intégrer mon flux existant |
| Convive | Consulter les recettes et menus | Savoir ce qu'on mange |
| Convive | Noter et commenter les recettes | Partager mes préférences |
| Convive | Proposer des repas | Participer à la planification |
| Tout utilisateur | Utiliser l'app en cuisine sur mobile | Suivre les étapes avec les mains occupées |

**Interactions entre fonctionnalités** :
Le Cuisinier crée des recettes (3), les ajoute à un menu hebdomadaire (5), valide le menu (5.6), puis génère la liste de courses (6) et exporte vers Google (7). Les Convives notent les recettes (3.3) et proposent des repas (5.4) que le Cuisinier consulte lors de la composition du menu.

---

## 2. Acteurs et Rôles

| Acteur | Description | Accès |
|--------|-------------|-------|
| Chef Étoilé | Administrateur global de la plateforme | CRUD complet, gestion utilisateurs et familles |
| Cuisinier | Membre d'une famille avec droits de gestion | Recettes, planning, courses, exports Google |
| Convive | Membre d'une famille en lecture + participation | Consultation, notation, propositions |
| Administrateur Django | Gestion technique via `/admin/` | CRUD complet + suppressions physiques |

**Authentification** : Django auth + `django-allauth` (login email/password + Google OAuth).
Chaque utilisateur appartient à **une seule famille**. Un Cuisinier crée sa famille et invite les membres par email ou lien d'invitation.

**Progression (gamification)** : Le rang de chaque utilisateur est calculé dynamiquement selon ses contributions. Il n'y a pas de champ rang — c'est une propriété calculée sur le modèle.

**Rangs Cuisinier** (basés sur recettes ajoutées, complexité, diversité des cuisines) :

| Rang | Nom |
|------|-----|
| 1 | Commis |
| 2 | Cuisinier |
| 3 | Chef de Partie |
| 4 | Sous-Chef |
| 5 | Chef Exécutif |

**Rangs Convive** (basés sur avis donnés, commentaires, propositions) :

| Rang | Nom |
|------|-----|
| 1 | Convive |
| 2 | Gourmet |
| 3 | Épicurien |
| 4 | Critique |
| 5 | Guide Michelin |

---

## 3. Services externes

### 3.1 Services utilisés

| Service | Usage | Variable d'env | Fichier `integrations/` |
|---------|-------|----------------|--------------------------|
| Ciqual 2020 (local) | Référentiel nutritionnel ingrédients | *(aucune clé — table locale PostgreSQL)* | *(pas d'intégration externe)* |
| Cloudinary | Stockage des photos (original brut) + optimisation à l'affichage (`f_auto,q_auto,w_X,c_limit` via filtre template `cloudinary_img`) | `CLOUDINARY_URL` | `integrations/cloudinary.py` |
| Google Calendar | Export des menus planifiés | `GOOGLE_CLIENT_ID`, `GOOGLE_CLIENT_SECRET` | `integrations/google_calendar.py` |
| Google Tasks | Export des listes de courses | `GOOGLE_CLIENT_ID`, `GOOGLE_CLIENT_SECRET` | `integrations/google_tasks.py` |

> Google Calendar et Google Tasks partagent les mêmes credentials OAuth Google.

### 3.2 Flux OAuth2 — Google Calendar & Tasks

| Étape | Description |
|-------|-------------|
| 1. Autorisation | L'utilisateur clique "Connecter Google" → redirect vers Google OAuth avec scopes Calendar + Tasks |
| 2. Callback | Google redirige vers `/google/callback/` avec un code temporaire |
| 3. Échange | Le code est échangé contre `access_token` + `refresh_token` |
| 4. Stockage | Les tokens sont stockés dans le modèle `TokenOAuth` (voir section 4.1) |
| 5. Rafraîchissement | Avant chaque appel API, vérifier `expires_at` et renouveler si nécessaire |

**URL de callback** : `/google/callback/` → `menu:google_callback`

**Scopes requis** :
- `https://www.googleapis.com/auth/calendar.events` (écriture événements uniquement — moindre privilège)
- `https://www.googleapis.com/auth/tasks` (écriture tâches)

### 3.3 Référentiel nutritionnel Ciqual (ANSES) — version retravaillée

Table locale PostgreSQL (`IngredientRef`), importée depuis un fichier XLS ANSES Ciqual retravaillé.
**Aucun appel réseau** — calcul 100% hors-ligne.

**Import** : via l'UI Management (upload XLS → `import_ciqual --wipe`) ou :
`python manage.py import_ciqual --file data/CIRQUAL_MENU_APP.xls --wipe`

**Construction de la base de connaissance** : `python manage.py build_known_ingredients` — construit `KnownIngredient` à partir des noms d'ingrédients déjà utilisés dans les recettes.

**Recalcul** : `python manage.py recalculate_nutrition` — purge les orphelins, resynchronise les `ciqual_ref`, recalcule les macros par portion pour toutes les recettes actives.

**Nettoyage Ciqual** : `python manage.py clean_ciqual [--dry-run]` — supprime les plats composés et les entrées sans données kcal (hors exceptions : eau, sel, bouillon…).

**Architecture en deux couches** :
- `IngredientRef` : référentiel officiel ANSES Ciqual — table en lecture seule (sauf via Management)
- `KnownIngredient` : base de connaissance des ingrédients utilisés dans les recettes, avec lien vers `IngredientRef` et synonymes. Enrichie automatiquement à chaque sauvegarde de recette.

**Autocomplete** : à la saisie dans le formulaire recette, une dropdown interroge `KnownIngredient` (debounce 350ms, `GET /api/ingredients/connus/?q=`). Priorité aux correspondances par synonymes puis par nom normalisé.

Fallback : si aucune correspondance, les macros restent vides (`nutrition_status = 'missing'`).

**Règle `nutrition_status`** :
- `ok` : tous les ingrédients non-optionnels ont un `ciqual_ref`
- `partial` : au moins un ingrédient non-optionnel non mappé
- `missing` : aucun ingrédient non-optionnel mappé

**Calcul des macros** (`calculer_macros_recette`) : calcule directement depuis `ciqual_ref` (pas les valeurs stockées), **tous les ingrédients contribuent au calcul (y compris les optionnels)**. Le `nutrition_status` est déterminé uniquement sur les non-optionnels. Un `kcal_100g NULL` (sel, eau) est traité comme 0 kcal — l'ingrédient est considéré mappé.

---

## 4. Modèle de Données

### 4.1 `TokenOAuth`

Stockage des tokens Google OAuth par utilisateur.

| Champ | Type Django | Nullable | Défaut | Description |
|-------|-------------|----------|--------|-------------|
| `id` | `BigAutoField` | non | auto | Clé primaire |
| `user` | `ForeignKey(User)` | non | — | Utilisateur propriétaire |
| `service` | `CharField(50)` | non | — | `"google"` |
| `access_token` | `TextField` | non | — | Token d'accès (courte durée) |
| `refresh_token` | `TextField` | non | — | Token de rafraîchissement (longue durée) |
| `expires_at` | `DateTimeField` | oui | — | Date d'expiration de l'access token |
| `created_at` | `DateTimeField` | non | auto | Date de création |
| `updated_at` | `DateTimeField` | non | auto | Dernière mise à jour |

**Contrainte DB** : `(user, service)` unique

---

### 4.2 `Family`

Groupe familial. Créé par un Cuisinier lors de l'inscription.

| Champ | Type Django | Nullable | Défaut | Description |
|-------|-------------|----------|--------|-------------|
| `id` | `BigAutoField` | non | auto | Clé primaire |
| `name` | `CharField(100)` | non | — | Nom de la famille |
| `created_by` | `ForeignKey(User)` | non | — | Cuisinier fondateur |
| `invite_token` | `UUIDField` | non | auto | Token d'invitation par lien |
| `created_at` | `DateTimeField` | non | auto | Date de création |

---

### 4.3 `UserProfile`

Extension du modèle User Django. Un profil par utilisateur.

| Champ | Type Django | Nullable | Défaut | Description |
|-------|-------------|----------|--------|-------------|
| `id` | `BigAutoField` | non | auto | Clé primaire |
| `user` | `OneToOneField(User)` | non | — | Utilisateur Django |
| `family` | `ForeignKey(Family)` | oui | `null` | Famille d'appartenance (null avant invitation acceptée) |
| `role` | `CharField(20)` | non | `"convive"` | `chef_etoile` / `cuisinier` / `convive` |
| `dietary_tags` | `JSONField` | non | `[]` | Ex. `["gluten", "lactose"]` — liste fixe |
| `google_calendar_id` | `CharField(200)` | oui | `null` | ID du calendrier Google cible |
| `google_tasklist_id` | `CharField(200)` | oui | `null` | ID de la liste Google Tasks cible |
| `lunch_start` | `TimeField` | non | `12:00` | Début déjeuner pour export Google Calendar |
| `lunch_end` | `TimeField` | non | `13:00` | Fin déjeuner pour export Google Calendar |
| `dinner_start` | `TimeField` | non | `20:30` | Début dîner pour export Google Calendar |
| `dinner_end` | `TimeField` | non | `21:30` | Fin dîner pour export Google Calendar |
| `portions_factor` | `FloatField` | non | `1.0` | Facteur de portion individuel pour le calcul nutritionnel personnalisé. Adulte référence = 1.0 ; ado garçon 15–16 ans ≈ 1.3 ; ado fille 13 ans ≈ 0.9. Configurable librement dans le profil. |

**Propriété calculée `rank`** : retourne `(level, name)` — calculée à partir du rôle et des contributions (non stockée en base).

**Propriété calculée `rank_info`** : retourne un dict complet `{level, name, emoji, progress, next_name, next_threshold, metric, metric_label, current_threshold}` — utilisé dans les templates profil et detail recette.

---

### 4.4 `Recipe`

Catalogue global partagé entre toutes les familles.

| Champ | Type Django | Nullable | Défaut | Description |
|-------|-------------|----------|--------|-------------|
| `id` | `BigAutoField` | non | auto | Clé primaire |
| `title` | `CharField(200)` | non | — | Titre de la recette |
| `description` | `TextField` | oui | — | Description courte |
| `photo_url` | `URLField` | oui | — | URL Cloudinary de la photo principale |
| `base_servings` | `PositiveIntegerField` | non | — | Nombre de parts de référence |
| `prep_time` | `PositiveIntegerField` | oui | — | Temps de préparation (minutes) |
| `cook_time` | `PositiveIntegerField` | oui | — | Temps de cuisson (minutes) |
| `category` | `CharField(20)` | non | — | `entree` / `plat` / `dessert` / `brunch` / `snack` |
| `cuisine_type` | `CharField(50)` | oui | — | Française / Asiatique / Méditerranéenne… |
| `seasons` | `JSONField` | non | `[]` | Ex. `["printemps", "ete"]` |
| `health_tags` | `JSONField` | non | `[]` | Ex. `["leger", "proteine"]` |
| `complexity` | `CharField(20)` | non | `"simple"` | `simple` / `intermediaire` / `elabore` |
| `protein_type` | `CharField(20)` | oui | `null` | Protéine principale : `boeuf` / `volaille` / `porc` / `poisson` / `oeufs` / `legumineuses` / `autre` / `aucune`. Utilisé par l'algorithme de suggestions pour assurer la variété. |
| `calories_per_serving` | `FloatField` | oui | — | Kcal par portion (calculé via Ciqual) |
| `proteins_per_serving` | `FloatField` | oui | — | Protéines (g) par portion (calculé) |
| `carbs_per_serving` | `FloatField` | oui | — | Glucides (g) par portion (calculé) |
| `fats_per_serving` | `FloatField` | oui | — | Lipides (g) par portion (calculé) |
| `nutrition_status` | `CharField(10)` | non | `'missing'` | Statut du calcul nutritionnel : `ok` / `partial` / `missing` |
| `created_by` | `ForeignKey(User)` | non | — | Auteur |
| `actif` | `BooleanField` | non | `True` | Soft delete |
| `created_at` | `DateTimeField` | non | auto | Date de création |

**Tri par défaut** : `["-created_at"]`
**Soft delete** : `actif=False` masque la recette du catalogue sans suppression physique.
**`nutrition_status`** mis à jour automatiquement à chaque sauvegarde de recette et par `recalculate_nutrition`.

---

### 4.5 `IngredientGroup`

Groupe d'ingrédients dans une recette (ex. "Base viande", "Purée", "Finition").

| Champ | Type Django | Nullable | Défaut | Description |
|-------|-------------|----------|--------|-------------|
| `id` | `BigAutoField` | non | auto | Clé primaire |
| `recipe` | `ForeignKey(Recipe)` | non | — | Recette parente |
| `name` | `CharField(100)` | non | — | Nom du groupe |
| `order` | `PositiveIntegerField` | non | `0` | Ordre d'affichage |

---

### 4.6 `Ingredient`

Ingrédient d'une recette, rattaché à un groupe.

| Champ | Type Django | Nullable | Défaut | Description |
|-------|-------------|----------|--------|-------------|
| `id` | `BigAutoField` | non | auto | Clé primaire |
| `recipe` | `ForeignKey(Recipe)` | non | — | Recette parente (`CASCADE`) |
| `group` | `ForeignKey(IngredientGroup)` | oui | — | Groupe (`SET_NULL` — voir note) |
| `name` | `CharField(200)` | non | — | Nom de l'ingrédient |
| `quantity` | `FloatField` | oui | — | Quantité (relative à `base_servings`) — valeur basse si fourchette |
| `quantity_note` | `CharField(50)` | oui | — | Précision libre sur la quantité (ex. "150–200g", "selon votre goût"). Affiché à la place de `quantity + unit` quand renseigné. |
| `unit` | `CharField(50)` | oui | — | Unité (g, ml, c. à soupe…) |
| `is_optional` | `BooleanField` | non | `False` | Ingrédient optionnel — inclus dans le calcul nutritionnel, exclu du `nutrition_status` |
| `category` | `CharField(50)` | oui | — | Catégorie courses (viandes, légumes, épicerie…) |
| `known_ingredient` | `ForeignKey(KnownIngredient)` | oui | — | Lien vers la base de connaissance (`SET_NULL`) |
| `ciqual_ref` | `ForeignKey(IngredientRef)` | oui | — | Référence Ciqual dérivée de `known_ingredient.ciqual_ref` à la sauvegarde |
| `calories` | `FloatField` | oui | — | Kcal calculés pour la quantité définie (cache — source de vérité : Ciqual) |
| `proteins` | `FloatField` | oui | — | Protéines (g) |
| `carbs` | `FloatField` | oui | — | Glucides (g) |
| `fats` | `FloatField` | oui | — | Lipides (g) |
| `order` | `PositiveIntegerField` | non | `0` | Ordre dans le groupe |

> **Note `group` SET_NULL** : `Ingredient.group` utilise `on_delete=SET_NULL`. La suppression d'un groupe orphelinise les ingrédients (group=NULL) sans les supprimer. `sauvegarder_recette_depuis_post()` supprime explicitement `recipe.ingredients.all()` avant de supprimer les groupes pour éviter toute accumulation.

---

### 4.6b `IngredientRef`

Référentiel nutritionnel ANSES Ciqual — importé depuis le fichier XLS retravaillé `CIRQUAL_MENU_APP.xls`.
Modifiable via la page `/management/ciqual/`. Les entrées personnalisées ont un code `CUSTOM-XXXX`.

| Champ | Type Django | Nullable | Défaut | Description |
|-------|-------------|----------|--------|-------------|
| `id` | `BigAutoField` | non | auto | Clé primaire |
| `ciqual_code` | `CharField(10)` | non | — | Code Ciqual unique (ex. `"22000"` ou `"CUSTOM-0001"`) |
| `nom_fr` | `CharField(300)` | non | — | Nom officiel Ciqual (ex. "Œuf entier, cru") |
| `nom_normalise` | `CharField(300)` | non | — | Nom normalisé pour recherche (ascii, minuscules) |
| `synonymes` | `TextField` | oui | `""` | Noms courants séparés par virgules (ex. "steak,bœuf haché") — boostés dans l'autocomplete |
| `groupe` | `CharField(100)` | oui | — | Groupe alimentaire Ciqual |
| `sous_groupe` | `CharField(100)` | oui | — | Sous-groupe Ciqual |
| `kcal_100g` | `FloatField` | oui | — | Énergie (kcal/100g) — NULL pour sel, eau, etc. → traité comme 0 kcal |
| `proteines_100g` | `FloatField` | oui | — | Protéines (g/100g) |
| `glucides_100g` | `FloatField` | oui | — | Glucides (g/100g) |
| `sucres_100g` | `FloatField` | oui | — | Sucres simples (g/100g) |
| `lipides_100g` | `FloatField` | oui | — | Lipides (g/100g) |
| `ag_satures_100g` | `FloatField` | oui | — | Acides gras saturés (g/100g) |
| `fibres_100g` | `FloatField` | oui | — | Fibres alimentaires (g/100g) |
| `sel_100g` | `FloatField` | oui | — | Sel (g/100g) |
| `default_weight_g` | `FloatField` | oui | — | Poids par défaut pour unités dénombrables (ex. 1 œuf = 60g) |
| `protein_type` | `CharField(20)` | oui | — | Type de protéine (`boeuf`, `volaille`, `poisson`, etc.) |
| `shopping_category` | `CharField(50)` | oui | — | Catégorie liste de courses |

### 4.6c `KnownIngredient`

Base de connaissance des ingrédients utilisés dans les recettes. Intermédiaire entre `Ingredient` et `IngredientRef`. Enrichie automatiquement à chaque sauvegarde de recette (`_sync_known_ingredient`).

| Champ | Type Django | Nullable | Défaut | Description |
|-------|-------------|----------|--------|-------------|
| `id` | `BigAutoField` | non | auto | Clé primaire |
| `name` | `CharField(200)` | non | — | Nom de l'ingrédient (unique) |
| `nom_normalise` | `CharField(200)` | non | — | Calculé automatiquement via `_normaliser_nom(name)` à chaque save |
| `synonymes` | `TextField` | oui | `""` | Noms alternatifs séparés par virgules — utilisés dans l'autocomplete |
| `ciqual_ref` | `ForeignKey(IngredientRef)` | oui | — | Correspondance Ciqual (`SET_NULL`) |
| `default_unit` | `CharField(20)` | non | `'g'` | Unité pré-remplie dans le formulaire recette |
| `created_at` | `DateTimeField` | non | auto | Date de création |

**Propriétés calculées** : `kcal_100g`, `proteines_100g` — délèguent à `ciqual_ref`.

**Autocomplete** (`GET /api/ingredients/connus/?q=`) : recherche sur `nom_normalise` et `synonymes`, triée par pertinence (startswith > contains > synonyme).

---

### 4.7 `RecipeStep`

Étape de préparation d'une recette.

| Champ | Type Django | Nullable | Défaut | Description |
|-------|-------------|----------|--------|-------------|
| `id` | `BigAutoField` | non | auto | Clé primaire |
| `recipe` | `ForeignKey(Recipe)` | non | — | Recette parente |
| `order` | `PositiveIntegerField` | non | — | Numéro de l'étape |
| `instruction` | `TextField` | non | — | Texte de l'étape |
| `chef_note` | `TextField` | oui | — | Note/conseil du chef (👉) |
| `timer_seconds` | `PositiveIntegerField` | oui | — | Durée du timer (0 = pas de timer) |

---

### 4.8 `RecipeSection`

Section libre en fin de recette (Points critiques, Conseils, Ce qui fait la différence…).

| Champ | Type Django | Nullable | Défaut | Description |
|-------|-------------|----------|--------|-------------|
| `id` | `BigAutoField` | non | auto | Clé primaire |
| `recipe` | `ForeignKey(Recipe)` | non | — | Recette parente |
| `section_type` | `CharField(30)` | non | — | `critique` / `conseil` / `difference` / `libre` |
| `title` | `CharField(100)` | oui | — | Titre personnalisé (si `libre`) |
| `content` | `TextField` | non | — | Contenu Markdown ou texte libre |
| `order` | `PositiveIntegerField` | non | `0` | Ordre d'affichage |

---

### 4.9 `Review`

Avis d'un utilisateur sur une recette. Plusieurs avis possibles par utilisateur dans le temps.

| Champ | Type Django | Nullable | Défaut | Description |
|-------|-------------|----------|--------|-------------|
| `id` | `BigAutoField` | non | auto | Clé primaire |
| `recipe` | `ForeignKey(Recipe)` | non | — | Recette notée |
| `user` | `ForeignKey(User)` | non | — | Utilisateur |
| `stars` | `PositiveSmallIntegerField` | non | — | Note 1–5 |
| `comment` | `TextField` | oui | — | Commentaire optionnel |
| `created_at` | `DateTimeField` | non | auto | Date de l'avis |

**Contrainte** : `stars` entre 1 et 5 (validation Python `clean`).
**Pas de contrainte d'unicité** : plusieurs avis par utilisateur autorisés (les goûts évoluent).

---

### 4.10 `WeekPlan`

Planning hebdomadaire d'une famille.

| Champ | Type Django | Nullable | Défaut | Description |
|-------|-------------|----------|--------|-------------|
| `id` | `BigAutoField` | non | auto | Clé primaire |
| `family` | `ForeignKey(Family)` | non | — | Famille |
| `period_start` | `DateField` | non | — | Début de la période (paramétrable) |
| `period_end` | `DateField` | non | — | Fin de la période |
| `status` | `CharField(20)` | non | `"draft"` | `draft` / `published` |
| `created_by` | `ForeignKey(User)` | non | — | Cuisinier auteur |
| `created_at` | `DateTimeField` | non | auto | Date de création |

**Contrainte DB** : `(family, period_start)` unique — une seule planification par famille par période de départ.

---

### 4.11 `Meal`

Repas planifié dans un WeekPlan.

| Champ | Type Django | Nullable | Défaut | Description |
|-------|-------------|----------|--------|-------------|
| `id` | `BigAutoField` | non | auto | Clé primaire |
| `week_plan` | `ForeignKey(WeekPlan)` | non | — | Planning parent |
| `date` | `DateField` | non | — | Date du repas |
| `meal_time` | `CharField(10)` | non | — | `lunch` / `dinner` |
| `recipe` | `ForeignKey(Recipe)` | oui | `null` | Recette (null si créneau vide) |
| `servings_count` | `PositiveIntegerField` | oui | — | Nombre de parts à préparer |
| `is_leftovers` | `BooleanField` | non | `False` | Ce repas = restes d'un autre |
| `source_meal` | `ForeignKey('self')` | oui | `null` | Repas source des restes |
| `google_event_id` | `CharField(200)` | non | `""` | ID de l'événement Google Calendar créé (vide si non exporté) |

**Contrainte DB** : `(week_plan, date, meal_time)` unique.
**Règle** : si `is_leftovers=True`, ce repas n'est pas pris en compte dans la génération de la liste de courses.

---

### 4.12 `MealProposal`

Proposition d'un Convive pour un repas à venir.

| Champ | Type Django | Nullable | Défaut | Description |
|-------|-------------|----------|--------|-------------|
| `id` | `BigAutoField` | non | auto | Clé primaire |
| `family` | `ForeignKey(Family)` | non | — | Famille |
| `recipe` | `ForeignKey(Recipe)` | non | — | Recette proposée |
| `proposed_by` | `ForeignKey(User)` | non | — | Convive auteur |
| `message` | `TextField` | oui | — | Message optionnel |
| `week_plan` | `ForeignKey(WeekPlan)` | oui | `null` | Lié à un planning si déjà créé |
| `created_at` | `DateTimeField` | non | auto | Date de la proposition |

---

### 4.13 `ShoppingList`

Liste de courses générée pour un WeekPlan.

| Champ | Type Django | Nullable | Défaut | Description |
|-------|-------------|----------|--------|-------------|
| `id` | `BigAutoField` | non | auto | Clé primaire |
| `family` | `ForeignKey(Family)` | non | — | Famille |
| `week_plan` | `ForeignKey(WeekPlan)` | non | — | Planning source |
| `generated_at` | `DateTimeField` | non | auto | Date de génération |

**Contrainte DB** : `week_plan` unique — une liste de courses par planning.

---

### 4.14 `ShoppingItem`

Article dans une liste de courses.

| Champ | Type Django | Nullable | Défaut | Description |
|-------|-------------|----------|--------|-------------|
| `id` | `BigAutoField` | non | auto | Clé primaire |
| `shopping_list` | `ForeignKey(ShoppingList)` | non | — | Liste parente |
| `name` | `CharField(200)` | non | — | Nom de l'ingrédient |
| `quantity` | `FloatField` | oui | — | Quantité agrégée |
| `unit` | `CharField(50)` | oui | — | Unité |
| `category` | `CharField(50)` | oui | — | Catégorie (viandes, légumes…) |
| `checked` | `BooleanField` | non | `False` | Coché lors des courses |

---

### 4.15 `NotificationPreference`

Préférences de notification par utilisateur et par canal. Utilisé par les services email pour respecter l'opt-out.

| Champ | Type Django | Nullable | Défaut | Description |
|-------|-------------|----------|--------|-------------|
| `id` | `BigAutoField` | non | auto | Clé primaire |
| `user` | `ForeignKey(User)` | non | — | Utilisateur |
| `channel` | `CharField(20)` | non | — | `email` / `push` / `in_app` |
| `enabled` | `BooleanField` | non | `True` | Activé/désactivé |

**Comportement** : si un utilisateur a un enregistrement `channel="email", enabled=False`, il ne reçoit aucun email transactionnel. Absence d'enregistrement = opt-in par défaut. Configurable uniquement via l'admin Django (pas d'UI utilisateur pour le MVP).

---

## 5. Fonctionnalités

### 5.1 Inscription et création de famille

**URL** : `GET/POST /inscription/` → `menu:inscription`
**Vue** : `inscription(request)`
**Template** : `menu/inscription.html`

**Règles de gestion** :
1. L'utilisateur choisit son rôle : Cuisinier (crée une nouvelle famille) ou Convive (rejoindra via invitation)
2. Un Cuisinier crée sa famille à l'inscription
3. Un Convive sans famille peut rejoindre via lien d'invitation ultérieurement

**Réponse** :
- Succès : redirection vers `/` + message flash "Bienvenue !"

---

### 5.2 Invitation d'un membre

**URL** : `GET /famille/inviter/<token>/` → `menu:rejoindre_famille`
**Vue** : `rejoindre_famille(request, token)`

**Règles de gestion** :
1. Le token est vérifié contre `Family.invite_token`
2. Si l'utilisateur est connecté et sans famille → le rattache à la famille
3. Si non connecté → redirige vers inscription avec le token en session
4. Un utilisateur déjà dans une famille ne peut pas rejoindre une autre

---

### 5.3 Catalogue des recettes

**URL** : `GET /recettes/` → `menu:liste_recettes`
**Vue** : `liste_recettes(request)`
**Template** : `menu/recettes/liste.html`

**Règles de gestion** :
1. Affiche toutes les recettes `actif=True` du catalogue global
2. Filtres disponibles : catégorie, saison courante, type de cuisine, complexité
3. Tri disponible : récentes, mieux notées, les plus simples
4. Barre de recherche sur le titre

---

### 5.4 Création / édition d'une recette

**URL** :
- `GET/POST /recettes/creer/` → `menu:creer_recette`
- `GET/POST /recettes/<id>/modifier/` → `menu:modifier_recette`

**Vue** : `creer_recette(request)` / `modifier_recette(request, id)`
**Template** : `menu/recettes/formulaire.html`
**Accès création** : Cuisinier uniquement
**Accès modification / suppression** : le Cuisinier créateur OU tout autre Cuisinier (catalogue global partagé entre familles)

**Champs du formulaire** :
- `title` : texte, obligatoire
- `description` : texte, optionnel
- `photo` : upload fichier image, optionnel
- `base_servings` : entier, obligatoire
- `prep_time`, `cook_time` : entiers (minutes), optionnels
- `category` : choix, obligatoire
- `cuisine_type` : texte libre, optionnel
- `seasons` : multi-select, optionnel
- `health_tags` : multi-select, optionnel
- `complexity` : choix, obligatoire
- Groupes d'ingrédients : ajout dynamique (vanilla JS)
- Ingrédients par groupe : nom + quantité + unité + optionnel + catégorie
- Étapes : ajout dynamique, instruction + note chef + timer optionnel
- Sections libres : ajout dynamique

**Règles de gestion** :
1. La photo est uploadée vers Cloudinary via `integrations/cloudinary.py` → l'URL retournée est stockée dans `photo_url`
2. À la saisie de chaque ingrédient (debounce 350ms), une requête AJAX interroge `services.rechercher_connus()` (base `KnownIngredient`) et propose les correspondances dans une dropdown avec badge kcal/100g. Si kcal=NULL (sel, eau), affiche "Ciqual ✓". Si kcal=0, affiche "0 kcal/100g".
3. Si un `KnownIngredient` est sélectionné, son `ciqual_ref` est résolu et les macros sont calculées (quantité → grammes → facteur × kcal/100g)
4. Les macros de la recette sont recalculées via `services.calculer_macros_recette()` à chaque enregistrement : calcul direct depuis `ciqual_ref`, tous les ingrédients inclus (optionnels compris)
5. `Recipe.nutrition_status` est mis à jour simultanément : `ok` / `partial` / `missing`

**Gestion des erreurs** :
- Objet introuvable → `get_object_or_404` → HTTP 404
- Upload photo échoué → message flash, recette sauvegardée sans photo
- Ciqual sans résultat → dropdown vide, macros restent vides (ingrédient non-calculable)

**Réponse** :
- Succès POST : redirection vers `/recettes/<id>/` + message flash "Recette enregistrée"

---

### 5.5 Fiche recette

**URL** : `GET /recettes/<id>/` → `menu:detail_recette`
**Vue** : `detail_recette(request, id)`
**Template** : `menu/recettes/detail.html`

**Contenu affiché** :
- Toutes les métadonnées, photo, ingrédients groupés, étapes, sections libres
- Informations nutritionnelles par portion
- Note moyenne globale + nombre d'avis
- Historique des avis (tous les utilisateurs)
- Avis de chaque membre de la famille (vue personnalisée)
- Alertes d'incompatibilité allergies/régimes basées sur le profil de l'utilisateur connecté

---

### 5.6 Notation d'une recette

**URL** : `POST /recettes/<id>/noter/` → `menu:noter_recette`
**Vue** : `noter_recette(request, id)`
**Accès** : tout utilisateur connecté

**Règles de gestion** :
1. Crée un nouveau `Review` à chaque soumission — pas de mise à jour de l'avis existant
2. Plusieurs avis du même utilisateur sont conservés dans l'historique

**Réponse** :
- `{"ok": true, "new_average": 4.2, "review_count": 12}`
- Erreur : `{"ok": false, "error": "description", "code": "NOM_ERREUR"}`

---

### 5.7 Recherche Ciqual (autocomplete ingrédients)

**URL** : `GET /api/ingredients/ciqual/?q=<terme>` → `menu:recherche_ciqual`
**Vue** : `recherche_ciqual(request)`
**Accès** : utilisateur connecté

**Règles de gestion** :
1. Normalise le terme (minuscules, sans accents) et interroge `IngredientRef.nom_normalise__icontains`
2. Retourne les 8 meilleurs résultats triés par `nom_fr`
3. Aucun appel réseau — base PostgreSQL locale

**Réponse** :
- `{"ok": true, "results": [{"id": 42, "ciqual_code": "22000", "nom_fr": "Œuf entier, cru", "kcal_100g": 147, "proteines_100g": 12.6, ...}]}`

---

### 5.8 Planning hebdomadaire

**URL** :
- `GET /planning/` → `menu:planning` (semaine courante ou prochaine)
- `GET /planning/<year>/<week>/` → `menu:planning_semaine`

**Vue** : `planning(request)` / `planning_semaine(request, year, week)`
**Template** : `menu/planning/semaine.html`
**Accès** : tout membre de la famille

**Contenu affiché** :
- Grille 7 jours × 2 repas (midi / soir), créneaux vides autorisés
- Statut du planning (Brouillon / Publié)
- Propositions des Convives en attente (visibles par le Cuisinier)
- Indicateurs nutritionnels de la semaine (calories / protéines cumulés)

**Création automatique du WeekPlan** : si aucun plan n'existe pour la semaine demandée, `planning_semaine` le crée automatiquement en `draft`. `created_by` est toujours un Cuisinier — si l'utilisateur courant est un Convive, le premier Cuisinier de la famille est utilisé comme auteur.

---

### 5.9 Composition et modification du planning

**URL** : `POST /planning/<id>/meal/` → `menu:modifier_meal`
**Vue** : `modifier_meal(request, plan_id)`
**Accès** : Cuisinier uniquement

**Règles de gestion** :
1. Crée ou met à jour un `Meal` pour une date + créneau donnés
2. Si `recipe=None` → créneau vide (cantine, repas extérieur)
3. Si `is_leftovers=True` → `source_meal` obligatoire
4. Un créneau "restes" n'est pas pris en compte dans la liste de courses

**Réponse** :
- `{"ok": true, "meal_id": 42, "recipe_title": "Hachis Parmentier"}`

---

### 5.10 Publication du planning

**URL** : `POST /planning/<id>/publier/` → `menu:publier_planning`
**Vue** : `publier_planning(request, id)`
**Accès** : Cuisinier uniquement

**Règles de gestion** :
1. Passe `WeekPlan.status` de `draft` à `published`
2. La liste de courses n'est **pas** générée automatiquement — le Cuisinier la génère manuellement depuis le toolbar du planning via `POST /courses/generer/<plan_id>/`

**Réponse** :
- Succès : redirection vers `/planning/<year>/<week>/` + message flash "Menu publié"

---

### 5.11 Propositions de repas

**URL** : `POST /planning/<id>/proposer/` → `menu:proposer_repas`
**Vue** : `proposer_repas(request, plan_id)`
**Accès** : Convive uniquement (les Cuisiniers modifient le planning directement)

**Règles de gestion** :
1. Crée un `MealProposal` lié à la famille et au planning
2. Un Cuisinier qui tente de proposer reçoit une erreur 403 — il doit utiliser `modifier_meal` directement

**Réponse** :
- Succès : `{"ok": true}` + mise à jour de l'UI

---

### 5.12 Génération de la liste de courses

**URL** : `POST /courses/generer/<plan_id>/` → `menu:generer_courses`
**Vue** : `generer_courses(request, plan_id)`
**Accès** : Cuisinier uniquement — plan `published` uniquement (le bouton n'apparaît pas sur un brouillon)

**Règles de gestion** :
1. Récupère tous les `Meal` du plan avec `is_leftovers=False` et `recipe` non null
2. Pour chaque `Meal`, calcule les quantités de chaque ingrédient : `quantite_ingredient × (servings_count / base_servings)`
3. Agrège les ingrédients identiques (même nom + même unité) en les additionnant
4. Crée ou recrée le `ShoppingList` et les `ShoppingItem` associés (suppression + recréation)

---

### 5.13 Liste de courses

**URL** : `GET /courses/<plan_id>/` → `menu:liste_courses`
**Vue** : `liste_courses(request, plan_id)`
**Template** : `menu/courses/liste.html`
**Accès** : tout membre de la famille

**Contenu** :
- Articles regroupés par catégorie
- Cochage possible sur mobile (mise à jour AJAX de `ShoppingItem.checked`)

---

### 5.14 Cochage d'un article (AJAX)

**URL** : `POST /courses/item/<id>/cocher/` → `menu:cocher_item`
**Vue** : `cocher_item(request, id)`

**Réponse** :
- `{"ok": true, "checked": true}`

---

### 5.15 Mode Cuisine

**URL** : `GET /recettes/<id>/cuisine/` → `menu:mode_cuisine`
**Vue** : `mode_cuisine(request, id)`
**Template** : `menu/recettes/cuisine.html`

Vue dédiée mobile avec :
- Ingrédients cochables (JS)
- Étapes cochables avec mise en avant de l'étape courante (JS)
- Timer par étape en secondes (JS natif — `setTimeout` / `setInterval`)
- Grande police, boutons larges, fond sombre optionnel

---

### 5.16 Export Google Calendar

**URL** : `POST /planning/<id>/export-calendar/` → `menu:export_calendar`
**Vue** : `export_calendar(request, plan_id)`
**Accès** : Cuisinier avec Google connecté

**Règles de gestion** :
1. Vérifie que `TokenOAuth` existe et est valide pour l'utilisateur (renouvelle si expiré)
2. Pour chaque `Meal` non vide du planning, crée un événement Google Calendar via `integrations/google_calendar.py`
3. Créneaux : midi = 12h00–13h00, soir = 20h30–21h30 (configurables dans le profil)
4. Titre de l'événement : titre de la recette

**Gestion des erreurs** :
- Google non connecté → message warning + redirection vers la page planning de la semaine
- Erreur API Google → message flash + log

**Réponse** :
- Succès : message flash avec bilan (N créés / N mis à jour)

---

### 5.17 Export Google Tasks

**URL** : `POST /courses/<plan_id>/export-tasks/` → `menu:export_tasks`
**Vue** : `export_tasks(request, plan_id)`
**Accès** : Cuisinier avec Google connecté

**Règles de gestion** :
1. Vérifie le token OAuth (renouvelle si expiré)
2. Pousse chaque `ShoppingItem` non coché vers la liste Google Tasks cible via `integrations/google_tasks.py`
3. Chaque article = une tâche avec titre `"{quantite} {unite} {nom}"`

**Gestion des erreurs** :
- Google non connecté → message warning + redirection vers la liste de courses
- Erreur API Google → message flash + log

---

## 6. Comportements JavaScript

### 6.1 Formulaire recette — ajout dynamique d'ingrédients et d'étapes

**Fichier JS** : `static/menu/js/recette_form.js` — chargé avec `defer` sur `formulaire.html`

Comportements :
1. Bouton "Ajouter un ingrédient" : clone le dernier bloc ingrédient et incrémente les indices de nommage
2. Bouton "Ajouter un groupe" : crée un nouveau groupe vide
3. Bouton "Ajouter une étape" : clone la dernière étape et incrémente
4. À la saisie du nom d'un ingrédient (debounce 350ms) : appelle `/api/ingredients/ciqual/` et affiche les suggestions Ciqual dans `.ciqual-dropdown` avec badge kcal/100g
5. Sélection d'un résultat : remplit `.ing-ciqual-ref-id` (ID de l'`IngredientRef`), affiche le badge de confirmation

**Gestion des erreurs JS** :
- Si `/api/ingredients/ciqual/` ne répond pas → dropdown vide, saisie manuelle disponible

---

### 6.2 Mode Cuisine — timers et cochage

**Fichier JS** : `static/menu/js/mode_cuisine.js` — chargé avec `defer` sur `cuisine.html`

Comportements :
1. Clic sur un ingrédient → bascule une classe CSS `checked` + mise à jour visuelle
2. Clic sur "Valider l'étape" → coche l'étape, fait défiler vers la suivante, lance le timer si `timer_seconds > 0`
3. Timer : affichage `MM:SS` décrémenté chaque seconde, alerte visuelle + sonore (Web Audio API) à 0

---

### 6.3 Cochage des articles de la liste de courses (AJAX)

**Fichier JS** : `static/menu/js/courses.js` — chargé avec `defer` sur `liste.html`

Comportement :
1. Clic sur un article → `POST /courses/item/<id>/cocher/` avec CSRF
2. Mise à jour visuelle immédiate (classe `checked`)

---

## 7. États du système

### États de `WeekPlan`

```
DRAFT ──[publier_planning]──► PUBLISHED
```

| Transition | Vue | Conditions |
|------------|-----|------------|
| `DRAFT` → `PUBLISHED` | `publier_planning` | Cuisinier de la famille, au moins 1 Meal non vide |

**Transition interdite** : `PUBLISHED` → `DRAFT` non prévue (modification directe possible).

---

### 4.16 `NutritionConfig`

Singleton de configuration du cadre nutritionnel de référence (PNNS — ANSES France). Un seul enregistrement en base, modifiable uniquement via l'admin Django.

Toutes les valeurs sont des **repères indicatifs de bonne pratique**, jamais des prescriptions médicales. Toujours affichées avec la mention "Valeurs estimées — repères indicatifs PNNS".

| Champ | Type Django | Défaut | Description |
|-------|-------------|--------|-------------|
| `calories_dinner_target` | `PositiveIntegerField` | `850` | Cible kcal pour un dîner (adulte référence, `portions_factor = 1.0`) |
| `proteins_dinner_target` | `PositiveIntegerField` | `27` | Cible protéines (g) pour un dîner |
| `max_red_meat_per_week` | `PositiveSmallIntegerField` | `3` | Max repas viande rouge par semaine (bœuf + porc) |
| `min_fish_per_week` | `PositiveSmallIntegerField` | `1` | Min repas poisson par semaine |
| `min_vegetarian_per_week` | `PositiveSmallIntegerField` | `1` | Min repas végétarien par semaine (`protein_type = "aucune"` ou `"legumineuses"`) |
| `min_days_before_repeat` | `PositiveSmallIntegerField` | `14` | Jours minimum avant de replanifier un même plat |
| `min_days_low_rated_repeat` | `PositiveSmallIntegerField` | `21` | Jours minimum avant de replanifier un plat noté < 2★ par la famille |

**Pattern singleton** : `save()` surchargé pour forcer `pk=1`. Accès via `NutritionConfig.objects.get_or_create(pk=1)`.

---

### 4.17 `RecipePhoto`

Photos supplémentaires d'une recette (galerie). La photo principale reste `Recipe.photo_url` (Cloudinary, upload à la création).

| Champ | Type Django | Nullable | Défaut | Description |
|-------|-------------|----------|--------|-------------|
| `id` | `BigAutoField` | non | auto | Clé primaire |
| `recipe` | `ForeignKey(Recipe)` | non | — | Recette parente |
| `photo_url` | `URLField` | non | — | URL Cloudinary |
| `caption` | `CharField(100)` | oui | — | Légende optionnelle |
| `is_main` | `BooleanField` | non | `False` | Photo mise en avant dans la galerie (≠ `Recipe.photo_url`) |
| `order` | `PositiveIntegerField` | non | `0` | Ordre d'affichage |
| `uploaded_by` | `ForeignKey(User)` | oui | `null` | Auteur de l'upload — `SET_NULL` si l'utilisateur est supprimé (préserve la photo) |
| `actif` | `BooleanField` | non | `True` | Soft delete — retrait par le Cuisinier |
| `created_at` | `DateTimeField` | non | auto | Date d'upload |

**Accès** : tout utilisateur connecté peut uploader. Seul le Cuisinier peut promouvoir ou retirer une photo.

---

## 5.18 Algorithme de suggestions de menu

**URL** : `GET /planning/<plan_id>/suggestions/?date=YYYY-MM-DD&meal_time=lunch|dinner` → `menu:suggestions_repas`
**Vue** : `suggestions_repas(request, plan_id)`
**Accès** : Cuisinier uniquement

**Service** : `services.suggerer_recettes(family, week_plan, date, meal_time)` — retourne une liste de 5 recettes triées par score décroissant.

**Calcul du score composite (0.0 → 1.0) — poids dynamiques :**

Chaque recette candidate reçoit un score sur 5 dimensions. Les poids varient dynamiquement selon le déficit protéique hebdomadaire (voir WPD ci-dessous). Les poids sont toujours normalisés à 100%.

**Dimension 1 — Fraîcheur / rotation (nominal 30%) :**
- Score 0 si < `min_days_before_repeat` jours depuis la dernière utilisation pour cette famille
- Score 0 si < `min_days_low_rated_repeat` ET note famille < 2★
- Score linéaire 0.3→1.0 au-delà du seuil · Score 1.0 si jamais cuisiné

**Dimension 2 — Appréciation famille (nominal 30%) :**
- Moyenne des `Review.stars` des membres de **cette famille uniquement**. Score = note / 5
- Score neutre 0.5 si aucun avis famille

**Dimension 3 — Variété protéines (nominal 20%) :**
- Score 0 (règle dure) si : même `protein_type` déjà 2× dans la journée, OU viande rouge (`boeuf` + `porc`) ≥ `max_red_meat_per_week` dans la semaine
- Bonus +0.3 si ce `protein_type` absent de la semaine · Malus −0.2 si déjà présent 2× dans la semaine
- **Bonus adéquation** +0.1 si `proteins_per_serving > 25g` (plafonné à 1.0) — récompense les plats très protéinés indépendamment du type

**Dimension 4 — Saisonnalité (nominal 10%) :**
- Compatible saison courante → 1.0 · Toutes saisons → 0.7 · Incompatible → 0.2

**Dimension 5 — Adéquation protéique + équilibre (nominal 10%, jusqu'à 25%) :**

*Protein Score (PS) — basé sur `proteins_per_serving` réel :*
```
proteins_per_serving non renseigné → PS = 0.5  (neutre)
< 15g par portion                  → PS = 0.3  (faible)
15 – 25g par portion               → PS = 0.6  (correct)
> 25g par portion                  → PS = 1.0  (élevé)
```

*Weekly Protein Deficit factor (WPD) — calculé sur la semaine en cours :*
```python
proteins_planned = sum(
    meal.recipe.proteins_per_serving * meal.servings_count / meal.recipe.base_servings
    for meal in week_plan.meals if not meal.is_leftovers and meal.recipe
)
repas_restants = nb_creneaux_non_remplis_dans_la_semaine
proteins_target = config.proteins_dinner_target * repas_restants

deficit_ratio = proteins_planned / proteins_target  # 0 si target = 0

if deficit_ratio < 0.6:   WPD = 1.5   # déficit fort
elif deficit_ratio < 0.8: WPD = 1.2   # déficit modéré
else:                      WPD = 1.0   # dans la cible
```

*Score dimension 5 :*
```python
score_nutrition = min(PS * WPD, 1.0)
```

*Poids dynamiques normalisés selon WPD :*

| WPD | Fraîcheur | Appréciation | Variété | Saisonnalité | Nutrition |
|-----|-----------|--------------|---------|--------------|-----------|
| 1.0 (nominal) | 30% | 30% | 20% | 10% | 10% |
| 1.2 (déficit modéré) | 27% | 27% | 18% | 9% | 19% |
| 1.5 (déficit fort) | 25% | 25% | 17% | 8% | 25% |

**score_final = Σ(score_dimension × poids_normalisé)**

**Interface :**
- Bouton "💡 Suggestions" sur chaque créneau vide du planning
- 5 recettes proposées avec icônes de justification : 🔄 rotation · ⭐ avis famille · 🥩 variété · 🌿 saison · ⚖️ équilibre
- Indicateur protéines sur chaque carte : `🥩 12g` / `🥩🥩 20g` / `🥩🥩🥩 32g`
- Justification enrichie si WPD > 1.0 : `⚖️ Semaine en déficit protéique · Cette recette apporte 32g`
- Sélection libre — le Cuisinier peut ignorer et choisir autre chose

**Gestion des erreurs** :
- Aucune recette candidate après filtrage → message "Pas assez de recettes dans le catalogue pour cette période"
- Erreur serveur → HTTP 500 loggé + message générique

**Réponse** :
- `{"ok": true, "wpd": 1.5, "suggestions": [{"recipe_id": 12, "title": "...", "score": 0.82, "protein_score": 1.0, "proteins_per_serving": 32, "reasons": {"rotation": 0.9, "famille": 0.8, "variete": 1.0, "saison": 0.7, "nutrition": 1.0}}]}`

> [LOG 2026-04-27] Refactoring `services.suggerer_recettes` : remplacement du nudge statique par PS×WPD, poids dynamiques normalisés, bonus adéquation dim.3 (+0.1 si >25g). Réponse JSON enrichie : `wpd`, `deficit_proteique`, `protein_score`, `protein_level`. JS suggestions : indicateur protéines coloré (🥩/🥩🥩/🥩🥩🥩), bandeau déficit conditionnel, tooltip enrichi nutrition si WPD > 1.0.

---

## 5.19 Dashboard nutritionnel individuel

**URL** : `GET /profil/nutrition/` → `menu:dashboard_nutrition`
**Vue** : `dashboard_nutrition(request)`
**Template** : `menu/profil/nutrition.html`
**Accès** : tout utilisateur connecté

**Principe clé** : tout est calculé **par utilisateur** via son `portions_factor`.
`macros_utilisateur = macros_recette_par_portion × portions_factor`

**Données affichées — vue semaine en cours :**
- Liste des repas planifiés pour la famille (WeekPlan publié ou en cours)
- Pour chaque repas : calories et protéines calculées pour cet utilisateur
- Total journalier et hebdomadaire
- Barre de progression vs cibles (`NutritionConfig × portions_factor`) :
  - 🟢 Dans la cible : 80–110%
  - 🟡 Légèrement hors cible : 60–80% ou 110–130%
  - 🔴 Significativement hors cible : < 60% ou > 130%
- Mention systématique : *"Valeurs estimées — repères indicatifs PNNS"*

**Données affichées — bloc dans la fiche recette (`detail_recette`) :**
- Ligne "Pour toi : ~X kcal · Yg de protéines" calculée avec `portions_factor`
- Affichage conditionnel : uniquement si `calories_per_serving` renseigné sur la recette

**Ce qu'on n'affiche PAS :**
- Pas de total famille agrégé
- Pas de graphes complexes
- Pas de recommandations médicales

**Gestion des erreurs** :
- Aucun WeekPlan publié pour la semaine → message "Aucun menu planifié cette semaine"

---

## 5.20 Alertes équilibre (nudges planning)

Affichées dans la vue planning (`planning_semaine`). Jamais bloquantes, jamais en modal. Visibles uniquement par le Cuisinier.

**Règles — banderoles dismissables, recalculées à chaque modification du menu :**

| Condition | Message affiché |
|-----------|----------------|
| 0 repas `protein_type = "poisson"` dans la semaine | 🐟 Pensez à intégrer un repas poisson cette semaine |
| Repas viande rouge (`boeuf` + `porc`) ≥ `max_red_meat_per_week` | 🥩 Vous avez déjà X repas de viande rouge cette semaine |
| 0 repas végétarien (`protein_type = "aucune"` ou `"legumineuses"`) | 🥦 Un repas végétarien serait bienvenu |
| Calories semaine > 130% objectif (`NutritionConfig`) | ⚠️ La semaine semble chargée en calories |
| Protéines semaine < 60% objectif | 💪 Les protéines sont un peu faibles cette semaine |

**Implémentation** : calcul dans `services.py` → `calculer_alertes_planning(week_plan, family)` → retourne une liste de dicts `{type, message, dismissable}`. Rendu dans le template via `{% for alerte in alertes %}`.

**Dismissal** : via sessionStorage JS — les alertes réapparaissent si le menu est modifié.

---

## 5.21 Galerie photos recette

**Upload :**
**URL** : `POST /recettes/<id>/photos/ajouter/` → `menu:ajouter_photo_recette`
**Accès** : tout utilisateur connecté

**Règles de gestion** :
1. Upload vers Cloudinary via `integrations/cloudinary.py`
2. Crée un `RecipePhoto` avec `uploaded_by = request.user`
3. Redirection vers la fiche recette + message flash

**Gestion de la galerie (Cuisinier uniquement) :**
**URL** : `POST /recettes/<id>/photos/<photo_id>/retirer/` → `menu:retirer_photo_recette`
**URL** : `POST /recettes/<id>/photos/<photo_id>/promouvoir/` → `menu:promouvoir_photo_recette`

- Retirer : passe `actif=False` (soft delete)
- Promouvoir : passe `is_main=True` sur cette photo, `False` sur les autres

**Affichage dans `detail_recette` :**
- Carousel vanilla JS sous la photo principale (`menu/js/galerie.js`)
- Navigation gauche/droite, indicateur de position
- Légende optionnelle affichée sous chaque photo

**Optimisation bande passante Cloudinary :**
L'URL brute est stockée en base. Le filtre template `cloudinary_img` (dans `menu_extras.py`) insère les paramètres de transformation dans l'URL à l'affichage — Cloudinary génère la version optimisée au premier appel et la met en cache.

| Preset | Transformation | Contexte |
|--------|---------------|---------|
| `card` | `f_auto,q_auto,w_600,c_limit` | Vignettes catalogue |
| `header` | `f_auto,q_auto,w_1200,c_limit` | Photo principale fiche recette |
| `gallery` | `f_auto,q_auto,w_900,c_limit` | Carousel galerie |
| `thumb` | `f_auto,q_auto,w_300,c_limit` | Miniature formulaire |

Usage : `{{ photo.photo_url|cloudinary_img:"gallery" }}`

**Gestion des erreurs** :
- Upload Cloudinary échoué → message flash, pas de `RecipePhoto` créé
- Photo non trouvée → `get_object_or_404` → HTTP 404

---

---

## 5.22 Page Management (Chef Étoilé / Staff uniquement)

**URL** : `GET /management/` → `menu:management_page`
**Accès** : `is_staff` ou `role = chef_etoile`

### Actions disponibles

| Action | URL | Méthode | Description |
|--------|-----|---------|-------------|
| 🏗️ Construire la base | `POST /management/actions/build/` | POST | Lance `build_known_ingredients` — construit `KnownIngredient` depuis les noms d'ingrédients des recettes existantes |
| 🔗 Lier les recettes | `POST /management/actions/link/` | POST | Lance `match_ingredients` — associe `Ingredient` aux `KnownIngredient` existants |
| 🔄 Recalculer les macros | `POST /management/actions/recalculate/` | POST | Lance `recalculate_nutrition` — purge orphelins + recalcule toutes les macros |
| 📥 Import Ciqual | `POST /management/actions/import-ciqual/` | POST | Upload XLS → `import_ciqual --wipe` (efface et réimporte la table) |
| 🧹 Nettoyer Ciqual | `POST /management/actions/clean-ciqual/` | POST | Lance `clean_ciqual` — supprime plats composés et entrées sans kcal |
| 🗑️ Vider les recettes | `POST /management/actions/reset-recipes/` | POST | `reset_mode=recipes` — supprime Recipe + WeekPlan, conserve KnownIngredient |
| ⚠️ Reset complet | `POST /management/actions/reset-recipes/` | POST | `reset_mode=full` — supprime Recipe + KnownIngredient + WeekPlan |

Toutes les actions mutantes utilisent `@require_POST` et affichent un résumé via message flash.

### Référentiel Ciqual (CRUD)

**URL** : `GET /management/ciqual/` → `menu:gestion_ciqual_ref`

- Liste paginée (50/page) avec recherche texte et filtre par groupe alimentaire
- Chaque ligne est éditable inline (JS + AJAX `POST /management/ciqual/<ref_id>/`)
- Ajout d'une nouvelle entrée (formulaire collapsible, code `CUSTOM-XXXX` auto)
- Suppression avec confirmation (`POST /management/ciqual/<ref_id>/supprimer/`) — `SET_NULL` sur `KnownIngredient.ciqual_ref`
- Les entrées personnalisées sont distinguées par un badge "perso"

---

## 8. Fixtures de référence

### 8.1 Recette exemple — Hachis Parmentier

Fichier : `fixtures/recette-exemple-hachis-parmentier.json`

Recette complète (8 personnes) utilisée pour valider le modèle de données lors de la conception. Couvre les cas suivants :
- Ingrédients avec quantité nulle (sel, poivre, huile) → `quantity: null`
- Ingrédient optionnel (champignons) → `is_optional: true`
- Quantité en fourchette (150–200g champignons) → `quantity: 175, quantity_note: "150–200g"`
- Ingrédient présent dans deux groupes distincts (beurre) → test de l'agrégation liste de courses
- Timers par étape : 900s (mijoter), 2100s (cuisson four)
- Deux sections libres : `critique` + `difference`

---

## 9. Historique des migrations

| Migration | Date | Description |
|-----------|------|-------------|
| `0001_initial` | 2026-04-25 | Schéma initial — tous les modèles |
| `0002_calendar_fields` | 2026-04-26 | `UserProfile` : créneaux Google Calendar (4 TimeField) — `Meal` : `google_event_id` |
| `0003_intelligence_fields` | 2026-04-26 | `Recipe.protein_type` + `UserProfile.portions_factor` |
| `0004_nutrition_config` | 2026-04-26 | Modèle `NutritionConfig` singleton PNNS |
| `0005_recipe_photos` | 2026-04-26 | Modèle `RecipePhoto` — galerie photos recette |
| `0006_meal_absent_field` | 2026-04-27 | `Meal.absent` BooleanField (étape 25 — créneaux sans repas) |
| `0007_ciqual_ingredientref` | 2026-04-29 | Modèle `IngredientRef` (Ciqual 2020) + `Ingredient.ciqual_ref` FK |
| `0008_remove_openfoodfacts_id` | 2026-04-30 | Suppression du champ legacy Open Food Facts |
| `0009_synonymes_ingredientref` | 2026-04-30 | `IngredientRef.synonymes` TextField |
| `0010_known_ingredient` | 2026-05-01 | Modèle `KnownIngredient` — base de connaissance ingrédients |
| `0011_known_ingredient_fk_and_default_unit` | 2026-05-01 | `Ingredient.known_ingredient` FK + `KnownIngredient.default_unit` |
| `0012_recipe_nutrition_status` | 2026-05-02 | `Recipe.nutrition_status` CharField (`ok`/`partial`/`missing`) |
| `0013_ingredientref_new_nutrition_fields` | 2026-05-02 | `IngredientRef` : `sucres_100g`, `fibres_100g`, `ag_satures_100g`, `sel_100g` |

---

## 10. ChangeLog

| Version | Date | Description |
|---------|------|-------------|
| v1.0 | 2026-04-25 | Initialisation du projet — spec complète |
| v1.1 | 2026-04-25 | Ajout `Ingredient.quantity_note` + fixture Hachis Parmentier |
| v2.0 | 2026-04-26 | Application complète — Phases 1, 2 et 3 livrées (16 étapes) |
| v2.1 | 2026-04-26 | Phase 4 spécifiée — cadre PNNS, algo suggestions, dashboard individuel, alertes, galerie photos |
| v2.2 | 2026-04-26 | Étape 17 — `Recipe.protein_type` + `UserProfile.portions_factor` (migration 0003, formulaire recette, profil) |
| v2.3 | 2026-04-26 | Étape 18 — modèle `NutritionConfig` singleton PNNS (migration 0004, admin uniquement) |
| v2.4 | 2026-04-26 | Étape 19 — algorithme de suggestions de menu (5 dimensions pondérées, dialog planning, JS) |
| v2.5 | 2026-04-26 | Étape 20 — dashboard nutritionnel individuel + bloc "Pour toi" dans fiche recette |
| v2.6 | 2026-04-26 | Étape 21 — alertes équilibre planning (nudges Cuisinier, dismissables, sessionStorage) |
| v2.7 | 2026-04-26 | Étape 22 — galerie photos recette (carousel, upload Cloudinary, gestion Cuisinier) |
| v2.8 | 2026-04-26 | Étape 23 — notifications email (planning publié → Convives, proposition → Cuisiniers) |
| v2.9 | 2026-04-26 | Étape 24 — allergies enrichies : 16 tags EU, alertes par ingrédient, formulaire profil, page compatibilité famille |
| v3.0 | 2026-04-26 | Revue de code — B1 WeekPlan created_by, B2 prefetch photos, B3 profil N+1, S1-S3 spec, Q1-Q2 qualité |
| v3.1 | 2026-04-27 | Algo suggestions affiné — PS×WPD, poids dynamiques normalisés, bonus adéquation protéique dim.3, réponse JSON enrichie |
| v3.2 | 2026-04-29 | Intégration ANSES Ciqual 2020 — IngredientRef (3185 entrées), matching 74.3%, macros recalculées, autocomplete formulaire, suppression Open Food Facts |
| v4.0 | 2026-05-03 | Base de connaissance KnownIngredient — architecture deux couches Ciqual, badges nutrition_status, page CRUD référentiel Ciqual, page Management enrichie, refactoring nutrition unifiée, corrections bugs accumulation calories |
| v4.1 | 2026-05-03 | Calcul nutritionnel : ingrédients optionnels inclus (ne plus minorer les calories) |
| v4.2 | 2026-05-04 | Galerie photos opérationnelle — Cloudinary configuré, filtre `cloudinary_img` (4 presets) pour optimisation bande passante à l'affichage |

### Détail v2.0

**Phase 1 — MVP Core (étapes 1–9)**
- Structure Django : Procfile, requirements, settings dev/prod, context processor `IS_DEV`
- 15 modèles, migration initiale, fixture Hachis Parmentier
- Authentification email (inscription avec rôle, connexion, invitation famille par token)
- Catalogue recettes : liste avec filtres/tri/recherche, fiche complète avec infos nutritionnelles et alertes allergies
- Création/édition/suppression de recettes (Cloudinary, macros calculées depuis Ciqual, soft delete)
- Autocomplete ingrédients depuis référentiel local Ciqual 2020 (base PostgreSQL, hors-ligne)
- Planning hebdomadaire : grille 7j×2, AJAX, restes, publication, indicateurs nutritionnels
- Liste de courses : génération automatique agrégée, cochage AJAX avec optimistic UI
- PWA installable : manifest, service worker (cache-first/network-first), icônes, offline recettes
- Backup/Restore/Import recettes (ZIP + JSON) réservé aux is_staff

**Phase 2 — Mode Cuisine & Social (étapes 10–13)**
- Mode Cuisine mobile : étapes cochables, timers (Web Audio API), thème sombre, défilement auto
- Notation étoiles 1–5 (AJAX, historique multi-avis, avis famille)
- Propositions enrichies : placer dans un créneau, ignorer (Cuisinier), annuler (Convive)
- Gamification : rangs Cuisinier (Commis→Chef Exécutif) et Convive (Convive→Guide Michelin), page profil avec progression

**Phase 3 — Intégrations Google (étapes 14–16)**
- OAuth 2.0 Google custom (httpx, state CSRF, TokenOAuth, auto-refresh)
- Export Google Calendar : un événement par repas, créneaux configurables, create/update idempotent
- Export Google Tasks : une tâche par article non coché, format `{qty} {unité} {nom}`

**Revue de cohérence (2026-04-26)**
- Scope OAuth aligné sur `calendar.events` (moindre privilège)
- Spec 4.3/4.11 complétée (champs ajoutés en migration 0002)
- Règles publication planning et comportement Google non connecté corrigés dans la spec

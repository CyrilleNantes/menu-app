# Spécifications Fonctionnelles — Menu Familial

> Document vivant — mis à jour par l'IA après chaque implémentation validée.
> Version courante : **v1.1** — affichée dans le footer de l'application.
> Dernière mise à jour : 2026-04-25

---

## 1. Contexte, Objectifs et Limites

### 1.1 Objectif principal

Permettre à des familles de planifier leurs menus hebdomadaires, gérer un catalogue de recettes communautaire, générer automatiquement leurs listes de courses, et synchroniser le tout avec Google Calendar et Google Tasks.

### 1.2 Périmètre inclus

- Gestion des familles et invitation des membres
- Catalogue de recettes partagé (communauté globale)
- Fiche recette enrichie : ingrédients groupés, étapes avec timers, notes de chef, sections libres
- Calcul nutritionnel automatique via API Open Food Facts
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

### 1.3 Hors périmètre (Anti-Scope)

> ⚠️ CRITIQUE — L'IA ne doit jamais implémenter ce qui suit sans accord explicite.

- Ne PAS utiliser React, Vue ou tout framework JS — vanilla JS uniquement
- Ne PAS utiliser Supabase — Railway PostgreSQL uniquement
- Ne PAS utiliser SQLite — PostgreSQL en dev comme en prod
- Ne PAS exposer d'API REST publique (pas de DRF)
- Ne PAS implémenter Docker
- Ne PAS ajouter de système de messagerie entre utilisateurs
- Ne PAS implémenter de notifications (architecture prévue, implémentation ultérieure)
- Ne PAS implémenter de galerie de photos d'étapes (architecture prévue, implémentation ultérieure)
- Ne PAS gérer des allergies avec un moteur de règles complexe — tags simples uniquement
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
| Open Food Facts | Calcul nutritionnel des ingrédients | *(aucune clé requise — API publique)* | `integrations/openfoodfacts.py` |
| Cloudinary | Stockage et redimensionnement des photos | `CLOUDINARY_URL` | `integrations/cloudinary.py` |
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
- `https://www.googleapis.com/auth/calendar.events` (écriture événements)
- `https://www.googleapis.com/auth/tasks` (écriture tâches)

### 3.3 Open Food Facts

API publique REST, sans clé. Interrogée lors de la saisie d'un ingrédient pour suggérer les valeurs nutritionnelles.

Endpoint utilisé : `https://world.openfoodfacts.org/cgi/search.pl?search_terms={terme}&json=1`

Fallback : si aucun résultat, l'utilisateur saisit les valeurs manuellement.

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

**Propriété calculée `rank`** : calculée à partir du rôle et des contributions (non stockée en base).

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
| `calories_per_serving` | `FloatField` | oui | — | Kcal par portion (calculé) |
| `proteins_per_serving` | `FloatField` | oui | — | Protéines (g) par portion (calculé) |
| `carbs_per_serving` | `FloatField` | oui | — | Glucides (g) par portion (calculé) |
| `fats_per_serving` | `FloatField` | oui | — | Lipides (g) par portion (calculé) |
| `created_by` | `ForeignKey(User)` | non | — | Auteur |
| `actif` | `BooleanField` | non | `True` | Soft delete |
| `created_at` | `DateTimeField` | non | auto | Date de création |

**Tri par défaut** : `["-created_at"]`
**Soft delete** : `actif=False` masque la recette du catalogue sans suppression physique.

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
| `recipe` | `ForeignKey(Recipe)` | non | — | Recette parente |
| `group` | `ForeignKey(IngredientGroup)` | oui | — | Groupe (optionnel) |
| `name` | `CharField(200)` | non | — | Nom de l'ingrédient |
| `quantity` | `FloatField` | oui | — | Quantité (relative à `base_servings`) — valeur basse si fourchette |
| `quantity_note` | `CharField(50)` | oui | — | Précision libre sur la quantité (ex. "150–200g", "2 à 3 sachets") |
| `unit` | `CharField(50)` | oui | — | Unité (g, ml, c. à soupe…) |
| `is_optional` | `BooleanField` | non | `False` | Ingrédient optionnel |
| `category` | `CharField(50)` | oui | — | Catégorie courses (viandes, légumes, épicerie…) |
| `openfoodfacts_id` | `CharField(100)` | oui | — | ID produit Open Food Facts (si correspondance) |
| `calories` | `FloatField` | oui | — | Kcal pour la quantité définie |
| `proteins` | `FloatField` | oui | — | Protéines (g) |
| `carbs` | `FloatField` | oui | — | Glucides (g) |
| `fats` | `FloatField` | oui | — | Lipides (g) |
| `order` | `PositiveIntegerField` | non | `0` | Ordre dans le groupe |

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

### 4.15 `NotificationPreference` *(architecture prévue — non implémentée)*

| Champ | Type Django | Nullable | Défaut | Description |
|-------|-------------|----------|--------|-------------|
| `id` | `BigAutoField` | non | auto | Clé primaire |
| `user` | `ForeignKey(User)` | non | — | Utilisateur |
| `channel` | `CharField(20)` | non | — | `email` / `push` / `in_app` |
| `enabled` | `BooleanField` | non | `True` | Activé/désactivé |

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
**Accès** : Cuisinier uniquement

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
2. À la saisie de chaque ingrédient, une requête AJAX interroge `integrations/openfoodfacts.py` et retourne des suggestions de valeurs nutritionnelles
3. Les macros de la recette (`calories_per_serving` etc.) sont recalculées et sauvegardées à chaque enregistrement via `services.py`
4. Le calcul : somme des macros de tous les ingrédients / `base_servings`

**Gestion des erreurs** :
- Objet introuvable → `get_object_or_404` → HTTP 404
- Upload photo échoué → message flash, recette sauvegardée sans photo
- API Open Food Facts indisponible → suggestions vides, saisie manuelle

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

### 5.7 Recherche de valeurs nutritionnelles (AJAX)

**URL** : `GET /api/ingredients/nutrition/?q=<terme>` → `menu:recherche_nutrition`
**Vue** : `recherche_nutrition(request)`
**Accès** : Cuisinier uniquement

**Règles de gestion** :
1. Appelle `integrations/openfoodfacts.py` avec le terme
2. Retourne les 5 meilleurs résultats avec nom, calories, protéines, glucides, lipides pour 100g

**Réponse** :
- `{"ok": true, "results": [{"id": "...", "name": "...", "calories": 250, ...}]}`

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
2. Déclenche la (re)génération automatique de la liste de courses (appel `services.py`)

**Réponse** :
- Succès : redirection vers `/planning/<year>/<week>/` + message flash "Menu publié"

---

### 5.11 Propositions de repas

**URL** : `POST /planning/<id>/proposer/` → `menu:proposer_repas`
**Vue** : `proposer_repas(request, plan_id)`
**Accès** : Convive uniquement

**Règles de gestion** :
1. Crée un `MealProposal` lié à la famille et au planning

**Réponse** :
- Succès : `{"ok": true}` + mise à jour de l'UI

---

### 5.12 Génération de la liste de courses

**URL** : `POST /courses/generer/<plan_id>/` → `menu:generer_courses`
**Vue** : `generer_courses(request, plan_id)`
**Accès** : Cuisinier uniquement

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
- Google non connecté → redirection vers le flux OAuth
- Erreur API Google → message flash + log

**Réponse** :
- Succès : message flash "Menu exporté vers Google Agenda"

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
- Google non connecté → redirection vers le flux OAuth
- Erreur API Google → message flash + log

---

## 6. Comportements JavaScript

### 6.1 Formulaire recette — ajout dynamique d'ingrédients et d'étapes

**Fichier JS** : `static/menu/js/recette_form.js` — chargé avec `defer` sur `formulaire.html`

Comportements :
1. Bouton "Ajouter un ingrédient" : clone le dernier bloc ingrédient et incrémente les indices de nommage
2. Bouton "Ajouter un groupe" : crée un nouveau groupe vide
3. Bouton "Ajouter une étape" : clone la dernière étape et incrémente
4. À la saisie du nom d'un ingrédient (debounce 400ms) : appelle `/api/ingredients/nutrition/` et affiche les suggestions dans une dropdown

**Gestion des erreurs JS** :
- Si `/api/ingredients/nutrition/` ne répond pas → dropdown vide, saisie manuelle disponible

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

> [LOG 2026-04-25] Étape 1 complétée — Structure Django initialisée : Procfile Railway, requirements.txt complet (httpx, django-allauth, cloudinary ajoutés), .env corrigé (ENVIRONMENT=dev), structure app menu/ créée (urls.py, views.py, forms.py, services.py, integrations/, templatetags/, templates/menu/, static/menu/). Template base.html mobile-first avec bannière IS_DEV et footer v1.1. Django system check : 0 issues. Migrations Django core appliquées. collectstatic : 131 fichiers.

---

> [LOG 2026-04-25] Étape 3 complétée — Authentification custom (sans allauth) : InscriptionForm (rôle Cuisinier/Convive, création famille automatique), vues inscription/connexion/déconnexion/rejoindre_famille. LOGIN_URL, AUTHENTICATION_BACKENDS configurés. Templates mobile-first : inscription.html (JS toggle champ famille), connexion.html, rejoindre.html, planning/index.html (placeholder). Nav mise à jour avec liens auth contextuels. CSS formulaires ajouté. Allauth configuré en amont (ACCOUNT_SIGNUP_FIELDS) pour étape 14.

> [LOG 2026-04-25] Étape 2 complétée — 15 modèles créés dans models.py (Family, UserProfile, TokenOAuth, Recipe, IngredientGroup, Ingredient, RecipeStep, RecipeSection, Review, WeekPlan, Meal, MealProposal, ShoppingList, ShoppingItem, NotificationPreference). Tous enregistrés dans admin.py avec inlines et filtres. Migration 0001_initial appliquée sur Railway PostgreSQL. Commande `load_hachis_fixture` créée et testée : 3 groupes, 21 ingrédients, 6 étapes, 2 sections insérés sans erreur. Cas couverts validés : quantity_note champignons ('150–200g'), is_optional=True, timers 900s et 2100s.

---

## 9. Historique des migrations

| Migration | Date | Description |
|-----------|------|-------------|
| `0001_initial` | 2026-04-25 | Schéma initial — tous les modèles |

> [REVIEW 2026-04-25] `Ingredient` : ajout du champ `quantity_note (CharField 50, nullable)` — détecté lors du mapping de la recette Hachis Parmentier (cas des quantités en fourchette). La migration `0001_initial` intègre ce champ dès le départ.

---

## 10. ChangeLog

| Version | Date | Description |
|---------|------|-------------|
| v1.0 | 2026-04-25 | Initialisation du projet — spec complète |
| v1.1 | 2026-04-25 | Ajout `Ingredient.quantity_note` + fixture Hachis Parmentier |

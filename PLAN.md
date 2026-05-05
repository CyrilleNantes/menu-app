# PLAN.md — Plan de développement

> Ce fichier définit l'ordre strict d'implémentation.
> L'IA DOIT suivre cet ordre et NE PAS anticiper une étape ultérieure.
> Chaque étape est validée par l'utilisateur avant de passer à la suivante.
> Mettre à jour `spec.md` (LOG/DRAFT/REVIEW) après chaque étape complétée.

---

## Règle absolue

**Une étape à la fois.** Quand une étape est terminée, l'IA s'arrête et attend validation.
Elle ne commence pas l'étape suivante sans instruction explicite.

---

## Phase 1 — MVP Core ✅

### Étape 1 — Initialisation du projet Django ✅
### Étape 2 — Modèles et migration initiale ✅
### Étape 3 — Authentification et gestion des familles ✅
### Étape 4 — Catalogue recettes (lecture) ✅
### Étape 5 — Création et édition de recettes ✅
### Étape 6 — API nutritionnelle Open Food Facts ✅
### Étape 7 — Planning hebdomadaire ✅
### Étape 8 — Liste de courses ✅
### Étape 9 — PWA (Progressive Web App) ✅

---

## Phase 2 — Mode Cuisine & Social ✅

### Étape 10 — Mode Cuisine ✅
### Étape 11 — Notation et historique ✅
### Étape 12 — Propositions des Convives ✅
### Étape 13 — Gamification (rangs) ✅

---

## Phase 3 — Intégrations Google ✅

### Étape 14 — OAuth Google ✅
### Étape 15 — Export Google Calendar ✅
### Étape 16 — Export Google Tasks ✅

---

## Phase 4 — Intelligence

### Étape 17 — Migration : nouveaux champs pour l'intelligence

Avant tout algorithme, deux champs manquants à ajouter via migration :

**Sur `Recipe` :**
- `protein_type` : `CharField(20)`, nullable, valeurs : `boeuf` / `volaille` / `porc` / `poisson` / `oeufs` / `legumineuses` / `autre` / `aucune`
- Ajouter le champ dans le formulaire recette (étape 5) et dans l'admin

**Sur `UserProfile` :**
- `portions_factor` : `FloatField`, défaut `1.0` — facteur de portion individuel pour le calcul nutritionnel personnalisé
  - Adulte référence : 1.0
  - Ado garçon 15–16 ans : suggérer 1.3 par défaut selon l'âge
  - Ado fille 13 ans : suggérer 0.9 par défaut selon l'âge
  - Configurable librement dans le profil utilisateur

**Migration** : `0002_intelligence_fields`

**✅ Livrable : migration appliquée, champs visibles dans admin et formulaire recette**

---

### Étape 18 — Cadre nutritionnel de référence (PNNS)

Implémenter les objectifs nutritionnels basés sur le Programme National Nutrition Santé (ANSES France). Ces valeurs sont des **guidelines publiques de bonne pratique**, pas des prescriptions médicales. Toujours affichées comme des repères indicatifs.

**Nouveau modèle `NutritionConfig` (singleton admin) :**

| Paramètre | Valeur par défaut | Description |
|-----------|------------------|-------------|
| `calories_dinner_target` | 850 | Cibles kcal pour un dîner (adulte référence) |
| `proteins_dinner_target` | 27 | Cibles protéines g pour un dîner (adulte référence) |
| `max_red_meat_per_week` | 3 | Nombre max de repas viande rouge par semaine |
| `min_fish_per_week` | 1 | Nombre min de repas poisson par semaine |
| `min_vegetarian_per_week` | 1 | Nombre min de repas végétarien par semaine |
| `min_days_before_repeat` | 14 | Jours minimum avant de replanifier un même plat |
| `min_days_low_rated_repeat` | 21 | Jours minimum avant de replanifier un plat noté < 2★ par la famille |

**Migration** : `0003_nutrition_config`

**✅ Livrable : modèle `NutritionConfig` configurable dans l'admin Django**

---

### Étape 19 — Algorithme de suggestions de menu

Implémentation dans `services.py` : fonction `suggerer_recettes(family, week_plan, date, meal_time)`.

Chaque recette candidate reçoit un **score composite 0–1** sur 5 dimensions pondérées. Retourne les 5 meilleures.

**Dimension 1 — Fraîcheur / rotation** (poids 30%)
- Jours depuis le dernier `Meal` de cette recette pour cette famille
- Score = 0 si < `min_days_before_repeat` jours (exclusion douce)
- Score = 0 si < `min_days_low_rated_repeat` jours ET note famille < 2★ (exclusion forte)
- Score linéaire entre 0.3 et 1.0 au-delà du seuil (1.0 si jamais cuisiné)

**Dimension 2 — Appréciation famille** (poids 30%)
- Moyenne des `Review.stars` des membres de **cette famille uniquement** (pas note globale)
- Score = note_moyenne / 5
- Score neutre 0.5 si aucun avis famille

**Dimension 3 — Variété protéines sur la semaine** (poids 20%)
- Analyse les `protein_type` déjà planifiés dans le `WeekPlan`
- Score = 0 (règle dure) si : même `protein_type` déjà 2× dans la journée OU viande rouge déjà 3× dans la semaine
- Bonus +0.3 si ce `protein_type` est absent de la semaine
- Malus −0.2 si ce `protein_type` déjà présent 2× dans la semaine

**Dimension 4 — Saisonnalité** (poids 10%)
- Recette compatible saison courante → 1.0
- Recette toutes saisons → 0.7
- Recette incompatible → 0.2

**Dimension 5 — Équilibre nutritionnel de la semaine** (poids 10%)
- Compare calories et protéines déjà planifiées aux cibles hebdomadaires (`NutritionConfig × 7`)
- Si semaine déjà > 110% objectif calorique → favorise les recettes avec `health_tag = "leger"` (+0.2)
- Si semaine < 70% objectif protéines → favorise les recettes avec `health_tag = "proteine"` (+0.2)
- Nudge uniquement, jamais de score 0

**Interface :**
- Bouton "💡 Suggestions" sur chaque créneau vide du planning
- Affiche les 5 recettes proposées avec icônes de justification :
  🔄 fraîcheur · ⭐ avis famille · 🥩 variété · 🌿 saison · ⚖️ équilibre
- Choix libre — le Cuisinier peut ignorer et choisir autre chose

**✅ Livrable : bouton Suggestions → 5 recettes proposées avec justification visible**

---

### Étape 20 — Dashboard nutritionnel individuel

Vue accessible depuis le profil ou le planning : `/profil/nutrition/`

**Principe clé : tout est calculé par utilisateur**, en appliquant son `portions_factor`.
`macros_affichées = macros_recette_par_portion × portions_factor_utilisateur`

**Contenu — Vue semaine :**
- Liste des repas planifiés avec, pour cet utilisateur : calories estimées + protéines estimées
- Total journalier et hebdomadaire
- Barre de progression vs cibles (`NutritionConfig × portions_factor`) :
  - 🟢 Dans la cible (80–110%)
  - 🟡 Légèrement hors cible (60–80% ou 110–130%)
  - 🔴 Significativement hors cible (< 60% ou > 130%)

**Contenu — Dans la fiche recette :**
- Bloc "Pour toi" : `~750 kcal · 32g de protéines`
- Petit, discret, basé sur `portions_factor`

**Ce qu'on n'affiche PAS :**
- Pas de total famille agrégé (pas parlant)
- Pas de graphes complexes
- Pas de recommandations médicales
- Mention systématique : "Valeurs estimées — repères indicatifs PNNS"

**✅ Livrable : voir mes macros personnelles pour la semaine, différentes de celles d'un ado**

---

### Étape 21 — Alertes équilibre (nudges)

Alertes légères affichées dans la vue planning. Jamais bloquantes, jamais en modal.

**Règles (basées sur `NutritionConfig`) — banderoles dismissables :**

| Condition | Message |
|-----------|---------|
| 0 repas poisson planifié sur la semaine | 🐟 Pensez à intégrer un repas poisson cette semaine |
| 3+ repas viande rouge planifiés | 🥩 Vous avez déjà 3 repas de viande rouge cette semaine |
| 0 repas végétarien planifié | 🥦 Un repas végétarien serait bienvenu |
| Calories semaine > 130% objectif | ⚠️ La semaine semble chargée en calories |
| Protéines semaine < 60% objectif | 💪 Les protéines sont un peu faibles cette semaine |

- Recalculées à chaque modification du menu
- Dismissable par session (réapparaissent si le menu change)
- Visibles uniquement par le Cuisinier dans la vue planning

**✅ Livrable : alertes visibles dans le planning, disparaissent quand le menu s'équilibre**

---

## Phase 5 — Extensions

### Étape 22 — Galerie photos ⚡ Priorité remontée

Priorité remontée par rapport à la planification initiale : l'expérience sans visuels est trop austère en usage réel.

**Migration `0004_recipe_photos` — nouveau modèle `RecipePhoto` :**

| Champ | Type | Description |
|-------|------|-------------|
| `recipe` | ForeignKey(Recipe) | Recette parente |
| `photo_url` | URLField | URL Cloudinary |
| `caption` | CharField(100), nullable | Légende optionnelle |
| `is_main` | BooleanField, défaut False | Photo principale de la galerie |
| `order` | PositiveIntegerField | Ordre d'affichage |
| `uploaded_by` | ForeignKey(User) | Auteur de l'upload |
| `created_at` | DateTimeField auto | Date d'upload |

**Fonctionnalités :**
- Upload de photos supplémentaires depuis la fiche recette (tout utilisateur connecté)
- Galerie sous la photo principale (carousel vanilla JS)
- Le Cuisinier peut promouvoir une photo Convive en photo principale
- Soft delete : retrait possible par le Cuisinier

**✅ Livrable : galerie de photos sur la fiche recette, upload possible par les Convives**

---

### Étape 23 — Notifications email

**Cas d'usage prioritaires :**
- Menu publié → email aux Convives de la famille
- Nouvelle proposition de repas → email au(x) Cuisinier(s) de la famille

**Implémentation :**
- `django.core.mail` + SMTP via variables d'env Railway (`EMAIL_HOST`, `EMAIL_HOST_USER`, `EMAIL_HOST_PASSWORD`)
- Respecte `NotificationPreference` déjà en base
- Pas de push notifications à cette étape

**✅ Livrable : email reçu quand le menu de la semaine est publié**

---

### Étape 24 — Gestion des allergies enrichie

> Nice to have — implémenter uniquement sur demande explicite.

- Enrichir la liste fixe d'allergènes (ajouter : noix, soja, crustacés, céleri, moutarde…)
- Alertes par ingrédient (pas seulement par recette)
- Page "compatibilité" listant les membres incompatibles et pourquoi

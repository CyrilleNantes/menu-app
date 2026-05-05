# 🍽️ Cahier des Charges — Menu Familial App
> Version 0.5 — Algo suggestions affiné · Avril 2026

---

## 1. Contexte & Objectifs

Application web communautaire (PWA mobile-first) de gestion de recettes, planification des menus et génération de listes de courses — pour un usage familial élargi (~15–20 utilisateurs, plusieurs familles).

**Principes directeurs :**
- Mobile-first (PWA installable, utilisable en cuisine sans PC)
- Catalogue de recettes communautaire partagé entre toutes les familles
- Planning et courses isolés par famille
- Équilibre nutritionnel piloté automatiquement via API
- Intégration native Google Calendar & Tasks
- Architecture évolutive sans fermer de portes

---

## 2. Utilisateurs, Rôles & Gamification

### Structure des familles
- Un **Cuisinier** crée sa famille et invite les membres (par email ou lien)
- Chaque utilisateur appartient à une famille
- Les recettes sont partagées globalement ; menus, courses et membres sont propres à chaque famille

### 🏆 Chef Étoilé (Admin global)
- Gestion de la plateforme (utilisateurs, familles, signalements)
- Accès à toutes les fonctionnalités

### Rôle Cuisinier — Progression par rangs

| Rang | Nom | Critères indicatifs |
|------|-----|---------------------|
| 1 | Commis | Rôle de départ |
| 2 | Cuisinier | 5 recettes ajoutées |
| 3 | Chef de Partie | 15 recettes, diversité de cuisines |
| 4 | Sous-Chef | 30 recettes, recettes complexes |
| 5 | Chef Exécutif | Contributeur majeur |

> Le rang est une propriété calculée dynamiquement — pas stocké en base.

### Rôle Convive — Progression par rangs

| Rang | Nom | Critères indicatifs |
|------|-----|---------------------|
| 1 | Convive | Rôle de départ |
| 2 | Gourmet | 5 recettes notées |
| 3 | Épicurien | 15 avis + commentaires |
| 4 | Critique | Propositions régulières + avis détaillés |
| 5 | Guide Michelin | Contributeur très actif, avis influents |

---

## 3. Module Recettes

### 3.1 Format de la Fiche Recette

**Métadonnées :**
- Titre + description courte
- Photo principale + galerie de photos supplémentaires (upload par tout utilisateur)
- Nombre de parts de référence
- Temps de préparation / cuisson / total
- Catégorie : Entrée / Plat / Dessert / Brunch / Snack
- Type de cuisine (tag libre)
- Saisonnalité : Printemps / Été / Automne / Hiver (multi-select)
- Tags santé : Léger / Équilibré / Plaisir raisonné / Protéiné / Végétarien / Végétalien
- Niveau de complexité : Simple / Intermédiaire / Élaboré
- **Type de protéine principale** : Bœuf / Volaille / Porc / Poisson / Œufs / Légumineuses / Autre / Aucune *(nouveau — utilisé par l'algorithme de suggestions)*

**Ingrédients (obligatoire) :** groupes nommés, quantité, unité, catégorie courses, valeurs nutritionnelles via Open Food Facts

**Étapes pas à pas (obligatoire) :** numérotées, notes de chef, timers

**Sections libres (optionnel) :** Points critiques / Ce qui fait la différence / Conseils du chef

### 3.2 Données Nutritionnelles — Via API Open Food Facts

Auto-complétion à la saisie, macros agrégées automatiquement, saisie manuelle en fallback.

### 3.3 Système de Notation

Étoiles 1–5, plusieurs avis par utilisateur dans le temps, historique conservé, vue par membre de la famille.

### 3.4 Allergies & Régimes (léger)

Tags simples sur profil, bandeau d'avertissement non bloquant sur la fiche recette.

---

## 4. Mode Cuisine (Mobile)

Vue dédiée avec ingrédients cochables, étapes cochables, timers par étape (comme l'app muscu), grande police, boutons larges, fonctionne hors-ligne via cache PWA.

---

## 5. Module Planning Menu

### 5.1 Période paramétrable par Cuisinier
Chaque Cuisinier définit son propre découpage (ex. vendredi → jeudi). La liste de courses est cohérente avec cette période.

### 5.2 Structure du menu
2 repas par jour (midi / soir), créneaux vides autorisés, nombre de parts paramétrable par repas.

### 5.3 Repas avec restes
Option cochable "Ce repas couvre [repas cible]" — pas de doublon dans la liste de courses.

### 5.4 Propositions des Convives
Suggestion de recette + message → visible par le Cuisinier dans le planning. Placeable directement dans un créneau.

### 5.5 Suggestions automatiques de menu

Algorithme à score composite — bouton "💡 Suggestions" sur chaque créneau vide. Retourne 5 recettes triées par pertinence, avec justification visible par dimension.

#### Les 5 dimensions du score

**🔄 Fraîcheur / rotation (poids variable — nominal 30%)** — Éviter la répétition
- Seuil minimal : 14 jours avant de replanifier un plat pour cette famille
- Seuil renforcé : 21 jours si le plat est noté < 2★ par la famille
- Score linéaire 0.3→1.0 au-delà du seuil, 1.0 si jamais cuisiné, 0 si sous le seuil

**⭐ Appréciation famille (poids variable — nominal 30%)** — Faire plaisir
- Moyenne des étoiles des membres de **cette famille uniquement** (pas la note globale)
- Score = note_famille / 5 · Score neutre 0.5 si aucun avis famille

**🥩 Variété protéines (poids variable — nominal 20%)** — Diversité + bonus adéquation
- Règles dures (score 0) : même `protein_type` déjà 2× dans la journée, ou viande rouge ≥ 3× dans la semaine
- Bonus +0.3 si ce `protein_type` absent de la semaine, malus −0.2 si déjà 2× dans la semaine
- **Bonus adéquation** +0.1 si `proteins_per_serving > 25g` (plafonné à 1.0) — un plat très protéiné bénéficie d'un avantage même si son type est déjà présent

**🌿 Saisonnalité (poids variable — nominal 10%)** — Manger de saison
- Compatible saison courante → 1.0 · Toutes saisons → 0.7 · Incompatible → 0.2

**⚖️ Adéquation protéique + équilibre (poids variable — nominal 10%, jusqu'à 25%)** — Nudge intelligent

C'est la dimension qui évolue le plus. Elle combine deux sous-signaux :

*Protein Score (PS) — basé sur `proteins_per_serving` réel :*
```
proteins_per_serving non renseigné → PS = 0.5  (neutre)
< 15g par portion                  → PS = 0.3  (faible)
15 – 25g par portion               → PS = 0.6  (correct)
> 25g par portion                  → PS = 1.0  (élevé)
```

*Weekly Protein Deficit factor (WPD) — calculé dynamiquement sur la semaine :*
```
proteins_planned = Σ protéines des repas déjà planifiés (portions × factor admin 1.0)
proteins_target  = NutritionConfig.proteins_dinner_target × repas_restants_semaine

deficit_ratio = proteins_planned / proteins_target
→ < 0.6  : WPD = 1.5  (déficit fort — boost significatif)
→ < 0.8  : WPD = 1.2  (déficit modéré — boost léger)
→ sinon  : WPD = 1.0  (dans la cible — comportement nominal)
```

*Score dimension 5 :*
```
score_nutrition = min(PS × WPD, 1.0)
```

#### Poids dynamiques normalisés selon WPD

Les poids s'ajustent selon le déficit hebdomadaire en protéines, toujours normalisés à 100% :

| Situation | Fraîcheur | Appréciation | Variété | Saisonnalité | Nutrition |
|-----------|-----------|--------------|---------|--------------|-----------|
| Nominal (WPD 1.0) | 30% | 30% | 20% | 10% | 10% |
| Déficit modéré (WPD 1.2) | 27% | 27% | 18% | 9% | 19% |
| Déficit fort (WPD 1.5) | 25% | 25% | 17% | 8% | 25% |

**Comportement clé** : quand la semaine est équilibrée en protéines, l'algo se comporte exactement comme avant. Il ne s'adapte que quand c'est utile.

#### Score final
```
score = Σ(score_dimension × poids_normalisé)
```

#### UX — Affichage des suggestions
- 5 recettes proposées avec icônes de justification :
  `🔄 rotation · ⭐ avis famille · 🥩 variété · 🌿 saison · ⚖️ équilibre`
- Indicateur protéines sur chaque carte : `🥩 12g` / `🥩🥩 20g` / `🥩🥩🥩 32g`
- Justification enrichie si WPD > 1.0 : `⚖️ Semaine en déficit protéique · Cette recette apporte 32g`
- Sélection libre — le Cuisinier peut ignorer et choisir autre chose

### 5.6 Validation et publication
Brouillon → Publié. Modification possible après publication.

---

## 6. Module Liste de Courses

Génération automatique agrégée, dédoublonnage, regroupement par catégorie, cochage mobile, modification manuelle, export Google Tasks.

---

## 7. Intégrations Google

OAuth Google par utilisateur, export menu → Google Calendar, export courses → Google Tasks. Créneaux configurables dans le profil.

---

## 8. Cadre Nutritionnel — Repères PNNS

> ⚠️ Ces données sont des **repères indicatifs de bonne pratique** issus du Programme National Nutrition Santé (ANSES France). Elles ne constituent pas des recommandations médicales et ne remplacent pas l'avis d'un professionnel de santé. Toujours affichées avec cette mention dans l'app.

### 8.1 Objectifs journaliers de référence (adulte)

L'app utilise un adulte de référence (`portions_factor = 1.0`) dont les besoins estimés au dîner sont :
- **Calories** : ~850 kcal (≈ 35% de 2 400 kcal/jour)
- **Protéines** : ~27 g (≈ 35% de 75 g/jour)

Ces valeurs sont configurables dans les paramètres admin — elles ne sont pas gravées dans le code.

### 8.2 Facteur de portion individuel (`portions_factor`)

Chaque utilisateur a un `portions_factor` qui personalise les calculs nutritionnels **sans changer les recettes** :

| Profil | `portions_factor` suggéré |
|--------|--------------------------|
| Adulte référence | 1.0 |
| Ado garçon 15–16 ans (croissance + sport) | 1.3 |
| Ado fille 13 ans | 0.9 |

Ce facteur est modifiable librement dans le profil utilisateur. Il est suggéré automatiquement à l'inscription selon l'âge si renseigné.

**Calcul** : `macros affichées pour cet utilisateur = macros_par_portion × portions_factor`

Exemple : Hachis Parmentier à 750 kcal / portion → affiché **975 kcal** pour un ado garçon (×1.3).

### 8.3 Règles de diversité alimentaire (PNNS)

Utilisées par l'algorithme de suggestions ET les alertes planning :

| Règle | Valeur par défaut |
|-------|------------------|
| Max viande rouge (bœuf + porc) / semaine | 3 repas |
| Min poisson / semaine | 1 repas |
| Min végétarien / semaine | 1 repas |
| Délai min avant répétition d'un plat | 14 jours |
| Délai min si plat mal noté (< 2★ famille) | 21 jours |

### 8.4 Dashboard nutritionnel individuel

Vue `/profil/nutrition/` — affiche pour l'utilisateur connecté :
- Ses macros estimées pour chaque repas de la semaine (calculées avec son `portions_factor`)
- Total journalier et hebdomadaire avec indicateur de progression :
  - 🟢 Dans la cible (80–110%)
  - 🟡 Légèrement hors cible (60–80% ou 110–130%)
  - 🔴 Significativement hors cible (< 60% ou > 130%)
- Bloc "Pour toi" sur chaque fiche recette : `~X kcal · Yg protéines`

**Pas de vue agrégée famille** — chaque utilisateur voit ses propres données uniquement.

### 8.5 Alertes équilibre dans le planning

Banderoles non bloquantes, dismissables, visibles uniquement par le Cuisinier :

| Condition | Alerte |
|-----------|--------|
| Aucun repas poisson planifié | 🐟 Pensez à intégrer un repas poisson |
| Viande rouge ≥ 3 repas | 🥩 Déjà X repas de viande rouge cette semaine |
| Aucun repas végétarien | 🥦 Un repas végétarien serait bienvenu |
| Calories semaine > 130% objectif | ⚠️ La semaine semble chargée en calories |
| Protéines semaine < 60% objectif | 💪 Les protéines sont un peu faibles |

---

## 9. Architecture Technique

| Composant | Technologie |
|-----------|-------------|
| Framework web | Django + templates, vues fonctions |
| Frontend | Vanilla JS (PWA) |
| Base de données | PostgreSQL sur Railway |
| Auth | Django auth + django-allauth (email + Google OAuth) |
| Stockage photos | Cloudinary |
| API nutritionnelle | Open Food Facts (public, sans clé) |
| Intégration Google | Google OAuth 2.0 + APIs Calendar & Tasks |
| Déploiement | Railway (env dev + prod) |

---

## 10. Modèle de Données — Entités Principales

```
Family
└── id, name, created_by, invite_token

UserProfile
├── user, family, role: chef_etoile | cuisinier | convive
├── dietary_tags[], portions_factor (défaut 1.0)  ← nouveau
└── google_calendar_id, google_tasklist_id, créneaux Calendar

TokenOAuth
└── user, service: "google", access_token, refresh_token, expires_at

Recipe  ← catalogue global partagé
├── id, title, description, photo_url, base_servings
├── prep_time, cook_time, category, cuisine_type
├── seasons[], health_tags[], complexity, protein_type  ← nouveau
├── calories_per_serving, proteins_per_serving, carbs_per_serving, fats_per_serving
└── created_by, actif (soft delete)

NutritionConfig  ← singleton admin  ← nouveau
└── calories_dinner_target, proteins_dinner_target
    max_red_meat_per_week, min_fish_per_week, min_vegetarian_per_week
    min_days_before_repeat, min_days_low_rated_repeat

RecipePhoto  ← nouveau
└── recipe, photo_url (Cloudinary), caption, is_main, order, uploaded_by, actif

IngredientGroup → Ingredient (groupes nommés, quantité, unité, quantity_note, macros, openfoodfacts_id)
RecipeStep (instruction, chef_note, timer_seconds)
RecipeSection (section_type, title, content)
Review (stars 1–5, comment, created_at — plusieurs par user)
MealProposal (family, recipe, proposed_by, message, week_plan)
WeekPlan (family, period_start, period_end, status: draft|published)
Meal (week_plan, date, meal_time, recipe, servings_count, is_leftovers, source_meal, google_event_id)
ShoppingList → ShoppingItem (name, quantity, unit, category, checked)
NotificationPreference (user, channel, enabled — architecture prévue)
```

---

## 11. Roadmap — Phases de Développement

### Phase 1 — MVP Core ✅
Auth, familles, CRUD recettes, planning, courses, PWA

### Phase 2 — Mode Cuisine & Social ✅
Mode cuisine, notation, propositions, gamification

### Phase 3 — Intégrations Google ✅
OAuth, export Calendar, export Tasks

### Phase 4 — Intelligence (en cours)
- Migration : `protein_type` sur Recipe + `portions_factor` sur UserProfile + `NutritionConfig` + `RecipePhoto`
- Algorithme de suggestions de menu (score composite 5 dimensions)
- Dashboard nutritionnel individuel
- Alertes équilibre dans le planning
- Galerie photos recette

### Phase 5 — Extensions futures
- Notifications email (menu publié, nouvelle proposition)
- Gestion des allergies enrichie

---

## 12. Points Fermés ✅

| Sujet | Décision |
|-------|----------|
| Stack | Django + PostgreSQL Railway + vanilla JS + Cloudinary |
| Auth | django-allauth email + Google OAuth |
| Données nutritionnelles | Open Food Facts auto-complétion + saisie manuelle fallback |
| Format recette | Enrichi (groupes, notes chef, sections libres, galerie photos) |
| Isolation familles | Familles isolées, catalogue recettes global partagé |
| Notation | Étoiles 1–5, plusieurs avis par utilisateur dans le temps |
| Dashboard nutritionnel | Individuel uniquement, basé sur `portions_factor` |
| Cadre nutritionnel | Repères PNNS indicatifs, configurables admin, jamais médical |
| Variété protéines | Tag `protein_type` sur la recette, 8 valeurs possibles |
| Suggestions menu | Algo score composite 5 dimensions, poids dynamiques selon déficit protéique hebdomadaire |
| Protein Score | Basé sur `proteins_per_serving` réel (< 15g / 15–25g / > 25g), pas sur `protein_type` seul |
| Poids dynamiques | WPD 1.0 (nominal) → 1.2 (déficit modéré) → 1.5 (déficit fort) — poids nutrition monte jusqu'à 25% |
| Alertes planning | Banderoles non bloquantes, dismissables, Cuisinier uniquement |
| Galerie photos | Upload tout utilisateur, gestion (retrait/promotion) par Cuisinier |
| Notifications | Email uniquement, implémentation ultérieure |
| Déploiement | Railway uniquement (dev + prod) |

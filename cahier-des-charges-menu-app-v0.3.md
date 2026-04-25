# 🍽️ Cahier des Charges — Menu Familial App
> Version 0.3 — Stack validée · Avril 2026

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

---

### Rôle Cuisinier — Progression par rangs

Basée sur : fréquence de contribution, complexité des recettes ajoutées, diversité des cuisines (tag `cuisine_type` sur la recette : française, asiatique, méditerranéenne...).

| Rang | Nom | Critères indicatifs |
|------|-----|---------------------|
| 1 | Commis | Rôle de départ |
| 2 | Cuisinier | 5 recettes ajoutées |
| 3 | Chef de Partie | 15 recettes, diversité de cuisines |
| 4 | Sous-Chef | 30 recettes, recettes complexes |
| 5 | Chef Exécutif | Contributeur majeur |

> Le Chef Étoilé reste au-dessus de la progression, c'est le rôle admin plateforme.
> Le rang est une propriété calculée dynamiquement — pas stocké en base.

---

### Rôle Convive — Progression par rangs

Basée sur : avis donnés, commentaires, propositions de repas, participation au fil du temps.

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

Inspiré de CookLang mais enrichi — rien n'est bloquant sauf les ingrédients et les étapes de base.

**Métadonnées :**
- Titre + description courte
- Photo principale du plat (upload — galerie d'étapes possible plus tard sans casser l'archi)
- Nombre de parts de référence (base de calcul des quantités et des apports nutritionnels)
- Temps de préparation / cuisson / total
- Catégorie : Entrée / Plat / Dessert / Brunch / Snack
- Type de cuisine : Française / Asiatique / Méditerranéenne / Italienne / Autre… (tag libre)
- Saisonnalité : Printemps / Été / Automne / Hiver (multi-select)
- Tags santé : Léger / Équilibré / Plaisir raisonné / Protéiné / Végétarien / Végétalien (multi-select)
- Niveau de complexité : Simple / Intermédiaire / Élaboré (impact sur la progression du Cuisinier)

**Ingrédients (obligatoire) :**
- Organisés en **groupes nommés** (ex. "Base viande", "Purée", "Finition")
- Chaque ingrédient : nom, quantité, unité, catégorie courses (viandes / légumes / épicerie…)
- Valeurs nutritionnelles récupérées automatiquement via API au moment de la saisie (voir 3.2)
- Options marquées comme telles (ex. "option recommandée : champignons")

**Étapes pas à pas (obligatoire) :**
- Numérotées, texte libre
- Notes de chef optionnelles inline (👉 conseils, résultats attendus)
- Timer optionnel par étape (utilisé dans le "Mode Cuisine" mobile)

**Sections libres (optionnel, richesse de la recette) :**
- ⚠️ Points critiques
- 🎯 Ce qui fait vraiment la différence
- 💡 Conseils du chef / variantes

### 3.2 Données Nutritionnelles — Via API

Au moment de la saisie d'un ingrédient, l'app interroge **Open Food Facts** (API publique, open source, très riche en produits FR). L'utilisateur sélectionne la correspondance dans une liste de suggestions. Les macros (calories, protéines, glucides, lipides) sont stockées par ingrédient et agrégées automatiquement à la recette entière, ramenées à la portion selon le nombre de parts.

Saisie manuelle possible en fallback si aucune correspondance API.

### 3.3 Système de Notation

- Notation par **étoiles 1–5**
- Plusieurs avis possibles par utilisateur dans le temps (les goûts évoluent)
- Chaque avis : utilisateur, date, note, commentaire optionnel
- Historique complet conservé et consultable
- Vue par membre de la famille (préférences individuelles)
- Affichage : note moyenne globale + évolution dans le temps

### 3.4 Allergies & Régimes (léger)

- Chaque utilisateur renseigne ses intolérances dans son profil (liste fixe : gluten, lactose, fruits à coque, végétarien…)
- Les recettes incompatibles affichent un bandeau d'avertissement — pas de blocage
- Pas d'usine à gaz : tags simples, pas de moteur de règles complexe

---

## 4. Mode Cuisine (Mobile)

Vue dédiée activée depuis la fiche recette, pensée pour être utilisée en cuisine avec les mains occupées.

- **Ingrédients cochables** : sortir au fur et à mesure
- **Étapes cochables** : progression visuelle, l'étape courante est mise en avant
- **Timers par étape** : se lancent à la validation de l'étape (comme l'app muscu)
- Interface grande police, contraste élevé, boutons larges
- Fonctionne hors-ligne si recette déjà chargée (PWA cache)

---

## 5. Module Planning Menu

### 5.1 Période paramétrable par Cuisinier
- Chaque Cuisinier définit son propre découpage (ex. vendredi → jeudi, ou mercredi → mardi)
- La liste de courses générée est cohérente avec cette période
- Plusieurs Cuisiniers dans une même famille peuvent coexister — la liste de courses est agrégée pour la famille

### 5.2 Structure du menu
- 2 repas par jour : **déjeuner** (midi) et **dîner** (soir)
- Les créneaux peuvent être laissés vides (travail, cantine, repas extérieur)
- Pour chaque repas : sélection d'une recette + nombre de parts à préparer

### 5.3 Repas avec restes
- Option cochable sur un repas : "Ce repas couvre aussi [repas cible]"
- Exemple : Hachis Parmentier dimanche soir pour 8 → couvre le dîner du lundi
- Le repas cible est automatiquement renseigné et marqué "restes" (pas de doublon d'ingrédients dans la liste de courses)

### 5.4 Propositions des Convives
- Un Convive peut suggérer une recette pour une période donnée + message optionnel
- Les propositions sont visibles par le Cuisinier dans l'interface de composition du menu
- Le Cuisinier reste libre de valider ou non

### 5.5 Suggestions automatiques
Le système peut proposer des recettes pour compléter le menu, en tenant compte de :
- Saisonnalité actuelle
- Équilibre nutritionnel de la semaine (objectifs calories / protéines)
- Variété : éviter les répétitions récentes (historique des menus)
- Préférences : favoriser les recettes bien notées par les membres de la famille
- Propositions des Convives en attente

### 5.6 Validation et publication
- Menu en statut **Brouillon** pendant la composition
- Le Cuisinier publie → statut **Publié**
- Les Convives voient le menu publié
- Modification possible après publication

---

## 6. Module Liste de Courses

### 6.1 Génération automatique
- Agrège tous les ingrédients du menu validé de la famille
- Recalcul des quantités selon le nombre de parts de chaque repas
- Dédoublonnage et addition des ingrédients identiques (même nom + même unité)
- Les repas "restes" ne génèrent pas de doublon

### 6.2 Gestion de la liste
- Modification manuelle possible (ajout, suppression, ajustement)
- **Cochage des articles** au fur et à mesure des courses (vue mobile)
- Regroupement par catégorie (catégorie héritée de l'ingrédient dans la recette, modifiable manuellement)

### 6.3 Export Google Tasks
- Bouton "Exporter vers Google Tasks" → pousse vers la liste "Course" de l'utilisateur
- Chaque ingrédient = une tâche : `"{quantité} {unité} {nom}"`

---

## 7. Intégrations Google

### 7.1 Google Calendar
- Export du menu publié → événements dans le calendrier "Menu"
- Format : `[Titre recette]` sur le créneau paramétré (ex. 12h–13h / 20h30–21h30)
- Mis à jour si le menu est modifié après publication

### 7.2 Google Tasks
- Export liste de courses → liste "Course" dans Google Tasks

### 7.3 Authentification
- OAuth Google par utilisateur (scopes : Calendar write + Tasks write)
- Configuration des cibles (calendrier, liste Tasks) dans les paramètres utilisateur

---

## 8. Architecture Technique

| Composant | Technologie | Justification |
|-----------|-------------|---------------|
| Framework web | Django + templates | Stack standard du projet, vues fonctions |
| Frontend | Vanilla JS (PWA) | Cohérent Claude.md — pas de framework JS |
| Base de données | PostgreSQL sur Railway | Dev et prod, pas de SQLite |
| Auth | Django auth + django-allauth | Login email + Google OAuth |
| Stockage photos | Cloudinary | Railway filesystem éphémère — upload via `integrations/cloudinary.py` |
| API nutritionnelle | Open Food Facts | Open source, FR, gratuit, via `integrations/openfoodfacts.py` |
| Intégration Google | Google OAuth 2.0 + APIs Calendar & Tasks | Via `integrations/google_calendar.py` et `integrations/google_tasks.py` |
| Déploiement | Railway (unique — env dev + prod) | Cohérent Claude.md |
| Notifications | Architecture prévue, implémentation ultérieure | Ne pas fermer la porte |
| Photos d'étapes | Modèle de données prévu, implémentation ultérieure | Ne pas fermer la porte |

---

## 9. Modèle de Données — Entités Principales

```
Family
└── id, name, created_by, invite_token

UserProfile (extension User Django)
├── user, family, role: chef_etoile | cuisinier | convive
├── dietary_tags[] (gluten, lactose, végétarien…)
└── google_calendar_id, google_tasklist_id

TokenOAuth
└── user, service: "google", access_token, refresh_token, expires_at

Recipe  ← catalogue global partagé
├── id, title, description, photo_url (Cloudinary), base_servings
├── prep_time, cook_time, category, cuisine_type
├── seasons[], health_tags[], complexity, actif (soft delete)
├── calories_per_serving, proteins_per_serving, carbs_per_serving, fats_per_serving
└── created_by (User)

IngredientGroup (groupes dans une recette)
└── id, recipe_id, name, order

Ingredient
├── id, recipe_id, group_id, name, quantity, unit, is_optional
├── category (viandes / légumes / épicerie… — hérité dans la liste de courses)
├── openfoodfacts_id, calories, proteins, carbs, fats
└── order

RecipeStep
├── id, recipe_id, order, instruction
├── chef_note (optionnel)
└── timer_seconds (optionnel)

RecipeSection  ← sections libres (Points critiques, Conseils…)
└── id, recipe_id, section_type, title, content, order

Review
├── id, recipe_id, user_id, stars (1-5), comment
└── created_at  ← plusieurs par user dans le temps

MealProposal
├── id, family_id, recipe_id, proposed_by, message
└── week_plan_id (optionnel), created_at

WeekPlan
├── id, family_id, period_start, period_end
├── status: draft | published
└── created_by (Cuisinier)

Meal
├── id, week_plan_id, date, meal_time: lunch | dinner
├── recipe_id (null si créneau vide), servings_count
└── is_leftovers (bool), source_meal_id (FK self)

ShoppingList
└── id, family_id, week_plan_id, generated_at

ShoppingItem
└── id, shopping_list_id, name, quantity, unit, category, checked

NotificationPreference  ← architecture prévue, implémentation future
└── id, user_id, channel: email | push | in_app, enabled
```

---

## 10. Roadmap — Phases de Développement

### Phase 1 — MVP Core
- Auth Django + familles + invitation membres
- CRUD Recettes (ingrédients groupés, étapes, photo Cloudinary, tags)
- API nutritionnelle Open Food Facts
- Planning semaine (période paramétrable, repas avec restes)
- Génération liste de courses
- Interface mobile-first responsive (PWA)

### Phase 2 — Mode Cuisine & Social
- Mode Cuisine (cochage ingrédients/étapes, timers)
- Système de notation étoiles + historique
- Propositions des Convives
- Gamification (rangs Cuisinier et Convive)

### Phase 3 — Intégrations Google
- OAuth Google par utilisateur (django-allauth)
- Export menu → Google Calendar
- Export courses → Google Tasks

### Phase 4 — Intelligence
- Suggestions de menu automatiques (saisonnalité, nutrition, variété, préférences)
- Tableau de bord nutritionnel hebdomadaire
- Alertes équilibre

### Phase 5 — Extensions futures
- Notifications (email / push)
- Galerie photos d'étapes
- Gestion des allergies enrichie

---

## 11. Points Fermés ✅

| Sujet | Décision |
|-------|----------|
| Stack frontend | Django templates + vanilla JS (pas de React/Next.js) |
| Stack backend | Django + PostgreSQL Railway (pas de Supabase) |
| Auth | Django auth + django-allauth pour Google OAuth |
| Stockage photos | Cloudinary via `integrations/cloudinary.py` |
| Données nutritionnelles | Open Food Facts (API publique), auto-complétion à la saisie |
| Format recette | Enrichi (groupes ingrédients, notes chef, sections libres) |
| Isolation familles | Familles isolées pour menus/courses, catalogue recettes global partagé |
| Plusieurs Cuisiniers | Possible dans une famille, liste de courses agrégée |
| Interface cible | PWA mobile-first (Django + service worker vanilla JS) |
| Notation | Étoiles 1–5, plusieurs avis par utilisateur dans le temps |
| Catégorie courses | Portée par l'ingrédient dans la recette, héritée dans la liste |
| Rangs gamification | Propriété calculée dynamiquement, pas stockée en base |
| Photos d'étapes | Architecture prévue, pas prioritaire |
| Notifications | Architecture prévue, pas prioritaire |
| Allergies | Tags simples sur profil, avertissement non bloquant |
| Mode cuisine | Cochage ingrédients/étapes + timers (comme app muscu) |
| Déploiement | Railway uniquement (dev + prod) |

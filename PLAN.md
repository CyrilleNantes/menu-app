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

## Phase 1 — MVP Core

### Étape 1 — Initialisation du projet Django

- Créer la structure standard définie dans `Claude.md` (section 2.2)
- Configurer `settings.py` (dev/prod via variables d'env, `dj-database-url`, WhiteNoise)
- Configurer `requirements.txt` avec les dépendances initiales : `django`, `gunicorn`, `whitenoise`, `psycopg2-binary`, `python-dotenv`, `dj-database-url`, `httpx`, `django-allauth`, `cloudinary`
- Créer le `Procfile` Railway
- Vérifier que `python manage.py runserver` fonctionne avec PostgreSQL Railway
- Afficher la version `v1.1` dans le footer (contexte processor `IS_DEV`)

**✅ Livrable : projet Django qui démarre, connecté à Railway PostgreSQL**

---

### Étape 2 — Modèles et migration initiale

Créer tous les modèles définis en section 4 de `spec.md` dans cet ordre :
`Family` → `UserProfile` → `TokenOAuth` → `Recipe` → `IngredientGroup` → `Ingredient` → `RecipeStep` → `RecipeSection` → `Review` → `WeekPlan` → `Meal` → `MealProposal` → `ShoppingList` → `ShoppingItem` → `NotificationPreference`

- Migration `0001_initial`
- Enregistrer tous les modèles dans `admin.py`
- Charger la fixture `recette-exemple-hachis-parmentier.json` et vérifier qu'elle s'insère sans erreur

**✅ Livrable : `python manage.py migrate` + fixture chargée sans erreur**

---

### Étape 3 — Authentification et gestion des familles

- Configurer `django-allauth` : login email/password uniquement (Google OAuth en Phase 3)
- Pages : inscription, connexion, déconnexion
- À l'inscription : choix du rôle (Cuisinier → crée une famille / Convive → sans famille)
- Création de famille automatique pour le Cuisinier à l'inscription
- Page d'invitation : `GET /famille/inviter/<token>/` — rattache l'utilisateur connecté à la famille
- Redirection post-login vers le planning si famille, sinon vers une page "rejoindre une famille"
- Templates mobile-first (base layout responsive avec menu de navigation)

**✅ Livrable : inscription → connexion → accès à l'app fonctionnel**

---

### Étape 4 — Catalogue recettes (lecture)

- Liste des recettes : `/recettes/` avec filtres (catégorie, saison, complexité) et recherche titre
- Fiche recette : `/recettes/<id>/` — affichage complet (ingrédients groupés, étapes, sections libres, infos nutri, note moyenne)
- Aucun formulaire de création à cette étape — utiliser la fixture pour tester l'affichage
- Alerte allergies basée sur `UserProfile.dietary_tags`

**✅ Livrable : fiche Hachis Parmentier s'affiche correctement sur mobile**

---

### Étape 5 — Création et édition de recettes

- Formulaire recette : `/recettes/creer/` et `/recettes/<id>/modifier/`
- Ingrédients et étapes ajoutables dynamiquement (vanilla JS — `recette_form.js`)
- Upload photo → `integrations/cloudinary.py` → stockage `photo_url`
- Calcul et sauvegarde des macros agrégées (`services.py`) à chaque enregistrement
- Soft delete : `/recettes/<id>/supprimer/` (passe `actif=False`)

**✅ Livrable : créer une recette complète depuis le formulaire mobile**

---

### Étape 6 — API nutritionnelle Open Food Facts

- `integrations/openfoodfacts.py` : fonction `rechercher_ingredient(terme)` via `httpx`
- Endpoint AJAX : `GET /api/ingredients/nutrition/?q=<terme>` → 5 suggestions max
- Intégration dans le formulaire recette (debounce 400ms sur le champ nom d'ingrédient)
- Fallback : dropdown vide si API indisponible → saisie manuelle

**✅ Livrable : saisir "steak haché" dans le formulaire → suggestions nutritionnelles apparaissent**

---

### Étape 7 — Planning hebdomadaire

- Vue planning : `/planning/` et `/planning/<year>/<week>/`
- Grille 7 jours × 2 repas, créneaux vides autorisés
- Ajout/modification d'un repas (AJAX) : sélection recette + nombre de parts
- Gestion des restes : cocher "ce repas couvre [repas cible]"
- Propositions des Convives visibles par le Cuisinier
- Publication du menu : `POST /planning/<id>/publier/`
- Indicateurs nutritionnels de la semaine (calories / protéines cumulés)

**✅ Livrable : composer et publier un menu complet pour une semaine**

---

### Étape 8 — Liste de courses

- Génération automatique : `POST /courses/generer/<plan_id>/` via `services.py`
- Agrégation des ingrédients (même nom + même unité), exclusion des repas "restes"
- Vue liste : `/courses/<plan_id>/` — articles groupés par catégorie, cochage AJAX
- Modification manuelle (ajout, suppression, ajustement quantité)

**✅ Livrable : publier un menu → générer la liste de courses → cocher des articles sur mobile**

---

### Étape 9 — PWA (Progressive Web App)

- `manifest.json` : nom, icône, couleurs, `display: standalone`
- Service worker (`sw.js`) : mise en cache des recettes consultées pour usage hors-ligne
- Balise `<meta name="theme-color">` et icône Apple touch
- Tester l'installation sur mobile (Android Chrome + iOS Safari)

**✅ Livrable : app installable sur l'écran d'accueil du téléphone**

---

## Phase 2 — Mode Cuisine & Social

### Étape 10 — Mode Cuisine

- Vue dédiée : `/recettes/<id>/cuisine/`
- Ingrédients cochables (JS), étapes cochables avec défilement automatique
- Timer par étape (`mode_cuisine.js`) : compte à rebours MM:SS, alerte visuelle + sonore à 0
- Interface grande police, boutons larges, fond optimisé mobile

**✅ Livrable : suivre la recette Hachis Parmentier en mode cuisine avec les timers**

---

### Étape 11 — Notation et historique

- Formulaire de notation (étoiles 1–5 + commentaire) depuis la fiche recette (AJAX)
- Historique des avis par recette (tous utilisateurs)
- Vue "avis de ma famille" sur la fiche recette
- Note moyenne recalculée et affichée

**✅ Livrable : noter une recette, voir l'évolution des avis dans le temps**

---

### Étape 12 — Propositions des Convives

- Formulaire de proposition depuis le planning : `POST /planning/<id>/proposer/`
- Affichage des propositions dans la vue planning (côté Cuisinier)

**✅ Livrable : un Convive propose une recette, le Cuisinier la voit dans le planning**

---

### Étape 13 — Gamification (rangs)

- Propriété calculée `rank` sur `UserProfile` pour Cuisinier et Convive
- Affichage du rang dans le profil et à côté du nom dans les avis
- Aucune logique bloquante — informatif uniquement

**✅ Livrable : rang affiché sur le profil selon les contributions**

---

## Phase 3 — Intégrations Google

### Étape 14 — OAuth Google

- Configurer `django-allauth` avec le provider Google (scopes Calendar + Tasks)
- Flux : autorisation → callback `/google/callback/` → stockage `TokenOAuth`
- Rafraîchissement automatique du token avant chaque appel API
- Bouton "Connecter Google" dans les paramètres utilisateur

**✅ Livrable : connexion Google fonctionnelle, token stocké en base**

---

### Étape 15 — Export Google Calendar

- `integrations/google_calendar.py` : créer/mettre à jour un événement par repas
- `POST /planning/<id>/export-calendar/`
- Créneaux configurables dans le profil (défaut : 12h–13h / 20h30–21h30)

**✅ Livrable : menu publié → événements créés dans Google Agenda**

---

### Étape 16 — Export Google Tasks

- `integrations/google_tasks.py` : créer une tâche par article non coché
- `POST /courses/<plan_id>/export-tasks/`
- Format tâche : `"{quantité} {unité} {nom}"`

**✅ Livrable : liste de courses → tâches créées dans Google Tasks**

---

## Phase 4 — Intelligence (à planifier après Phase 3)

> Détail à affiner quand les phases précédentes sont stables.

- Suggestions de menu automatiques (saisonnalité, nutrition, variété, préférences)
- Tableau de bord nutritionnel hebdomadaire
- Alertes équilibre (manque protéines, excès calories)

---

## Phase 5 — Extensions futures (à planifier après Phase 4)

> Ne pas implémenter sans instruction explicite.

- Notifications (email / push) — `NotificationPreference` déjà en base
- Galerie photos d'étapes — modèle extensible sans migration
- Gestion des allergies enrichie

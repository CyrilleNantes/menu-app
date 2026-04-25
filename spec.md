# Spécifications Fonctionnelles — [Nom du Projet]

> Document vivant — mis à jour par l'IA après chaque implémentation validée.
> Dernière mise à jour : YYYY-MM-DD

---

## 1. Contexte, Objectifs et Limites

### 1.1 Objectif principal

> Une phrase claire, impérative, sans ambiguïté.
> Ex : Permettre à un utilisateur solo de planifier ses menus et générer sa liste de courses.

### 1.2 Périmètre inclus

- Fonctionnalité A
- Fonctionnalité B
- Fonctionnalité C

### 1.3 Hors périmètre (Anti-Scope)

> ⚠️ CRITIQUE — L'IA ne doit jamais implémenter ce qui suit sans accord explicite.

- Ne PAS implémenter X
- Ne PAS anticiper Y
- Ne PAS ajouter de logique métier non décrite ici

---

## 2. Acteurs et Rôles

| Acteur | Description | Accès |
|--------|-------------|-------|
| [Acteur principal] | [Description] | [Ce qu'il peut faire] |
| Administrateur Django | Gestion via `/admin/` | CRUD complet |

> Préciser ici si l'application implémente une authentification ou non.

---

## 3. Services externes

> Ne remplir que si le projet consomme des APIs ou services tiers.
> Toutes les clés et secrets vont dans Railway — jamais dans le code.

### 3.1 Services utilisés

| Service | Usage | Variable d'env | Fichier `integrations/` |
|---------|-------|----------------|--------------------------|
| [ex: OpenAI] | [ex: Conseils diététiques] | `OPENAI_API_KEY` | `integrations/llm.py` |
| [ex: Google Calendar] | [ex: Push des menus planifiés] | `GOOGLE_CLIENT_ID`, `GOOGLE_CLIENT_SECRET` | `integrations/google_calendar.py` |

### 3.2 Flux OAuth2 *(si applicable)*

> Supprimer cette section si aucun service n'utilise OAuth2.

| Étape | Description |
|-------|-------------|
| 1. Autorisation | L'utilisateur clique "Connecter [service]" → redirect vers la page d'autorisation du service |
| 2. Callback | Le service redirige vers `/[service]/callback/` avec un code temporaire |
| 3. Échange | Le code est échangé contre un `access_token` + `refresh_token` |
| 4. Stockage | Les tokens sont stockés en base (voir modèle `TokenOAuth` en section 4) |
| 5. Rafraîchissement | Avant chaque appel, vérifier si l'`access_token` est expiré et le renouveler |

**URL de callback** : `/[service]/callback/` → `[namespace]:[service]_callback`

---

## 4. Modèle de Données

### 4.1 `TokenOAuth` *(si applicable — supprimer si pas d'OAuth2)*

Stockage des tokens d'autorisation pour les services OAuth2.

| Champ | Type Django | Nullable | Défaut | Description |
|-------|-------------|----------|--------|-------------|
| `id` | `BigAutoField` | non | auto | Clé primaire |
| `service` | `CharField(50)` | non | — | Nom du service (ex. `"google_calendar"`) |
| `access_token` | `TextField` | non | — | Token d'accès (courte durée) |
| `refresh_token` | `TextField` | non | — | Token de rafraîchissement (longue durée) |
| `expires_at` | `DateTimeField` | oui | — | Date d'expiration de l'access token |
| `created_at` | `DateTimeField` | non | auto | Date de création |
| `updated_at` | `DateTimeField` | non | auto | Dernière mise à jour |

**Contrainte DB** : `service` unique (un seul token par service)

**Règle** : avant tout appel au service, vérifier `expires_at`. Si expiré, appeler `integrations/[service].py` pour renouveler et mettre à jour l'entrée.

---

### 4.2 [Nom de l'entité principale du projet]

[Description de ce que représente cette entité]

| Champ | Type Django | Nullable | Défaut | Description |
|-------|-------------|----------|--------|-------------|
| `id` | `BigAutoField` | non | auto | Clé primaire |
| `nom` | `CharField(X)` | non | — | [Description] |

**Tri par défaut** : `["nom"]`

**Contraintes DB** :
- [Contrainte unique, check, etc.]

**Validation Python (`clean`)** :
- [Règle de validation si applicable]

---

### 4.3 [Nom de l'entité suivante]

> Dupliquer cette section pour chaque modèle.

---

## 5. Fonctionnalités

### 5.1 [Nom de la fonctionnalité]

**URL** : `GET/POST /[chemin]/` → `[namespace]:[nom_url]`
**Vue** : `[nom_vue](request)`
**Template** : `[app]/[template].html`
**Formulaire** : `[NomFormulaire]` *(si applicable)*

**Champs du formulaire** *(si applicable)* :
- `[champ]` : [description]

**Règles de gestion** :
1. [Règle 1]
2. [Règle 2]

**Gestion des erreurs** :
- Si [condition] → [comportement]

---

### 5.2 [Nom de la fonctionnalité suivante]

> Dupliquer cette section pour chaque fonctionnalité.

---

## 6. Comportements JavaScript *(si applicable)*

> Ne remplir que si des comportements JS spécifiques existent.

### 6.1 [Nom du comportement]

**Sélecteur / déclencheur** : `[data-*, événement, etc.]`

Comportement :
1. [Étape 1]
2. [Étape 2]

---

## 7. États du système *(si applicable)*

> Ne remplir que si des entités ont des états et des transitions.

### États de `[Entité]`

```
ETAT_A ──[action]──► ETAT_B ──[action]──► ETAT_C
```

| Transition | Vue / Service | Conditions |
|------------|---------------|------------|
| `ETAT_A` → `ETAT_B` | `[vue]` | [condition] |
| `ETAT_B` → `ETAT_C` | `[vue]` | [condition] |

**Transitions interdites** :
- `ETAT_C` → `ETAT_A` : [raison]

---

## 8. Historique des migrations

| Migration | Date | Description |
|-----------|------|-------------|
| `0001_initial` | YYYY-MM-DD | Schéma initial |

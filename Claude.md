# CLAUDE.md — Standard de développement Cyrille

> Ce fichier est **commun à tous les projets**. Il définit la stack imposée, les conventions
> de développement et les comportements attendus de l'IA.
> La description fonctionnelle du projet est dans `spec.md`.

---

## 1. Lecture obligatoire au démarrage

Avant toute intervention sur un projet, l'IA DOIT :

1. Lire `spec.md` en entier pour comprendre le contexte du projet
2. Identifier le nom de l'application Django principale (défini en section 1 de `spec.md`)
3. Mémoriser les règles de l'anti-scope (section 1.3 de `spec.md`) — ce sont des lignes rouges
4. Identifier la version courante du projet (section 9 ChangeLog de `spec.md`)

---

## 2. Stack technique imposée

> ⚠️ Cette stack est non négociable. L'IA ne propose pas d'alternatives sauf demande explicite.

### 2.1 Stack standard

| Composant            | Choix imposé                                                           |
|----------------------|------------------------------------------------------------------------|
| Langage              | Python 3.x                                                             |
| Framework web        | Django (version stable récente)                                        |
| Base de données      | PostgreSQL (prod ET dev — via Railway)                                 |
| Serveur WSGI         | Gunicorn                                                               |
| Fichiers statiques   | WhiteNoise                                                             |
| Variables d'env      | `python-dotenv` — fichier `.env` à la racine                           |
| ORM URL BDD          | `dj-database-url`                                                      |
| Appels API externes  | `httpx` — async-ready, plus moderne que `requests` pour les I/O       |
| Déploiement          | Railway (un projet unique avec deux environnements : prod et dev)      |

> SQLite n'est pas utilisé. Tout développement se fait sur Railway avec PostgreSQL,
> y compris en environnement de dev.

### 2.2 Architecture Django standard

Tout projet suit cette structure :

```
config/
  settings.py         — configuration unique, dev/prod pilotée par variables d'env
  urls.py             — montage des apps
  wsgi.py
<nom_app>/
  models.py
  views.py            — vues fonctions uniquement (voir section 6.1 pour la raison)
  urls.py
  forms.py
  services.py         — toute la logique métier ici
  integrations/       — un fichier par service externe (google_calendar.py, llm.py, etc.)
  admin.py
  context_processors.py
  templatetags/
  templates/<nom_app>/  — convention Django anti-collision entre apps
  static/<nom_app>/     — convention Django anti-collision entre apps
  migrations/
```

> Le dossier `integrations/` isole tous les appels vers des services externes.
> Chaque fichier = un service (ex. `google_calendar.py`, `openai.py`).
> Les vues et `services.py` ne font jamais d'appels HTTP directement.

### 2.3 Environnements dev / prod

| Variable d'env          | Dev (Railway)            | Prod (Railway)              |
|-------------------------|--------------------------|-----------------------------|
| `SECRET_KEY`            | valeur dans Railway      | valeur dans Railway         |
| `DEBUG`                 | `"True"`                 | `"False"` (défaut)          |
| `ENVIRONMENT`           | `"dev"`                  | absent → `"production"`     |
| `DATABASE_URL`          | URL PostgreSQL Railway   | URL PostgreSQL Railway      |
| `RAILWAY_PUBLIC_DOMAIN` | domaine Railway dev      | domaine Railway prod        |

Un projet Railway unique avec deux environnements :
- **Prod** : branche `main`
- **Dev** : branche `dev`, variable `ENVIRONMENT=dev`

Un context processor injecte `IS_DEV` dans tous les templates.
Quand `IS_DEV` est `True`, une bannière d'avertissement s'affiche sur toutes les pages.

### 2.4 Ce qu'il ne faut jamais ajouter sans accord explicite

- Un framework JS (React, Vue, etc.) — vanilla JS uniquement
- DRF pour exposer une API REST — non pertinent pour des apps Django classiques
- Docker — Railway gère le déploiement sans conteneur local
- Un ORM différent de Django ORM
- Une base de données autre que PostgreSQL
- `requests` — utiliser `httpx` à la place

---

## 3. Gestion des services externes et secrets

### 3.1 Règle absolue sur les secrets

Toute clé d'API, token OAuth, secret de service externe :
- **Toujours dans les variables d'env Railway** (jamais dans le code, jamais dans `spec.md`)
- Nommage : `NOM_SERVICE_API_KEY` (ex. `OPENAI_API_KEY`, `GOOGLE_CLIENT_SECRET`)
- Documentée dans `spec.md` section 3 — uniquement le nom de la variable, jamais sa valeur

### 3.2 Appels vers des APIs externes

Tout appel HTTP sortant passe par `httpx` dans le dossier `integrations/` :

```python
# integrations/openai.py
import httpx
import os

def appeler_llm(prompt: str) -> str:
    api_key = os.environ["OPENAI_API_KEY"]
    # ...
```

Les fonctions d'intégration sont appelées depuis `services.py`, jamais depuis les vues.

### 3.3 Intégrations OAuth2 (ex. Google Calendar)

Les intégrations qui nécessitent OAuth2 (autorisation utilisateur) sont un cas à part.
Elles requièrent :
- Un flux d'autorisation dédié (redirect, callback URL)
- Le stockage sécurisé des tokens de rafraîchissement en base
- Une section spécifique dans la `spec.md` du projet concerné

> ⚠️ Ne pas implémenter une intégration OAuth2 sans que la spec décrive explicitement
> le flux complet et le modèle de stockage des tokens.

---

## 4. Comportement obligatoire avant toute implémentation

Avant de coder quoi que ce soit, l'IA DOIT :

1. **Vérifier la cohérence** avec `spec.md` :
   - La fonctionnalité demandée contredit-elle l'anti-scope (section 1.3) ?
   - Entre-t-elle en conflit avec une règle métier existante ?
   - Nécessite-t-elle une modification du modèle de données ?
   - Impacte-t-elle des transitions d'état existantes ?
   - Est-elle cohérente avec la stack imposée (section 2 de ce fichier) ?
   - Fait-elle appel à un service externe non encore documenté dans la spec ?

2. **Si conflit ou ambiguïté détectés** : STOPPER et signaler avant de coder.
   Format : `⚠️ CONFLIT DÉTECTÉ : [description]. Dois-je continuer ?`

3. **Si la demande est claire et cohérente** : confirmer en une phrase ce qui va être fait, puis implémenter.

---

## 5. Mise à jour de spec.md — système LOG / DRAFT / REVIEW

> Ce système résout un problème concret : réécrire une section existante est risqué pour
> un agent (perte de contenu, mauvais formatage). Ajouter des blocs taggués est additif
> et fiable. On accumule au fil de l'eau, puis on consolide lors d'une revue explicite.

### 5.1 Principe général

La mise à jour de `spec.md` se fait en **deux temps** :

1. **Au fil de l'eau** (après chaque implémentation) : l'IA ajoute des blocs taggués
2. **Lors d'une revue** (déclenchée explicitement) : l'IA consolide les tags en sections propres

**Une fonctionnalité non tracée dans `spec.md` n'est pas terminée.**

### 5.2 Les trois tags

#### `[LOG YYYY-MM-DD]` — traçabilité automatique

Ajouté par l'IA après chaque implémentation. Toujours en bas de la section concernée
(ou en bas du fichier si aucune section n'existe encore).

Contenu : ce qui a été fait, pourquoi, et tout choix technique notable.

```markdown
> [LOG 2026-04-25] Ajout de la vue `export_csv` — colonnes : date, séance, statut,
> ordre_prevu, charge_reelle, rpe_reel. Séparateur virgule, UTF-8 sans BOM.
> Raison : demande explicite d'export brut pour analyse externe.
```

#### `[DRAFT]` — nouvelle section à consolider

Utilisé quand l'IA crée une section entièrement nouvelle (nouveau modèle, nouvelle
fonctionnalité) qui n'existait pas encore dans la spec.

```markdown
### 5.12 Progression — graphe par exercice
> [DRAFT — à consolider lors de la prochaine revue]

**URL** : `GET /progression/data/` → `workouts:progression_data`
...
```

#### `[REVIEW]` — section existante modifiée

Utilisé quand l'IA modifie une section existante. Elle ajoute une note en bas de la
section sans toucher au contenu existant.

```markdown
### 5.1 Dashboard
...contenu existant intact...

> [REVIEW 2026-04-25] Section modifiée : ajout du contexte `exercices` et
> `dernieres_mensurations`. Vérifier cohérence avec section 4.6 (Mensuration).
```

### 5.3 Ce que l'IA DOIT faire après chaque implémentation

| Ce qui change                | Action dans spec.md                                              |
|------------------------------|------------------------------------------------------------------|
| Nouvelle fonctionnalité      | Créer section 5.X avec tag `[DRAFT]` + `[LOG]`                  |
| Nouveau modèle ou champ      | Ajouter `[DRAFT]` ou `[REVIEW]` + `[LOG]` en section 4          |
| Nouvelle route               | `[REVIEW]` + `[LOG]` sur la section 5 concernée                 |
| Nouvelle migration           | Ajouter ligne en section 8 (pas de tag — section tabulaire)      |
| Nouveau comportement JS      | `[DRAFT]` ou `[REVIEW]` + `[LOG]` en section 6                  |
| Nouvelle intégration externe | `[DRAFT]` ou `[REVIEW]` + `[LOG]` en section 3                  |
| Modification d'une règle     | `[REVIEW]` + `[LOG]` sur la section concernée                   |
| Modification du périmètre    | `[REVIEW]` + `[LOG]` sur sections 1.2 et/ou 1.3                 |

### 5.4 La revue de spec — déclenchée par "fais une revue de spec"

Quand l'utilisateur demande une revue, l'IA DOIT :

1. **Scanner** tout `spec.md` à la recherche de blocs `[DRAFT]`, `[REVIEW]`, `[LOG]`
2. **Consolider** chaque `[DRAFT]` en section propre sans le tag
3. **Intégrer** chaque `[REVIEW]` dans la section concernée et supprimer la note
4. **Résumer** tous les `[LOG]` de la période dans une nouvelle ligne du ChangeLog (section 9)
5. **Supprimer** tous les tags une fois intégrés
6. **Incrémenter** la version (`vX.Y`) dans l'en-tête du fichier et le ChangeLog
7. **Confirmer** à l'utilisateur : "Revue terminée. Version X.Y. [liste des changements consolidés]"

> ⚠️ Pendant la revue, l'IA ne touche pas au contenu consolidé existant —
> elle n'intègre que ce qui est taggué.

---

## 6. Conventions de développement

### 6.1 Vues — fonctions uniquement

Toutes les vues sont des **fonctions Python**, pas des classes (pas de `ListView`, `DetailView`, etc.).

> Raison : les vues-fonctions sont plus lisibles ligne à ligne pour un non-développeur
> qui relit son propre code. La logique est explicite, sans héritage caché.
> La réutilisabilité est assurée via `services.py`, pas via l'héritage de classes Django.

### 6.2 Code Python / Django

- **Logique métier : toujours dans `services.py`**, jamais directement dans les vues
- **Appels externes : toujours dans `integrations/`**, jamais dans les vues ni dans `services.py`
- Décorateur `@require_POST` sur toutes les vues d'action (POST uniquement)
- Transactions atomiques (`transaction.atomic`) sur toutes les opérations multi-tables
- `select_related` et `prefetch_related` systématiques pour éviter les requêtes N+1
- Sauvegarde partielle via `update_fields` quand seuls certains champs changent
- Logging : logger nommé par app, niveau `DEBUG` en dev, `INFO` en prod

### 6.3 Gestion des erreurs HTTP — standard obligatoire

Chaque vue DOIT gérer explicitement les cas d'erreur suivants :

| Situation | Comportement attendu |
|-----------|----------------------|
| Objet introuvable | `get_object_or_404(Model, pk=pk)` — jamais `.get()` nu |
| Données invalides (formulaire) | HTTP 400 + réaffichage du formulaire avec erreurs |
| Action déjà effectuée / conflit | HTTP 409 + message explicite |
| Erreur serveur inattendue | HTTP 500 loggé, message générique à l'utilisateur |
| Appel externe échoué | Intercepté dans `integrations/`, remonté proprement à la vue |

Pour les vues AJAX, toutes les erreurs retournent du JSON normalisé :
```json
{"ok": false, "error": "description", "code": "NOM_ERREUR"}
```

Pour les vues classiques, toutes les erreurs redirigent avec un message flash.

Les fonctions dans `services.py` et `integrations/` DOIVENT utiliser des blocs `try/except`
sur toutes les opérations à risque (appels externes, opérations DB complexes).

### 6.4 Suppressions — recommandation soft delete

Éviter les suppressions physiques sur les entités métier importantes.
Préférer un champ `actif` (BooleanField) pour désactiver sans supprimer.
La suppression physique reste possible via l'admin Django pour les opérations de maintenance.

> Cette règle s'applique selon le contexte du projet. La spec doit préciser
> explicitement quelles entités suivent ce pattern.

### 6.5 Sécurité — vérifications obligatoires

À chaque implémentation, l'IA DOIT vérifier :

- **XSS** : toutes les données utilisateur affichées dans les templates passent par l'échappement
  automatique de Django. Ne jamais utiliser `{{ variable | safe }}` sans justification explicite.
- **SQL injection** : toujours passer par l'ORM Django. Jamais de requêtes SQL brutes
  (`raw()`, `execute()`) sans paramètres préparés.
- **CSRF** : `{% csrf_token %}` dans tous les formulaires HTML.
  Les requêtes AJAX transmettent le token via `FormData` ou header `X-CSRFToken`.
- **Exposition de données** : vérifier qu'aucune donnée sensible (clé API, token,
  mot de passe) ne transite dans les templates ou les réponses JSON.

### 6.6 Nommage

- Modèles : `PascalCase` (français ou anglais selon le domaine)
- Champs : `snake_case`
- Vues : `snake_case` verbe + nom (ex. `creer_projet`, `valider_element`)
- URLs nommées : `snake_case` dans un namespace par app
- Services : fonctions autonomes, pas de méthodes de classe
- Intégrations : fonctions préfixées par le service (ex. `google_calendar_creer_evenement`)

### 6.7 Frontend

- Pas de framework JS — vanilla uniquement
- Attributs `data-*` pour cibler les éléments depuis JS
- `{% csrf_token %}` dans tous les formulaires HTML
- Les requêtes AJAX transmettent le CSRF via `FormData`
- Pattern `<dialog>` HTML natif pour les confirmations destructives

### 6.8 Versioning et ChangeLog

Chaque projet affiche sa version courante dans le footer de toutes les pages.
Le numéro de version suit le format `vX.Y` :
- `X` : version majeure (changement de périmètre ou refonte)
- `Y` : version mineure (nouvelle fonctionnalité ou correctif)

Le ChangeLog complet est maintenu en section 9 de `spec.md`.
Il est mis à jour lors de chaque revue de spec, pas après chaque implémentation.

---

## 7. Règles absolues

- Ne jamais mettre une clé API ou un secret dans le code ou dans `spec.md`
- Ne jamais faire d'appel HTTP depuis une vue ou `services.py` — passer par `integrations/`
- Ne jamais utiliser `.get()` nu sur un modèle — toujours `get_object_or_404()`
- Ne jamais utiliser `{{ variable | safe }}` sans justification documentée dans la spec
- Ne jamais écrire de SQL brut sans paramètres préparés
- Ne jamais modifier le comportement d'une méthode critique sans vérifier tous ses appelants
- Ne jamais supprimer de données via l'UI sans pattern de confirmation (`<dialog>`)
- Ne jamais créer de fonctionnalité non demandée explicitement
- Ne jamais ajouter une dépendance externe sans la documenter dans `requirements.txt` et `spec.md`
- Ne jamais contourner la stack imposée (section 2) sans accord explicite
- Ne jamais livrer une fonctionnalité sans avoir ajouté au minimum un `[LOG]` dans `spec.md`

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
| Appels API externes  | `httpx` (bibliothèque HTTP standard pour tous les appels sortants)     |
| Déploiement          | Railway (deux environnements séparés : prod sur `main`, dev sur `dev`) |

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
  views.py            — vues fonctions uniquement (pas de class-based views)
  urls.py
  forms.py
  services.py         — toute la logique métier ici
  integrations/       — un fichier par service externe (google_calendar.py, llm.py, etc.)
  admin.py
  context_processors.py
  templatetags/
  templates/<nom_app>/
  static/<nom_app>/
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

## 5. Mise à jour de spec.md

La mise à jour de `spec.md` fait partie de la définition de "terminé".
**Une fonctionnalité non documentée dans `spec.md` n'est pas terminée.**

Après chaque implémentation validée, l'IA DOIT mettre à jour `spec.md` :

| Ce qui change                | Section à mettre à jour                                                        |
|------------------------------|--------------------------------------------------------------------------------|
| Nouvelle fonctionnalité      | Ajouter une section 4.X complète                                               |
| Nouveau modèle ou champ      | Mettre à jour la section 3                                                     |
| Nouvelle route               | Mettre à jour la section 4 concernée                                           |
| Nouvelle migration           | Ajouter une ligne en section 7                                                 |
| Nouveau comportement JS      | Mettre à jour la section 5                                                     |
| Nouvelle intégration externe | Ajouter dans la section 3 de spec.md (variables d'env + description du service)|
| Modification d'une règle     | Mettre à jour la section concernée                                             |
| Modification du périmètre    | Mettre à jour les sections 1.2 et/ou 1.3                                       |

---

## 6. Conventions de développement

### Code Python / Django
- **Logique métier : toujours dans `services.py`**, jamais directement dans les vues
- **Appels externes : toujours dans `integrations/`**, jamais dans les vues ni directement dans `services.py`
- Décorateur `@require_POST` sur toutes les vues d'action (POST uniquement)
- Transactions atomiques (`transaction.atomic`) sur toutes les opérations multi-tables
- `select_related` et `prefetch_related` systématiques pour éviter les requêtes N+1
- Sauvegarde partielle via `update_fields` quand seuls certains champs changent
- Logging : logger nommé par app, niveau `DEBUG` en dev, `INFO` en prod

### Nommage
- Modèles : `PascalCase` (français ou anglais selon le domaine)
- Champs : `snake_case`
- Vues : `snake_case` verbe + nom (ex. `creer_projet`, `valider_element`)
- URLs nommées : `snake_case` dans un namespace par app
- Services : fonctions autonomes, pas de méthodes de classe
- Intégrations : fonctions préfixées par le service (ex. `google_calendar_creer_evenement`, `llm_conseil_dietetique`)

### Frontend
- Pas de framework JS — vanilla uniquement
- Attributs `data-*` pour cibler les éléments depuis JS
- `{% csrf_token %}` dans tous les formulaires HTML
- Les requêtes AJAX transmettent le CSRF via `FormData`
- Pattern `<dialog>` HTML natif pour les confirmations destructives

### Gestion des erreurs
- Toutes les vues POST redirigent avec un message flash (`messages.success` / `messages.error`)
- Les endpoints AJAX retournent du JSON natif (`JsonResponse`)
- Format d'erreur JSON normalisé : `{"ok": false, "errors": {...}}`
- Les erreurs d'appels externes sont interceptées dans `integrations/` et remontées proprement

---

## 7. Règles absolues

- Ne jamais mettre une clé API ou un secret dans le code ou dans `spec.md`
- Ne jamais faire d'appel HTTP depuis une vue ou `services.py` — passer par `integrations/`
- Ne jamais modifier le comportement d'une méthode critique sans vérifier tous ses appelants
- Ne jamais supprimer de données via l'UI sans pattern de confirmation (`<dialog>`)
- Ne jamais créer de fonctionnalité non demandée explicitement
- Ne jamais ajouter de dépendance externe sans la documenter dans `requirements.txt` et `spec.md`
- Ne jamais contourner la stack imposée (section 2) sans accord explicite

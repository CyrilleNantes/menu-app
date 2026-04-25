import json
import logging
import zipfile
from datetime import date, timedelta

from django.contrib import messages
from django.contrib.auth import login, logout
from django.contrib.auth.decorators import login_required
from django.contrib.auth.models import User
from django.db import transaction
from django.db.models import Avg, Count, Q
from django.http import HttpResponse, JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.http import require_GET, require_POST

from .forms import InscriptionForm, RecipeForm
from .integrations.cloudinary import upload_photo
from .integrations.openfoodfacts import rechercher_ingredient
from .models import Family, Ingredient, Meal, MealProposal, Recipe, Review, ShoppingItem, ShoppingList, UserProfile, WeekPlan
from .services import (
    exporter_backup,
    generer_liste_courses,
    importer_recette_depuis_json,
    restaurer_backup,
    sauvegarder_recette_depuis_post,
)

logger = logging.getLogger("menu")


# ─── PWA ─────────────────────────────────────────────────────────────────────

@require_GET
def service_worker(request):
    """Sert sw.js depuis la racine pour que son scope couvre toute l'application."""
    return render(
        request,
        "sw.js",
        content_type="application/javascript",
        headers={"Service-Worker-Allowed": "/"},
    )


# Mots-clés par tag alimentaire pour les alertes allergies (simple, non bloquant)
ALLERGEN_KEYWORDS = {
    "gluten": ["farine", "blé", "seigle", "orge", "avoine", "pain", "pâte", "semoule", "couscous"],
    "lactose": ["lait", "beurre", "crème", "fromage", "yaourt", "mozzarella", "cheddar", "parmesan", "gruyère"],
    "fruits_a_coque": ["noix", "noisette", "amande", "cajou", "pistache", "noix de coco", "pécan"],
    "arachides": ["cacahuète", "arachide", "beurre de cacahuète"],
    "oeufs": ["œuf", "oeuf", "jaune d'œuf", "blanc d'œuf"],
    "poisson": ["saumon", "thon", "cabillaud", "sardine", "anchois", "truite"],
    "fruits_de_mer": ["crevette", "moule", "homard", "crabe", "calamar", "poulpe"],
    "soja": ["soja", "tofu", "edamame", "miso"],
    "vegetarien": [],
    "vegan": [],
}


def _saison_courante():
    mois = date.today().month
    if mois in (3, 4, 5):
        return "printemps"
    if mois in (6, 7, 8):
        return "ete"
    if mois in (9, 10, 11):
        return "automne"
    return "hiver"


def _alertes_allergies(recipe, dietary_tags):
    if not dietary_tags:
        return []
    alertes = []
    noms = [ing.name.lower() for ing in recipe.ingredients.all()]
    for tag in dietary_tags:
        mots = ALLERGEN_KEYWORDS.get(tag, [])
        for mot in mots:
            if any(mot in nom for nom in noms):
                alertes.append(tag)
                break
    return alertes


# ─── Auth ────────────────────────────────────────────────────────────────────

def home(request):
    if request.user.is_authenticated:
        return redirect("menu:planning")
    return render(request, "menu/home.html")


def inscription(request):
    if request.user.is_authenticated:
        return redirect("menu:home")

    form = InscriptionForm(request.POST or None)
    if request.method == "POST" and form.is_valid():
        cd = form.cleaned_data
        user = User.objects.create_user(
            username=cd["email"],
            email=cd["email"],
            password=cd["password1"],
            first_name=cd["prenom"],
            last_name=cd["nom"],
        )
        family = None
        if cd["role"] == "cuisinier":
            family = Family.objects.create(name=cd["nom_famille"], created_by=user)

        UserProfile.objects.create(user=user, family=family, role=cd["role"])
        login(request, user, backend="django.contrib.auth.backends.ModelBackend")
        messages.success(request, "Bienvenue !")
        logger.info("Nouvel utilisateur inscrit : %s (rôle : %s)", user.email, cd["role"])
        return redirect("menu:home")

    return render(request, "menu/auth/inscription.html", {"form": form})


def connexion(request):
    if request.user.is_authenticated:
        return redirect("menu:home")

    error = None
    if request.method == "POST":
        from django.contrib.auth import authenticate
        email = request.POST.get("email", "").strip()
        password = request.POST.get("password", "")
        user = authenticate(request, username=email, password=password)
        if user is not None:
            login(request, user)
            next_url = request.GET.get("next", "")
            return redirect(next_url or "menu:home")
        error = "Email ou mot de passe incorrect."

    return render(request, "menu/auth/connexion.html", {"error": error})


@require_POST
@login_required
def deconnexion(request):
    logout(request)
    return redirect("menu:connexion")


@login_required
def rejoindre_famille(request, token):
    try:
        profile = request.user.profile
    except UserProfile.DoesNotExist:
        messages.error(request, "Profil utilisateur introuvable.")
        return redirect("menu:home")

    if profile.family:
        messages.warning(request, "Vous appartenez déjà à une famille.")
        return redirect("menu:home")

    famille = get_object_or_404(Family, invite_token=token)
    profile.family = famille
    profile.save(update_fields=["family"])
    messages.success(request, f"Vous avez rejoint la famille « {famille.name} » !")
    logger.info("Utilisateur %s a rejoint la famille %s", request.user.email, famille.name)
    return redirect("menu:home")


@login_required
def rejoindre_famille_page(request):
    return render(request, "menu/auth/rejoindre.html")


def _get_profile(request):
    """Retourne le profil utilisateur ou None."""
    try:
        return request.user.profile
    except UserProfile.DoesNotExist:
        return None


# ─── Planning hebdomadaire ────────────────────────────────────────────────────

@login_required
def planning(request):
    """Redirige vers le planning de la semaine courante."""
    profile = _get_profile(request)
    if not profile:
        return redirect("menu:rejoindre_famille_page")
    if not profile.family:
        return redirect("menu:rejoindre_famille_page")
    iso = date.today().isocalendar()
    return redirect("menu:planning_semaine", year=iso[0], week=iso[1])


@login_required
def planning_semaine(request, year, week):
    profile = _get_profile(request)
    if not profile:
        return redirect("menu:rejoindre_famille_page")
    if not profile.family:
        return redirect("menu:rejoindre_famille_page")

    try:
        week_start = date.fromisocalendar(year, week, 1)   # lundi
    except ValueError:
        return redirect("menu:planning")
    week_end = week_start + timedelta(days=6)              # dimanche

    # Créer le WeekPlan s'il n'existe pas encore
    with transaction.atomic():
        plan, _ = WeekPlan.objects.get_or_create(
            family=profile.family,
            period_start=week_start,
            defaults={
                "period_end": week_end,
                "created_by": request.user,
                "status": "draft",
            },
        )

    # Repas de la semaine
    meals_qs = (
        Meal.objects.filter(week_plan=plan)
        .select_related("recipe", "source_meal__recipe")
    )
    meal_by_slot = {(m.date, m.meal_time): m for m in meals_qs}

    # Construction de la grille
    JOURS_FR = ["Lundi", "Mardi", "Mercredi", "Jeudi", "Vendredi", "Samedi", "Dimanche"]
    grid = []
    for i in range(7):
        d = week_start + timedelta(days=i)
        grid.append({
            "date": d,
            "day_name": JOURS_FR[i],
            "lunch": meal_by_slot.get((d, "lunch")),
            "dinner": meal_by_slot.get((d, "dinner")),
        })

    # Indicateurs nutritionnels de la semaine
    total_calories = total_proteins = 0.0
    for m in meals_qs:
        if not m.is_leftovers and m.recipe:
            n = m.servings_count or m.recipe.base_servings or 1
            total_calories += (m.recipe.calories_per_serving or 0) * n
            total_proteins += (m.recipe.proteins_per_serving or 0) * n

    # Propositions (visibles par le Cuisinier)
    proposals = []
    is_cuisinier = profile.role in ("cuisinier", "chef_etoile")
    if is_cuisinier:
        proposals = list(
            MealProposal.objects.filter(week_plan=plan)
            .select_related("recipe", "proposed_by")
            .order_by("-created_at")
        )

    # Navigation prev/next
    prev_monday = week_start - timedelta(days=7)
    next_monday = week_start + timedelta(days=7)
    prev_iso = prev_monday.isocalendar()
    next_iso = next_monday.isocalendar()

    ctx = {
        "plan": plan,
        "grid": grid,
        "week_start": week_start,
        "week_end": week_end,
        "year": year,
        "week": week,
        "prev_year": prev_iso[0],
        "prev_week": prev_iso[1],
        "next_year": next_iso[0],
        "next_week": next_iso[1],
        "total_calories": round(total_calories) if total_calories else None,
        "total_proteins": round(total_proteins, 1) if total_proteins else None,
        "proposals": proposals,
        "is_cuisinier": is_cuisinier,
        # Pour le dialog "restes" : tous les repas avec recette de cette semaine
        "meals_avec_recette": [
            {"id": m.id, "label": f"{m.date} {'Midi' if m.meal_time == 'lunch' else 'Soir'} — {m.recipe.title}"}
            for m in meals_qs if m.recipe and not m.is_leftovers
        ],
        # Lien courses
        "has_shopping_list": ShoppingList.objects.filter(week_plan=plan).exists(),
    }
    return render(request, "menu/planning/semaine.html", ctx)


@require_POST
@login_required
def modifier_meal(request, plan_id):
    """AJAX : crée ou met à jour un Meal (créneau du planning)."""
    profile = _get_profile(request)
    if not profile or not profile.family:
        return JsonResponse({"ok": False, "error": "Famille requise", "code": "NO_FAMILY"}, status=403)
    if not _verifier_cuisinier(request):
        return JsonResponse({"ok": False, "error": "Réservé aux Cuisiniers", "code": "FORBIDDEN"}, status=403)

    plan = get_object_or_404(WeekPlan, id=plan_id, family=profile.family)

    try:
        body = json.loads(request.body)
    except (json.JSONDecodeError, AttributeError):
        return JsonResponse({"ok": False, "error": "JSON invalide", "code": "BAD_JSON"}, status=400)

    # Validation date
    try:
        meal_date = date.fromisoformat(body.get("date", ""))
    except (ValueError, TypeError):
        return JsonResponse({"ok": False, "error": "Date invalide", "code": "INVALID_DATE"}, status=400)

    meal_time = body.get("meal_time", "")
    if meal_time not in ("lunch", "dinner"):
        return JsonResponse({"ok": False, "error": "Créneau invalide", "code": "INVALID_TIME"}, status=400)

    # Recette (optionnelle)
    recipe = None
    recipe_id = body.get("recipe_id")
    if recipe_id:
        recipe = Recipe.objects.filter(id=recipe_id, actif=True).first()
        if not recipe:
            return JsonResponse({"ok": False, "error": "Recette introuvable", "code": "NO_RECIPE"}, status=404)

    is_leftovers = bool(body.get("is_leftovers", False))
    source_meal = None
    if is_leftovers:
        src_id = body.get("source_meal_id")
        if src_id:
            source_meal = Meal.objects.filter(id=src_id, week_plan=plan).first()

    try:
        servings = int(body.get("servings_count") or 0) or (recipe.base_servings if recipe else None)
    except (ValueError, TypeError):
        servings = recipe.base_servings if recipe else None

    meal, _ = Meal.objects.update_or_create(
        week_plan=plan,
        date=meal_date,
        meal_time=meal_time,
        defaults={
            "recipe": recipe,
            "servings_count": servings,
            "is_leftovers": is_leftovers,
            "source_meal": source_meal,
        },
    )

    return JsonResponse({
        "ok": True,
        "meal_id": meal.id,
        "recipe_id": recipe.id if recipe else None,
        "recipe_title": recipe.title if recipe else None,
        "servings_count": meal.servings_count,
        "is_leftovers": meal.is_leftovers,
        "calories_per_serving": recipe.calories_per_serving if recipe else None,
    })


@require_POST
@login_required
def publier_planning(request, plan_id):
    """Publie un WeekPlan (brouillon → publié)."""
    profile = _get_profile(request)
    if not profile or not _verifier_cuisinier(request):
        messages.error(request, "Réservé aux Cuisiniers.")
        return redirect("menu:planning")

    plan = get_object_or_404(WeekPlan, id=plan_id, family=profile.family)

    if plan.status == "published":
        messages.warning(request, "Ce planning est déjà publié.")
    elif not plan.meals.filter(recipe__isnull=False).exists():
        messages.error(request, "Impossible de publier un planning vide (aucune recette planifiée).")
    else:
        plan.status = "published"
        plan.save(update_fields=["status"])
        messages.success(request, "Menu publié ! Vous pouvez maintenant générer la liste de courses.")
        logger.info("Planning %d publié par %s.", plan.id, request.user.email)

    iso = plan.period_start.isocalendar()
    return redirect("menu:planning_semaine", year=iso[0], week=iso[1])


@require_POST
@login_required
def proposer_repas(request, plan_id):
    """AJAX : un Convive propose une recette pour ce planning."""
    profile = _get_profile(request)
    if not profile or not profile.family:
        return JsonResponse({"ok": False, "error": "Famille requise", "code": "NO_FAMILY"}, status=403)

    plan = get_object_or_404(WeekPlan, id=plan_id, family=profile.family)

    try:
        body = json.loads(request.body)
    except (json.JSONDecodeError, AttributeError):
        return JsonResponse({"ok": False, "error": "JSON invalide", "code": "BAD_JSON"}, status=400)

    recipe_id = body.get("recipe_id")
    if not recipe_id:
        return JsonResponse({"ok": False, "error": "Recette requise", "code": "NO_RECIPE"}, status=400)

    recipe = get_object_or_404(Recipe, id=recipe_id, actif=True)
    message = (body.get("message") or "").strip() or None

    proposal = MealProposal.objects.create(
        family=profile.family,
        recipe=recipe,
        proposed_by=request.user,
        message=message,
        week_plan=plan,
    )

    return JsonResponse({
        "ok": True,
        "proposal_id": proposal.id,
        "recipe_title": recipe.title,
        "proposed_by": request.user.first_name or request.user.email,
    })


@login_required
def api_recettes(request):
    """API JSON : liste de recettes filtrées par titre (pour le planning)."""
    q = request.GET.get("q", "").strip()
    qs = Recipe.objects.filter(actif=True).only(
        "id", "title", "category", "complexity", "base_servings", "calories_per_serving"
    )
    if q:
        qs = qs.filter(title__icontains=q)
    qs = qs.order_by("title")[:20]
    results = [
        {
            "id": r.id,
            "title": r.title,
            "category": r.category,
            "base_servings": r.base_servings,
            "calories_per_serving": r.calories_per_serving,
        }
        for r in qs
    ]
    return JsonResponse({"ok": True, "results": results})


# ─── Liste de courses ────────────────────────────────────────────────────────

@require_POST
@login_required
def generer_courses(request, plan_id):
    """Génère (ou recrée) la liste de courses d'un planning. Cuisinier uniquement."""
    plan = get_object_or_404(WeekPlan, pk=plan_id)
    profile = _get_profile(request)
    if not profile or profile.family != plan.family:
        messages.error(request, "Accès refusé.")
        return redirect("menu:planning")
    if profile.role not in ("cuisinier", "chef_etoile"):
        messages.error(request, "Réservé au Cuisinier.")
        return redirect("menu:planning")

    try:
        generer_liste_courses(plan)
        messages.success(request, "Liste de courses générée !")
    except Exception as exc:
        logger.error("generer_courses error plan=%s : %s", plan_id, exc)
        messages.error(request, "Erreur lors de la génération de la liste.")

    return redirect("menu:liste_courses", plan_id=plan_id)


@login_required
def liste_courses(request, plan_id):
    """Affiche la liste de courses d'un planning. Visible par tous les membres de la famille."""
    plan = get_object_or_404(WeekPlan, pk=plan_id)
    profile = _get_profile(request)
    if not profile or profile.family != plan.family:
        messages.error(request, "Accès refusé.")
        return redirect("menu:planning")

    # Récupère la liste si elle existe
    shopping_list = ShoppingList.objects.filter(week_plan=plan).first()

    # Grouper les articles par catégorie
    groups: dict[str, list] = {}
    nb_checked = 0
    if shopping_list:
        for item in shopping_list.items.all().order_by("category", "name"):
            cat = item.category or "Divers"
            groups.setdefault(cat, []).append(item)
            if item.checked:
                nb_checked += 1

    nb_total = sum(len(v) for v in groups.values())

    # Navigation semaine pour les liens retour
    year, week, _ = plan.period_start.isocalendar()

    is_cuisinier = profile.role in ("cuisinier", "chef_etoile")

    ctx = {
        "plan": plan,
        "shopping_list": shopping_list,
        "groups": groups,
        "nb_total": nb_total,
        "nb_checked": nb_checked,
        "year": year,
        "week": week,
        "is_cuisinier": is_cuisinier,
    }
    return render(request, "menu/courses/liste.html", ctx)


@require_POST
@login_required
def cocher_item(request, id):
    """Bascule le statut coché/décoché d'un article. Réponse JSON."""
    item = get_object_or_404(ShoppingItem, pk=id)
    profile = _get_profile(request)
    if not profile or profile.family != item.shopping_list.family:
        return JsonResponse({"ok": False, "error": "Accès refusé"}, status=403)

    item.checked = not item.checked
    item.save(update_fields=["checked"])
    return JsonResponse({"ok": True, "checked": item.checked})


# ─── Catalogue recettes ───────────────────────────────────────────────────────

@login_required
def mode_cuisine(request, id):
    """Vue mode cuisine : ingrédients cochables, étapes avec timer."""
    recipe = get_object_or_404(
        Recipe.objects.prefetch_related(
            "ingredient_groups__ingredients",
            "steps",
        ),
        id=id,
        actif=True,
    )
    groups = list(recipe.ingredient_groups.prefetch_related("ingredients").all())
    steps  = list(recipe.steps.all())
    ctx = {
        "recipe": recipe,
        "groups": groups,
        "steps": steps,
        "step_count": len(steps),
    }
    return render(request, "menu/recettes/cuisine.html", ctx)


@login_required
def liste_recettes(request):
    qs = Recipe.objects.filter(actif=True).select_related("created_by").annotate(
        note_moyenne=Avg("reviews__stars"),
        nb_avis=Count("reviews"),
    )

    # Filtres
    q = request.GET.get("q", "").strip()
    categorie = request.GET.get("categorie", "")
    saison = request.GET.get("saison", "")
    complexite = request.GET.get("complexite", "")
    tri = request.GET.get("tri", "recentes")

    if q:
        qs = qs.filter(title__icontains=q)
    if categorie:
        qs = qs.filter(category=categorie)
    if saison:
        qs = qs.filter(seasons__contains=[saison])
    if complexite:
        qs = qs.filter(complexity=complexite)

    if tri == "mieux_notees":
        qs = qs.order_by("-note_moyenne", "-created_at")
    elif tri == "plus_simples":
        ordre_complexite = {"simple": 0, "intermediaire": 1, "elabore": 2}
        qs = sorted(qs, key=lambda r: ordre_complexite.get(r.complexity, 1))
    else:
        qs = qs.order_by("-created_at")

    ctx = {
        "recettes": qs,
        "q": q,
        "categorie": categorie,
        "saison": saison,
        "complexite": complexite,
        "tri": tri,
        "saison_courante": _saison_courante(),
        "categories": Recipe.CATEGORY_CHOICES,
        "saisons": [("printemps", "Printemps"), ("ete", "Été"), ("automne", "Automne"), ("hiver", "Hiver")],
        "complexites": Recipe.COMPLEXITY_CHOICES,
    }
    return render(request, "menu/recettes/liste.html", ctx)


@login_required
def detail_recette(request, id):
    recipe = get_object_or_404(
        Recipe.objects.select_related("created_by").prefetch_related(
            "ingredient_groups__ingredients",
            "steps",
            "sections",
            "reviews__user",
        ),
        id=id,
        actif=True,
    )

    stats = recipe.reviews.aggregate(note_moyenne=Avg("stars"), nb_avis=Count("id"))

    dietary_tags = []
    try:
        dietary_tags = request.user.profile.dietary_tags or []
    except UserProfile.DoesNotExist:
        pass

    alertes = _alertes_allergies(recipe, dietary_tags)

    # Dernier avis de l'utilisateur courant
    user_last_review = recipe.reviews.filter(user=request.user).order_by("-created_at").first()

    # Avis des membres de la famille (hors l'utilisateur courant, pour la section dédiée)
    family_reviews = []
    try:
        profile = request.user.profile
        if profile.family:
            family_ids = list(
                UserProfile.objects.filter(family=profile.family)
                .exclude(user=request.user)
                .values_list("user_id", flat=True)
            )
            family_reviews = list(
                recipe.reviews.filter(user_id__in=family_ids)
                .select_related("user")
                .order_by("-created_at")[:20]
            )
    except UserProfile.DoesNotExist:
        pass

    ctx = {
        "recipe": recipe,
        "note_moyenne": stats["note_moyenne"],
        "nb_avis": stats["nb_avis"],
        "alertes": alertes,
        "user_last_review": user_last_review,
        "family_reviews": family_reviews,
        "all_reviews": list(recipe.reviews.select_related("user").order_by("-created_at")[:30]),
    }
    return render(request, "menu/recettes/detail.html", ctx)


@require_POST
@login_required
def noter_recette(request, id):
    """Crée un avis (étoiles + commentaire). Répond en JSON."""
    recipe = get_object_or_404(Recipe, pk=id, actif=True)

    try:
        data  = json.loads(request.body)
        stars = int(data.get("stars", 0))
        comment = (data.get("comment") or "").strip() or None
    except (json.JSONDecodeError, ValueError, TypeError):
        return JsonResponse({"ok": False, "error": "Données invalides", "code": "INVALID_DATA"}, status=400)

    if not (1 <= stars <= 5):
        return JsonResponse({"ok": False, "error": "La note doit être entre 1 et 5", "code": "INVALID_STARS"}, status=400)

    Review.objects.create(recipe=recipe, user=request.user, stars=stars, comment=comment)

    stats = recipe.reviews.aggregate(note_moyenne=Avg("stars"), nb_avis=Count("id"))

    return JsonResponse({
        "ok": True,
        "new_average": round(stats["note_moyenne"], 1),
        "review_count": stats["nb_avis"],
        "review": {
            "user":    request.user.first_name or request.user.email,
            "stars":   stars,
            "comment": comment or "",
            "date":    date.today().strftime("%d/%m/%Y"),
        },
    })


# ─── API nutritionnelle ──────────────────────────────────────────────────────

@login_required
def recherche_nutrition(request):
    q = request.GET.get("q", "").strip()
    if not q:
        return JsonResponse({"ok": True, "results": []})
    results = rechercher_ingredient(q)
    return JsonResponse({"ok": True, "results": results})


# ─── Création / édition / suppression ────────────────────────────────────────

def _verifier_cuisinier(request):
    """Retourne le profil si Cuisinier, sinon None."""
    try:
        profile = request.user.profile
        return profile if profile.role in ("cuisinier", "chef_etoile") else None
    except UserProfile.DoesNotExist:
        return None


@login_required
def creer_recette(request):
    if not _verifier_cuisinier(request):
        messages.error(request, "Seuls les Cuisiniers peuvent créer des recettes.")
        return redirect("menu:liste_recettes")

    form = RecipeForm(request.POST or None, request.FILES or None)
    if request.method == "POST" and form.is_valid():
        cd = form.cleaned_data
        photo_url = None
        if cd.get("photo"):
            photo_url = upload_photo(cd["photo"])
            if cd["photo"] and photo_url is None:
                messages.warning(request, "L'upload de la photo a échoué — recette sauvegardée sans photo.")

        recipe = Recipe.objects.create(
            title=cd["title"],
            description=cd.get("description") or None,
            photo_url=photo_url,
            base_servings=cd["base_servings"],
            prep_time=cd.get("prep_time"),
            cook_time=cd.get("cook_time"),
            category=cd["category"],
            cuisine_type=cd.get("cuisine_type") or None,
            seasons=cd.get("seasons") or [],
            health_tags=cd.get("health_tags") or [],
            complexity=cd["complexity"],
            created_by=request.user,
        )
        sauvegarder_recette_depuis_post(recipe, request.POST)
        messages.success(request, "Recette enregistrée !")
        return redirect("menu:detail_recette", id=recipe.id)

    return render(request, "menu/recettes/formulaire.html", {"form": form, "recipe": None})


@login_required
def modifier_recette(request, id):
    recipe = get_object_or_404(Recipe, id=id, actif=True)
    if recipe.created_by != request.user and not _verifier_cuisinier(request):
        messages.error(request, "Vous ne pouvez pas modifier cette recette.")
        return redirect("menu:detail_recette", id=id)

    if request.method == "POST":
        form = RecipeForm(request.POST, request.FILES)
        if form.is_valid():
            cd = form.cleaned_data
            if cd.get("photo"):
                new_url = upload_photo(cd["photo"])
                if new_url:
                    recipe.photo_url = new_url
                else:
                    messages.warning(request, "L'upload de la photo a échoué — ancienne photo conservée.")

            recipe.title = cd["title"]
            recipe.description = cd.get("description") or None
            recipe.base_servings = cd["base_servings"]
            recipe.prep_time = cd.get("prep_time")
            recipe.cook_time = cd.get("cook_time")
            recipe.category = cd["category"]
            recipe.cuisine_type = cd.get("cuisine_type") or None
            recipe.seasons = cd.get("seasons") or []
            recipe.health_tags = cd.get("health_tags") or []
            recipe.complexity = cd["complexity"]
            recipe.save()
            sauvegarder_recette_depuis_post(recipe, request.POST)
            messages.success(request, "Recette enregistrée !")
            return redirect("menu:detail_recette", id=recipe.id)
    else:
        form = RecipeForm(initial={
            "title": recipe.title,
            "description": recipe.description,
            "base_servings": recipe.base_servings,
            "prep_time": recipe.prep_time,
            "cook_time": recipe.cook_time,
            "category": recipe.category,
            "cuisine_type": recipe.cuisine_type,
            "seasons": recipe.seasons,
            "health_tags": recipe.health_tags,
            "complexity": recipe.complexity,
        })

    recipe_data = recipe
    recipe_data.groups_prefetched = recipe.ingredient_groups.prefetch_related("ingredients").all()
    recipe_data.steps_prefetched = recipe.steps.all()
    recipe_data.sections_prefetched = recipe.sections.all()

    return render(request, "menu/recettes/formulaire.html", {"form": form, "recipe": recipe_data})


@require_POST
@login_required
def supprimer_recette(request, id):
    recipe = get_object_or_404(Recipe, id=id, actif=True)
    if recipe.created_by != request.user and not _verifier_cuisinier(request):
        messages.error(request, "Vous ne pouvez pas supprimer cette recette.")
        return redirect("menu:detail_recette", id=id)

    recipe.actif = False
    recipe.save(update_fields=["actif"])
    messages.success(request, f"« {recipe.title} » a été supprimée.")
    return redirect("menu:liste_recettes")


# ─── Backup / Restore / Import recettes ──────────────────────────────────────

def _verifier_staff(request):
    """Retourne True si l'utilisateur est staff Django."""
    return request.user.is_staff


@login_required
def backup_page(request):
    if not _verifier_staff(request):
        messages.error(request, "Accès réservé aux administrateurs.")
        return redirect("menu:home")
    return render(request, "menu/admin/backup.html")


@login_required
def export_backup(request):
    if not _verifier_staff(request):
        messages.error(request, "Accès réservé aux administrateurs.")
        return redirect("menu:home")
    try:
        zip_bytes = exporter_backup()
        from datetime import datetime
        filename = f"menu_backup_{datetime.now().strftime('%Y%m%d_%H%M%S')}.zip"
        response = HttpResponse(zip_bytes, content_type="application/zip")
        response["Content-Disposition"] = f'attachment; filename="{filename}"'
        logger.info("Backup exporté par %s.", request.user.email)
        return response
    except Exception as exc:
        logger.error("Erreur export backup : %s", exc)
        messages.error(request, f"Erreur lors de l'export : {exc}")
        return redirect("menu:backup_page")


@require_POST
@login_required
def import_backup(request):
    if not _verifier_staff(request):
        messages.error(request, "Accès réservé aux administrateurs.")
        return redirect("menu:home")

    zip_file = request.FILES.get("backup_zip")
    if not zip_file:
        messages.error(request, "Aucun fichier sélectionné.")
        return redirect("menu:backup_page")

    try:
        stats = restaurer_backup(zip_file.read())
        messages.success(
            request,
            f"Restauration réussie — {stats['total']} objets restaurés. "
            "Reconnectez-vous pour continuer.",
        )
        logout(request)
        return redirect("menu:connexion")
    except Exception as exc:
        logger.error("Erreur restauration backup : %s", exc)
        messages.error(request, f"Erreur lors de la restauration : {exc}")
        return redirect("menu:backup_page")


@require_POST
@login_required
def import_recettes(request):
    if not _verifier_staff(request) and not _verifier_cuisinier(request):
        messages.error(request, "Accès non autorisé.")
        return redirect("menu:home")

    json_file = request.FILES.get("recette_json")
    zip_file = request.FILES.get("recettes_zip")
    imported, skipped, errors = 0, 0, []

    if json_file:
        try:
            data = json.loads(json_file.read().decode("utf-8"))
            _, created = importer_recette_depuis_json(data, request.user)
            if created:
                imported += 1
            else:
                skipped += 1
        except Exception as exc:
            errors.append(str(exc))

    elif zip_file:
        try:
            with zipfile.ZipFile(zip_file, "r") as zf:
                json_names = [n for n in zf.namelist() if n.lower().endswith(".json")]
                for name in json_names:
                    try:
                        data = json.loads(zf.read(name).decode("utf-8"))
                        _, created = importer_recette_depuis_json(data, request.user)
                        if created:
                            imported += 1
                        else:
                            skipped += 1
                    except Exception as exc:
                        errors.append(f"{name} : {exc}")
        except Exception as exc:
            errors.append(str(exc))
    else:
        messages.warning(request, "Aucun fichier sélectionné.")
        return redirect("menu:backup_page")

    parts = [f"{imported} recette(s) importée(s)"]
    if skipped:
        parts.append(f"{skipped} ignorée(s) (titre déjà existant)")
    if errors:
        parts.append(f"{len(errors)} erreur(s) : {' | '.join(errors[:3])}")

    if errors and not imported:
        messages.error(request, " — ".join(parts))
    elif errors:
        messages.warning(request, " — ".join(parts))
    else:
        messages.success(request, " — ".join(parts))

    logger.info("Import recettes par %s : %d créées, %d ignorées, %d erreurs.",
                request.user.email, imported, skipped, len(errors))
    return redirect("menu:backup_page")

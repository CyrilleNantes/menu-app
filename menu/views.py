import logging
from datetime import date

from django.contrib import messages
from django.contrib.auth import login, logout
from django.contrib.auth.decorators import login_required
from django.contrib.auth.models import User
from django.db.models import Avg, Count, Q
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.http import require_POST

from .forms import InscriptionForm, RecipeForm
from .integrations.cloudinary import upload_photo
from .models import Family, Ingredient, Recipe, UserProfile
from .services import sauvegarder_recette_depuis_post

logger = logging.getLogger("menu")

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


@login_required
def planning(request):
    # Placeholder — implémenté à l'étape 7
    try:
        profile = request.user.profile
    except UserProfile.DoesNotExist:
        return redirect("menu:rejoindre_famille_page")

    if not profile.family:
        return redirect("menu:rejoindre_famille_page")

    return render(request, "menu/planning/index.html")


# ─── Catalogue recettes ───────────────────────────────────────────────────────

@login_required
def mode_cuisine(request, id):
    # Placeholder — implémenté à l'étape 10
    recipe = get_object_or_404(Recipe, id=id, actif=True)
    return render(request, "menu/recettes/cuisine.html", {"recipe": recipe})


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

    ctx = {
        "recipe": recipe,
        "note_moyenne": stats["note_moyenne"],
        "nb_avis": stats["nb_avis"],
        "alertes": alertes,
    }
    return render(request, "menu/recettes/detail.html", ctx)


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

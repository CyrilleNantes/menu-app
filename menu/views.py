import json
import logging
import secrets
import zipfile
from datetime import date, timedelta

from django.contrib import messages
from django.contrib.auth import login, logout
from django.contrib.auth.decorators import login_required
from django.contrib.auth.models import User
from django.db import transaction
from django.db.models import Avg, Count, Prefetch, Q
from django.http import HttpResponse, JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils import timezone
from django.views.decorators.http import require_GET, require_POST

from .forms import InscriptionForm, RecipeForm
from .integrations.cloudinary import upload_photo
from .integrations.google_auth import google_build_auth_url, google_exchange_code
from .integrations.google_calendar import google_calendar_export_planning
from .integrations.google_tasks import google_tasks_export_courses
from .models import Family, Ingredient, IngredientRef, KnownIngredient, Meal, MealProposal, NutritionConfig, Recipe, RecipePhoto, Review, ShoppingItem, ShoppingList, TokenOAuth, UserProfile, WeekPlan
from .services import (
    bilan_planning,
    calculer_alertes_planning,
    calculer_macros_recette,
    calculer_wpd,
    compute_ingredient_macros_from_ciqual,
    exporter_backup,
    generer_liste_courses,
    importer_recette_depuis_json,
    notifier_nouvelle_proposition,
    notifier_planning_publie,
    rechercher_ciqual,
    rechercher_connus,
    restaurer_backup,
    sauvegarder_recette_depuis_post,
    suggerer_recettes,
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


# Configuration des tags alimentaires : 14 allergènes majeurs EU + végétarien/végan
DIETARY_TAG_CONFIG = {
    "gluten":         {"label": "Gluten",          "emoji": "🌾", "keywords": ["farine", "blé", "seigle", "orge", "avoine", "pain", "pâte", "semoule", "couscous", "boulgour", "épeautre", "chapelure", "brioche"]},
    "lactose":        {"label": "Lactose",         "emoji": "🥛", "keywords": ["lait", "beurre", "crème", "fromage", "yaourt", "mozzarella", "cheddar", "parmesan", "gruyère", "ricotta", "mascarpone", "kéfir", "crème fraîche"]},
    "oeufs":          {"label": "Œufs",            "emoji": "🥚", "keywords": ["œuf", "oeuf", "jaune d'œuf", "blanc d'œuf", "mayonnaise"]},
    "poisson":        {"label": "Poisson",         "emoji": "🐟", "keywords": ["saumon", "thon", "cabillaud", "sardine", "anchois", "truite", "dorade", "maquereau", "sole", "bar", "lieu", "merlan", "tilapia", "hareng"]},
    "crustaces":      {"label": "Crustacés",       "emoji": "🦐", "keywords": ["crevette", "homard", "crabe", "langoustine", "écrevisse", "langouste"]},
    "mollusques":     {"label": "Mollusques",      "emoji": "🦪", "keywords": ["moule", "huître", "calamar", "poulpe", "seiche", "escargot", "palourde", "coque", "bulot"]},
    "fruits_a_coque": {"label": "Fruits à coque",  "emoji": "🥜", "keywords": ["noix", "noisette", "amande", "cajou", "pistache", "noix de coco", "pécan", "macadamia", "noix du brésil", "noix de cajou"]},
    "arachides":      {"label": "Arachides",       "emoji": "🥜", "keywords": ["cacahuète", "arachide", "beurre de cacahuète"]},
    "soja":           {"label": "Soja",            "emoji": "🫘", "keywords": ["soja", "tofu", "edamame", "miso", "sauce soja", "tempeh", "lait de soja"]},
    "celeri":         {"label": "Céleri",          "emoji": "🌿", "keywords": ["céleri", "celeri", "céleri-rave"]},
    "moutarde":       {"label": "Moutarde",        "emoji": "🌿", "keywords": ["moutarde", "graines de moutarde"]},
    "sesame":         {"label": "Sésame",          "emoji": "🌾", "keywords": ["sésame", "sesame", "tahini", "halva"]},
    "sulfites":       {"label": "Sulfites",        "emoji": "🍷", "keywords": ["vin", "vinaigre de vin", "vinaigre balsamique", "raisin sec", "abricot sec"]},
    "lupin":          {"label": "Lupin",           "emoji": "🌿", "keywords": ["lupin", "farine de lupin"]},
    "vegetarien":     {"label": "Végétarien",      "emoji": "🥦", "keywords": []},
    "vegan":          {"label": "Végan",           "emoji": "🌱", "keywords": []},
}

# Liste ordonnée pour les formulaires / templates
DIETARY_TAG_CHOICES = [
    (key, cfg["label"], cfg["emoji"])
    for key, cfg in DIETARY_TAG_CONFIG.items()
]


def _saison_courante():
    mois = date.today().month
    if mois in (3, 4, 5):
        return "printemps"
    if mois in (6, 7, 8):
        return "ete"
    if mois in (9, 10, 11):
        return "automne"
    return "hiver"


def _alertes_allergies(ingredients, dietary_tags):
    """
    Retourne une liste de dicts {tag, label, emoji, ingredients}
    pour chaque restriction de l'utilisateur correspondant à un ingrédient.

    ingredients : liste d'objets Ingredient (déjà chargés)
    dietary_tags : liste de tags du UserProfile
    """
    if not dietary_tags or not ingredients:
        return []
    alertes = []
    noms = [(ing.name, ing.name.lower()) for ing in ingredients]
    for tag in dietary_tags:
        cfg = DIETARY_TAG_CONFIG.get(tag)
        if not cfg or not cfg["keywords"]:
            continue
        matching = []
        for ing_name, ing_lower in noms:
            for mot in cfg["keywords"]:
                if mot in ing_lower:
                    if ing_name not in matching:
                        matching.append(ing_name)
                    break
        if matching:
            alertes.append({
                "tag": tag,
                "label": cfg["label"],
                "emoji": cfg["emoji"],
                "ingredients": matching,
            })
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
        next_url = request.GET.get("next", "")
        return redirect(next_url if next_url.startswith("/") else "menu:home")

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
    if request.method == "POST":
        import re
        invite_link = request.POST.get("invite_link", "").strip()
        match = re.search(r"famille/inviter/([0-9a-f-]{36})", invite_link)
        if not match:
            return render(request, "menu/auth/rejoindre.html", {"error": "Lien invalide. Vérifiez l'URL copiée."})
        return redirect("menu:rejoindre_famille", token=match.group(1))
    return render(request, "menu/auth/rejoindre.html")


@login_required
def profil(request):
    """Page de profil : rang, progression, stats, membres de la famille."""
    try:
        profile = request.user.profile
    except UserProfile.DoesNotExist:
        return redirect("menu:home")

    rank_info = profile.rank_info

    # Stats selon le rôle
    nb_recettes   = Recipe.objects.filter(created_by=request.user, actif=True).count()
    nb_avis       = Review.objects.filter(user=request.user).count()
    nb_proposals  = MealProposal.objects.filter(proposed_by=request.user).count()

    # Membres de la famille
    famille_members = []
    if profile.family:
        famille_members = list(
            UserProfile.objects
            .filter(family=profile.family)
            .exclude(user=request.user)
            .select_related("user")
            .order_by("user__first_name")
        )

    google_connected = TokenOAuth.objects.filter(user=request.user, service="google").exists()

    ctx = {
        "profile":              profile,
        "rank_info":            rank_info,
        "nb_recettes":          nb_recettes,
        "nb_avis":              nb_avis,
        "nb_proposals":         nb_proposals,
        "famille_members":      famille_members,
        "google_connected":     google_connected,
        "dietary_tag_choices":  DIETARY_TAG_CHOICES,
        "rank_cuisinier":       UserProfile._RANK_CUISINIER,
        "rank_convive":         UserProfile._RANK_CONVIVE,
    }
    return render(request, "menu/profil.html", ctx)


@login_required
def dashboard_nutrition(request):
    """
    Dashboard nutritionnel individuel — semaine en cours, macros personnalisées
    via UserProfile.portions_factor. Toutes les valeurs sont des repères indicatifs PNNS.
    """
    from datetime import date as date_type

    profile = _get_profile(request)
    if not profile:
        return redirect("menu:home")

    pf = profile.portions_factor  # facteur de portion de l'utilisateur
    config = NutritionConfig.get()

    # Cibles journalières personnalisées (déjeuner + dîner = 2 × cible dîner)
    cal_day_target  = config.calories_dinner_target  * 2 * pf
    prot_day_target = config.proteins_dinner_target  * 2 * pf
    cal_week_target  = cal_day_target  * 7
    prot_week_target = prot_day_target * 7

    # Planning de la semaine en cours pour la famille
    today     = date_type.today()
    iso       = today.isocalendar()
    week_plan = None
    days_data = []
    total_cal_week  = 0.0
    total_prot_week = 0.0

    if profile.family:
        from datetime import timedelta
        monday = today - timedelta(days=today.weekday())
        week_plan = (
            WeekPlan.objects
            .filter(family=profile.family, period_start__lte=monday + timedelta(days=6), period_end__gte=monday)
            .order_by("-period_start")
            .first()
        )

    # Q1 — _status défini une seule fois, hors boucle
    def _status(actual, target):
        if target <= 0 or actual <= 0:
            return "neutral"
        pct = actual / target * 100
        if pct < 60 or pct > 130:
            return "alert"
        if pct < 80 or pct > 110:
            return "warning"
        return "ok"

    if week_plan:
        meals_qs = (
            Meal.objects
            .filter(week_plan=week_plan, recipe__isnull=False)
            .select_related("recipe")
            .order_by("date", "meal_time")
        )
        meals_by_date: dict = {}
        for m in meals_qs:
            meals_by_date.setdefault(m.date, []).append(m)

        DAY_NAMES = ["Lundi", "Mardi", "Mercredi", "Jeudi", "Vendredi", "Samedi", "Dimanche"]
        from datetime import timedelta
        monday = week_plan.period_start

        for i in range(7):
            d = monday + timedelta(days=i)
            day_meals_raw = meals_by_date.get(d, [])
            day_cal  = 0.0
            day_prot = 0.0
            meals_out = []

            for m in day_meals_raw:
                r = m.recipe
                cal  = round((r.calories_per_serving  or 0) * pf, 1)
                prot = round((r.proteins_per_serving or 0) * pf, 1)
                day_cal  += cal
                day_prot += prot
                meals_out.append({
                    "meal_time":     m.meal_time,
                    "recipe_id":     r.id,
                    "recipe_title":  r.title,
                    "calories":      cal  if r.calories_per_serving  else None,
                    "proteins":      prot if r.proteins_per_serving else None,
                    "is_leftovers":  m.is_leftovers,
                })

            total_cal_week  += day_cal
            total_prot_week += day_prot

            days_data.append({
                "date":       d,
                "day_name":   DAY_NAMES[i],
                "is_today":   d == today,
                "meals":      meals_out,
                "total_cal":  round(day_cal, 0),
                "total_prot": round(day_prot, 1),
                "cal_status":  _status(day_cal,  cal_day_target),
                "prot_status": _status(day_prot, prot_day_target),
            })

    def _pct(actual, target):
        return min(round(actual / target * 100) if target > 0 else 0, 130)

    ctx = {
        "profile":           profile,
        "week_plan":         week_plan,
        "days_data":         days_data,
        "total_cal_week":    round(total_cal_week, 0),
        "total_prot_week":   round(total_prot_week, 1),
        "cal_day_target":    round(cal_day_target,  0),
        "prot_day_target":   round(prot_day_target, 1),
        "cal_week_target":   round(cal_week_target,  0),
        "prot_week_target":  round(prot_week_target, 1),
        "cal_week_pct":      _pct(total_cal_week,  cal_week_target),
        "prot_week_pct":     _pct(total_prot_week, prot_week_target),
        # Q2 — réutilise _status au lieu de lambdas anonymes dupliquées
        "cal_week_status":   _status(total_cal_week,  cal_week_target),
        "prot_week_status":  _status(total_prot_week, prot_week_target),
    }
    return render(request, "menu/profil/nutrition.html", ctx)


def _get_profile(request):
    """Retourne le profil utilisateur ou None."""
    try:
        return request.user.profile
    except UserProfile.DoesNotExist:
        return None


# ─── Planning par période ─────────────────────────────────────────────────────

@login_required
def planning(request):
    """Redirige vers la période en cours ou la création si aucune n'existe."""
    profile = _get_profile(request)
    if not profile or not profile.family:
        return redirect("menu:rejoindre_famille_page")
    today = date.today()
    plan = (
        WeekPlan.objects
        .filter(family=profile.family, period_end__gte=today)
        .order_by("period_start")
        .first()
    )
    if not plan:
        plan = (
            WeekPlan.objects
            .filter(family=profile.family)
            .order_by("-period_end")
            .first()
        )
    if plan:
        return redirect("menu:planning_periode", plan_id=plan.id)
    return redirect("menu:creer_periode")


@login_required
def creer_periode(request):
    """GET : formulaire de création d'une période. POST : crée le WeekPlan."""
    profile = _get_profile(request)
    if not profile or not profile.family:
        return redirect("menu:rejoindre_famille_page")
    if not _verifier_cuisinier(request):
        messages.error(request, "Réservé aux Cuisiniers.")
        return redirect("menu:planning")

    today = date.today()

    if request.method == "POST":
        jours_raw = request.POST.getlist("jours")  # liste de "YYYY-MM-DD"
        if not jours_raw:
            messages.error(request, "Sélectionne au moins un jour.")
            return redirect("menu:creer_periode")

        try:
            jours = sorted(set([date.fromisoformat(d) for d in jours_raw]))
        except ValueError:
            messages.error(request, "Dates invalides.")
            return redirect("menu:creer_periode")

        if jours[0] < today:
            messages.error(request, "Impossible de créer une période dans le passé.")
            return redirect("menu:creer_periode")
        if len(jours) > 14:
            messages.error(request, "Une période ne peut pas dépasser 14 jours.")
            return redirect("menu:creer_periode")

        period_start = jours[0]
        period_end   = jours[-1]

        if WeekPlan.objects.filter(family=profile.family, period_start=period_start).exists():
            messages.error(request, "Une période commençant ce jour existe déjà.")
            return redirect("menu:creer_periode")

        plan = WeekPlan.objects.create(
            family=profile.family,
            period_start=period_start,
            period_end=period_end,
            active_dates=[d.isoformat() for d in jours],
            created_by=request.user,
            status="draft",
        )
        return redirect("menu:planning_periode", plan_id=plan.id)

    # GET — calcule la date de départ suggérée
    after_str = request.GET.get("after")
    if after_str:
        try:
            suggested_start = date.fromisoformat(after_str) + timedelta(days=1)
        except ValueError:
            suggested_start = today
    else:
        last_plan = (
            WeekPlan.objects
            .filter(family=profile.family)
            .order_by("-period_end")
            .first()
        )
        if last_plan and last_plan.period_end >= today:
            suggested_start = last_plan.period_end + timedelta(days=1)
        else:
            suggested_start = today

    JOURS_FR = ["Lundi", "Mardi", "Mercredi", "Jeudi", "Vendredi", "Samedi", "Dimanche"]

    # 7 jours depuis suggested_start, ordre chronologique
    candidate_days_info = [
        {"date": suggested_start + timedelta(days=i), "label": JOURS_FR[(suggested_start + timedelta(days=i)).weekday()], "iso": (suggested_start + timedelta(days=i)).isoformat()}
        for i in range(7)
    ]

    return render(request, "menu/planning/creer_periode.html", {
        "today_iso": today.isoformat(),
        "suggested_start": suggested_start,
        "candidate_days": candidate_days_info,
    })


@login_required
def planning_periode(request, plan_id):
    profile = _get_profile(request)
    if not profile or not profile.family:
        return redirect("menu:rejoindre_famille_page")

    plan = get_object_or_404(WeekPlan, id=plan_id, family=profile.family)
    is_cuisinier = profile.role in ("cuisinier", "chef_etoile")

    active_dates = plan.get_active_dates()

    meals_qs = (
        Meal.objects.filter(week_plan=plan)
        .select_related("recipe", "source_meal__recipe")
    )
    meal_by_slot = {(m.date, m.meal_time): m for m in meals_qs}

    JOURS_FR = ["Lundi", "Mardi", "Mercredi", "Jeudi", "Vendredi", "Samedi", "Dimanche"]
    grid = [
        {
            "date": d,
            "day_name": JOURS_FR[d.weekday()],
            "lunch": meal_by_slot.get((d, "lunch")),
            "dinner": meal_by_slot.get((d, "dinner")),
        }
        for d in active_dates
    ]

    # Backlog propositions famille
    proposals = []
    user_proposals = []
    if is_cuisinier:
        proposals = list(
            MealProposal.objects.filter(family=profile.family, week_plan__isnull=True)
            .select_related("recipe", "proposed_by")
            .order_by("-created_at")
        )
    else:
        user_proposals = list(
            MealProposal.objects.filter(family=profile.family, week_plan__isnull=True)
            .select_related("recipe", "proposed_by")
            .order_by("-created_at")
        )

    # Navigation prev/next par date
    prev_plan = (
        WeekPlan.objects
        .filter(family=profile.family, period_end__lt=plan.period_start)
        .order_by("-period_end")
        .first()
    )
    next_plan = (
        WeekPlan.objects
        .filter(family=profile.family, period_start__gt=plan.period_end)
        .order_by("period_start")
        .first()
    )

    # Présence
    family_members = list(
        UserProfile.objects
        .filter(family=profile.family)
        .select_related("user")
        .order_by("user__first_name")
    )
    present_member_ids = set(plan.present_members.values_list("id", flat=True))

    # Sélecteur de jours : 7 jours depuis period_start, ordre chronologique
    active_dates_iso = set(plan.active_dates) if plan.active_dates else {d.isoformat() for d in active_dates}

    periode_candidate_days = [
        {"date": plan.period_start + timedelta(days=i), "label": JOURS_FR[(plan.period_start + timedelta(days=i)).weekday()], "iso": (plan.period_start + timedelta(days=i)).isoformat()}
        for i in range(7)
    ]

    ctx = {
        "plan": plan,
        "grid": grid,
        "period_start": plan.period_start,
        "period_end": plan.period_end,
        "prev_plan": prev_plan,
        "next_plan": next_plan,
        "proposals": proposals,
        "user_proposals": user_proposals,
        "is_cuisinier": is_cuisinier,
        "meals_avec_recette": [
            {"id": m.id, "label": f"{JOURS_FR[m.date.weekday()]} {'Midi' if m.meal_time == 'lunch' else 'Soir'} — {m.recipe.title}"}
            for m in meals_qs if m.recipe and not m.is_leftovers
        ],
        "has_shopping_list": ShoppingList.objects.filter(week_plan=plan).exists(),
        "google_connected": TokenOAuth.objects.filter(user=request.user, service="google").exists(),
        "bilan": bilan_planning(plan) if is_cuisinier else None,
        "family_members": family_members,
        "present_member_ids": present_member_ids,
        "guests": plan.guests,
        "periode_candidate_days": periode_candidate_days,
        "active_dates_iso": active_dates_iso,
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

    # ── Créneau absent (personne ne mange à la maison) ─────────────────────────
    if body.get("absent") is True:
        meal, _ = Meal.objects.update_or_create(
            week_plan=plan,
            date=meal_date,
            meal_time=meal_time,
            defaults={
                "recipe": None,
                "servings_count": None,
                "is_leftovers": False,
                "source_meal": None,
                "absent": True,
            },
        )
        return JsonResponse({"ok": True, "absent": True, "meal_id": meal.id})

    # ── Lever l'absence (retour à créneau vide normal) ──────────────────────────
    if body.get("absent") is False:
        Meal.objects.filter(week_plan=plan, date=meal_date, meal_time=meal_time).update(absent=False)
        return JsonResponse({"ok": True, "absent": False})

    # ── Recette (optionnelle) ────────────────────────────────────────────────────
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
            "absent": False,  # toute sauvegarde de recette lève l'absence
        },
    )

    return JsonResponse({
        "ok": True,
        "absent": False,
        "meal_id": meal.id,
        "recipe_id": recipe.id if recipe else None,
        "recipe_title": recipe.title if recipe else None,
        "servings_count": meal.servings_count,
        "is_leftovers": meal.is_leftovers,
        "calories_per_serving": recipe.calories_per_serving if recipe else None,
    })


@login_required
def suggestions_repas(request, plan_id):
    """
    AJAX GET : retourne les 5 meilleures suggestions de recettes pour un créneau.
    Params GET : date=YYYY-MM-DD & meal_time=lunch|dinner
    """
    profile = _get_profile(request)
    if not profile or not _verifier_cuisinier(request):
        return JsonResponse({"ok": False, "error": "Réservé aux Cuisiniers", "code": "FORBIDDEN"}, status=403)

    plan = get_object_or_404(WeekPlan, id=plan_id, family=profile.family)

    date_str  = request.GET.get("date", "").strip()
    meal_time = request.GET.get("meal_time", "").strip()

    if not date_str or meal_time not in ("lunch", "dinner"):
        return JsonResponse({"ok": False, "error": "Paramètres invalides", "code": "BAD_PARAMS"}, status=400)

    try:
        from datetime import date as date_type
        target_date = date_type.fromisoformat(date_str)
    except ValueError:
        return JsonResponse({"ok": False, "error": "Date invalide", "code": "BAD_DATE"}, status=400)

    try:
        wpd     = calculer_wpd(plan, NutritionConfig.get())
        results = suggerer_recettes(profile.family, plan, target_date, meal_time)
    except Exception as exc:
        logger.error("suggestions_repas — erreur inattendue : %s", exc, exc_info=True)
        return JsonResponse({"ok": False, "error": "Erreur serveur", "code": "SERVER_ERROR"}, status=500)

    if not results:
        return JsonResponse({
            "ok": True,
            "wpd": 1.0,
            "deficit_proteique": False,
            "suggestions": [],
            "message": "Pas assez de recettes dans le catalogue pour cette période.",
        })

    return JsonResponse({
        "ok":               True,
        "wpd":              wpd,
        "deficit_proteique": wpd > 1.0,
        "suggestions": [
            {
                "recipe_id":          r["recipe"].id,
                "title":              r["recipe"].title,
                "score":              r["score"],
                "protein_score":      r["protein_score"],
                "protein_level":      r["protein_level"],
                "proteins_per_serving": r["proteins_per_serving"],
                "reasons":            r["reasons"],
            }
            for r in results
        ],
    })


@require_GET
@login_required
def bilan_planning_ajax(request, plan_id):
    """AJAX GET : retourne le bilan équilibre de la semaine (variété + nutrition)."""
    profile = _get_profile(request)
    if not profile or not profile.family:
        return JsonResponse({"ok": False, "error": "Famille requise", "code": "NO_FAMILY"}, status=403)
    if not _verifier_cuisinier(request):
        return JsonResponse({"ok": False, "error": "Réservé aux Cuisiniers", "code": "FORBIDDEN"}, status=403)

    plan = get_object_or_404(WeekPlan, id=plan_id, family=profile.family)
    data = bilan_planning(plan)
    return JsonResponse({"ok": True, "bilan": data})


@require_POST
@login_required
def valider_planning(request, plan_id):
    """Valide un WeekPlan (brouillon → publié)."""
    profile = _get_profile(request)
    if not profile or not _verifier_cuisinier(request):
        messages.error(request, "Réservé aux Cuisiniers.")
        return redirect("menu:planning")

    plan = get_object_or_404(WeekPlan, id=plan_id, family=profile.family)

    if plan.status in ("published", "finished"):
        messages.warning(request, "Ce planning est déjà validé.")
    elif not plan.meals.filter(recipe__isnull=False).exists():
        messages.error(request, "Impossible de valider un planning vide (aucune recette planifiée).")
    else:
        plan.status = "published"
        plan.save(update_fields=["status"])
        messages.success(request, "Menu validé ! Vous pouvez maintenant générer la liste de courses.")
        logger.info("Planning %d validé par %s.", plan.id, request.user.email)
        notifier_planning_publie(plan)

    return redirect("menu:planning_periode", plan_id=plan.id)


@require_POST
@login_required
def rouvrir_planning(request, plan_id):
    """Repasse un WeekPlan en brouillon. Supprime la liste de courses si statut était finished."""
    profile = _get_profile(request)
    if not profile or not _verifier_cuisinier(request):
        messages.error(request, "Réservé aux Cuisiniers.")
        return redirect("menu:planning")

    plan = get_object_or_404(WeekPlan, id=plan_id, family=profile.family)

    if plan.status == "finished":
        ShoppingList.objects.filter(week_plan=plan).delete()
        messages.info(request, "Liste de courses supprimée. Planning repassé en brouillon.")
    elif plan.status == "published":
        messages.info(request, "Planning repassé en brouillon.")
    else:
        messages.warning(request, "Le planning est déjà en brouillon.")
        return redirect("menu:planning_periode", plan_id=plan.id)

    plan.status = "draft"
    plan.save(update_fields=["status"])
    logger.info("Planning %d réouvert par %s.", plan.id, request.user.email)
    return redirect("menu:planning_periode", plan_id=plan.id)


@require_POST
@login_required
def maj_presence(request, plan_id):
    """AJAX : met à jour les membres présents et invités d'une période."""
    profile = _get_profile(request)
    if not profile or not profile.family:
        return JsonResponse({"ok": False, "error": "Famille requise"}, status=403)

    plan = get_object_or_404(WeekPlan, id=plan_id, family=profile.family)

    try:
        body = json.loads(request.body)
    except (json.JSONDecodeError, AttributeError):
        return JsonResponse({"ok": False, "error": "JSON invalide"}, status=400)

    member_ids = body.get("member_ids", [])
    guests = [g.strip() for g in body.get("guests", []) if g.strip()]

    valid_ids = set(
        UserProfile.objects
        .filter(family=profile.family, user_id__in=member_ids)
        .values_list("user_id", flat=True)
    )
    with transaction.atomic():
        plan.present_members.set(valid_ids)
        plan.guests = guests
        plan.save(update_fields=["guests"])

    return JsonResponse({"ok": True})


@require_POST
@login_required
def modifier_jours_periode(request, plan_id):
    """Met à jour les jours actifs d'une période (active_dates + period_end). Cuisinier uniquement."""
    profile = _get_profile(request)
    if not profile or not _verifier_cuisinier(request):
        messages.error(request, "Réservé aux Cuisiniers.")
        return redirect("menu:planning_periode", plan_id=plan_id)

    plan = get_object_or_404(WeekPlan, id=plan_id, family=profile.family)

    jours_raw = request.POST.getlist("jours")
    if not jours_raw:
        messages.error(request, "Sélectionne au moins un jour.")
        return redirect("menu:planning_periode", plan_id=plan_id)

    try:
        jours = sorted(set([date.fromisoformat(d) for d in jours_raw]))
    except ValueError:
        messages.error(request, "Dates invalides.")
        return redirect("menu:planning_periode", plan_id=plan_id)

    if len(jours) > 14:
        messages.error(request, "Maximum 14 jours par période.")
        return redirect("menu:planning_periode", plan_id=plan_id)

    with transaction.atomic():
        old_end = plan.period_end
        plan.active_dates = [d.isoformat() for d in jours]
        plan.period_end = jours[-1]
        plan.save(update_fields=["active_dates", "period_end"])
        Meal.objects.filter(week_plan=plan).exclude(date__in=jours).delete()

        # Si la fin a changé, recaler la période suivante (brouillon sans repas)
        new_end = jours[-1]
        if new_end != old_end:
            next_plan = (
                WeekPlan.objects
                .filter(family=profile.family, period_start__gt=plan.period_start)
                .order_by("period_start")
                .first()
            )
            expected_start = new_end + timedelta(days=1)
            if (next_plan
                    and next_plan.period_start != expected_start
                    and next_plan.status == "draft"
                    and not Meal.objects.filter(week_plan=next_plan).exists()):
                delta = expected_start - next_plan.period_start
                shifted = [d + delta for d in next_plan.get_active_dates()]
                next_plan.period_start = expected_start
                next_plan.period_end = shifted[-1]
                next_plan.active_dates = [d.isoformat() for d in shifted]
                next_plan.save(update_fields=["period_start", "period_end", "active_dates"])

    return redirect("menu:planning_periode", plan_id=plan_id)


@require_POST
@login_required
def proposer_repas(request, plan_id):
    """AJAX : un Convive propose une recette pour ce planning. Réservé aux Convives."""
    profile = _get_profile(request)
    if not profile or not profile.family:
        return JsonResponse({"ok": False, "error": "Famille requise", "code": "NO_FAMILY"}, status=403)
    if profile.role in ("cuisinier", "chef_etoile"):
        return JsonResponse({"ok": False, "error": "Les Cuisiniers peuvent directement modifier le planning", "code": "FORBIDDEN"}, status=403)

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
        week_plan=None,
    )

    return JsonResponse({
        "ok": True,
        "proposal_id": proposal.id,
        "recipe_title": recipe.title,
        "proposed_by": request.user.first_name or request.user.email,
    })


@require_POST
@login_required
def creer_proposition_recette(request, id):
    """Propose une recette depuis sa fiche. Alimente le backlog famille pour tous les membres."""
    profile = _get_profile(request)
    if not profile or not profile.family:
        messages.error(request, "Vous devez appartenir à une famille pour proposer une recette.")
        return redirect("menu:detail_recette", id=id)

    recipe = get_object_or_404(Recipe, id=id, actif=True)
    MealProposal.objects.create(
        family=profile.family,
        recipe=recipe,
        proposed_by=request.user,
        week_plan=None,
    )
    messages.success(request, f"« {recipe.title} » ajouté à tes propositions !")
    logger.info("Proposition recette '%s' par %s.", recipe.title, request.user.email)
    return redirect("menu:detail_recette", id=id)


@require_POST
@login_required
def supprimer_proposition(request, proposal_id):
    """Supprime une proposition — accessible au Cuisinier (ignorer) et au Convive proposant (annuler)."""
    proposal = get_object_or_404(MealProposal, pk=proposal_id)
    profile  = _get_profile(request)

    if not profile or profile.family != proposal.family:
        return JsonResponse({"ok": False, "error": "Accès refusé"}, status=403)

    is_cuisinier = profile.role in ("cuisinier", "chef_etoile")
    is_proposer  = proposal.proposed_by == request.user

    if not is_cuisinier and not is_proposer:
        return JsonResponse({"ok": False, "error": "Accès refusé"}, status=403)

    proposal.delete()
    return JsonResponse({"ok": True})


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
    """Génère la liste de courses et passe le plan en 'finished'. Cuisinier uniquement."""
    plan = get_object_or_404(WeekPlan, pk=plan_id)
    profile = _get_profile(request)
    if not profile or profile.family != plan.family:
        messages.error(request, "Accès refusé.")
        return redirect("menu:planning")
    if profile.role not in ("cuisinier", "chef_etoile"):
        messages.error(request, "Réservé au Cuisinier.")
        return redirect("menu:planning")
    if plan.status not in ("published", "finished"):
        messages.error(request, "Valide d'abord le menu avant de générer la liste de courses.")
        return redirect("menu:planning_periode", plan_id=plan.id)

    try:
        generer_liste_courses(plan)
        plan.status = "finished"
        plan.save(update_fields=["status"])
        messages.success(request, "Liste de courses générée ! La période est maintenant terminée.")
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

    is_cuisinier = profile.role in ("cuisinier", "chef_etoile")

    ctx = {
        "plan": plan,
        "shopping_list": shopping_list,
        "groups": groups,
        "nb_total": nb_total,
        "nb_checked": nb_checked,
        "is_cuisinier": is_cuisinier,
        "google_connected": TokenOAuth.objects.filter(user=request.user, service="google").exists(),
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
def audit_ciqual(request):
    """
    Page temporaire d'audit du mapping ingrédients ↔ IngredientRef Ciqual.
    Accessible aux Cuisiniers et staff uniquement.
    """
    if not (request.user.is_staff or _verifier_cuisinier(request)):
        return redirect("menu:liste_recettes")

    ingredients = (
        Ingredient.objects
        .select_related("recipe", "ciqual_ref")
        .filter(recipe__actif=True)
        .order_by("recipe__title", "name")
    )

    total      = ingredients.count()
    matched    = ingredients.filter(ciqual_ref__isnull=False).count()
    non_calc   = ingredients.filter(ciqual_ref__isnull=True, calories__isnull=True).count()
    non_mapped = total - matched - non_calc

    return render(request, "menu/recettes/ciqual_audit.html", {
        "ingredients": ingredients,
        "total":       total,
        "matched":     matched,
        "non_calc":    non_calc,
        "non_mapped":  non_mapped,
    })


@login_required
def gestion_ciqual_ref(request):
    """Liste paginée + recherche du référentiel Ciqual (IngredientRef)."""
    if not (request.user.is_staff or _verifier_cuisinier(request)):
        return redirect("menu:liste_recettes")

    q      = request.GET.get('q', '').strip()
    groupe = request.GET.get('groupe', '').strip()

    qs = IngredientRef.objects.all().order_by('nom_fr')
    if q:
        qs = qs.filter(Q(nom_fr__icontains=q) | Q(nom_normalise__icontains=q))
    if groupe:
        qs = qs.filter(groupe=groupe)

    groupes = (IngredientRef.objects.values_list('groupe', flat=True)
               .distinct().order_by('groupe'))

    from django.core.paginator import Paginator
    paginator = Paginator(qs, 50)
    page      = paginator.get_page(request.GET.get('page', 1))

    return render(request, 'menu/admin/ciqual_ref.html', {
        'page_obj': page,
        'q':        q,
        'groupe':   groupe,
        'groupes':  groupes,
        'total':    qs.count(),
    })


@require_POST
@login_required
def maj_ciqual_ref(request, ref_id):
    """AJAX — Crée (ref_id=0) ou met à jour un IngredientRef."""
    if not (request.user.is_staff or _verifier_cuisinier(request)):
        return JsonResponse({'ok': False, 'error': 'Non autorisé'}, status=403)

    FLOAT_FIELDS = [
        'kcal_100g', 'proteines_100g', 'glucides_100g', 'lipides_100g',
        'sucres_100g', 'fibres_100g', 'ag_satures_100g', 'sel_100g',
    ]

    if ref_id == 0:
        # Création
        nom_fr = request.POST.get('nom_fr', '').strip()
        if not nom_fr:
            return JsonResponse({'ok': False, 'error': 'Nom requis'}, status=400)
        from .models import _normaliser_nom
        ref = IngredientRef(
            ciqual_code=f'CUSTOM-{IngredientRef.objects.count() + 1:04d}',
            nom_fr=nom_fr,
            nom_normalise=_normaliser_nom(nom_fr),
            groupe=request.POST.get('groupe', 'aides culinaires et ingrédients divers').strip(),
        )
    else:
        ref = get_object_or_404(IngredientRef, pk=ref_id)
        nom_fr = request.POST.get('nom_fr', '').strip()
        if nom_fr:
            from .models import _normaliser_nom
            ref.nom_fr        = nom_fr
            ref.nom_normalise = _normaliser_nom(nom_fr)
        groupe = request.POST.get('groupe', '').strip()
        if groupe:
            ref.groupe = groupe

    for field in FLOAT_FIELDS:
        raw = request.POST.get(field, '').strip()
        if raw == '':
            setattr(ref, field, None)
        else:
            try:
                setattr(ref, field, float(raw.replace(',', '.')))
            except ValueError:
                pass

    ref.save()
    return JsonResponse({
        'ok':   True,
        'id':   ref.pk,
        'nom_fr': ref.nom_fr,
        'kcal': ref.kcal_100g,
    })


@require_POST
@login_required
def supprimer_ciqual_ref(request, ref_id):
    """Supprime un IngredientRef (les KnownIngredient liés passent à ciqual_ref=NULL)."""
    if not (request.user.is_staff or _verifier_cuisinier(request)):
        return JsonResponse({'ok': False, 'error': 'Non autorisé'}, status=403)
    ref = get_object_or_404(IngredientRef, pk=ref_id)
    ref.delete()
    return JsonResponse({'ok': True})


@login_required
def gestion_synonymes(request):
    """Page de gestion des synonymes Ciqual — Cuisinier/staff uniquement."""
    if not (request.user.is_staff or _verifier_cuisinier(request)):
        return redirect("menu:liste_recettes")

    q = request.GET.get('q', '').strip()
    filtre = request.GET.get('filtre', 'tous')

    refs = IngredientRef.objects.annotate(
        nb_ingredients=Count('ingredients', distinct=True)
    )
    if q:
        refs = refs.filter(
            Q(nom_fr__icontains=q) | Q(synonymes__icontains=q)
        )
    if filtre == 'avec_synonymes':
        refs = refs.exclude(synonymes='')
    elif filtre == 'sans_synonymes':
        refs = refs.filter(synonymes='', nb_ingredients__gt=0)

    refs = refs.order_by('nom_fr')[:200]

    return render(request, "menu/recettes/ciqual_synonymes.html", {
        'refs': refs,
        'q': q,
        'filtre': filtre,
    })


@require_POST
@login_required
def maj_synonymes(request, ref_id):
    """AJAX — Met à jour les synonymes d'un IngredientRef."""
    if not (request.user.is_staff or _verifier_cuisinier(request)):
        return JsonResponse({'ok': False, 'error': 'Accès refusé'}, status=403)

    ref = get_object_or_404(IngredientRef, pk=ref_id)
    synonymes = request.POST.get('synonymes', '').strip()
    ref.synonymes = synonymes
    ref.save(update_fields=['synonymes'])
    return JsonResponse({'ok': True, 'synonymes': ref.synonymes})


@require_POST
@login_required
def set_ciqual_ingredient(request, ingredient_id):
    """
    AJAX — Associe (ou retire) une référence Ciqual à un ingrédient individuel.
    Utilisé par la page d'audit pour corriger le mapping sans ouvrir la recette.
    """
    if not (request.user.is_staff or _verifier_cuisinier(request)):
        return JsonResponse({"ok": False, "error": "Permission refusée"}, status=403)

    ingr = get_object_or_404(Ingredient, id=ingredient_id)
    ciqual_id_raw = request.POST.get("ciqual_ref_id", "").strip()

    if ciqual_id_raw:
        try:
            ref = IngredientRef.objects.get(pk=int(ciqual_id_raw))
        except (IngredientRef.DoesNotExist, ValueError):
            return JsonResponse({"ok": False, "error": "Référence Ciqual inconnue"}, status=400)
        ingr.ciqual_ref = ref
        ingr.save(update_fields=["ciqual_ref"])
        # Recalculer les macros depuis Ciqual
        macros = compute_ingredient_macros_from_ciqual(ingr)
        if macros:
            ingr.calories = macros["calories"]
            ingr.proteins = macros["proteins"]
            ingr.carbs    = macros["carbs"]
            ingr.fats     = macros["fats"]
            ingr.save(update_fields=["calories", "proteins", "carbs", "fats"])
        return JsonResponse({
            "ok":         True,
            "status":     "ok",
            "ciqual_code": ref.ciqual_code,
            "nom_fr":      ref.nom_fr,
            "kcal_100g":   ref.kcal_100g,
            "prot_100g":   ref.proteines_100g,
        })
    else:
        # Retrait du mapping
        ingr.ciqual_ref = None
        ingr.save(update_fields=["ciqual_ref"])
        return JsonResponse({"ok": True, "status": "none"})


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
    # Profil chargé une seule fois — réutilisé partout dans la vue (B3)
    profile = _get_profile(request)

    recipe = get_object_or_404(
        Recipe.objects.select_related("created_by").prefetch_related(
            "ingredient_groups__ingredients",
            "ingredients",
            "steps",
            "sections",
            "reviews__user",
            # B2 — prefetch filtré : évite la 2ᵉ requête dans gallery_photos
            Prefetch(
                "photos",
                queryset=RecipePhoto.objects.filter(actif=True).order_by("order", "created_at"),
                to_attr="active_photos",
            ),
        ),
        id=id,
        actif=True,
    )

    stats = recipe.reviews.aggregate(note_moyenne=Avg("stars"), nb_avis=Count("id"))

    # Alertes allergies — profil réutilisé (B3)
    dietary_tags = profile.dietary_tags if profile else []
    recipe_ingredients = list(recipe.ingredients.all())
    alertes = _alertes_allergies(recipe_ingredients, dietary_tags)

    # Dernier avis de l'utilisateur courant
    user_last_review = recipe.reviews.filter(user=request.user).order_by("-created_at").first()

    # Avis des membres de la famille — profil réutilisé (B3)
    family_reviews = []
    if profile and profile.family:
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

    # Pré-calcul des rangs par reviewer pour éviter le N+1
    raw_reviews = list(
        recipe.reviews
        .select_related("user", "user__profile")
        .order_by("-created_at")[:30]
    )
    rank_cache: dict = {}
    all_reviews_with_rank = []
    for r in raw_reviews:
        uid = r.user_id
        if uid not in rank_cache:
            try:
                rank_cache[uid] = r.user.profile.rank
            except Exception:
                rank_cache[uid] = (0, "")
        all_reviews_with_rank.append((r, rank_cache[uid]))

    # Bloc "Pour toi" — profil réutilisé (B3)
    portions_factor = profile.portions_factor if profile else 1.0
    pour_toi_cal  = round(recipe.calories_per_serving  * portions_factor, 0) if recipe.calories_per_serving  else None
    pour_toi_prot = round(recipe.proteins_per_serving * portions_factor, 1) if recipe.proteins_per_serving else None

    # Totaux pour la recette entière (utile pour comprendre le calcul par portion)
    n_servings = recipe.base_servings or 1
    total_recipe_cal  = round(recipe.calories_per_serving  * n_servings, 0) if recipe.calories_per_serving  else None
    total_recipe_prot = round(recipe.proteins_per_serving * n_servings, 1) if recipe.proteins_per_serving else None

    # Galerie photos — utilise le prefetch filtré (B2)
    gallery_photos = recipe.active_photos
    is_cuisinier_here = bool(profile and profile.role in ("cuisinier", "chef_etoile"))

    ctx = {
        "recipe": recipe,
        "note_moyenne": stats["note_moyenne"],
        "nb_avis": stats["nb_avis"],
        "alertes": alertes,
        "user_last_review": user_last_review,
        "family_reviews": family_reviews,
        "all_reviews": all_reviews_with_rank,
        "pour_toi_cal":  pour_toi_cal,
        "pour_toi_prot": pour_toi_prot,
        "total_recipe_cal":  total_recipe_cal,
        "total_recipe_prot": total_recipe_prot,
        "gallery_photos": gallery_photos,
        "is_cuisinier": is_cuisinier_here,
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


# ─── Création / édition / suppression ────────────────────────────────────────

def _verifier_cuisinier(request):
    """Retourne le profil si Cuisinier, sinon None."""
    try:
        profile = request.user.profile
        return profile if profile.role in ("cuisinier", "chef_etoile") else None
    except UserProfile.DoesNotExist:
        return None


@login_required
def recherche_ciqual(request):
    """GET /api/ingredients/ciqual/?q=... — autocomplete Ciqual pour le formulaire recette."""
    q = request.GET.get("q", "").strip()
    results = rechercher_ciqual(q)
    return JsonResponse({"ok": True, "results": results})


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
            protein_type=cd.get("protein_type") or None,
            created_by=request.user,
        )
        sauvegarder_recette_depuis_post(recipe, request.POST)
        calculer_macros_recette(recipe)
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
            recipe.protein_type = cd.get("protein_type") or None
            recipe.save()
            sauvegarder_recette_depuis_post(recipe, request.POST)
            calculer_macros_recette(recipe)
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
            "protein_type": recipe.protein_type or "",
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


# ─── Galerie photos ──────────────────────────────────────────────────────────

@require_POST
@login_required
def ajouter_photo_recette(request, id):
    """Upload d'une photo supplémentaire — accessible à tout utilisateur connecté."""
    recipe = get_object_or_404(Recipe, id=id, actif=True)
    photo_file = request.FILES.get("photo")

    if not photo_file:
        messages.error(request, "Aucun fichier fourni.")
        return redirect("menu:detail_recette", id=id)

    photo_url = upload_photo(photo_file)
    if not photo_url:
        messages.error(request, "L'upload de la photo a échoué. Réessayez.")
        return redirect("menu:detail_recette", id=id)

    caption = request.POST.get("caption", "").strip() or None
    order   = recipe.photos.filter(actif=True).count()

    RecipePhoto.objects.create(
        recipe=recipe,
        photo_url=photo_url,
        caption=caption,
        order=order,
        uploaded_by=request.user,
    )
    messages.success(request, "Photo ajoutée à la galerie !")
    logger.info("Photo ajoutée à la recette '%s' par %s.", recipe.title, request.user.email)
    return redirect("menu:detail_recette", id=id)


@require_POST
@login_required
def retirer_photo_recette(request, id, photo_id):
    """Soft-delete d'une photo de galerie — Cuisinier uniquement."""
    if not _verifier_cuisinier(request):
        messages.error(request, "Réservé aux Cuisiniers.")
        return redirect("menu:detail_recette", id=id)

    photo = get_object_or_404(RecipePhoto, id=photo_id, recipe_id=id)
    photo.actif = False
    photo.save(update_fields=["actif"])
    messages.success(request, "Photo retirée de la galerie.")
    return redirect("menu:detail_recette", id=id)


@require_POST
@login_required
def promouvoir_photo_recette(request, id, photo_id):
    """Passe une photo en is_main=True, remet toutes les autres à False — Cuisinier uniquement."""
    if not _verifier_cuisinier(request):
        messages.error(request, "Réservé aux Cuisiniers.")
        return redirect("menu:detail_recette", id=id)

    photo = get_object_or_404(RecipePhoto, id=photo_id, recipe_id=id, actif=True)
    recipe = get_object_or_404(Recipe, id=id)

    with transaction.atomic():
        RecipePhoto.objects.filter(recipe_id=id).update(is_main=False)
        photo.is_main = True
        photo.save(update_fields=["is_main"])
        recipe.photo_url = photo.photo_url
        recipe.save(update_fields=["photo_url"])

    messages.success(request, "Photo principale mise à jour.")
    return redirect("menu:detail_recette", id=id)


# ─── Backup / Restore / Import recettes ──────────────────────────────────────

def _verifier_staff(request):
    """Retourne True si l'utilisateur est staff Django."""
    return request.user.is_staff


@login_required
def backup_page(request):
    return redirect("menu:management_page")


@require_POST
@login_required
def link_known_ingredients_view(request):
    """Lance la commande link_known_ingredients via l'UI Management."""
    if not (_verifier_staff(request) or _verifier_cuisinier(request)):
        messages.error(request, "Accès non autorisé.")
        return redirect("menu:management_page")
    from django.core.management import call_command
    from io import StringIO
    out = StringIO()
    call_command('link_known_ingredients', stdout=out)
    result = out.getvalue()
    # Extraire les totaux du résultat pour le message flash
    lines = [l.strip() for l in result.splitlines() if l.strip()]
    summary = ' · '.join(lines[-4:]) if len(lines) >= 4 else result.strip()
    messages.success(request, f"🔗 Liaison terminée — {summary}")
    return redirect("menu:management_page")


@require_POST
@login_required
def recalculate_nutrition_view(request):
    """Lance la commande recalculate_nutrition via l'UI Management."""
    if not (_verifier_staff(request) or _verifier_cuisinier(request)):
        messages.error(request, "Accès non autorisé.")
        return redirect("menu:management_page")
    from django.core.management import call_command
    from io import StringIO
    out = StringIO()
    call_command('recalculate_nutrition', stdout=out)
    result = out.getvalue()
    lines = [l.strip() for l in result.splitlines() if l.strip()]
    summary = ' · '.join(lines[-4:]) if len(lines) >= 4 else result.strip()
    messages.success(request, f"🔄 Recalcul terminé — {summary}")
    return redirect("menu:management_page")


@require_POST
@login_required
def build_known_ingredients_view(request):
    """Lance la commande build_known_ingredients via l'UI Management."""
    if not (_verifier_staff(request) or _verifier_cuisinier(request)):
        messages.error(request, "Accès non autorisé.")
        return redirect("menu:management_page")
    from django.core.management import call_command
    from io import StringIO
    out = StringIO()
    call_command('build_known_ingredients', stdout=out)
    result = out.getvalue()
    lines = [l.strip() for l in result.splitlines() if l.strip()]
    summary = ' · '.join(lines[-3:]) if len(lines) >= 3 else result.strip()
    messages.success(request, f"🏗️ Base construite — {summary}")
    return redirect("menu:management_page")


@require_POST
@login_required
def import_ciqual_view(request):
    """Upload + import d'un fichier XLS Ciqual via l'UI Management."""
    if not (_verifier_staff(request) or _verifier_cuisinier(request)):
        messages.error(request, "Accès non autorisé.")
        return redirect("menu:management_page")

    xls_file = request.FILES.get('ciqual_xls')
    if not xls_file:
        messages.error(request, "Aucun fichier sélectionné.")
        return redirect("menu:management_page")

    import tempfile, os
    from django.core.management import call_command
    from io import StringIO

    # Écrire le fichier uploadé dans un temp file pour xlrd
    suffix = '.xls' if xls_file.name.endswith('.xls') else '.xlsx'
    with tempfile.NamedTemporaryFile(delete=False, suffix=suffix) as tmp:
        for chunk in xls_file.chunks():
            tmp.write(chunk)
        tmp_path = tmp.name

    try:
        out = StringIO()
        call_command('import_ciqual', file=tmp_path, wipe=True, stdout=out)
        result = out.getvalue()
        lines  = [l.strip() for l in result.splitlines() if l.strip()]
        summary = lines[-1] if lines else result.strip()
        messages.success(request, f"✅ Ciqual importé — {summary}")
    except Exception as e:
        messages.error(request, f"Erreur lors de l'import Ciqual : {e}")
    finally:
        os.unlink(tmp_path)

    return redirect("menu:management_page")


@require_POST
@login_required
def clean_ciqual_view(request):
    """Lance la commande clean_ciqual (nettoyage plats composés + sans kcal)."""
    if not (_verifier_staff(request) or _verifier_cuisinier(request)):
        messages.error(request, "Accès non autorisé.")
        return redirect("menu:management_page")
    from django.core.management import call_command
    from io import StringIO
    dry_run = request.POST.get('dry_run') == '1'
    out = StringIO()
    call_command('clean_ciqual', stdout=out, dry_run=dry_run)
    result = out.getvalue()
    if dry_run:
        # Afficher le résultat complet en message info pour la simulation
        messages.info(request, f"🔍 Simulation nettoyage Ciqual :\n{result}")
    else:
        lines = [l.strip() for l in result.splitlines() if l.strip()]
        summary = ' · '.join(lines[-4:]) if len(lines) >= 4 else result.strip()
        messages.success(request, f"🧹 Ciqual nettoyé — {summary}")
    return redirect("menu:management_page")


@require_POST
@login_required
def reset_recipes_view(request):
    """Supprime les recettes et données associées selon le mode choisi."""
    if not (_verifier_staff(request) or _verifier_cuisinier(request)):
        messages.error(request, "Accès non autorisé.")
        return redirect("menu:management_page")
    from django.core.management import call_command
    from io import StringIO
    mode = request.POST.get('reset_mode', 'recipes')  # 'recipes' | 'full'
    out = StringIO()
    kwargs = {'stdout': out}
    if mode == 'full':
        kwargs['full'] = True
    call_command('reset_recipes', **kwargs)
    result = out.getvalue()
    lines = [l.strip() for l in result.splitlines() if l.strip()]
    summary = ' · '.join(lines[-3:]) if len(lines) >= 3 else result.strip()
    messages.success(request, f"🗑️ Reset effectué — {summary}")
    return redirect("menu:management_page")


@login_required
def management_page(request):
    if not (_verifier_staff(request) or _verifier_cuisinier(request)):
        messages.error(request, "Accès non autorisé.")
        return redirect("menu:home")

    q = request.GET.get('q', '').strip()
    filtre = request.GET.get('filtre', 'tous')

    ings = KnownIngredient.objects.select_related('ciqual_ref').annotate(
        nb_recettes=Count('ciqual_ref__ingredients__recipe', distinct=True)
    )
    if q:
        ings = ings.filter(Q(name__icontains=q) | Q(synonymes__icontains=q))
    if filtre == 'sans_ciqual':
        ings = ings.filter(ciqual_ref__isnull=True)
    elif filtre == 'avec_ciqual':
        ings = ings.filter(ciqual_ref__isnull=False)

    ings = ings.order_by('name')

    return render(request, "menu/admin/management.html", {
        'ingredients': ings,
        'q': q,
        'filtre': filtre,
        'total': ings.count(),
        'is_staff': _verifier_staff(request),
    })


@login_required
def api_connus(request):
    """Autocomplete ingrédients depuis la base de connaissance."""
    q = request.GET.get('q', '').strip()
    results = rechercher_connus(q)
    return JsonResponse({'ok': True, 'results': results})


@require_POST
@login_required
def ajouter_known_ingredient(request):
    """Ajoute un ingrédient dans la base de connaissance."""
    if not (_verifier_staff(request) or _verifier_cuisinier(request)):
        return JsonResponse({'ok': False, 'error': 'Accès refusé'}, status=403)

    name = request.POST.get('name', '').strip()
    ciqual_id = request.POST.get('ciqual_ref_id', '').strip()
    if not name:
        return JsonResponse({'ok': False, 'error': 'Nom requis'})

    ciqual_ref = None
    if ciqual_id:
        try:
            ciqual_ref = IngredientRef.objects.get(pk=int(ciqual_id))
        except (IngredientRef.DoesNotExist, ValueError):
            pass

    from .models import _normaliser_nom
    nom_norm = _normaliser_nom(name)
    if KnownIngredient.objects.filter(nom_normalise=nom_norm).exists():
        return JsonResponse({'ok': False, 'error': 'Ingrédient déjà dans la base'})

    ki = KnownIngredient.objects.create(name=name, ciqual_ref=ciqual_ref)
    return JsonResponse({
        'ok': True,
        'id': ki.pk,
        'name': ki.name,
        'ciqual_nom': ciqual_ref.nom_fr if ciqual_ref else None,
        'kcal_100g': ciqual_ref.kcal_100g if ciqual_ref else None,
    })


@require_POST
@login_required
def maj_known_ingredient(request, ki_id):
    """Met à jour synonymes et/ou ciqual_ref d'un KnownIngredient (AJAX)."""
    if not (_verifier_staff(request) or _verifier_cuisinier(request)):
        return JsonResponse({'ok': False, 'error': 'Accès refusé'}, status=403)

    ki = get_object_or_404(KnownIngredient, pk=ki_id)
    fields = []

    if 'synonymes' in request.POST:
        ki.synonymes = request.POST.get('synonymes', '').strip()
        fields.append('synonymes')

    if 'default_unit' in request.POST:
        ki.default_unit = request.POST.get('default_unit', '').strip() or 'g'
        fields.append('default_unit')

    if 'ciqual_ref_id' in request.POST:
        ciqual_id = request.POST.get('ciqual_ref_id', '').strip()
        if ciqual_id:
            try:
                ki.ciqual_ref = IngredientRef.objects.get(pk=int(ciqual_id))
            except (IngredientRef.DoesNotExist, ValueError):
                ki.ciqual_ref = None
        else:
            ki.ciqual_ref = None
        fields.append('ciqual_ref')

    if fields:
        ki.save(update_fields=fields)

    ref = ki.ciqual_ref
    return JsonResponse({
        'ok': True,
        'synonymes': ki.synonymes,
        'ciqual_nom': ref.nom_fr if ref else None,
        'kcal_100g': ref.kcal_100g if ref else None,
        'proteines_100g': ref.proteines_100g if ref else None,
    })


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


# ─── Export Google Calendar ──────────────────────────────────────────────────

@require_POST
@login_required
def export_calendar(request, plan_id):
    """
    Exporte le planning vers Google Calendar.
    Crée ou met à jour un événement par repas planifié.
    """
    profile = _get_profile(request)
    if not profile or not profile.family:
        messages.error(request, "Profil ou famille introuvable.")
        return redirect("menu:planning")

    plan = get_object_or_404(WeekPlan, pk=plan_id, family=profile.family)

    if not TokenOAuth.objects.filter(user=request.user, service="google").exists():
        messages.warning(request, "Connecte ton compte Google dans ton profil avant d'exporter.")
        return redirect("menu:planning_periode", plan_id=plan.id)

    try:
        stats = google_calendar_export_planning(request.user, plan)
    except Exception as exc:
        logger.error("export_calendar : erreur pour user %s : %s", request.user.id, exc)
        messages.error(request, "Erreur lors de l'export Google Calendar. Réessaie dans quelques instants.")
        return redirect("menu:planning_periode", plan_id=plan.id)

    total = stats["created"] + stats["updated"]
    parts = []
    if stats["created"]:
        parts.append(f"{stats['created']} événement{'s' if stats['created'] > 1 else ''} créé{'s' if stats['created'] > 1 else ''}")
    if stats["updated"]:
        parts.append(f"{stats['updated']} mis à jour")
    if stats["skipped"]:
        parts.append(f"{stats['skipped']} ignoré{'s' if stats['skipped'] > 1 else ''} (sans recette)")

    if total > 0:
        messages.success(request, "📅 Export Google Calendar : " + ", ".join(parts) + ".")
    else:
        messages.info(request, "📅 Aucun repas avec recette à exporter cette semaine.")

    return redirect("menu:planning_periode", plan_id=plan.id)


@require_POST
@login_required
def modifier_creneaux_calendar(request):
    """Enregistre les créneaux horaires configurés par l'utilisateur pour Google Calendar."""
    profile = _get_profile(request)
    if not profile:
        messages.error(request, "Profil introuvable.")
        return redirect("menu:profil")

    from datetime import time as parse_time

    def _parse_time(value: str, fallback):
        """Parse HH:MM en datetime.time, retourne fallback si invalide."""
        try:
            h, m = value.strip().split(":")
            return parse_time(int(h), int(m))
        except Exception:
            return fallback

    profile.lunch_start  = _parse_time(request.POST.get("lunch_start",  ""), profile.lunch_start)
    profile.lunch_end    = _parse_time(request.POST.get("lunch_end",    ""), profile.lunch_end)
    profile.dinner_start = _parse_time(request.POST.get("dinner_start", ""), profile.dinner_start)
    profile.dinner_end   = _parse_time(request.POST.get("dinner_end",   ""), profile.dinner_end)

    profile.save(update_fields=["lunch_start", "lunch_end", "dinner_start", "dinner_end"])
    messages.success(request, "Créneaux Google Calendar mis à jour.")
    logger.debug("modifier_creneaux_calendar : créneaux mis à jour pour user %s", request.user.id)
    return redirect("menu:profil")


@require_POST
@login_required
def modifier_portions_factor(request):
    """Enregistre le facteur de portion individuel de l'utilisateur."""
    profile = _get_profile(request)
    if not profile:
        messages.error(request, "Profil introuvable.")
        return redirect("menu:profil")

    try:
        value = float(request.POST.get("portions_factor", "1.0"))
        if value <= 0 or value > 5:
            raise ValueError("Hors plage")
    except (ValueError, TypeError):
        messages.error(request, "Valeur invalide pour le facteur de portion (entre 0.1 et 5.0).")
        return redirect("menu:profil")

    profile.portions_factor = round(value, 2)
    profile.save(update_fields=["portions_factor"])
    messages.success(request, "Facteur de portion mis à jour.")
    logger.debug("modifier_portions_factor : portions_factor=%.2f pour user %s", profile.portions_factor, request.user.id)
    return redirect("menu:profil")


@require_POST
@login_required
def modifier_dietary_tags(request):
    """Enregistre les restrictions alimentaires / allergènes du profil utilisateur."""
    profile = _get_profile(request)
    if not profile:
        messages.error(request, "Profil introuvable.")
        return redirect("menu:profil")

    tags = request.POST.getlist("tags")
    # Valider que les tags soumis font partie de la liste connue
    tags_valides = [t for t in tags if t in DIETARY_TAG_CONFIG]
    profile.dietary_tags = tags_valides
    profile.save(update_fields=["dietary_tags"])
    messages.success(request, "Restrictions alimentaires mises à jour.")
    logger.debug("modifier_dietary_tags : %s pour user %s", tags_valides, request.user.id)
    return redirect("menu:profil")


@login_required
def compatibilite_recette(request, id):
    """
    Page de compatibilité famille : qui peut manger cette recette ?
    Accessible à tous les membres authentifiés de la famille.
    """
    recipe = get_object_or_404(
        Recipe.objects.prefetch_related("ingredients"),
        id=id,
        actif=True,
    )
    profile = _get_profile(request)
    if not profile or not profile.family:
        messages.error(request, "Vous devez appartenir à une famille pour voir cette page.")
        return redirect("menu:detail_recette", id=id)

    membres = (
        UserProfile.objects
        .filter(family=profile.family)
        .select_related("user")
        .order_by("user__first_name")
    )

    ingredients = list(recipe.ingredients.all())

    compat = []
    for m in membres:
        alertes = _alertes_allergies(ingredients, m.dietary_tags or [])
        compat.append({
            "profil": m,
            "alertes": alertes,
            "ok": len(alertes) == 0,
        })

    return render(request, "menu/recettes/compatibilite.html", {
        "recipe": recipe,
        "compat": compat,
    })


# ─── Export Google Tasks ─────────────────────────────────────────────────────

@require_POST
@login_required
def export_tasks(request, plan_id):
    """
    Exporte les articles non cochés de la liste de courses vers Google Tasks.
    """
    profile = _get_profile(request)
    if not profile or not profile.family:
        messages.error(request, "Profil ou famille introuvable.")
        return redirect("menu:planning")

    plan = get_object_or_404(WeekPlan, pk=plan_id, family=profile.family)

    if not TokenOAuth.objects.filter(user=request.user, service="google").exists():
        messages.warning(request, "Connecte ton compte Google dans ton profil avant d'exporter.")
        return redirect("menu:liste_courses", plan_id=plan_id)

    shopping_list = ShoppingList.objects.filter(week_plan=plan).first()
    if not shopping_list:
        messages.warning(request, "Génère d'abord la liste de courses.")
        return redirect("menu:liste_courses", plan_id=plan_id)

    nb_unchecked = shopping_list.items.filter(checked=False).count()
    if nb_unchecked == 0:
        messages.info(request, "✅ Tous les articles sont déjà cochés — rien à exporter.")
        return redirect("menu:liste_courses", plan_id=plan_id)

    try:
        stats = google_tasks_export_courses(request.user, shopping_list)
    except Exception as exc:
        logger.error("export_tasks : erreur pour user %s : %s", request.user.id, exc)
        messages.error(request, "Erreur lors de l'export Google Tasks. Réessaie dans quelques instants.")
        return redirect("menu:liste_courses", plan_id=plan_id)

    parts = []
    if stats["created"]:
        n = stats["created"]
        parts.append(f"{n} tâche{'s' if n > 1 else ''} créée{'s' if n > 1 else ''}")
    if stats["skipped"]:
        n = stats["skipped"]
        parts.append(f"{n} ignorée{'s' if n > 1 else ''}")

    if stats["created"]:
        messages.success(request, "✅ Export Google Tasks : " + ", ".join(parts) + ".")
    else:
        messages.warning(request, "Aucune tâche créée. " + ", ".join(parts))

    return redirect("menu:liste_courses", plan_id=plan_id)


# ─── OAuth Google ─────────────────────────────────────────────────────────────

@login_required
def google_connect(request):
    """
    Démarre le flux OAuth Google.
    Génère un state aléatoire (protection CSRF), le stocke en session,
    puis redirige l'utilisateur vers Google.
    """
    state = secrets.token_urlsafe(32)
    request.session["google_oauth_state"] = state

    redirect_uri = request.build_absolute_uri(reverse("menu:google_callback"))
    auth_url = google_build_auth_url(redirect_uri, state)
    return redirect(auth_url)


@login_required
def google_callback(request):
    """
    Callback OAuth Google.
    Valide le state, échange le code contre des tokens, stocke dans TokenOAuth.
    """
    # Erreur renvoyée par Google (ex. accès refusé par l'utilisateur)
    error = request.GET.get("error")
    if error:
        messages.warning(request, f"Connexion Google annulée ({error}).")
        return redirect("menu:profil")

    # Validation du state anti-CSRF
    state = request.GET.get("state", "")
    expected_state = request.session.pop("google_oauth_state", None)
    if not expected_state or state != expected_state:
        messages.error(request, "Erreur de sécurité OAuth. Réessaie la connexion Google.")
        logger.warning("google_callback : state invalide pour user %s", request.user.id)
        return redirect("menu:profil")

    code = request.GET.get("code", "")
    if not code:
        messages.error(request, "Code d'autorisation manquant. Réessaie.")
        return redirect("menu:profil")

    redirect_uri = request.build_absolute_uri(reverse("menu:google_callback"))

    try:
        data = google_exchange_code(code, redirect_uri)
    except Exception:
        messages.error(request, "Erreur lors de l'échange avec Google. Réessaie dans quelques instants.")
        return redirect("menu:profil")

    # Calcul de la date d'expiration
    expires_at = None
    if "expires_in" in data:
        expires_at = timezone.now() + timedelta(seconds=int(data["expires_in"]))

    refresh_token = data.get("refresh_token", "")
    if not refresh_token:
        # Google ne renvoie le refresh_token qu'au premier consentement.
        # Si absent, conserver l'ancien s'il existe.
        existing = TokenOAuth.objects.filter(user=request.user, service="google").first()
        if existing:
            refresh_token = existing.refresh_token

    TokenOAuth.objects.update_or_create(
        user=request.user,
        service="google",
        defaults={
            "access_token":  data["access_token"],
            "refresh_token": refresh_token,
            "expires_at":    expires_at,
        },
    )

    logger.info("google_callback : tokens Google stockés pour user %s", request.user.id)
    messages.success(request, "✅ Compte Google connecté avec succès !")
    return redirect("menu:profil")


@require_POST
@login_required
def google_disconnect(request):
    """Supprime les tokens Google de l'utilisateur."""
    deleted, _ = TokenOAuth.objects.filter(user=request.user, service="google").delete()
    if deleted:
        logger.info("google_disconnect : tokens supprimés pour user %s", request.user.id)
        messages.success(request, "Compte Google déconnecté.")
    else:
        messages.info(request, "Aucune connexion Google active.")
    return redirect("menu:profil")

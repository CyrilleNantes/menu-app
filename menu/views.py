import logging

from django.contrib import messages
from django.contrib.auth import login, logout
from django.contrib.auth.decorators import login_required
from django.contrib.auth.models import User
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.http import require_POST

from .forms import InscriptionForm
from .models import Family, UserProfile

logger = logging.getLogger("menu")


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

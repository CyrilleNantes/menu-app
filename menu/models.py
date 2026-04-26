import uuid
from datetime import time as datetime_time

from django.contrib.auth.models import User
from django.core.validators import MinValueValidator, MaxValueValidator
from django.db import models


class Family(models.Model):
    name = models.CharField(max_length=100)
    created_by = models.ForeignKey(User, on_delete=models.PROTECT, related_name="families_created")
    invite_token = models.UUIDField(default=uuid.uuid4, unique=True, editable=False)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = "Famille"
        verbose_name_plural = "Familles"

    def __str__(self):
        return self.name


class UserProfile(models.Model):
    ROLE_CHOICES = [
        ("chef_etoile", "Chef Étoilé"),
        ("cuisinier", "Cuisinier"),
        ("convive", "Convive"),
    ]

    user = models.OneToOneField(User, on_delete=models.CASCADE, related_name="profile")
    family = models.ForeignKey(Family, on_delete=models.SET_NULL, null=True, blank=True, related_name="members")
    role = models.CharField(max_length=20, choices=ROLE_CHOICES, default="convive")
    dietary_tags = models.JSONField(default=list, blank=True)
    google_calendar_id = models.CharField(max_length=200, null=True, blank=True)
    google_tasklist_id = models.CharField(max_length=200, null=True, blank=True)
    # Créneaux horaires pour l'export Google Calendar
    lunch_start  = models.TimeField(default=datetime_time(12, 0),  verbose_name="Début déjeuner")
    lunch_end    = models.TimeField(default=datetime_time(13, 0),  verbose_name="Fin déjeuner")
    dinner_start = models.TimeField(default=datetime_time(20, 30), verbose_name="Début dîner")
    dinner_end   = models.TimeField(default=datetime_time(21, 30), verbose_name="Fin dîner")
    portions_factor = models.FloatField(
        default=1.0,
        verbose_name="Facteur de portion",
        help_text="1.0 = adulte référence. Ado garçon 15–16 ans ≈ 1.3, ado fille 13 ans ≈ 0.9.",
    )

    class Meta:
        verbose_name = "Profil utilisateur"
        verbose_name_plural = "Profils utilisateurs"

    def __str__(self):
        return f"{self.user.username} ({self.get_role_display()})"

    # ── Seuils de progression ──────────────────────────────────────────────
    _RANK_CUISINIER = [
        (0,  1, "Commis",         "🥄"),
        (3,  2, "Cuisinier",      "🍳"),
        (8,  3, "Chef de Partie", "👨‍🍳"),
        (15, 4, "Sous-Chef",      "⭐"),
        (30, 5, "Chef Exécutif",  "🌟"),
    ]
    _RANK_CONVIVE = [
        (0,  1, "Convive",        "🍽️"),
        (2,  2, "Gourmet",        "😋"),
        (5,  3, "Épicurien",      "🍷"),
        (10, 4, "Critique",       "✍️"),
        (20, 5, "Guide Michelin", "⭐⭐"),
    ]

    @property
    def rank(self):
        """Retourne (niveau, nom) du rang courant."""
        info = self.rank_info
        return (info["level"], info["name"])

    @property
    def rank_info(self):
        """Retourne le rang complet + progression vers le rang suivant."""
        if self.role in ("cuisinier", "chef_etoile"):
            metric   = Recipe.objects.filter(created_by=self.user, actif=True).count()
            thresholds = self._RANK_CUISINIER
            metric_label = "recette"
        elif self.role == "convive":
            from .models import MealProposal  # import local pour éviter circularité
            reviews   = Review.objects.filter(user=self.user).count()
            proposals = MealProposal.objects.filter(proposed_by=self.user).count()
            metric    = reviews + proposals
            thresholds = self._RANK_CONVIVE
            metric_label = "contribution"
        else:
            return {
                "level": 0, "name": self.get_role_display(), "emoji": "👤",
                "progress": 100, "next_name": None, "next_threshold": None,
                "metric": 0, "metric_label": "", "current_threshold": 0,
            }

        # Rang courant = dernier seuil franchi
        current = thresholds[0]
        for entry in thresholds:
            if metric >= entry[0]:
                current = entry
        cur_threshold, cur_level, cur_name, cur_emoji = current

        # Rang suivant
        cur_idx = thresholds.index(current)
        if cur_idx + 1 < len(thresholds):
            next_t = thresholds[cur_idx + 1][0]
            next_name = thresholds[cur_idx + 1][2]
            span    = next_t - cur_threshold
            progress = int((metric - cur_threshold) / span * 100) if span else 100
            progress = max(0, min(99, progress))
        else:
            next_t    = None
            next_name = None
            progress  = 100

        return {
            "level":             cur_level,
            "name":              cur_name,
            "emoji":             cur_emoji,
            "progress":          progress,
            "next_name":         next_name,
            "next_threshold":    next_t,
            "metric":            metric,
            "metric_label":      metric_label,
            "current_threshold": cur_threshold,
        }


class TokenOAuth(models.Model):
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name="oauth_tokens")
    service = models.CharField(max_length=50)
    access_token = models.TextField()
    refresh_token = models.TextField()
    expires_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "Token OAuth"
        verbose_name_plural = "Tokens OAuth"
        constraints = [
            models.UniqueConstraint(fields=["user", "service"], name="unique_user_service_token")
        ]

    def __str__(self):
        return f"{self.user.username} — {self.service}"


class Recipe(models.Model):
    CATEGORY_CHOICES = [
        ("entree", "Entrée"),
        ("plat", "Plat"),
        ("dessert", "Dessert"),
        ("brunch", "Brunch"),
        ("snack", "Snack"),
    ]
    COMPLEXITY_CHOICES = [
        ("simple", "Simple"),
        ("intermediaire", "Intermédiaire"),
        ("elabore", "Élaboré"),
    ]

    title = models.CharField(max_length=200)
    description = models.TextField(blank=True, null=True)
    photo_url = models.URLField(blank=True, null=True)
    base_servings = models.PositiveIntegerField()
    prep_time = models.PositiveIntegerField(blank=True, null=True)
    cook_time = models.PositiveIntegerField(blank=True, null=True)
    category = models.CharField(max_length=20, choices=CATEGORY_CHOICES)
    cuisine_type = models.CharField(max_length=50, blank=True, null=True)
    seasons = models.JSONField(default=list, blank=True)
    health_tags = models.JSONField(default=list, blank=True)
    complexity = models.CharField(max_length=20, choices=COMPLEXITY_CHOICES, default="simple")
    calories_per_serving = models.FloatField(blank=True, null=True)
    proteins_per_serving = models.FloatField(blank=True, null=True)
    carbs_per_serving = models.FloatField(blank=True, null=True)
    fats_per_serving = models.FloatField(blank=True, null=True)
    created_by = models.ForeignKey(User, on_delete=models.PROTECT, related_name="recipes")
    PROTEIN_TYPE_CHOICES = [
        ("boeuf",        "Bœuf"),
        ("volaille",     "Volaille"),
        ("porc",         "Porc"),
        ("poisson",      "Poisson"),
        ("oeufs",        "Œufs"),
        ("legumineuses", "Légumineuses"),
        ("autre",        "Autre"),
        ("aucune",       "Aucune (végétarien)"),
    ]
    protein_type = models.CharField(
        max_length=20,
        choices=PROTEIN_TYPE_CHOICES,
        null=True,
        blank=True,
        verbose_name="Protéine principale",
    )
    actif = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = "Recette"
        verbose_name_plural = "Recettes"
        ordering = ["-created_at"]

    def __str__(self):
        return self.title


class IngredientGroup(models.Model):
    recipe = models.ForeignKey(Recipe, on_delete=models.CASCADE, related_name="ingredient_groups")
    name = models.CharField(max_length=100)
    order = models.PositiveIntegerField(default=0)

    class Meta:
        verbose_name = "Groupe d'ingrédients"
        verbose_name_plural = "Groupes d'ingrédients"
        ordering = ["order"]

    def __str__(self):
        return f"{self.recipe.title} — {self.name}"


class Ingredient(models.Model):
    recipe = models.ForeignKey(Recipe, on_delete=models.CASCADE, related_name="ingredients")
    group = models.ForeignKey(IngredientGroup, on_delete=models.SET_NULL, null=True, blank=True, related_name="ingredients")
    name = models.CharField(max_length=200)
    quantity = models.FloatField(blank=True, null=True)
    quantity_note = models.CharField(max_length=50, blank=True, null=True)
    unit = models.CharField(max_length=50, blank=True, null=True)
    is_optional = models.BooleanField(default=False)
    category = models.CharField(max_length=50, blank=True, null=True)
    openfoodfacts_id = models.CharField(max_length=100, blank=True, null=True)
    calories = models.FloatField(blank=True, null=True)
    proteins = models.FloatField(blank=True, null=True)
    carbs = models.FloatField(blank=True, null=True)
    fats = models.FloatField(blank=True, null=True)
    order = models.PositiveIntegerField(default=0)

    class Meta:
        verbose_name = "Ingrédient"
        verbose_name_plural = "Ingrédients"
        ordering = ["order"]

    def __str__(self):
        return f"{self.name} ({self.recipe.title})"


class RecipeStep(models.Model):
    recipe = models.ForeignKey(Recipe, on_delete=models.CASCADE, related_name="steps")
    order = models.PositiveIntegerField()
    instruction = models.TextField()
    chef_note = models.TextField(blank=True, null=True)
    timer_seconds = models.PositiveIntegerField(blank=True, null=True)

    class Meta:
        verbose_name = "Étape"
        verbose_name_plural = "Étapes"
        ordering = ["order"]

    def __str__(self):
        return f"Étape {self.order} — {self.recipe.title}"


class RecipeSection(models.Model):
    SECTION_TYPE_CHOICES = [
        ("critique", "Points critiques"),
        ("conseil", "Conseils"),
        ("difference", "Ce qui fait la différence"),
        ("libre", "Section libre"),
    ]

    recipe = models.ForeignKey(Recipe, on_delete=models.CASCADE, related_name="sections")
    section_type = models.CharField(max_length=30, choices=SECTION_TYPE_CHOICES)
    title = models.CharField(max_length=100, blank=True, null=True)
    content = models.TextField()
    order = models.PositiveIntegerField(default=0)

    class Meta:
        verbose_name = "Section libre"
        verbose_name_plural = "Sections libres"
        ordering = ["order"]

    def __str__(self):
        return f"{self.get_section_type_display()} — {self.recipe.title}"


class Review(models.Model):
    recipe = models.ForeignKey(Recipe, on_delete=models.CASCADE, related_name="reviews")
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name="reviews")
    stars = models.PositiveSmallIntegerField(
        validators=[MinValueValidator(1), MaxValueValidator(5)]
    )
    comment = models.TextField(blank=True, null=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = "Avis"
        verbose_name_plural = "Avis"
        ordering = ["-created_at"]

    def clean(self):
        from django.core.exceptions import ValidationError
        if not (1 <= self.stars <= 5):
            raise ValidationError({"stars": "La note doit être entre 1 et 5."})

    def __str__(self):
        return f"{self.user.username} — {self.recipe.title} ({self.stars}★)"


class WeekPlan(models.Model):
    STATUS_CHOICES = [
        ("draft", "Brouillon"),
        ("published", "Publié"),
    ]

    family = models.ForeignKey(Family, on_delete=models.CASCADE, related_name="week_plans")
    period_start = models.DateField()
    period_end = models.DateField()
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default="draft")
    created_by = models.ForeignKey(User, on_delete=models.PROTECT, related_name="week_plans")
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = "Planning hebdomadaire"
        verbose_name_plural = "Plannings hebdomadaires"
        constraints = [
            models.UniqueConstraint(fields=["family", "period_start"], name="unique_family_period_start")
        ]

    def __str__(self):
        return f"{self.family.name} — {self.period_start}"


class Meal(models.Model):
    MEAL_TIME_CHOICES = [
        ("lunch", "Déjeuner"),
        ("dinner", "Dîner"),
    ]

    week_plan = models.ForeignKey(WeekPlan, on_delete=models.CASCADE, related_name="meals")
    date = models.DateField()
    meal_time = models.CharField(max_length=10, choices=MEAL_TIME_CHOICES)
    recipe = models.ForeignKey(Recipe, on_delete=models.SET_NULL, null=True, blank=True, related_name="meals")
    servings_count = models.PositiveIntegerField(blank=True, null=True)
    is_leftovers = models.BooleanField(default=False)
    source_meal = models.ForeignKey("self", on_delete=models.SET_NULL, null=True, blank=True, related_name="leftover_meals")
    google_event_id = models.CharField(max_length=200, blank=True, default="", verbose_name="ID événement Google Calendar")

    class Meta:
        verbose_name = "Repas"
        verbose_name_plural = "Repas"
        constraints = [
            models.UniqueConstraint(fields=["week_plan", "date", "meal_time"], name="unique_meal_slot")
        ]

    def __str__(self):
        return f"{self.date} {self.get_meal_time_display()} — {self.recipe or 'Vide'}"


class MealProposal(models.Model):
    family = models.ForeignKey(Family, on_delete=models.CASCADE, related_name="meal_proposals")
    recipe = models.ForeignKey(Recipe, on_delete=models.CASCADE, related_name="proposals")
    proposed_by = models.ForeignKey(User, on_delete=models.CASCADE, related_name="proposals")
    message = models.TextField(blank=True, null=True)
    week_plan = models.ForeignKey(WeekPlan, on_delete=models.SET_NULL, null=True, blank=True, related_name="proposals")
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = "Proposition de repas"
        verbose_name_plural = "Propositions de repas"

    def __str__(self):
        return f"{self.proposed_by.username} propose {self.recipe.title}"


class ShoppingList(models.Model):
    family = models.ForeignKey(Family, on_delete=models.CASCADE, related_name="shopping_lists")
    week_plan = models.OneToOneField(WeekPlan, on_delete=models.CASCADE, related_name="shopping_list")
    generated_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = "Liste de courses"
        verbose_name_plural = "Listes de courses"

    def __str__(self):
        return f"Courses — {self.family.name} ({self.week_plan.period_start})"


class ShoppingItem(models.Model):
    shopping_list = models.ForeignKey(ShoppingList, on_delete=models.CASCADE, related_name="items")
    name = models.CharField(max_length=200)
    quantity = models.FloatField(blank=True, null=True)
    unit = models.CharField(max_length=50, blank=True, null=True)
    category = models.CharField(max_length=50, blank=True, null=True)
    checked = models.BooleanField(default=False)

    class Meta:
        verbose_name = "Article de courses"
        verbose_name_plural = "Articles de courses"

    def __str__(self):
        return f"{self.name} ({self.shopping_list})"


class NotificationPreference(models.Model):
    CHANNEL_CHOICES = [
        ("email", "Email"),
        ("push", "Push"),
        ("in_app", "In-app"),
    ]

    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name="notification_preferences")
    channel = models.CharField(max_length=20, choices=CHANNEL_CHOICES)
    enabled = models.BooleanField(default=True)

    class Meta:
        verbose_name = "Préférence de notification"
        verbose_name_plural = "Préférences de notifications"

    def __str__(self):
        return f"{self.user.username} — {self.get_channel_display()}"

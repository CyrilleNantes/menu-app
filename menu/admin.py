from django.contrib import admin
from .models import (
    Family, UserProfile, TokenOAuth,
    Recipe, IngredientGroup, Ingredient, RecipeStep, RecipeSection,
    Review, WeekPlan, Meal, MealProposal,
    ShoppingList, ShoppingItem, NotificationPreference,
)


class IngredientInline(admin.TabularInline):
    model = Ingredient
    extra = 0


class IngredientGroupInline(admin.TabularInline):
    model = IngredientGroup
    extra = 0


class RecipeStepInline(admin.TabularInline):
    model = RecipeStep
    extra = 0


class RecipeSectionInline(admin.TabularInline):
    model = RecipeSection
    extra = 0


@admin.register(Recipe)
class RecipeAdmin(admin.ModelAdmin):
    list_display = ("title", "category", "complexity", "created_by", "actif", "created_at")
    list_filter = ("category", "complexity", "actif", "seasons")
    search_fields = ("title", "description")
    inlines = [IngredientGroupInline, RecipeStepInline, RecipeSectionInline]


@admin.register(Family)
class FamilyAdmin(admin.ModelAdmin):
    list_display = ("name", "created_by", "created_at")
    search_fields = ("name",)


@admin.register(UserProfile)
class UserProfileAdmin(admin.ModelAdmin):
    list_display = ("user", "role", "family")
    list_filter = ("role",)
    search_fields = ("user__username", "user__email")


@admin.register(TokenOAuth)
class TokenOAuthAdmin(admin.ModelAdmin):
    list_display = ("user", "service", "expires_at", "updated_at")
    list_filter = ("service",)


@admin.register(IngredientGroup)
class IngredientGroupAdmin(admin.ModelAdmin):
    list_display = ("name", "recipe", "order")
    inlines = [IngredientInline]


@admin.register(Ingredient)
class IngredientAdmin(admin.ModelAdmin):
    list_display = ("name", "recipe", "quantity", "unit", "category", "is_optional")
    list_filter = ("category", "is_optional")
    search_fields = ("name",)


@admin.register(RecipeStep)
class RecipeStepAdmin(admin.ModelAdmin):
    list_display = ("recipe", "order", "timer_seconds")


@admin.register(RecipeSection)
class RecipeSectionAdmin(admin.ModelAdmin):
    list_display = ("recipe", "section_type", "title", "order")
    list_filter = ("section_type",)


@admin.register(Review)
class ReviewAdmin(admin.ModelAdmin):
    list_display = ("recipe", "user", "stars", "created_at")
    list_filter = ("stars",)


@admin.register(WeekPlan)
class WeekPlanAdmin(admin.ModelAdmin):
    list_display = ("family", "period_start", "period_end", "status", "created_by")
    list_filter = ("status",)


@admin.register(Meal)
class MealAdmin(admin.ModelAdmin):
    list_display = ("week_plan", "date", "meal_time", "recipe", "is_leftovers")
    list_filter = ("meal_time", "is_leftovers")


@admin.register(MealProposal)
class MealProposalAdmin(admin.ModelAdmin):
    list_display = ("family", "recipe", "proposed_by", "created_at")


@admin.register(ShoppingList)
class ShoppingListAdmin(admin.ModelAdmin):
    list_display = ("family", "week_plan", "generated_at")


@admin.register(ShoppingItem)
class ShoppingItemAdmin(admin.ModelAdmin):
    list_display = ("name", "quantity", "unit", "category", "checked")
    list_filter = ("checked", "category")


@admin.register(NotificationPreference)
class NotificationPreferenceAdmin(admin.ModelAdmin):
    list_display = ("user", "channel", "enabled")
    list_filter = ("channel", "enabled")

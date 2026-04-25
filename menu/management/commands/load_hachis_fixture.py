import json
from pathlib import Path
from django.contrib.auth.models import User
from django.core.management.base import BaseCommand
from menu.models import Recipe, IngredientGroup, Ingredient, RecipeStep, RecipeSection


FIXTURE_PATH = Path(__file__).resolve().parents[3] / "fixtures" / "recette-exemple-hachis-parmentier.json"

QUANTITY_NOTES = {
    "champignons de Paris (hachés très fins)": "150–200g",
}


class Command(BaseCommand):
    help = "Charge la fixture Hachis Parmentier pour valider le modèle de données"

    def add_arguments(self, parser):
        parser.add_argument("--user", default="admin", help="Username du créateur (défaut: admin)")

    def handle(self, *args, **options):
        username = options["user"]

        user, created = User.objects.get_or_create(
            username=username,
            defaults={"is_staff": True, "is_superuser": True},
        )
        if created:
            user.set_password("admin")
            user.save()
            self.stdout.write(f"Utilisateur '{username}' créé.")

        data = json.loads(FIXTURE_PATH.read_text(encoding="utf-8"))
        r = data["recipe"]

        if Recipe.objects.filter(title=r["title"]).exists():
            self.stdout.write(self.style.WARNING(f"Recette '{r['title']}' déjà présente — ignorée."))
            return

        recipe = Recipe.objects.create(
            title=r["title"],
            description=r.get("description"),
            base_servings=r["base_servings"],
            prep_time=r.get("prep_time"),
            cook_time=r.get("cook_time"),
            category=r["category"],
            cuisine_type=r.get("cuisine_type"),
            seasons=r.get("seasons", []),
            health_tags=r.get("health_tags", []),
            complexity=r["complexity"],
            calories_per_serving=r.get("calories_per_serving"),
            proteins_per_serving=r.get("proteins_per_serving"),
            carbs_per_serving=r.get("carbs_per_serving"),
            fats_per_serving=r.get("fats_per_serving"),
            created_by=user,
        )

        for g in r.get("ingredient_groups", []):
            group = IngredientGroup.objects.create(
                recipe=recipe,
                name=g["name"],
                order=g["order"],
            )
            for ing in g.get("ingredients", []):
                Ingredient.objects.create(
                    recipe=recipe,
                    group=group,
                    name=ing["name"],
                    quantity=ing.get("quantity"),
                    quantity_note=QUANTITY_NOTES.get(ing["name"]),
                    unit=ing.get("unit"),
                    is_optional=ing.get("is_optional", False),
                    category=ing.get("category"),
                    openfoodfacts_id=ing.get("openfoodfacts_id"),
                    order=ing["order"],
                )

        for step in r.get("steps", []):
            RecipeStep.objects.create(
                recipe=recipe,
                order=step["order"],
                instruction=step["instruction"],
                chef_note=step.get("chef_note"),
                timer_seconds=step.get("timer_seconds"),
            )

        for section in r.get("sections", []):
            RecipeSection.objects.create(
                recipe=recipe,
                section_type=section["section_type"],
                title=section.get("title"),
                content=section["content"],
                order=section["order"],
            )

        self.stdout.write(self.style.SUCCESS(
            f"Recette '{recipe.title}' chargée — "
            f"{recipe.ingredient_groups.count()} groupes, "
            f"{recipe.ingredients.count()} ingrédients, "
            f"{recipe.steps.count()} étapes, "
            f"{recipe.sections.count()} sections."
        ))

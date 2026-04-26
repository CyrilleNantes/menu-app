import django.db.models.deletion
from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("menu", "0004_nutrition_config"),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.CreateModel(
            name="RecipePhoto",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("photo_url",   models.URLField()),
                ("caption",     models.CharField(blank=True, max_length=100, null=True)),
                ("is_main",     models.BooleanField(default=False, verbose_name="Photo principale de la galerie")),
                ("order",       models.PositiveIntegerField(default=0)),
                ("actif",       models.BooleanField(default=True)),
                ("created_at",  models.DateTimeField(auto_now_add=True)),
                ("recipe",      models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="photos", to="menu.recipe")),
                ("uploaded_by", models.ForeignKey(null=True, on_delete=django.db.models.deletion.SET_NULL, related_name="recipe_photos", to=settings.AUTH_USER_MODEL)),
            ],
            options={
                "verbose_name": "Photo de recette",
                "verbose_name_plural": "Photos de recettes",
                "ordering": ["order", "created_at"],
            },
        ),
    ]

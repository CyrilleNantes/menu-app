import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("menu", "0020_recipe_title_normalise"),
    ]

    operations = [
        migrations.CreateModel(
            name="MealDish",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("servings_count", models.PositiveIntegerField(
                    blank=True, null=True,
                    help_text="Portions. Si vide, hérite du servings_count du repas principal.",
                )),
                ("role", models.CharField(
                    blank=True, default="", max_length=50,
                    help_text="Libre : 'accompagnement', 'sauce', 'entrée'…",
                )),
                ("meal", models.ForeignKey(
                    on_delete=django.db.models.deletion.CASCADE,
                    related_name="dishes",
                    to="menu.meal",
                )),
                ("recipe", models.ForeignKey(
                    blank=True, null=True,
                    on_delete=django.db.models.deletion.SET_NULL,
                    related_name="as_dish",
                    to="menu.recipe",
                )),
            ],
            options={
                "verbose_name": "Accompagnement",
                "verbose_name_plural": "Accompagnements",
            },
        ),
    ]

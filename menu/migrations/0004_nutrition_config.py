from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("menu", "0003_intelligence_fields"),
    ]

    operations = [
        migrations.CreateModel(
            name="NutritionConfig",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("calories_dinner_target",    models.PositiveIntegerField(default=850,  verbose_name="Cible kcal dîner (adulte référence)")),
                ("proteins_dinner_target",    models.PositiveIntegerField(default=27,   verbose_name="Cible protéines g dîner (adulte référence)")),
                ("max_red_meat_per_week",     models.PositiveSmallIntegerField(default=3,  verbose_name="Max repas viande rouge / semaine")),
                ("min_fish_per_week",         models.PositiveSmallIntegerField(default=1,  verbose_name="Min repas poisson / semaine")),
                ("min_vegetarian_per_week",   models.PositiveSmallIntegerField(default=1,  verbose_name="Min repas végétarien / semaine")),
                ("min_days_before_repeat",    models.PositiveSmallIntegerField(default=14, verbose_name="Jours min avant de replanifier un même plat")),
                ("min_days_low_rated_repeat", models.PositiveSmallIntegerField(default=21, verbose_name="Jours min avant de replanifier un plat < 2★")),
            ],
            options={
                "verbose_name": "Configuration nutritionnelle PNNS",
                "verbose_name_plural": "Configuration nutritionnelle PNNS",
            },
        ),
    ]

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("menu", "0002_calendar_fields"),
    ]

    operations = [
        migrations.AddField(
            model_name="recipe",
            name="protein_type",
            field=models.CharField(
                blank=True,
                choices=[
                    ("boeuf",        "Bœuf"),
                    ("volaille",     "Volaille"),
                    ("porc",         "Porc"),
                    ("poisson",      "Poisson"),
                    ("oeufs",        "Œufs"),
                    ("legumineuses", "Légumineuses"),
                    ("autre",        "Autre"),
                    ("aucune",       "Aucune (végétarien)"),
                ],
                max_length=20,
                null=True,
                verbose_name="Protéine principale",
            ),
        ),
        migrations.AddField(
            model_name="userprofile",
            name="portions_factor",
            field=models.FloatField(
                default=1.0,
                help_text="1.0 = adulte référence. Ado garçon 15–16 ans ≈ 1.3, ado fille 13 ans ≈ 0.9.",
                verbose_name="Facteur de portion",
            ),
        ),
    ]

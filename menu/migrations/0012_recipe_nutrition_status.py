from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('menu', '0011_known_ingredient_fk_and_default_unit'),
    ]

    operations = [
        migrations.AddField(
            model_name='recipe',
            name='nutrition_status',
            field=models.CharField(
                choices=[
                    ('ok',      'Complet — tous les ingrédients mappés'),
                    ('partial', 'Partiel — certains ingrédients non mappés'),
                    ('missing', 'Manquant — aucun ingrédient mappé'),
                ],
                default='missing',
                max_length=10,
                verbose_name='Statut nutritionnel',
            ),
        ),
    ]

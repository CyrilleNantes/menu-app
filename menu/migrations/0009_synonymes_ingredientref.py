from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('menu', '0008_remove_openfoodfacts_id'),
    ]

    operations = [
        migrations.AddField(
            model_name='ingredientref',
            name='synonymes',
            field=models.TextField(
                blank=True, default='',
                help_text="Noms courants séparés par des virgules (ex: spaghetti, tagliatelles, penne). Utilisés pour l'autocomplete.",
                verbose_name='Synonymes',
            ),
        ),
    ]

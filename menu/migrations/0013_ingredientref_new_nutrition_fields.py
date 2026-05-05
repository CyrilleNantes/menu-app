from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('menu', '0012_recipe_nutrition_status'),
    ]

    operations = [
        migrations.AddField(
            model_name='ingredientref',
            name='sucres_100g',
            field=models.FloatField(blank=True, null=True, verbose_name='Sucres (g/100g)'),
        ),
        migrations.AddField(
            model_name='ingredientref',
            name='fibres_100g',
            field=models.FloatField(blank=True, null=True, verbose_name='Fibres alimentaires (g/100g)'),
        ),
        migrations.AddField(
            model_name='ingredientref',
            name='ag_satures_100g',
            field=models.FloatField(blank=True, null=True, verbose_name='AG saturés (g/100g)'),
        ),
        migrations.AddField(
            model_name='ingredientref',
            name='sel_100g',
            field=models.FloatField(blank=True, null=True, verbose_name='Sel (g/100g)'),
        ),
    ]

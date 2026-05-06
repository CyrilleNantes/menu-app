from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('menu', '0022_shoppingitem_known_ingredient_knowningredient_unit_weight_g'),
    ]

    operations = [
        migrations.AddField(
            model_name='knowningredient',
            name='transco_unit_label',
            field=models.CharField(
                blank=True, default='',
                max_length=30,
                verbose_name='Libellé unité transco',
                help_text='Libellé affiché sur la liste de courses : tranche, gousse, œuf, pavé… '
                          'Indépendant de l\'unité par défaut du formulaire recette.',
            ),
        ),
    ]

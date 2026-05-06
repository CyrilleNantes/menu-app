from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ('menu', '0021_mealdish'),
    ]

    operations = [
        migrations.AddField(
            model_name='knowningredient',
            name='unit_weight_g',
            field=models.FloatField(
                blank=True, null=True,
                verbose_name='Poids d\'une unité (g)',
                help_text='Transco pratique pour la liste de courses : 1 tranche pain de mie = 40g, '
                          '1 gousse d\'ail = 5g, 1 œuf = 50g… Laissez vide si non applicable.',
            ),
        ),
        migrations.AddField(
            model_name='shoppingitem',
            name='known_ingredient',
            field=models.ForeignKey(
                blank=True, null=True,
                on_delete=django.db.models.deletion.SET_NULL,
                related_name='shopping_items',
                to='menu.knowningredient',
                verbose_name='Ingrédient connu',
            ),
        ),
    ]

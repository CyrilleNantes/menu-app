"""
Migration 0007 — Référentiel Ciqual
====================================
Ajoute :
- `menu.IngredientRef` : référentiel nutritionnel ANSES Ciqual 2020
- `Ingredient.ciqual_ref` : FK nullable vers IngredientRef

Ne touche PAS aux champs existants.
"""

from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ('menu', '0006_meal_absent_field'),
    ]

    operations = [
        # ── 1. Créer la table IngredientRef ──────────────────────────────────
        migrations.CreateModel(
            name='IngredientRef',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False)),
                ('ciqual_code', models.CharField(max_length=10, unique=True, verbose_name='Code Ciqual')),
                ('nom_fr', models.CharField(max_length=300, verbose_name='Nom Ciqual (officiel)')),
                ('nom_normalise', models.CharField(max_length=300, db_index=True, verbose_name='Nom normalisé (recherche)')),
                ('groupe', models.CharField(max_length=100, blank=True, verbose_name='Groupe alimentaire Ciqual')),
                ('sous_groupe', models.CharField(max_length=100, blank=True, verbose_name='Sous-groupe Ciqual')),
                ('kcal_100g', models.FloatField(null=True, blank=True, verbose_name='Énergie (kcal/100g)')),
                ('proteines_100g', models.FloatField(null=True, blank=True, verbose_name='Protéines (g/100g)')),
                ('glucides_100g', models.FloatField(null=True, blank=True, verbose_name='Glucides (g/100g)')),
                ('lipides_100g', models.FloatField(null=True, blank=True, verbose_name='Lipides (g/100g)')),
                ('default_weight_g', models.FloatField(
                    null=True, blank=True,
                    verbose_name='Poids par défaut (g)',
                    help_text='Pour les unités dénombrables : 1 œuf = 60g, 1 oignon = 80g, etc.'
                )),
                ('protein_type', models.CharField(
                    max_length=20, blank=True, null=True,
                    choices=[
                        ('boeuf', 'Bœuf'), ('volaille', 'Volaille'), ('porc', 'Porc'),
                        ('poisson', 'Poisson'), ('oeufs', 'Œufs'),
                        ('legumineuses', 'Légumineuses'), ('autre', 'Autre'),
                    ],
                    verbose_name='Type de protéine'
                )),
                ('shopping_category', models.CharField(
                    max_length=50, blank=True, null=True,
                    verbose_name='Catégorie liste de courses'
                )),
            ],
            options={
                'verbose_name': 'Référentiel ingrédient (Ciqual)',
                'verbose_name_plural': 'Référentiel ingrédients (Ciqual)',
                'ordering': ['nom_fr'],
            },
        ),

        # ── 2. Ajouter FK ciqual_ref sur Ingredient ──────────────────────────
        migrations.AddField(
            model_name='ingredient',
            name='ciqual_ref',
            field=models.ForeignKey(
                to='menu.IngredientRef',
                on_delete=django.db.models.deletion.SET_NULL,
                null=True, blank=True,
                related_name='ingredients',
                verbose_name='Référence Ciqual',
                help_text='Correspondance dans le référentiel ANSES Ciqual 2020'
            ),
        ),
    ]

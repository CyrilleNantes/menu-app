from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('menu', '0014_sugars_per_serving'),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.AddField(
            model_name='weekplan',
            name='active_dates',
            field=models.JSONField(blank=True, default=list),
        ),
        migrations.AddField(
            model_name='weekplan',
            name='guests',
            field=models.JSONField(blank=True, default=list),
        ),
        migrations.AddField(
            model_name='weekplan',
            name='present_members',
            field=models.ManyToManyField(
                blank=True,
                related_name='planning_presences',
                to=settings.AUTH_USER_MODEL,
            ),
        ),
        migrations.AlterField(
            model_name='weekplan',
            name='status',
            field=models.CharField(
                choices=[
                    ('draft', 'Brouillon'),
                    ('published', 'Publié'),
                    ('finished', 'Terminé'),
                ],
                default='draft',
                max_length=20,
            ),
        ),
        migrations.AlterModelOptions(
            name='weekplan',
            options={
                'verbose_name': 'Planning de période',
                'verbose_name_plural': 'Plannings de période',
            },
        ),
    ]

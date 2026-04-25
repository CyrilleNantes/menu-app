import datetime
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("menu", "0001_initial"),
    ]

    operations = [
        # UserProfile — créneaux configurables pour l'export Google Calendar
        migrations.AddField(
            model_name="userprofile",
            name="lunch_start",
            field=models.TimeField(default=datetime.time(12, 0), verbose_name="Début déjeuner"),
        ),
        migrations.AddField(
            model_name="userprofile",
            name="lunch_end",
            field=models.TimeField(default=datetime.time(13, 0), verbose_name="Fin déjeuner"),
        ),
        migrations.AddField(
            model_name="userprofile",
            name="dinner_start",
            field=models.TimeField(default=datetime.time(20, 30), verbose_name="Début dîner"),
        ),
        migrations.AddField(
            model_name="userprofile",
            name="dinner_end",
            field=models.TimeField(default=datetime.time(21, 30), verbose_name="Fin dîner"),
        ),
        # Meal — stockage de l'ID événement créé dans Google Calendar
        migrations.AddField(
            model_name="meal",
            name="google_event_id",
            field=models.CharField(
                blank=True,
                default="",
                max_length=200,
                verbose_name="ID événement Google Calendar",
            ),
        ),
    ]

from django.db import migrations, models


def populate_title_normalise(apps, schema_editor):
    from menu.models import _normaliser_nom
    Recipe = apps.get_model("menu", "Recipe")
    batch = []
    for r in Recipe.objects.all():
        r.title_normalise = _normaliser_nom(r.title)
        batch.append(r)
    Recipe.objects.bulk_update(batch, ["title_normalise"])


class Migration(migrations.Migration):

    dependencies = [
        ("menu", "0019_userprofile_prot_fields_and_profile_type"),
    ]

    operations = [
        migrations.AddField(
            model_name="recipe",
            name="title_normalise",
            field=models.CharField(blank=True, db_index=True, editable=False, max_length=200),
        ),
        migrations.RunPython(populate_title_normalise, migrations.RunPython.noop),
    ]

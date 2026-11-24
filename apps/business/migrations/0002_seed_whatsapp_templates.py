from django.db import migrations

from apps.business.defaults import DEFAULT_TEMPLATES


def seed(apps, schema_editor):
    WhatsAppTemplate = apps.get_model("business", "WhatsAppTemplate")
    BusinessSettings = apps.get_model("business", "BusinessSettings")
    for key, languages in DEFAULT_TEMPLATES.items():
        for language, body in languages.items():
            WhatsAppTemplate.objects.get_or_create(key=key, language=language, defaults={"body": body})
    BusinessSettings.objects.get_or_create(singleton=True)


class Migration(migrations.Migration):
    dependencies = [("business", "0001_initial")]

    operations = [migrations.RunPython(seed, migrations.RunPython.noop)]

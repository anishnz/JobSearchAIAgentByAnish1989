from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [("agent", "0004_fill_slugs_onboarding")]

    operations = [
        migrations.AddField(model_name="job", name="saved_at", field=models.DateTimeField(blank=True, null=True)),
    ]

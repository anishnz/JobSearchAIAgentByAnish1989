import re

from django.db import migrations
from django.utils.text import slugify


def forwards(apps, schema_editor):
    Candidate = apps.get_model("agent", "Candidate")
    used = set(Candidate.objects.exclude(slug=None).values_list("slug", flat=True))
    for c in Candidate.objects.all():
        if not c.slug:
            base = slugify(re.split(r"[\s_.-]+", (c.full_name or "user").strip())[0]) + "cv"
            slug, n = base, 2
            while slug in used:
                slug, n = f"{base}{n}", n + 1
            c.slug = slug
            used.add(slug)
        if c.cvs.exists():
            c.onboarding_done = True
        c.save(update_fields=["slug", "onboarding_done"])


class Migration(migrations.Migration):
    dependencies = [("agent", "0003_users_portal_settings")]
    operations = [migrations.RunPython(forwards, migrations.RunPython.noop)]

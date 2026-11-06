from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [("agent", "0005_job_saved_at")]

    operations = [
        migrations.AddField(
            model_name="cvdocument",
            name="kb_doc_id",
            field=models.CharField(blank=True, editable=False, max_length=64,
                                   help_text="The same CV inside this person's knowledge base (kept in step automatically)."),
        ),
    ]

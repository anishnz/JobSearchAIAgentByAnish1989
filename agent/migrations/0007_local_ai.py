from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [("agent", "0006_cvdocument_kb_doc_id")]

    operations = [
        migrations.AddField(
            model_name="candidate",
            name="ai_provider",
            field=models.CharField(choices=[("claude", "Claude (my own API key)"),
                                            ("local", "Local AI on this laptop (Ollama, free)")],
                                   default="claude", max_length=10,
                                   help_text="Which AI writes your CVs, scores jobs and makes interview practice."),
        ),
        migrations.AddField(
            model_name="systemsettings",
            name="ollama_model",
            field=models.CharField(blank=True, max_length=120,
                                   help_text="Local AI model in Ollama on this laptop, e.g. llama3.2 (chosen by the admin)."),
        ),
    ]

"""apps.py - Knowledge Base app: pages and a JSON proxy to the RAG service (from CyberQuest)."""

from django.apps import AppConfig


class KbConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "kb"
    verbose_name = "Knowledge base"

    def ready(self):
        from django.db.models.signals import post_delete  # pylint: disable=import-outside-toplevel

        from agent.models import Candidate  # pylint: disable=import-outside-toplevel

        from .services import remove_candidate_documents  # pylint: disable=import-outside-toplevel

        def _remove_docs(sender, instance, **kwargs):  # pylint: disable=unused-argument
            remove_candidate_documents(instance)  # best effort: False if the service is not running

        post_delete.connect(_remove_docs, sender=Candidate, dispatch_uid="kb_remove_candidate_docs")

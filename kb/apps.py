"""apps.py - Knowledge Base app: pages and a JSON proxy to the RAG service (from CyberQuest)."""

from django.apps import AppConfig


class KbConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "kb"
    verbose_name = "Knowledge base"

    def ready(self):
        # pylint: disable=import-outside-toplevel,unused-argument
        from django.db.models.signals import post_delete, post_save

        from agent.models import Candidate, CVDocument

        from . import services

        def remove_candidate_docs(sender, instance, **kwargs):
            services.remove_candidate_documents(instance)  # best effort: False if the service is not running

        def cv_saved(sender, instance, raw=False, update_fields=None, **kwargs):
            """A CV saved or edited anywhere (profile, welcome, import) is kept in step in the knowledge base."""
            if raw or getattr(instance, "_kb_skip", False):
                return
            if update_fields is not None and set(update_fields) <= {"kb_doc_id", "updated_at"}:
                return
            services.index_cv(instance)

        def cv_deleted(sender, instance, **kwargs):
            if instance.kb_doc_id and not getattr(instance, "_kb_skip", False):
                services.delete_doc(instance.candidate_id, instance.kb_doc_id)  # works even while the user is deleted

        post_delete.connect(remove_candidate_docs, sender=Candidate, dispatch_uid="kb_remove_candidate_docs")
        post_save.connect(cv_saved, sender=CVDocument, dispatch_uid="kb_cv_saved")
        post_delete.connect(cv_deleted, sender=CVDocument, dispatch_uid="kb_cv_deleted")

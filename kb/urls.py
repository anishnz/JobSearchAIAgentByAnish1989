"""urls.py - Knowledge Base pages and JSON endpoints, inside each person's own space (/c/<cid>/kb/)."""

from django.urls import path

from . import api, views

app_name = "kb"
urlpatterns = [
    path("c/<int:cid>/kb/", views.ask, name="ask"),
    path("c/<int:cid>/kb/manage/", views.manage, name="manage"),
    path("c/<int:cid>/kb/api/ask/", api.ask, name="api_ask"),
    path("c/<int:cid>/kb/api/interview/", api.interview, name="api_interview"),
    path("c/<int:cid>/kb/api/documents/", api.documents, name="api_documents"),
    path("c/<int:cid>/kb/api/documents/<str:doc_id>/", api.document_delete, name="api_document_delete"),
    path("kb/api/admin/model/", api.model_settings, name="api_model"),
    path("kb/api/admin/model/test/", api.model_test, name="api_model_test"),
]

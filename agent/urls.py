from django.urls import path

from . import views

urlpatterns = [
    path("", views.home, name="home"),
    path("users/new/", views.candidate_new, name="candidate_new"),
    path("users/<int:cid>/toggle/", views.candidate_toggle_access, name="candidate_toggle_access"),
    path("audit/", views.audit, name="audit"),
    path("help/", views.help_page, name="help"),
    path("c/<int:cid>/", views.candidate_dashboard, name="candidate_dashboard"),
    path("c/<int:cid>/profile/", views.candidate_profile, name="candidate_profile"),
    path("c/<int:cid>/cv/<int:pk>/", views.cv_edit, name="cv_edit"),
    path("c/<int:cid>/cv/<int:pk>/delete/", views.cv_delete, name="cv_delete"),
    path("c/<int:cid>/jobs/", views.jobs, name="jobs"),
    path("c/<int:cid>/jobs/<int:pk>/", views.job_detail, name="job_detail"),
    path("c/<int:cid>/applications/", views.applications, name="applications"),
    path("c/<int:cid>/applications/<int:pk>/<slug:kind>.docx", views.download_docx, name="download_docx"),
    path("c/<int:cid>/questions/", views.questions, name="questions"),
]

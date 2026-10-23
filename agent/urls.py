from django.urls import path

from . import admin_views, views

urlpatterns = [
    path("", views.landing, name="landing"),
    path("u/<slug:slug>/", views.portal, name="portal"),
    path("home/", views.home, name="home"),
    path("help/", views.help_page, name="help"),
    # super admin
    path("manage/", admin_views.manage_home, name="manage_home"),
    path("manage/users/new/", admin_views.manage_user_new, name="manage_user_new"),
    path("manage/users/<int:cid>/", admin_views.manage_user_edit, name="manage_user_edit"),
    path("manage/settings/", admin_views.manage_settings, name="manage_settings"),
    path("manage/health/", admin_views.manage_health, name="manage_health"),
    path("manage/audit/", admin_views.manage_audit, name="manage_audit"),
    # each user's own space
    path("c/<int:cid>/", views.candidate_dashboard, name="candidate_dashboard"),
    path("c/<int:cid>/welcome/", views.welcome, name="welcome"),
    path("c/<int:cid>/welcome/review/", views.welcome_review, name="welcome_review"),
    path("c/<int:cid>/settings/", views.candidate_settings, name="candidate_settings"),
    path("c/<int:cid>/profile/", views.candidate_profile, name="candidate_profile"),
    path("c/<int:cid>/cv/<int:pk>/", views.cv_edit, name="cv_edit"),
    path("c/<int:cid>/cv/<int:pk>/delete/", views.cv_delete, name="cv_delete"),
    path("c/<int:cid>/jobs/", views.jobs, name="jobs"),
    path("c/<int:cid>/jobs/<int:pk>/", views.job_detail, name="job_detail"),
    path("c/<int:cid>/applications/", views.applications, name="applications"),
    path("c/<int:cid>/applications/<int:pk>/<slug:kind>.docx", views.download_docx, name="download_docx"),
    path("c/<int:cid>/questions/", views.questions, name="questions"),
]

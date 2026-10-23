from django.contrib import admin

from .models import AIQuestion, Application, AuditLog, Candidate, CVDocument, Job


@admin.register(Candidate)
class CandidateAdmin(admin.ModelAdmin):
    list_display = ("full_name", "user", "auto_mode", "auto_consent", "is_active", "last_search_at")
    list_filter = ("is_active", "auto_mode")


@admin.register(Job)
class JobAdmin(admin.ModelAdmin):
    list_display = ("title", "company", "candidate", "site", "match_score", "status", "found_at")
    list_filter = ("status", "site", "candidate")
    search_fields = ("title", "company")


@admin.register(Application)
class ApplicationAdmin(admin.ModelAdmin):
    list_display = ("job", "candidate", "status", "applied_at", "follow_up_date")
    list_filter = ("status", "candidate")


@admin.register(AuditLog)
class AuditLogAdmin(admin.ModelAdmin):
    list_display = ("created_at", "actor", "candidate", "action")
    list_filter = ("action",)
    readonly_fields = ("created_at", "actor", "candidate", "action", "detail")


admin.site.register(CVDocument)
admin.site.register(AIQuestion)
admin.site.site_header = "JobSearchAIAgentByAnish1989 - Admin"

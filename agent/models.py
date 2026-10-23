"""Data models. Every record belongs to ONE candidate so people's CVs never mix."""
import re

from django.conf import settings
from django.db import models
from django.utils import timezone


class Candidate(models.Model):
    MODE_SUGGEST = "suggest"
    MODE_QUEUE = "queue"
    MODE_AUTO = "auto"
    AUTO_MODES = [
        (MODE_SUGGEST, "Suggest only (default)"),
        (MODE_QUEUE, "Prepare CV + cover letter, wait for my review"),
        (MODE_AUTO, "Auto-prepare and mark ready to apply"),
    ]

    user = models.OneToOneField(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="candidate")
    full_name = models.CharField(max_length=120)
    email = models.EmailField(blank=True)
    phone = models.CharField(max_length=40, blank=True)
    location = models.CharField(max_length=120, default="Auckland")
    job_types = models.TextField(
        blank=True, help_text="Job types to search, one per line or comma separated (e.g. kitchen hand, retail assistant)."
    )
    availability = models.TextField(blank=True, help_text="When you can work, e.g. Mon-Fri any time.")
    extra_notes = models.TextField(blank=True, help_text="Anything true the AI should know (licence, certificates, etc.).")
    auto_mode = models.CharField(max_length=10, choices=AUTO_MODES, default=MODE_SUGGEST)
    auto_consent = models.BooleanField(
        default=False, help_text="I agree that the agent may prepare applications automatically for me."
    )
    min_match_score = models.PositiveSmallIntegerField(default=65)
    is_active = models.BooleanField(default=True, help_text="Include in the daily 8:00 AM search.")
    last_insight = models.TextField(blank=True)
    last_insight_at = models.DateTimeField(null=True, blank=True)
    last_search_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["full_name"]

    def __str__(self):
        return self.full_name

    def keyword_list(self):
        return [k.strip() for k in re.split(r"[,\n]", self.job_types or "") if k.strip()]

    def all_cv_text(self, limit=15000):
        parts = [f"--- CV: {cv.title} ---\n{cv.text}" for cv in self.cvs.all()]
        return "\n\n".join(parts)[:limit]

    def answered_facts(self):
        qs = self.questions.exclude(answer="")
        return "\n".join(f"Q: {q.question}\nA: {q.answer}" for q in qs)

    @property
    def auto_enabled(self):
        return self.auto_consent and self.auto_mode != self.MODE_SUGGEST


class CVDocument(models.Model):
    candidate = models.ForeignKey(Candidate, on_delete=models.CASCADE, related_name="cvs")
    title = models.CharField(max_length=120, help_text="e.g. Hospitality CV, Admin CV")
    text = models.TextField(help_text="CV content as plain text. You can edit this any time.")
    uploaded_file = models.FileField(upload_to="cvs/%Y/%m", blank=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-updated_at"]

    def __str__(self):
        return f"{self.candidate} - {self.title}"


class Job(models.Model):
    SOURCES = [("crawl", "Auto search"), ("url", "Website link"), ("paste", "Pasted description")]
    STATUSES = [
        ("new", "New"),
        ("suggested", "AI suggested"),
        ("skipped", "Skipped"),
        ("applied", "Applied"),
        ("closed", "Closed / expired"),
    ]

    candidate = models.ForeignKey(Candidate, on_delete=models.CASCADE, related_name="jobs")
    title = models.CharField(max_length=255)
    company = models.CharField(max_length=255, blank=True)
    location = models.CharField(max_length=255, blank=True)
    salary = models.CharField(max_length=120, blank=True)
    url = models.URLField(max_length=1000, blank=True)
    description = models.TextField(blank=True)
    source = models.CharField(max_length=10, choices=SOURCES, default="paste")
    site = models.CharField(max_length=60, blank=True)
    fingerprint = models.CharField(max_length=64, db_index=True)
    match_score = models.PositiveSmallIntegerField(null=True, blank=True)
    match_reason = models.TextField(blank=True)
    status = models.CharField(max_length=12, choices=STATUSES, default="new")
    found_at = models.DateTimeField(default=timezone.now)

    class Meta:
        ordering = ["-found_at"]
        constraints = [models.UniqueConstraint(fields=["candidate", "fingerprint"], name="unique_job_per_candidate")]

    def __str__(self):
        return f"{self.title} @ {self.company or self.site}"


class Application(models.Model):
    STATUSES = [
        ("draft", "Draft - needs review"),
        ("ready", "Ready to apply"),
        ("applied", "Applied"),
        ("interview", "Interview"),
        ("offer", "Offer"),
        ("rejected", "Rejected"),
        ("withdrawn", "Withdrawn"),
    ]

    candidate = models.ForeignKey(Candidate, on_delete=models.CASCADE, related_name="applications")
    job = models.OneToOneField(Job, on_delete=models.CASCADE, related_name="application")
    cv_text = models.TextField(blank=True)
    cover_letter = models.TextField(blank=True)
    email_draft = models.TextField(blank=True)
    interview_prep = models.TextField(blank=True)
    status = models.CharField(max_length=12, choices=STATUSES, default="draft")
    applied_at = models.DateField(null=True, blank=True)
    follow_up_date = models.DateField(null=True, blank=True)
    interview_date = models.DateTimeField(null=True, blank=True)
    notes = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-updated_at"]

    def __str__(self):
        return f"{self.candidate} -> {self.job}"


class AIQuestion(models.Model):
    """Questions the AI asks a candidate when it needs true information it cannot guess."""

    candidate = models.ForeignKey(Candidate, on_delete=models.CASCADE, related_name="questions")
    job = models.ForeignKey(Job, on_delete=models.SET_NULL, null=True, blank=True, related_name="questions")
    question = models.TextField()
    answer = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["answer", "-created_at"]

    def __str__(self):
        return f"Question for {self.candidate}: {self.question[:60]}"


class AuditLog(models.Model):
    actor = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True)
    candidate = models.ForeignKey(Candidate, on_delete=models.SET_NULL, null=True, blank=True)
    action = models.CharField(max_length=80)
    detail = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]

    @classmethod
    def log(cls, action, detail="", actor=None, candidate=None):
        if actor is not None and not getattr(actor, "is_authenticated", False):
            actor = None
        return cls.objects.create(action=action, detail=detail[:4000], actor=actor, candidate=candidate)

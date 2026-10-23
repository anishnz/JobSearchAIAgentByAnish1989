"""Data models. Every record belongs to ONE candidate so people's CVs never mix."""
import re

from django.conf import settings
from django.db import models
from django.utils import timezone
from django.utils.text import slugify

from .crypto import decrypt, encrypt


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
    slug = models.SlugField(max_length=40, unique=True, null=True, blank=True,
                            help_text="Personal link name, e.g. anishcv -> anishcv.localhost:8010")
    full_name = models.CharField(max_length=120)
    email = models.EmailField(blank=True)
    phone = models.CharField(max_length=40, blank=True)
    location = models.CharField(max_length=120, default="Auckland")
    job_types = models.TextField(
        blank=True, help_text="Job types to search, one per line or comma separated (e.g. kitchen hand, retail assistant)."
    )
    availability = models.TextField(blank=True, help_text="When you can work, e.g. Mon-Fri any time.")
    education = models.TextField(blank=True)
    experience_summary = models.TextField(blank=True)
    skills = models.TextField(blank=True)
    extra_notes = models.TextField(blank=True, help_text="Anything true the AI should know (licence, certificates, etc.).")
    auto_mode = models.CharField(max_length=10, choices=AUTO_MODES, default=MODE_SUGGEST)
    auto_consent = models.BooleanField(
        default=False, help_text="I agree that the agent may prepare applications automatically for me."
    )
    min_match_score = models.PositiveSmallIntegerField(default=65)
    is_active = models.BooleanField(default=True, help_text="Include in the daily 8:00 AM search.")
    search_paused = models.BooleanField(default=False)
    onboarding_done = models.BooleanField(default=False)

    # Permissions controlled by the super admin
    ai_allowed = models.BooleanField(default=True)
    email_allowed = models.BooleanField(default=True)
    auto_allowed = models.BooleanField(default=True)

    # Personal settings (secrets are encrypted)
    gmail_address = models.EmailField(blank=True)
    gmail_app_password_enc = models.TextField(blank=True)
    ai_key_enc = models.TextField(blank=True)

    last_insight = models.TextField(blank=True)
    last_insight_at = models.DateTimeField(null=True, blank=True)
    last_search_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["full_name"]

    def __str__(self):
        return self.full_name

    def save(self, *args, **kwargs):
        if not self.slug:
            base = slugify(re.split(r"[\s_.-]+", (self.full_name or self.user.username).strip())[0]) + "cv"
            slug, n = base, 2
            while Candidate.objects.filter(slug=slug).exclude(pk=self.pk).exists():
                slug, n = f"{base}{n}", n + 1
            self.slug = slug
        super().save(*args, **kwargs)

    # ---- secrets
    @property
    def ai_key(self):
        return decrypt(self.ai_key_enc)

    @ai_key.setter
    def ai_key(self, value):
        self.ai_key_enc = encrypt(value.strip()) if value else ""

    @property
    def gmail_app_password(self):
        return decrypt(self.gmail_app_password_enc)

    @gmail_app_password.setter
    def gmail_app_password(self, value):
        self.gmail_app_password_enc = encrypt(value.replace(" ", "")) if value else ""

    @property
    def gmail_ready(self):
        return bool(self.email_allowed and self.gmail_address and self.gmail_app_password_enc)

    # ---- helpers
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
        return self.auto_allowed and self.auto_consent and self.auto_mode != self.MODE_SUGGEST

    @property
    def first_name(self):
        return (self.full_name or "").split(" ")[0]


class CVDocument(models.Model):
    candidate = models.ForeignKey(Candidate, on_delete=models.CASCADE, related_name="cvs")
    title = models.CharField(max_length=120, help_text="e.g. Hospitality CV, Admin CV")
    text = models.TextField(help_text="CV content as plain text. You can edit this any time.")
    uploaded_file = models.FileField(upload_to="cvs/%Y/%m", blank=True)
    category = models.CharField(max_length=120, blank=True, help_text="e.g. IT: Software, Hospitality")
    best_for = models.CharField(max_length=255, blank=True, help_text="Which jobs this CV is best for.")
    source_path = models.CharField(max_length=500, blank=True, help_text="Original file location (for your reference).")
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["category", "title"]

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
    employer_email = models.EmailField(blank=True, help_text="Where to send the application (from the job advert).")
    email_sent_at = models.DateTimeField(null=True, blank=True)
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


class SystemSettings(models.Model):
    """One row of system-wide settings, edited by the super admin."""

    site_title = models.CharField(max_length=120, default="Job Search AI Agent")
    gmail_address = models.EmailField(blank=True, help_text="Sends 'forgot password' emails.")
    gmail_app_password_enc = models.TextField(blank=True)
    scheduler_heartbeat = models.DateTimeField(null=True, blank=True)
    last_daily_run = models.DateTimeField(null=True, blank=True)
    last_daily_result = models.TextField(blank=True)

    class Meta:
        verbose_name_plural = "System settings"

    @classmethod
    def load(cls):
        obj, _ = cls.objects.get_or_create(pk=1)
        return obj

    @property
    def gmail_app_password(self):
        return decrypt(self.gmail_app_password_enc)

    @gmail_app_password.setter
    def gmail_app_password(self, value):
        self.gmail_app_password_enc = encrypt(value.replace(" ", "")) if value else ""

    @property
    def email_ready(self):
        return bool(self.gmail_address and self.gmail_app_password_enc)


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

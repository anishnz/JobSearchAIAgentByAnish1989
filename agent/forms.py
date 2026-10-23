from django import forms
from django.contrib.auth.models import User
from django.utils.text import slugify

from .models import Application, Candidate, CVDocument, SystemSettings


def _slug_ok(value, exclude_pk=None):
    value = slugify(value)[:40]
    if not value:
        raise forms.ValidationError("Use letters and numbers, e.g. sarucv.")
    if Candidate.objects.filter(slug=value).exclude(pk=exclude_pk).exists():
        raise forms.ValidationError("This personal link name is already used.")
    return value


# ------------------------------------------------------------------ admin forms
class CandidateCreateForm(forms.Form):
    full_name = forms.CharField(max_length=120)
    username = forms.CharField(max_length=150, help_text="Login name, e.g. saru.")
    password = forms.CharField(widget=forms.PasswordInput, min_length=8, help_text="At least 8 characters.")
    email = forms.EmailField(required=False, help_text="Needed for 'Forgot password'.")
    slug = forms.CharField(max_length=40, required=False, label="Personal link name",
                           help_text="e.g. sarucv -> sarucv.localhost:8010. Leave empty to create one automatically.")

    def clean_username(self):
        name = self.cleaned_data["username"].strip()
        if User.objects.filter(username__iexact=name).exists():
            raise forms.ValidationError("This username is already used.")
        return name

    def clean_slug(self):
        value = self.cleaned_data.get("slug")
        return _slug_ok(value) if value else ""


class AdminUserForm(forms.ModelForm):
    login_enabled = forms.BooleanField(required=False, label="Login enabled")
    new_password = forms.CharField(required=False, widget=forms.PasswordInput, min_length=8,
                                   label="Set a new password", help_text="Leave empty to keep the current password.")

    class Meta:
        model = Candidate
        fields = ["full_name", "email", "slug", "is_active", "ai_allowed", "email_allowed", "auto_allowed"]
        labels = {"slug": "Personal link name", "is_active": "Include in daily 8:00 AM search",
                  "ai_allowed": "Can use AI (with their own key)", "email_allowed": "Can send emails from Gmail",
                  "auto_allowed": "Can turn on auto mode"}

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["login_enabled"].initial = self.instance.user.is_active

    def clean_slug(self):
        return _slug_ok(self.cleaned_data["slug"], exclude_pk=self.instance.pk)


class SystemSettingsForm(forms.ModelForm):
    gmail_app_password = forms.CharField(required=False, widget=forms.PasswordInput(render_value=False),
                                         label="Gmail App Password",
                                         help_text="16 letters from myaccount.google.com/apppasswords. Leave empty to keep the saved one.")

    class Meta:
        model = SystemSettings
        fields = ["site_title", "gmail_address"]
        labels = {"gmail_address": "Gmail address for system emails (forgot password)"}


# ------------------------------------------------------------------ user forms
class WelcomeCVForm(forms.Form):
    file = forms.FileField(required=False, label="Upload your CV", help_text="PDF, Word (.docx) or text file.")
    text = forms.CharField(required=False, widget=forms.Textarea(attrs={"rows": 8}),
                           label="...or paste your CV text here")

    def clean(self):
        data = super().clean()
        if not data.get("file") and not data.get("text", "").strip():
            raise forms.ValidationError("Please upload a CV file or paste your CV text.")
        f = data.get("file")
        if f and f.size > 5 * 1024 * 1024:
            raise forms.ValidationError("File is too big (max 5 MB).")
        return data


class WelcomeReviewForm(forms.ModelForm):
    job_choices = forms.MultipleChoiceField(required=False, widget=forms.CheckboxSelectMultiple,
                                            label="Job types that fit your CV (untick any you do not want)")
    more_jobs = forms.CharField(required=False, label="Other job types you want (comma separated)")

    class Meta:
        model = Candidate
        fields = ["full_name", "email", "phone", "location", "availability", "education", "experience_summary",
                  "skills"]
        widgets = {f: forms.Textarea(attrs={"rows": 3}) for f in
                   ["availability", "education", "experience_summary", "skills"]}
        labels = {"experience_summary": "Work experience (summary)"}

    def __init__(self, *args, suggestions=(), **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["job_choices"].choices = [(s, s) for s in suggestions]
        self.fields["job_choices"].initial = list(suggestions)
        self.fields["availability"].help_text = "e.g. Mon-Fri any time, weekends after 3pm"


class CandidateProfileForm(forms.ModelForm):
    class Meta:
        model = Candidate
        fields = ["full_name", "email", "phone", "location", "job_types", "availability", "education",
                  "experience_summary", "skills", "extra_notes", "min_match_score", "auto_mode", "auto_consent"]
        widgets = {f: forms.Textarea(attrs={"rows": 3}) for f in
                   ["job_types", "availability", "education", "experience_summary", "skills", "extra_notes"]}
        labels = {"experience_summary": "Work experience (summary)", "min_match_score": "Suggest jobs from score"}

    def __init__(self, *args, is_owner=True, **kwargs):
        super().__init__(*args, **kwargs)
        if not is_owner or not self.instance.auto_allowed:
            # Only the person themselves can give consent, and only if the admin allows auto mode.
            self.fields["auto_consent"].disabled = True
            self.fields["auto_mode"].disabled = True
            self.fields["auto_consent"].help_text = ("Only this person can change this in their own login."
                                                     if not is_owner else "Auto mode is turned off by the admin.")


class UserSettingsForm(forms.Form):
    gmail_address = forms.EmailField(required=False, label="Your Gmail address")
    gmail_app_password = forms.CharField(required=False, widget=forms.PasswordInput, label="Gmail App Password",
                                         help_text="Leave empty to keep the saved one.")
    ai_key = forms.CharField(required=False, widget=forms.PasswordInput, label="Your Claude API key",
                             help_text="Starts with sk-ant-. Leave empty to keep the saved one.")
    remove_ai_key = forms.BooleanField(required=False, label="Remove my saved Claude key")
    remove_gmail = forms.BooleanField(required=False, label="Remove my saved Gmail App Password")


class CVForm(forms.ModelForm):
    file = forms.FileField(required=False, help_text="PDF, DOCX or TXT. The text is extracted so you can edit it.")

    class Meta:
        model = CVDocument
        fields = ["title", "category", "best_for", "text"]
        widgets = {"text": forms.Textarea(attrs={"rows": 12})}

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["text"].required = False
        self.fields["category"].required = False
        self.fields["best_for"].required = False

    def clean(self):
        data = super().clean()
        if not data.get("text") and not data.get("file"):
            raise forms.ValidationError("Upload a CV file or paste the CV text.")
        f = data.get("file")
        if f and f.size > 5 * 1024 * 1024:
            raise forms.ValidationError("File is too big (max 5 MB).")
        return data


class SearchForm(forms.Form):
    keywords = forms.CharField(required=False, label="What type of job?",
                               widget=forms.TextInput(attrs={"placeholder": "e.g. retail assistant, cleaner (empty = my job types)"}))


class JobURLForm(forms.Form):
    url = forms.URLField(label="Job website link", max_length=1000,
                         widget=forms.URLInput(attrs={"placeholder": "https://..."}))


class JobPasteForm(forms.Form):
    title = forms.CharField(max_length=255, label="Job title")
    company = forms.CharField(max_length=255, required=False)
    url = forms.URLField(required=False, max_length=1000, label="Link (optional)")
    description = forms.CharField(widget=forms.Textarea(attrs={"rows": 8}), label="Job description (copy and paste)")


class ApplicationForm(forms.ModelForm):
    class Meta:
        model = Application
        fields = ["status", "employer_email", "applied_at", "follow_up_date", "interview_date", "cv_text",
                  "cover_letter", "email_draft", "notes"]
        widgets = {
            "applied_at": forms.DateInput(attrs={"type": "date"}),
            "follow_up_date": forms.DateInput(attrs={"type": "date"}),
            "interview_date": forms.DateTimeInput(attrs={"type": "datetime-local"}),
            "cv_text": forms.Textarea(attrs={"rows": 16}),
            "cover_letter": forms.Textarea(attrs={"rows": 10}),
            "email_draft": forms.Textarea(attrs={"rows": 6}),
            "notes": forms.Textarea(attrs={"rows": 3}),
        }
        labels = {"cv_text": "Tailored CV", "email_draft": "Application email"}

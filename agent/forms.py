from django import forms
from django.contrib.auth.models import User

from .models import Application, Candidate, CVDocument


class CandidateCreateForm(forms.Form):
    full_name = forms.CharField(max_length=120)
    username = forms.CharField(max_length=150, help_text="Login name for this person.")
    password = forms.CharField(widget=forms.PasswordInput, min_length=8)
    email = forms.EmailField(required=False)
    phone = forms.CharField(max_length=40, required=False)
    job_types = forms.CharField(widget=forms.Textarea(attrs={"rows": 3}), required=False,
                                help_text="One per line or comma separated.")

    def clean_username(self):
        name = self.cleaned_data["username"]
        if User.objects.filter(username__iexact=name).exists():
            raise forms.ValidationError("This username is already used.")
        return name


class CandidateProfileForm(forms.ModelForm):
    class Meta:
        model = Candidate
        fields = ["full_name", "email", "phone", "location", "job_types", "availability", "extra_notes",
                  "min_match_score", "is_active", "auto_mode", "auto_consent"]
        widgets = {f: forms.Textarea(attrs={"rows": 3}) for f in ["job_types", "availability", "extra_notes"]}

    def __init__(self, *args, is_owner=True, **kwargs):
        super().__init__(*args, **kwargs)
        if not is_owner:
            # Only the person themselves can give consent for automatic applications.
            self.fields["auto_consent"].disabled = True
            self.fields["auto_mode"].disabled = True
            self.fields["auto_consent"].help_text = "Only this person can change this in their own login."


class CVForm(forms.ModelForm):
    file = forms.FileField(required=False, help_text="PDF, DOCX or TXT. The text is extracted so you can edit it.")

    class Meta:
        model = CVDocument
        fields = ["title", "category", "best_for", "text"]
        widgets = {"text": forms.Textarea(attrs={"rows": 12})}

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["text"].required = False

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
                               widget=forms.TextInput(attrs={"placeholder": "e.g. retail assistant, cleaner (empty = use profile job types)"}))


class JobURLForm(forms.Form):
    url = forms.URLField(label="Job website link", max_length=1000)


class JobPasteForm(forms.Form):
    title = forms.CharField(max_length=255)
    company = forms.CharField(max_length=255, required=False)
    url = forms.URLField(required=False, max_length=1000)
    description = forms.CharField(widget=forms.Textarea(attrs={"rows": 8}), label="Job description (copy and paste)")


class ApplicationForm(forms.ModelForm):
    class Meta:
        model = Application
        fields = ["status", "applied_at", "follow_up_date", "interview_date", "cv_text", "cover_letter",
                  "email_draft", "notes"]
        widgets = {
            "applied_at": forms.DateInput(attrs={"type": "date"}),
            "follow_up_date": forms.DateInput(attrs={"type": "date"}),
            "interview_date": forms.DateTimeInput(attrs={"type": "datetime-local"}),
            "cv_text": forms.Textarea(attrs={"rows": 16}),
            "cover_letter": forms.Textarea(attrs={"rows": 10}),
            "email_draft": forms.Textarea(attrs={"rows": 6}),
            "notes": forms.Textarea(attrs={"rows": 3}),
        }

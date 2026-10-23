from datetime import timedelta

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.contrib.auth.models import User
from django.core.exceptions import PermissionDenied
from django.db import transaction
from django.db.models import Count, Q
from django.http import HttpResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from django.utils.text import slugify

from . import services, workflow
from .forms import (ApplicationForm, CandidateCreateForm, CandidateProfileForm, CVForm, JobPasteForm,
                    JobURLForm, SearchForm)
from .models import AIQuestion, Application, AuditLog, Candidate, CVDocument, Job

CLOSED = ["offer", "rejected", "withdrawn"]


# ------------------------------------------------------------------ helpers
def admin_required(view):
    @login_required
    def wrapper(request, *args, **kwargs):
        if not request.user.is_staff:
            raise PermissionDenied
        return view(request, *args, **kwargs)
    return wrapper


def get_candidate(request, cid):
    """A user can only open their own candidate. The admin can open any (and it is logged)."""
    candidate = get_object_or_404(Candidate, pk=cid)
    if candidate.user_id == request.user.id:
        return candidate
    if request.user.is_staff:
        seen = request.session.setdefault("admin_viewed", [])
        if cid not in seen:
            AuditLog.log("admin_viewed_records", f"Admin opened {candidate.full_name}'s records",
                         actor=request.user, candidate=candidate)
            request.session["admin_viewed"] = seen + [cid]
        return candidate
    raise PermissionDenied


def run_ai(request, label, fn, *args):
    """Run an AI/network step and show a friendly message if it fails."""
    try:
        return fn(*args)
    except PermissionError as exc:
        messages.error(request, str(exc))
    except Exception as exc:
        messages.error(request, f"{label} failed: {exc.__class__.__name__}: {str(exc)[:200]}")
    return None


def candidate_stats(candidate):
    today = timezone.localdate()
    apps = candidate.applications
    return {
        "jobs_today": candidate.jobs.filter(found_at__date=today).count(),
        "suggested_today": candidate.jobs.filter(found_at__date=today, status="suggested").count(),
        "total_jobs": candidate.jobs.count(),
        "suggested_total": candidate.jobs.filter(status="suggested").count(),
        "drafts": apps.filter(status__in=["draft", "ready"]).count(),
        "applied": apps.filter(status__in=["applied", "interview", "offer", "rejected"]).count(),
        "applied_today": apps.filter(applied_at=today).count(),
        "interviews": apps.filter(status="interview").count(),
        "offers": apps.filter(status="offer").count(),
        "follow_ups_due": apps.filter(follow_up_date__lte=today).exclude(status__in=CLOSED).count(),
        "open_questions": candidate.questions.filter(answer="").count(),
    }


# ------------------------------------------------------------------ help
@login_required
def help_page(request):
    own = Candidate.objects.filter(user=request.user).first()
    return render(request, "agent/help.html", {"own": own, "ai_on": services.claude_available()})


# ------------------------------------------------------------------ home / admin
@login_required
def home(request):
    if not request.user.is_staff:
        candidate = Candidate.objects.filter(user=request.user).first()
        if candidate:
            return redirect("candidate_dashboard", cid=candidate.pk)
        return render(request, "agent/no_access.html")
    today = timezone.localdate()
    candidates = Candidate.objects.annotate(
        jobs_today=Count("jobs", filter=Q(jobs__found_at__date=today), distinct=True),
        suggested=Count("jobs", filter=Q(jobs__status="suggested"), distinct=True),
        applied=Count("applications", filter=Q(applications__status__in=["applied", "interview", "offer", "rejected"]), distinct=True),
        interviews=Count("applications", filter=Q(applications__status="interview"), distinct=True),
    )
    totals = {
        "users": candidates.count(),
        "jobs_today": Job.objects.filter(found_at__date=today).count(),
        "applied": Application.objects.filter(status__in=["applied", "interview", "offer", "rejected"]).count(),
        "interviews": Application.objects.filter(status="interview").count(),
    }
    return render(request, "agent/home.html", {"candidates": candidates, "totals": totals,
                                               "ai_on": services.claude_available(),
                                               "recent_log": AuditLog.objects.all()[:10]})


@admin_required
def candidate_new(request):
    form = CandidateCreateForm(request.POST or None)
    if request.method == "POST" and form.is_valid():
        d = form.cleaned_data
        with transaction.atomic():
            user = User.objects.create_user(d["username"], email=d["email"], password=d["password"],
                                            first_name=d["full_name"][:150])
            candidate = Candidate.objects.create(user=user, full_name=d["full_name"], email=d["email"],
                                                 phone=d["phone"], job_types=d["job_types"])
        AuditLog.log("user_created", f"Access given to {candidate.full_name} ({user.username})",
                     actor=request.user, candidate=candidate)
        messages.success(request, f"Access created for {candidate.full_name}. Next: upload their CVs.")
        return redirect("candidate_profile", cid=candidate.pk)
    return render(request, "agent/candidate_new.html", {"form": form})


@admin_required
def candidate_toggle_access(request, cid):
    candidate = get_object_or_404(Candidate, pk=cid)
    if request.method == "POST" and candidate.user_id != request.user.id:
        candidate.user.is_active = not candidate.user.is_active
        candidate.user.save(update_fields=["is_active"])
        state = "enabled" if candidate.user.is_active else "disabled"
        AuditLog.log(f"access_{state}", candidate.full_name, actor=request.user, candidate=candidate)
        messages.success(request, f"Login {state} for {candidate.full_name}.")
    return redirect("home")


@admin_required
def audit(request):
    return render(request, "agent/audit.html", {"logs": AuditLog.objects.select_related("actor", "candidate")[:300]})


# ------------------------------------------------------------------ candidate pages
@login_required
def candidate_dashboard(request, cid):
    candidate = get_candidate(request, cid)
    stats = candidate_stats(candidate)
    if request.method == "POST" and request.POST.get("action") == "insight":
        text = run_ai(request, "AI summary", services.daily_insight, candidate, stats)
        if text:
            candidate.last_insight, candidate.last_insight_at = text, timezone.now()
            candidate.save(update_fields=["last_insight", "last_insight_at"])
        return redirect("candidate_dashboard", cid=cid)
    ctx = {
        "c": candidate, "stats": stats, "search_form": SearchForm(),
        "top_jobs": candidate.jobs.filter(status="suggested").order_by("-match_score")[:8],
        "follow_ups": candidate.applications.filter(follow_up_date__lte=timezone.localdate())
                                            .exclude(status__in=CLOSED).select_related("job")[:8],
        "ai_on": services.claude_available(),
    }
    return render(request, "agent/dashboard.html", ctx)


@login_required
def candidate_profile(request, cid):
    candidate = get_candidate(request, cid)
    is_owner = candidate.user_id == request.user.id
    action = request.POST.get("action")
    pform = CandidateProfileForm(request.POST if action == "profile" else None, instance=candidate, is_owner=is_owner)
    cvform = CVForm(request.POST if action == "cv" else None, request.FILES if action == "cv" else None)
    if action == "profile" and pform.is_valid():
        pform.save()
        AuditLog.log("profile_updated", f"auto_mode={candidate.auto_mode} consent={candidate.auto_consent}",
                     actor=request.user, candidate=candidate)
        messages.success(request, "Profile saved.")
        return redirect("candidate_profile", cid=cid)
    if action == "cv" and cvform.is_valid():
        cv = cvform.save(commit=False)
        cv.candidate = candidate
        upload = cvform.cleaned_data.get("file")
        if upload:
            try:
                extracted = services.extract_text_from_upload(upload)
            except Exception as exc:
                extracted = ""
                messages.warning(request, f"Could not read the file text ({exc.__class__.__name__}). Please paste it.")
            cv.text = cv.text or extracted
            cv.uploaded_file = upload
        cv.save()
        AuditLog.log("cv_added", cv.title, actor=request.user, candidate=candidate)
        messages.success(request, f"CV '{cv.title}' saved. Check the text and edit if needed.")
        return redirect("cv_edit", cid=cid, pk=cv.pk)
    return render(request, "agent/profile.html", {"c": candidate, "pform": pform, "cvform": cvform,
                                                  "is_owner": is_owner})


@login_required
def cv_edit(request, cid, pk):
    candidate = get_candidate(request, cid)
    cv = get_object_or_404(CVDocument, pk=pk, candidate=candidate)
    form = CVForm(request.POST or None, instance=cv)
    if request.method == "POST" and form.is_valid():
        form.save()
        messages.success(request, "CV updated.")
        return redirect("candidate_profile", cid=cid)
    return render(request, "agent/cv_edit.html", {"c": candidate, "cv": cv, "form": form})


@login_required
def cv_delete(request, cid, pk):
    candidate = get_candidate(request, cid)
    cv = get_object_or_404(CVDocument, pk=pk, candidate=candidate)
    if request.method == "POST":
        AuditLog.log("cv_deleted", cv.title, actor=request.user, candidate=candidate)
        cv.delete()
        messages.success(request, "CV deleted.")
    return redirect("candidate_profile", cid=cid)


@login_required
def jobs(request, cid):
    candidate = get_candidate(request, cid)
    action = request.POST.get("action")
    if action == "search":
        form = SearchForm(request.POST)
        if form.is_valid():
            kws = [k.strip() for k in form.cleaned_data["keywords"].split(",") if k.strip()] or None
            report = run_ai(request, "Job search", workflow.run_search, candidate, kws, request.user)
            if report:
                messages.success(request, f"Search finished: {report['new_jobs']} new jobs, "
                                          f"{report['suggested']} AI suggested, {report['prepared']} applications prepared.")
                for note in report["notes"][:12]:
                    messages.info(request, note)
        return redirect("jobs", cid=cid)
    if action == "add_url":
        form = JobURLForm(request.POST)
        if form.is_valid():
            url = form.cleaned_data["url"]
            job, created = workflow.create_job(candidate, title="Untitled job", url=url, source="url",
                                               site=url.split("/")[2])
            if run_ai(request, "Reading the job page", workflow.fill_job_details, job):
                run_ai(request, "Scoring", workflow.score, job)
            return redirect("job_detail", cid=cid, pk=job.pk)
        messages.error(request, "Please enter a valid link.")
        return redirect("jobs", cid=cid)
    if action == "paste":
        form = JobPasteForm(request.POST)
        if form.is_valid():
            d = form.cleaned_data
            job, _ = workflow.create_job(candidate, title=d["title"], company=d["company"], url=d["url"],
                                         description=d["description"], source="paste")
            run_ai(request, "Scoring", workflow.score, job)
            return redirect("job_detail", cid=cid, pk=job.pk)
        messages.error(request, "Please fill in the job title and description.")
        return redirect("jobs", cid=cid)

    status = request.GET.get("status", "")
    qs = candidate.jobs.select_related("application")
    if status:
        qs = qs.filter(status=status)
    ctx = {"c": candidate, "jobs": qs.order_by("-found_at")[:300], "status": status, "statuses": Job.STATUSES,
           "search_form": SearchForm(), "url_form": JobURLForm(), "paste_form": JobPasteForm()}
    return render(request, "agent/jobs.html", ctx)


@login_required
def job_detail(request, cid, pk):
    candidate = get_candidate(request, cid)
    job = get_object_or_404(Job, pk=pk, candidate=candidate)
    app = getattr(job, "application", None)
    action = request.POST.get("action")
    if action == "rescore":
        run_ai(request, "Reading the job page", workflow.fill_job_details, job)
        if run_ai(request, "Scoring", workflow.score, job):
            messages.success(request, f"Match score: {job.match_score}")
    elif action == "generate":
        if run_ai(request, "Creating CV and cover letter", workflow.prepare_application, job, request.user):
            messages.success(request, "Tailored CV, cover letter and email are ready below. Please review them.")
    elif action == "interview":
        if app is None:
            app = Application.objects.create(candidate=candidate, job=job)
        text = run_ai(request, "Interview preparation", services.interview_prep, candidate, job)
        if text:
            app.interview_prep = text
            app.save(update_fields=["interview_prep"])
    elif action == "status":
        new = request.POST.get("status")
        if new in dict(Job.STATUSES):
            job.status = new
            job.save(update_fields=["status"])
    elif action == "applied" and app:
        today = timezone.localdate()
        app.status, app.applied_at = "applied", app.applied_at or today
        app.follow_up_date = app.follow_up_date or today + timedelta(days=7)
        app.save()
        job.status = "applied"
        job.save(update_fields=["status"])
        AuditLog.log("marked_applied", str(job), actor=request.user, candidate=candidate)
        messages.success(request, "Recorded as applied. A follow-up reminder is set for 7 days.")
    elif action == "save_app" and app:
        form = ApplicationForm(request.POST, instance=app)
        if form.is_valid():
            form.save()
            messages.success(request, "Application saved.")
        else:
            messages.error(request, "Please check the form.")
    if action:
        return redirect("job_detail", cid=cid, pk=pk)
    app = getattr(job, "application", None)
    ctx = {"c": candidate, "job": job, "app": app, "app_form": ApplicationForm(instance=app) if app else None,
           "statuses": Job.STATUSES, "questions": job.questions.filter(answer="")}
    return render(request, "agent/job_detail.html", ctx)


@login_required
def applications(request, cid):
    candidate = get_candidate(request, cid)
    if request.method == "POST":
        app = get_object_or_404(Application, pk=request.POST.get("app_id"), candidate=candidate)
        new = request.POST.get("status")
        if new in dict(Application.STATUSES):
            app.status = new
            if new == "applied" and not app.applied_at:
                app.applied_at = timezone.localdate()
            app.save()
        return redirect("applications", cid=cid)
    apps = candidate.applications.select_related("job")
    return render(request, "agent/applications.html", {"c": candidate, "apps": apps,
                                                       "statuses": Application.STATUSES})


@login_required
def download_docx(request, cid, pk, kind):
    candidate = get_candidate(request, cid)
    app = get_object_or_404(Application, pk=pk, candidate=candidate)
    fields = {"cv": ("cv_text", "CV"), "cover-letter": ("cover_letter", "Cover Letter"),
              "interview": ("interview_prep", "Interview Preparation")}
    if kind not in fields:
        raise PermissionDenied
    field, label = fields[kind]
    heading = candidate.full_name if kind == "cv" else ""
    data = services.make_docx(getattr(app, field), heading=heading if not getattr(app, field).startswith(candidate.full_name) else "")
    name = slugify(f"{candidate.full_name} {label} {app.job.company or app.job.title}")[:80]
    resp = HttpResponse(data, content_type="application/vnd.openxmlformats-officedocument.wordprocessingml.document")
    resp["Content-Disposition"] = f'attachment; filename="{name}.docx"'
    return resp


@login_required
def questions(request, cid):
    candidate = get_candidate(request, cid)
    if request.method == "POST":
        q = get_object_or_404(AIQuestion, pk=request.POST.get("qid"), candidate=candidate)
        if request.POST.get("delete"):
            q.delete()
        else:
            q.answer = request.POST.get("answer", "").strip()
            q.save(update_fields=["answer"])
            messages.success(request, "Thanks - the AI will use this answer in future CVs.")
        return redirect("questions", cid=cid)
    return render(request, "agent/questions.html", {"c": candidate, "questions": candidate.questions.all()})

"""views.py - The Knowledge Base pages (Ask, Manage) and "make a CV for a job". The data comes from kb.api."""

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.shortcuts import redirect, render
from django.views.decorators.http import require_POST

from agent import workflow
from agent.views import get_candidate

from .services import KBError, prepare_application_from_kb


@login_required
def ask(request, cid):
    """Ask a question about your own documents (and the shared job-search tips)."""
    candidate = get_candidate(request, cid)
    return render(request, "kb/ask.html", {"c": candidate, "active": "kb"})


@login_required
def manage(request, cid):
    """Upload, list and delete documents (CVs too), make a CV for a job, practice interview questions.
    Admin also: shared documents, AI model."""
    candidate = get_candidate(request, cid)
    jobs = candidate.jobs.exclude(status__in=["skipped", "closed"]).order_by("-found_at")[:50]
    return render(request, "kb/manage.html",
                  {"c": candidate, "active": "kb", "is_admin": request.user.is_staff, "jobs": jobs,
                   "cv_count": candidate.cvs.count()})


@login_required
@require_POST
def tailor(request, cid):
    """Make a CV, cover letter and email for one job from this person's knowledge base.
    Either pick a saved job, or paste a new job advert (it is saved as a job so it shows in the tracker)."""
    candidate = get_candidate(request, cid)
    job_id = request.POST.get("job_id", "").strip()
    if job_id:
        job = candidate.jobs.filter(pk=job_id).first()
        if job is None:
            messages.error(request, "Please choose one of your jobs.")
            return redirect("kb:manage", cid=cid)
    else:
        title = request.POST.get("title", "").strip()[:255]
        description = request.POST.get("description", "").strip()[:15000]
        if not title or len(description) < 30:
            messages.error(request, "Please type the job title and paste the job advert (or choose a saved job).")
            return redirect("kb:manage", cid=cid)
        job, _ = workflow.create_job(candidate, title=title, company=request.POST.get("company", "").strip()[:255],
                                     url=request.POST.get("url", "").strip()[:1000], description=description,
                                     source="paste", site="Knowledge base")
    try:
        prepare_application_from_kb(job, actor=request.user)
    except KBError as exc:
        messages.error(request, str(exc))
        return redirect("job_detail", cid=cid, pk=job.pk) if job_id else redirect("kb:manage", cid=cid)
    messages.success(request, "Your new CV, cover letter and email are ready below. Read and check them, then "
                              "download PDF or Word. Replace any [ADD: ...] notes with true information.")
    return redirect("job_detail", cid=cid, pk=job.pk)

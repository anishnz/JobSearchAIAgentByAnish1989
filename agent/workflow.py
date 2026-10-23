"""Steps that combine services and the database. Used by the web pages and the daily scheduler."""
import logging
import time

from django.db import IntegrityError
from django.utils import timezone

from . import services
from .models import AIQuestion, Application, AuditLog, Job

log = logging.getLogger(__name__)
MAX_JOBS_SCORED_PER_RUN = 10  # keeps Claude costs and website load small


def add_questions(candidate, job, questions):
    for q in questions:
        text = f"Question for {candidate.full_name}: {q.strip()}"
        if not candidate.questions.filter(question=text).exists():
            AIQuestion.objects.create(candidate=candidate, job=job, question=text)


def create_job(candidate, *, title, url="", description="", company="", source="paste", site=""):
    """Create a job for this candidate unless it already exists. Returns (job, created)."""
    fp = services.fingerprint(title, company, url)
    existing = Job.objects.filter(candidate=candidate, fingerprint=fp).first()
    if existing:
        return existing, False
    try:
        job = Job.objects.create(candidate=candidate, title=title[:255] or "Untitled job", url=url,
                                 description=description, company=company[:255], source=source,
                                 site=site, fingerprint=fp)
        return job, True
    except IntegrityError:
        return Job.objects.get(candidate=candidate, fingerprint=fp), False


def fill_job_details(job):
    """Download the job page text if we only have a link."""
    if job.url and len(job.description) < 200:
        page_title, text, _ = services.fetch_page(job.url)
        job.description = text
        if not job.title or job.title == "Untitled job":
            job.title = page_title[:255]
        job.save(update_fields=["description", "title"])
    return job


def score(job):
    candidate = job.candidate
    value, reason, questions = services.score_job(candidate, job)
    job.match_score = value
    job.match_reason = reason
    if job.status == "new" and value >= candidate.min_match_score:
        job.status = "suggested"
    job.save(update_fields=["match_score", "match_reason", "status"])
    add_questions(candidate, job, questions)
    return job


def prepare_application(job, actor=None, status="draft"):
    candidate = job.candidate
    docs = services.generate_documents(candidate, job)
    app, _ = Application.objects.update_or_create(
        job=job, defaults={"candidate": candidate, "cv_text": docs["cv"],
                           "cover_letter": docs["cover_letter"], "email_draft": docs["email"]})
    if app.status == "draft" and status != "draft":
        app.status = status
        app.save(update_fields=["status"])
    AuditLog.log("documents_generated", f"{job}", actor=actor, candidate=candidate)
    return app


def run_search(candidate, keywords=None, actor=None):
    """Search job sites for one candidate, save new jobs, score them, auto-prepare if allowed."""
    keywords = keywords or candidate.keyword_list()
    report = {"new_jobs": 0, "scored": 0, "suggested": 0, "prepared": 0, "notes": []}
    if not keywords:
        report["notes"].append("No job types set. Add job types in the profile page first.")
        return report

    new_jobs = []
    for kw in keywords:
        results, notes = services.search_job_sites(kw)
        report["notes"].extend(notes)
        for r in results:
            job, created = create_job(candidate, title=r["title"], url=r["url"], source="crawl", site=r["site"])
            if created:
                new_jobs.append(job)
    report["new_jobs"] = len(new_jobs)

    for job in new_jobs[:MAX_JOBS_SCORED_PER_RUN]:
        try:
            fill_job_details(job)
            time.sleep(services.REQUEST_DELAY_SECONDS)
            score(job)
            report["scored"] += 1
            if job.status == "suggested":
                report["suggested"] += 1
                if candidate.auto_enabled and not hasattr(job, "application"):
                    target = "ready" if candidate.auto_mode == candidate.MODE_AUTO else "draft"
                    prepare_application(job, actor=actor, status=target)
                    report["prepared"] += 1
        except PermissionError as exc:
            report["notes"].append(str(exc))
        except Exception as exc:  # report, never lose the run
            log.exception("Job processing failed")
            report["notes"].append(f"Could not process '{job.title}': {exc.__class__.__name__}")

    candidate.last_search_at = timezone.now()
    candidate.save(update_fields=["last_search_at"])
    AuditLog.log("job_search", f"keywords={keywords} result={ {k: v for k, v in report.items() if k != 'notes'} }",
                 actor=actor, candidate=candidate)
    return report

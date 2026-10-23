from django.core.management.base import BaseCommand

from agent.models import AuditLog, Candidate
from agent.workflow import run_search


class Command(BaseCommand):
    help = "Run the job search now for every active candidate (each person's data stays separate)."

    def handle(self, *args, **options):
        for candidate in Candidate.objects.filter(is_active=True):
            self.stdout.write(f"Searching for {candidate.full_name} ...")
            try:
                report = run_search(candidate)
                self.stdout.write(f"  new={report['new_jobs']} suggested={report['suggested']} "
                                  f"prepared={report['prepared']}")
            except Exception as exc:
                AuditLog.log("job_search_failed", repr(exc), candidate=candidate)
                self.stderr.write(f"  failed: {exc!r}")

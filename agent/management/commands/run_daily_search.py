from django.conf import settings
from django.core.management.base import BaseCommand
from django.utils import timezone

from agent.models import AuditLog, Candidate, SystemSettings
from agent.services import week_xlsx
from agent.workflow import run_search


class Command(BaseCommand):
    help = "Run the job search now for every active, not-paused user (each person's data stays separate)."

    def handle(self, *args, **options):
        lines = []
        qs = Candidate.objects.filter(is_active=True, search_paused=False, user__is_active=True)
        for candidate in qs:
            self.stdout.write(f"Searching for {candidate.full_name} ...")
            try:
                report = run_search(candidate)
                line = (f"{candidate.full_name}: new={report['new_jobs']} suggested={report['suggested']} "
                        f"prepared={report['prepared']}")
            except Exception as exc:
                AuditLog.log("job_search_failed", repr(exc), candidate=candidate)
                line = f"{candidate.full_name}: failed ({exc.__class__.__name__})"
            try:  # offline copy of the last 7 days (Excel), one file per person
                out = settings.DATA_DIR / "exports" / candidate.slug
                out.mkdir(parents=True, exist_ok=True)
                (out / f"jobs-{timezone.localdate():%Y-%m-%d}.xlsx").write_bytes(week_xlsx(candidate))
            except Exception as exc:
                AuditLog.log("export_failed", repr(exc), candidate=candidate)
            lines.append(line)
            self.stdout.write("  " + line)
        s = SystemSettings.load()
        s.last_daily_run = timezone.now()
        s.last_daily_result = "\n".join(lines) or "No active users."
        s.save(update_fields=["last_daily_run", "last_daily_result"])

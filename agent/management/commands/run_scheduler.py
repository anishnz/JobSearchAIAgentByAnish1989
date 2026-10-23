"""Simple, reliable scheduler: runs the daily search at 8:00 AM Auckland time (configurable)."""
import time
from datetime import timedelta

from django.conf import settings
from django.core.management import call_command
from django.core.management.base import BaseCommand
from django.utils import timezone

from agent.models import SystemSettings


def next_run_after(now, hour, minute):
    target = now.replace(hour=hour, minute=minute, second=0, microsecond=0)
    if target <= now:
        target = target + timedelta(days=1)
        target = target.replace(hour=hour, minute=minute)  # keeps local time across daylight saving
    return target


class Command(BaseCommand):
    help = "Keep running and start the job search every day at the configured Auckland time."

    def handle(self, *args, **options):
        hour, minute = settings.DAILY_SEARCH_HOUR, settings.DAILY_SEARCH_MINUTE
        while True:
            now = timezone.localtime()
            target = next_run_after(now, hour, minute)
            self.stdout.write(f"[scheduler] now {now:%Y-%m-%d %H:%M %Z}; next search {target:%Y-%m-%d %H:%M %Z}",
                              ending="\n")
            while timezone.localtime() < target:
                SystemSettings.objects.update_or_create(pk=1, defaults={"scheduler_heartbeat": timezone.now()})
                time.sleep(min(60, max(1, (target - timezone.localtime()).total_seconds())))
            call_command("run_daily_search")

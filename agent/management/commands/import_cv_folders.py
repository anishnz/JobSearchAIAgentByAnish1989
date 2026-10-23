"""Import CVs from data/import/<login name>/ for each person (used by import_cvs.bat)."""
from pathlib import Path

from django.conf import settings
from django.contrib.auth.models import User
from django.core.management import call_command
from django.core.management.base import BaseCommand


class Command(BaseCommand):
    help = "For every folder data/import/<login name>/, import its CVs into that person's account."

    def handle(self, *args, **options):
        root = Path(settings.DATA_DIR) / "import"
        root.mkdir(parents=True, exist_ok=True)
        folders = [d for d in sorted(root.iterdir()) if d.is_dir()]
        if not folders:
            self.stdout.write("No folders in data\\import. Make a folder named after the login name and put CVs in it.")
        for d in folders:
            if not User.objects.filter(username=d.name).exists():
                self.stdout.write(f"Skipped '{d.name}': no login with that name.")
                continue
            call_command("setup_candidate", username=d.name, cv_folder=str(d), stdout=self.stdout)

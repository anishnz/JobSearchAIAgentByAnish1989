"""Create or update one person's account and import their CVs from a folder.

Example (run from the project folder):
  python manage.py setup_candidate --username anish --full-name "Anish Shrestha" \
      --email you@example.com --admin --cv-folder "D:/path/Job Positions"
Each CV is imported into THIS person's profile only.
"""
import re
from pathlib import Path

from django.contrib.auth.models import User
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction

from agent.models import AuditLog, Candidate, CVDocument


def read_cv_file(path):
    if path.suffix.lower() == ".docx":
        import docx

        return "\n".join(p.text for p in docx.Document(str(path)).paragraphs).strip()
    if path.suffix.lower() == ".pdf":
        from pypdf import PdfReader

        return "\n".join((p.extract_text() or "") for p in PdfReader(str(path)).pages).strip()
    return path.read_text(encoding="utf-8", errors="ignore").strip()


def clean_name(folder_name):
    return re.sub(r"^\d+\s*", "", folder_name).strip()


NAME_WORDS = []  # the person's own name words, removed from titles (set per import)


def clean_stem(stem):
    """'3e6fc2ce-Saru_Front_of_House' and 'Saru_Front_of_House' -> same key."""
    stem = re.sub(r"^[0-9a-f]{8}-", "", stem)
    return re.sub(r"[_\s-]+", " ", stem).strip().lower()


def nice_title(stem, drop=""):
    t = clean_stem(stem)
    words = ["cv of", "cv", drop] + [w for w in NAME_WORDS if w]
    for word in words:
        if word:
            t = re.sub(rf"\b{re.escape(word)}\b", " ", t)
    t = re.sub(r"\s+\d+$", "", re.sub(r"\s+", " ", t).strip())
    return t.title()


def fill_blank_profile(candidate, text):
    """Fill only EMPTY profile fields from the CV (never overwrite what the person typed)."""
    from agent.services import basic_cv_analysis

    data = basic_cv_analysis(text)
    for field, key in [("phone", "phone"), ("email", "email"), ("education", "education"),
                       ("experience_summary", "experience"), ("skills", "skills")]:
        if not getattr(candidate, field) and data.get(key):
            setattr(candidate, field, data[key])
    if not candidate.job_types:
        candidate.job_types = ", ".join(data["suggested_job_types"])
    candidate.onboarding_done = True
    candidate.save()


def load_index(folder):
    """Read an optional CV_Index.xlsx ('All CVs' sheet) -> {folder name: row dict}."""
    index_file = next(iter(folder.glob("CV_Index.xlsx")), None)
    if not index_file:
        return {}
    import openpyxl

    wb = openpyxl.load_workbook(index_file, data_only=True)
    ws = wb["All CVs"] if "All CVs" in wb.sheetnames else wb.worksheets[-1]
    rows = list(ws.iter_rows(values_only=True))
    if not rows:
        return {}
    header = [str(h or "").strip() for h in rows[0]]
    result = {}
    for r in rows[1:]:
        row = dict(zip(header, r))
        folder_col = str(row.get("Folder (in D:\\JobSearchAgent)") or row.get("Folder") or "")
        if folder_col:
            result[re.split(r"[\\/]", folder_col.rstrip("\\/"))[-1].lower()] = row
    return result


class Command(BaseCommand):
    help = "Create/update a person's login and profile, and import their CV files (.docx, .pdf, .txt)."

    def add_arguments(self, p):
        p.add_argument("--username", required=True)
        p.add_argument("--full-name", default="", help="Needed only when creating a new person.")
        p.add_argument("--email", default="")
        p.add_argument("--phone", default="")
        p.add_argument("--location", default="Auckland")
        p.add_argument("--job-types", default="", help="Comma separated job types for the daily search.")
        p.add_argument("--availability", default="")
        p.add_argument("--notes", default="", help="Extra true facts for the AI.")
        p.add_argument("--admin", action="store_true", help="Make this login an admin.")
        p.add_argument("--cv-folder", help="Folder with CV files (searched in sub-folders too).")

    @transaction.atomic
    def handle(self, *args, **o):
        if not User.objects.filter(username=o["username"]).exists() and not o["full_name"]:
            raise CommandError("New person: please give --full-name.")
        user, created = User.objects.get_or_create(username=o["username"], defaults={"email": o["email"]})
        if created:
            user.set_unusable_password()
            self.stdout.write(f"Created login '{user.username}' (set a password with set_password.bat).")
        user.email = o["email"] or user.email
        user.first_name = (o["full_name"] or user.first_name)[:150]
        if o["admin"]:
            user.is_staff = user.is_superuser = True
        user.save()

        candidate, _ = Candidate.objects.get_or_create(user=user, defaults={"full_name": o["full_name"] or user.username})
        if "_" in candidate.full_name:
            candidate.full_name = candidate.full_name.replace("_", " ")
        for field, key in [("full_name", "full_name"), ("email", "email"), ("phone", "phone"),
                           ("location", "location"), ("job_types", "job_types"),
                           ("availability", "availability"), ("extra_notes", "notes")]:
            if o[key]:
                setattr(candidate, field, o[key])
        candidate.save()

        imported = 0
        if o.get("cv_folder"):
            folder = Path(o["cv_folder"])
            if not folder.is_dir():
                raise CommandError(f"Folder not found: {folder}")
            index = load_index(folder)
            files = sorted(folder.rglob("*.docx")) + sorted(folder.rglob("*.pdf")) + sorted(folder.rglob("*.txt"))
            seen_text, seen_stems = set(), set()
            per_dir = {}
            for f in files:
                per_dir.setdefault(f.parent, []).append(f)
            main_text = ""
            used_titles = set()
            NAME_WORDS[:] = [w.lower() for w in re.split(r"[\s_]+", candidate.full_name) if len(w) > 1]
            for f in files:
                stem_key = (f.parent, clean_stem(f.stem))
                if f.name.startswith("~$") or stem_key in seen_stems:
                    continue  # same document as Word and PDF: keep the Word file
                text = read_cv_file(f)
                norm = re.sub(r"\s+", " ", text).strip().lower()
                if len(text) < 100 or norm in seen_text:
                    continue  # empty or an exact duplicate
                seen_stems.add(stem_key)
                seen_text.add(norm)
                is_cover = "cover" in f.stem.lower() or norm.startswith(("dear ", "to the hiring"))
                row = index.get(f.parent.name.lower(), {})
                if row and len(per_dir[f.parent]) <= 2:
                    title = str(row.get("Job Position")) + " CV"
                elif is_cover:
                    title = "Cover letter - " + (nice_title(f.stem, drop="cover letter") or "General")
                else:
                    folder_name = clean_name(f.parent.name) if f.parent != folder else ""
                    title = (nice_title(f.stem) or folder_name or "My") + " CV"
                base, n = title, 2
                while title in used_titles:
                    title, n = f"{base} ({n})", n + 1
                used_titles.add(title)
                parts = f.relative_to(folder).parts
                category = ("Cover letter sample" if is_cover else
                            str(row.get("Category") or (clean_name(parts[-3]) if len(parts) >= 3 else "")))
                CVDocument.objects.update_or_create(
                    candidate=candidate, title=title[:120],
                    defaults={"text": text, "category": category[:120],
                              "best_for": str(row.get("Best For") or "")[:255],
                              "source_path": str(f.relative_to(folder))[:500]})
                imported += 1
                if not is_cover and len(text) > len(main_text):
                    main_text = text
            if main_text:
                fill_blank_profile(candidate, main_text)
        AuditLog.log("candidate_setup", f"{candidate.full_name}: {imported} CVs imported", candidate=candidate)
        self.stdout.write(self.style.SUCCESS(
            f"{candidate.full_name}: profile saved, {imported} CVs imported, {candidate.cvs.count()} CVs in total."))

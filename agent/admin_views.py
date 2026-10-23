"""Super admin pages: users and access, system settings, system health, audit log."""
import platform
import shutil
import sqlite3
import time

import django
import requests
from django.conf import settings
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.contrib.auth.models import User
from django.core.exceptions import PermissionDenied
from django.db import connection, transaction
from django.db.models import Count, Q
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone

from . import services
from .forms import AdminUserForm, CandidateCreateForm, SystemSettingsForm
from .models import Application, AuditLog, Candidate, Job, SystemSettings
from .views import personal_links


def admin_required(view):
    @login_required
    def wrapper(request, *args, **kwargs):
        if not request.user.is_staff:
            raise PermissionDenied
        return view(request, *args, **kwargs)
    return wrapper


def quick_health():
    s = SystemSettings.load()
    beat = s.scheduler_heartbeat
    scheduler_ok = bool(beat and (timezone.now() - beat).total_seconds() < 300)
    return {"scheduler_ok": scheduler_ok, "email_ok": s.email_ready, "settings": s}


@admin_required
def manage_home(request):
    today = timezone.localdate()
    candidates = Candidate.objects.select_related("user").annotate(
        jobs_today=Count("jobs", filter=Q(jobs__found_at__date=today), distinct=True),
        suggested=Count("jobs", filter=Q(jobs__status="suggested"), distinct=True),
        applied=Count("applications", filter=Q(applications__status__in=["applied", "interview", "offer", "rejected"]), distinct=True),
        interviews=Count("applications", filter=Q(applications__status="interview"), distinct=True),
        cv_count=Count("cvs", distinct=True),
    )
    rows = [(c, personal_links(request, c)) for c in candidates]
    totals = {
        "users": candidates.count(),
        "jobs_today": Job.objects.filter(found_at__date=today).count(),
        "applied": Application.objects.filter(status__in=["applied", "interview", "offer", "rejected"]).count(),
        "interviews": Application.objects.filter(status="interview").count(),
    }
    return render(request, "agent/manage/home.html", {"rows": rows, "totals": totals, "health": quick_health(),
                                                      "recent_log": AuditLog.objects.select_related("actor", "candidate")[:8],
                                                      "active": "manage"})


@admin_required
def manage_user_new(request):
    form = CandidateCreateForm(request.POST or None)
    if request.method == "POST" and form.is_valid():
        d = form.cleaned_data
        with transaction.atomic():
            user = User.objects.create_user(d["username"], email=d["email"], password=d["password"],
                                            first_name=d["full_name"][:150])
            candidate = Candidate(user=user, full_name=d["full_name"], email=d["email"], slug=d["slug"] or None)
            candidate.save()
        AuditLog.log("user_created", f"Access given to {candidate.full_name} ({user.username})",
                     actor=request.user, candidate=candidate)
        links = personal_links(request, candidate)
        messages.success(request, f"Access created for {candidate.full_name}. Their link: {links['laptop']} "
                                  f"- on first login they will upload their CV.")
        return redirect("manage_home")
    return render(request, "agent/manage/user_new.html", {"form": form, "active": "manage"})


@admin_required
def manage_user_edit(request, cid):
    candidate = get_object_or_404(Candidate.objects.select_related("user"), pk=cid)
    form = AdminUserForm(request.POST or None, instance=candidate)
    if request.method == "POST" and form.is_valid():
        c = form.save()
        user = c.user
        if user.id != request.user.id:  # never lock yourself out
            user.is_active = form.cleaned_data["login_enabled"]
        if form.cleaned_data["new_password"]:
            user.set_password(form.cleaned_data["new_password"])
            AuditLog.log("password_reset_by_admin", c.full_name, actor=request.user, candidate=c)
        user.email = c.email or user.email
        user.save()
        AuditLog.log("user_access_updated",
                     f"login={user.is_active} ai={c.ai_allowed} email={c.email_allowed} auto={c.auto_allowed}",
                     actor=request.user, candidate=c)
        messages.success(request, f"Saved access settings for {c.full_name}.")
        return redirect("manage_home")
    return render(request, "agent/manage/user_edit.html", {
        "form": form, "c": candidate, "links": personal_links(request, candidate),
        "has_ai_key": bool(candidate.ai_key_enc), "has_gmail": candidate.gmail_ready, "active": "manage"})


@admin_required
def manage_settings(request):
    s = SystemSettings.load()
    form = SystemSettingsForm(request.POST or None, instance=s)
    action = request.POST.get("action")
    if request.method == "POST" and action == "save" and form.is_valid():
        obj = form.save(commit=False)
        if form.cleaned_data["gmail_app_password"]:
            obj.gmail_app_password = form.cleaned_data["gmail_app_password"]
        obj.save()
        AuditLog.log("system_settings_saved", "", actor=request.user)
        messages.success(request, "System settings saved.")
        return redirect("manage_settings")
    if request.method == "POST" and action == "test":
        if not s.email_ready:
            messages.error(request, "Save the Gmail address and App Password first.")
        else:
            ok, msg = services.test_gmail(s.gmail_address, s.gmail_app_password)
            (messages.success if ok else messages.error)(request, msg)
        return redirect("manage_settings")
    return render(request, "agent/manage/settings.html", {"form": form, "s": s, "active": "manage_settings"})


def _check(name, ok, detail):
    return {"name": name, "ok": ok, "detail": detail}


@admin_required
def manage_health(request):
    s = SystemSettings.load()
    checks = []
    # Database
    try:
        with connection.cursor() as cur:
            cur.execute("SELECT 1")
        db_file = settings.DATABASES["default"]["NAME"]
        size_mb = db_file.stat().st_size / 1e6 if hasattr(db_file, "stat") and db_file.exists() else 0
        integrity = sqlite3.connect(str(db_file)).execute("PRAGMA quick_check").fetchone()[0]
        checks.append(_check("Database", integrity == "ok", f"Working, {size_mb:.1f} MB, check: {integrity}"))
    except Exception as exc:
        checks.append(_check("Database", False, f"Problem: {exc.__class__.__name__}"))
    # Scheduler
    beat = s.scheduler_heartbeat
    if beat:
        age = int((timezone.now() - beat).total_seconds() / 60)
        checks.append(_check("Daily search scheduler", age < 5,
                             f"Last signal {age} min ago" + ("" if age < 5 else " - run start.bat to restart it")))
    else:
        checks.append(_check("Daily search scheduler", False, "No signal yet - is the scheduler container running?"))
    run = s.last_daily_run
    checks.append(_check("Last daily search", bool(run),
                         timezone.localtime(run).strftime("%d %b %Y %H:%M") if run else "Not run yet"))
    # Disk
    usage = shutil.disk_usage(settings.DATA_DIR)
    free_gb = usage.free / 1e9
    checks.append(_check("Disk space", free_gb > 2, f"{free_gb:.1f} GB free"))
    # Email + AI
    checks.append(_check("System email (forgot password)", s.email_ready,
                         s.gmail_address or "Not set up - Admin > System settings"))
    with_key = sum(1 for c in Candidate.objects.all() if c.ai_key_enc and c.ai_allowed)
    checks.append(_check("AI keys", True, f"{with_key} user(s) have their own Claude key; others use free basic mode"))
    # Job websites (on request, takes a few seconds)
    sites = []
    if request.method == "POST" and request.POST.get("action") == "sites":
        for src in services.SEARCH_SOURCES:
            url = src["url"].format(slug="kitchen-hand", q="kitchen+hand")
            t0 = time.time()
            try:
                allowed = services.allowed_by_robots(url)
                r = requests.get(url, headers={"User-Agent": services.USER_AGENT}, timeout=12) if allowed else None
                sites.append(_check(src["site"], bool(r is not None and r.status_code == 200),
                                    ("Blocked by the site's rules (robots.txt)" if not allowed
                                     else f"HTTP {r.status_code} in {time.time() - t0:.1f}s")))
            except requests.RequestException as exc:
                sites.append(_check(src["site"], False, f"Not reachable ({exc.__class__.__name__})"))
    errors = AuditLog.objects.filter(action__icontains="fail")[:10]
    info = {"Python": platform.python_version(), "Django": django.get_version(),
            "Server time": timezone.localtime().strftime("%d %b %Y %H:%M %Z"),
            "Users": Candidate.objects.count(), "Jobs": Job.objects.count(),
            "Applications": Application.objects.count()}
    return render(request, "agent/manage/health.html", {"checks": checks, "sites": sites, "errors": errors,
                                                        "info": info, "s": s, "active": "manage_health"})


@admin_required
def manage_audit(request):
    return render(request, "agent/manage/audit.html",
                  {"logs": AuditLog.objects.select_related("actor", "candidate")[:300], "active": "manage_audit"})

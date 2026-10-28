from datetime import datetime
from zoneinfo import ZoneInfo

from django.contrib.auth.models import User
from django.test import TestCase

from agent.management.commands.run_scheduler import next_run_after
from agent.models import Candidate, CVDocument, Job
from agent.services import fingerprint, keyword_score

AKL = ZoneInfo("Pacific/Auckland")


class SchedulerTests(TestCase):
    def test_next_run_same_day(self):
        now = datetime(2026, 10, 23, 7, 0, tzinfo=AKL)
        self.assertEqual(next_run_after(now, 8, 0).hour, 8)
        self.assertEqual(next_run_after(now, 8, 0).day, 23)

    def test_next_run_tomorrow(self):
        now = datetime(2026, 10, 23, 9, 0, tzinfo=AKL)
        self.assertEqual(next_run_after(now, 8, 0).day, 24)


class SeparationTests(TestCase):
    def setUp(self):
        self.a = Candidate.objects.create(user=User.objects.create_user("a", password="x"), full_name="A",
                                          job_types="kitchen hand")
        self.b = Candidate.objects.create(user=User.objects.create_user("b", password="x"), full_name="B")
        CVDocument.objects.create(candidate=self.a, title="A CV", text="kitchen hand dishwashing")
        CVDocument.objects.create(candidate=self.b, title="B CV", text="nurse aide")

    def test_cv_text_never_mixes(self):
        self.assertNotIn("nurse", self.a.all_cv_text())
        self.assertNotIn("kitchen", self.b.all_cv_text())

    def test_user_cannot_open_other_candidate(self):
        self.client.login(username="a", password="x")
        self.assertEqual(self.client.get(f"/c/{self.b.pk}/").status_code, 403)
        self.assertEqual(self.client.get(f"/c/{self.b.pk}/settings/").status_code, 403)
        self.assertEqual(self.client.get(f"/c/{self.a.pk}/jobs/").status_code, 200)

    def test_keyword_score_and_fingerprint(self):
        job = Job.objects.create(candidate=self.a, title="Kitchen Hand", description="dishwashing kitchen",
                                 fingerprint=fingerprint("Kitchen Hand"))
        score, _ = keyword_score(self.a, job)
        self.assertGreater(score, 30)
        self.assertEqual(fingerprint("x", url="https://a.nz/job/1?x=1"), fingerprint("y", url="https://a.nz/job/1"))


class PageTests(TestCase):
    def setUp(self):
        self.admin = User.objects.create_superuser("admin", password="x")
        self.c = Candidate.objects.create(user=User.objects.create_user("saru", password="x"), full_name="Saru",
                                          job_types="retail assistant", onboarding_done=True)
        CVDocument.objects.create(candidate=self.c, title="Retail CV", text="Retail assistant, customer service")

    def _pages(self):
        cid = self.c.pk
        return [f"/c/{cid}/", f"/c/{cid}/profile/", f"/c/{cid}/jobs/", f"/c/{cid}/applications/",
                f"/c/{cid}/questions/", f"/c/{cid}/cv/{self.c.cvs.first().pk}/", f"/c/{cid}/settings/", "/help/"]

    def test_all_pages_for_user_and_admin(self):
        self.client.login(username="saru", password="x")
        for url in self._pages():
            self.assertEqual(self.client.get(url).status_code, 200, url)
        self.assertEqual(self.client.get("/manage/").status_code, 403)
        self.client.login(username="admin", password="x")
        for url in self._pages() + ["/manage/", "/manage/users/new/", "/manage/audit/", "/manage/health/",
                                    "/manage/settings/", f"/manage/users/{self.c.pk}/"]:
            self.assertEqual(self.client.get(url).status_code, 200, url)
        self.assertRedirects(self.client.get("/"), "/home/", fetch_redirect_response=False)

    def test_paste_job_creates_application_and_docx(self):
        self.client.login(username="saru", password="x")
        r = self.client.post(f"/c/{self.c.pk}/jobs/", {"action": "paste", "title": "Retail Assistant",
                                                       "company": "Shop", "description": "customer service retail"})
        job = self.c.jobs.get()
        self.assertRedirects(r, f"/c/{self.c.pk}/jobs/{job.pk}/")
        self.client.post(f"/c/{self.c.pk}/jobs/{job.pk}/", {"action": "generate"})
        app = job.application
        r = self.client.get(f"/c/{self.c.pk}/applications/{app.pk}/cv.docx")
        self.assertEqual(r.status_code, 200)
        self.assertTrue(r.content.startswith(b"PK"))

    def test_admin_cannot_give_consent_for_user(self):
        self.client.login(username="admin", password="x")
        self.client.post(f"/c/{self.c.pk}/profile/", {"action": "profile", "full_name": "Saru", "location": "Auckland",
                                                      "min_match_score": 65, "auto_mode": "auto", "auto_consent": "on"})
        self.client.post(f"/c/{self.c.pk}/settings/", {"action": "save", "ai_key": "sk-ant-x"})
        self.c.refresh_from_db()
        self.assertFalse(self.c.auto_consent)


class CVImportAndSelectionTests(TestCase):
    def test_setup_candidate_imports_folder_and_picks_relevant_cv(self):
        import tempfile
        from pathlib import Path

        import docx
        from django.core.management import call_command

        from agent.services import relevant_cvs

        with tempfile.TemporaryDirectory() as tmp:
            for folder, text in [("01 Hospitality/01 Kitchen Hand", "Kitchen hand dishwashing food prep " * 10),
                                 ("02 IT/01 Software Engineer", "Software engineer Python Django Laravel " * 10)]:
                d = Path(tmp, "Group", folder)
                d.mkdir(parents=True)
                doc = docx.Document()
                doc.add_paragraph(text)
                doc.save(d / "cv.docx")
            call_command("setup_candidate", username="anish", full_name="Anish", admin=True, cv_folder=tmp)
        c = Candidate.objects.get(user__username="anish")
        self.assertTrue(c.user.is_superuser)
        self.assertEqual(c.cvs.count(), 2)
        job = Job.objects.create(candidate=c, title="Kitchen Hand", description="dishwashing",
                                 fingerprint=fingerprint("Kitchen Hand"))
        self.assertIn("Kitchen", relevant_cvs(c, job, n=1)[0].title)

    def test_help_page(self):
        User.objects.create_user("u", password="x")
        self.client.login(username="u", password="x")
        self.assertContains(self.client.get("/help/"), "Getting started")


class NewFeatureTests(TestCase):
    def setUp(self):
        self.admin = User.objects.create_superuser("boss", password="x", email="boss@example.com")
        self.u = User.objects.create_user("saru", password="pass12345", email="saru@example.com")
        self.c = Candidate.objects.create(user=self.u, full_name="Saru Tuitui")

    def test_slug_and_portal_links(self):
        self.assertEqual(self.c.slug, "sarucv")
        r = self.client.get("/", HTTP_HOST="sarucv.localhost:8010")
        self.assertContains(r, "Hi Saru")
        self.assertContains(self.client.get("/u/sarucv/"), "Hi Saru")
        self.assertContains(self.client.get("/"), "Log in")  # public front page

    def test_first_login_wizard_basic_mode(self):
        self.client.login(username="saru", password="pass12345")
        self.assertRedirects(self.client.get(f"/c/{self.c.pk}/"), f"/c/{self.c.pk}/welcome/")
        cv = ("SARU TUITUI\nAuckland | saru@example.com | 021 123 4567\nWORK EXPERIENCE\nCaregiver, aged care home, "
              "supporting residents\nRetail sales assistant at a shop\nEDUCATION\nNZ Certificate in Health and Wellbeing\n"
              "SKILLS\nCustomer service, caregiving, teamwork")
        r = self.client.post(f"/c/{self.c.pk}/welcome/", {"text": cv})
        self.assertRedirects(r, f"/c/{self.c.pk}/welcome/review/")
        r = self.client.get(f"/c/{self.c.pk}/welcome/review/")
        self.assertContains(r, "Caregiver / Support Worker")
        r = self.client.post(f"/c/{self.c.pk}/welcome/review/", {
            "full_name": "Saru Tuitui", "email": "saru@example.com", "phone": "021 123 4567", "location": "Auckland",
            "availability": "Weekdays", "education": "NZ Cert", "experience_summary": "Caregiver", "skills": "care",
            "job_choices": ["Caregiver / Support Worker", "Retail Assistant"], "more_jobs": "Cleaner"})
        self.assertRedirects(r, f"/c/{self.c.pk}/")
        self.c.refresh_from_db()
        self.assertTrue(self.c.onboarding_done)
        self.assertEqual(self.c.job_types, "Caregiver / Support Worker, Retail Assistant, Cleaner")

    def test_secrets_encrypted_and_pause(self):
        self.client.login(username="saru", password="pass12345")
        self.c.onboarding_done = True
        self.c.save()
        self.client.post(f"/c/{self.c.pk}/settings/", {"action": "save", "ai_key": "sk-ant-secret-123",
                                                       "gmail_address": "saru@gmail.com", "gmail_app_password": "abcd efgh ijkl mnop"})
        self.c.refresh_from_db()
        self.assertNotIn("secret", self.c.ai_key_enc)
        self.assertEqual(self.c.ai_key, "sk-ant-secret-123")
        self.assertEqual(self.c.gmail_app_password, "abcdefghijklmnop")
        self.client.post(f"/c/{self.c.pk}/", {"action": "pause"})
        self.c.refresh_from_db()
        self.assertTrue(self.c.search_paused)

    def test_admin_controls_access_and_password(self):
        self.client.login(username="boss", password="x")
        r = self.client.post(f"/manage/users/{self.c.pk}/", {
            "full_name": "Saru Tuitui", "email": "saru@example.com", "slug": "sarucv", "is_active": "on",
            "ai_allowed": "", "email_allowed": "on", "auto_allowed": "", "login_enabled": "", "new_password": "newpass999"})
        self.assertRedirects(r, "/manage/")
        self.u.refresh_from_db()
        self.c.refresh_from_db()
        self.assertFalse(self.u.is_active)
        self.assertFalse(self.c.ai_allowed)
        self.assertTrue(self.u.check_password("newpass999"))

    def test_admin_creates_user(self):
        self.client.login(username="boss", password="x")
        r = self.client.post("/manage/users/new/", {"full_name": "Ram Bahadur", "username": "ram",
                                                    "password": "ramram123", "email": "", "slug": ""})
        self.assertRedirects(r, "/manage/")
        self.assertEqual(Candidate.objects.get(user__username="ram").slug, "ramcv")

    def test_password_reset_without_email_setup(self):
        r = self.client.get("/password-reset/")
        self.assertContains(r, "ask the admin")

    def test_password_reset_sends_email(self):
        from django.core import mail

        from agent.models import SystemSettings
        s = SystemSettings.load()
        s.gmail_address = "system@gmail.com"
        s.gmail_app_password = "x"
        s.save()
        with self.settings(EMAIL_BACKEND="django.core.mail.backends.locmem.EmailBackend"):
            self.client.post("/password-reset/", {"email": "saru@example.com"})
        self.assertEqual(len(mail.outbox), 1)
        self.assertIn("/reset/", mail.outbox[0].body)


class AdminDesignTests(TestCase):
    def test_admin_pages_render(self):
        User.objects.create_superuser("boss", password="x")
        self.assertContains(self.client.get("/admin/login/"), "JobSearchAIAgentByAnish1989")
        self.client.login(username="boss", password="x")
        r = self.client.get("/admin/")
        self.assertContains(r, "Manage users, CVs, jobs and applications")
        self.assertEqual(self.client.get("/admin/agent/candidate/").status_code, 200)


class FallbackTests(TestCase):
    def test_basic_mode_used_when_claude_fails(self):
        from unittest import mock

        from agent import services

        c = Candidate.objects.create(user=User.objects.create_user("f", password="x"), full_name="F",
                                     job_types="kitchen hand")
        CVDocument.objects.create(candidate=c, title="Kitchen CV", text="kitchen hand dishwashing " * 10)
        job = Job.objects.create(candidate=c, title="Kitchen Hand", description="dishwashing kitchen",
                                 fingerprint=fingerprint("Kitchen Hand"))
        boom = Exception("Your credit balance is too low to access the Anthropic API.")
        c.ai_key = "sk-ant-test"
        c.save()
        with mock.patch.object(services, "ask_claude", side_effect=boom):
            score, reason, questions = services.score_job(c, job)
            self.assertGreater(score, 30)
            self.assertIn("no credit", reason)
            docs = services.generate_documents(c, job)
            self.assertIn("kitchen hand", docs["cv"])
            self.assertIn("no credit", services.interview_prep(c, job))
            self.assertIn("no credit", services.daily_insight(c, {"suggested_today": 0}))


class SlugTests(TestCase):
    def test_underscore_name_gives_short_link(self):
        c = Candidate.objects.create(user=User.objects.create_user("s2", password="x"), full_name="Saru_Tuitui")
        self.assertEqual(c.slug, "sarucv")


class WeekSaveSendTests(TestCase):
    def setUp(self):
        from datetime import timedelta

        from django.utils import timezone

        self.u = User.objects.create_user("anish", password="x")
        self.c = Candidate.objects.create(user=self.u, full_name="Anish Shrestha", onboarding_done=True,
                                          gmail_address="me@gmail.com")
        self.other = Candidate.objects.create(user=User.objects.create_user("saru", password="x"), full_name="Saru")
        self.new = Job.objects.create(candidate=self.c, title="Kitchen Hand", company="Cafe", url="https://x.nz/1",
                                      fingerprint=fingerprint("Kitchen Hand", "Cafe"), match_score=80)
        self.old = Job.objects.create(candidate=self.c, title="Old Job", fingerprint=fingerprint("Old Job"),
                                      found_at=timezone.now() - timedelta(days=9))
        Job.objects.create(candidate=self.other, title="Saru Job", fingerprint=fingerprint("Saru Job"))
        self.client.login(username="anish", password="x")

    def test_week_table_shows_only_last_7_days_and_own_jobs(self):
        r = self.client.get(f"/c/{self.c.pk}/week/")
        self.assertContains(r, "Kitchen Hand")
        self.assertNotContains(r, "Old Job")
        self.assertNotContains(r, "Saru Job")
        self.assertEqual(self.c.jobs.count(), 2)  # old job is kept

    def test_save_and_filter(self):
        self.client.post(f"/c/{self.c.pk}/week/", {"action": "toggle_save", "job_id": self.new.pk})
        self.new.refresh_from_db()
        self.assertIsNotNone(self.new.saved_at)
        self.assertContains(self.client.get(f"/c/{self.c.pk}/week/?saved=1"), "Kitchen Hand")
        self.client.post(f"/c/{self.c.pk}/jobs/{self.new.pk}/", {"action": "toggle_save"})
        self.new.refresh_from_db()
        self.assertIsNone(self.new.saved_at)

    def test_excel_download(self):
        r = self.client.get(f"/c/{self.c.pk}/week/download.xlsx")
        self.assertEqual(r.status_code, 200)
        self.assertTrue(r.content.startswith(b"PK"))

    def test_pdf_and_send_guard(self):
        from unittest import mock

        from agent.models import Application

        app = Application.objects.create(candidate=self.c, job=self.new, cv_text="SUMMARY\n- Reliable worker",
                                         cover_letter="Dear Manager,\nHello", email_draft="Subject: Kitchen Hand\nHi")
        r = self.client.get(f"/c/{self.c.pk}/applications/{app.pk}/cv.pdf")
        self.assertTrue(r.content.startswith(b"%PDF"))
        self.assertContains(self.client.get(f"/c/{self.c.pk}/jobs/{self.new.pk}/send/"), "Check before you send")
        url = f"/c/{self.c.pk}/jobs/{self.new.pk}/send/"
        with mock.patch("agent.services.send_gmail") as sent, \
                mock.patch.object(Candidate, "gmail_ready", new_callable=mock.PropertyMock, return_value=True):
            self.client.post(url, {"to": "bad", "subject": "s", "body": "b"})
            sent.assert_not_called()
            self.client.post(url, {"to": "boss@cafe.nz", "subject": "s", "body": "b"})
            self.assertEqual(sent.call_count, 1)
            files = sent.call_args[0][5]
            self.assertEqual([f[0] for f in files], ["anish-shrestha-CV.pdf", "anish-shrestha-Cover-Letter.pdf"])
            self.client.post(url, {"to": "boss@cafe.nz", "subject": "s", "body": "b"})  # duplicate blocked
            self.assertEqual(sent.call_count, 1)
        app.refresh_from_db()
        self.new.refresh_from_db()
        self.assertEqual(app.status, "applied")
        self.assertIsNotNone(self.new.saved_at)

    def test_other_user_cannot_open_pages(self):
        self.client.login(username="saru", password="x")
        self.assertEqual(self.client.get(f"/c/{self.c.pk}/week/").status_code, 403)
        self.assertEqual(self.client.get(f"/c/{self.c.pk}/jobs/{self.new.pk}/send/").status_code, 403)

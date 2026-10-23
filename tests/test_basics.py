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
        self.assertEqual(self.client.get(f"/c/{self.a.pk}/").status_code, 200)

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
                                          job_types="retail assistant")
        CVDocument.objects.create(candidate=self.c, title="Retail CV", text="Retail assistant, customer service")

    def _pages(self):
        cid = self.c.pk
        return [f"/c/{cid}/", f"/c/{cid}/profile/", f"/c/{cid}/jobs/", f"/c/{cid}/applications/",
                f"/c/{cid}/questions/", f"/c/{cid}/cv/{self.c.cvs.first().pk}/"]

    def test_all_pages_for_user_and_admin(self):
        self.client.login(username="saru", password="x")
        for url in self._pages():
            self.assertEqual(self.client.get(url).status_code, 200, url)
        self.assertEqual(self.client.get("/audit/").status_code, 403)
        self.client.login(username="admin", password="x")
        for url in self._pages() + ["/", "/users/new/", "/audit/"]:
            self.assertEqual(self.client.get(url).status_code, 200, url)

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
        self.assertContains(self.client.get("/help/"), "How to use")


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
        with self.settings(ANTHROPIC_API_KEY="sk-test"), mock.patch.object(services, "ask_claude", side_effect=boom):
            score, reason, questions = services.score_job(c, job)
            self.assertGreater(score, 30)
            self.assertIn("no credit", reason)
            docs = services.generate_documents(c, job)
            self.assertIn("kitchen hand", docs["cv"])
            self.assertIn("no credit", services.interview_prep(c, job))
            self.assertIn("no credit", services.daily_insight(c, {"suggested_today": 0}))

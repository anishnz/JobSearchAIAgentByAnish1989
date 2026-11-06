"""Knowledge base tests. The RAG service is always faked, so these run without it."""
import json
from unittest import mock

from django.contrib.auth.models import User
from django.core.cache import cache
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase

from agent.models import Application, AuditLog, Candidate, CVDocument, Job
from kb.services import RagUnavailable, owner_of, plain_text, role_of


def fake(status=200, data=None):
    return mock.patch("kb.api.call_rag", return_value=(status, data if data is not None else {}))


class KBTestBase(TestCase):
    def setUp(self):
        cache.clear()
        self.a = Candidate.objects.create(user=User.objects.create_user("a", password="x"), full_name="A")
        self.b = Candidate.objects.create(user=User.objects.create_user("b", password="x"), full_name="B")
        self.admin = User.objects.create_user("boss", password="x", is_staff=True, is_superuser=True)
        self.client.login(username="a", password="x")

    def post_json(self, url, body):
        return self.client.post(url, json.dumps(body), content_type="application/json")


class RoleAndOwnerTests(KBTestBase):
    def test_roles(self):
        self.assertEqual(role_of(self.a.user), "user")
        self.assertEqual(role_of(self.admin), "admin")

    def test_owner_name(self):
        self.assertEqual(owner_of(self.a), f"c{self.a.pk}")

    def test_plain_text_removes_markdown(self):
        self.assertEqual(plain_text("## Title\n**bold** [1]"), "Title\nbold [1]")


class PageTests(KBTestBase):
    def test_own_pages_open(self):
        self.assertEqual(self.client.get(f"/c/{self.a.pk}/kb/").status_code, 200)
        self.assertEqual(self.client.get(f"/c/{self.a.pk}/kb/manage/").status_code, 200)

    def test_other_users_pages_refused(self):
        self.assertEqual(self.client.get(f"/c/{self.b.pk}/kb/").status_code, 403)
        self.assertEqual(self.client.get(f"/c/{self.b.pk}/kb/manage/").status_code, 403)

    def test_model_settings_only_shown_to_admin(self):
        self.assertNotContains(self.client.get(f"/c/{self.a.pk}/kb/manage/"), "kb-model-form")
        self.client.login(username="boss", password="x")
        self.assertContains(self.client.get(f"/c/{self.a.pk}/kb/manage/"), "kb-model-form")

    def test_signed_out_api_gives_json_401(self):
        self.client.logout()
        r = self.post_json(f"/c/{self.a.pk}/kb/api/ask/", {"question": "hi"})
        self.assertEqual(r.status_code, 401)


class AskTests(KBTestBase):
    def test_ask_sends_own_owner_and_user_role(self):
        with fake(200, {"answer": "**Yes** [1]", "sources": [{"n": 1, "title": "CV", "snippet": "x"}]}) as rag:
            r = self.post_json(f"/c/{self.a.pk}/kb/api/ask/", {"question": "What is in my CV?"})
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.json()["answer"], "Yes [1]")
        args = rag.call_args[0]
        self.assertEqual(args[:4], ("POST", "/v1/ask", "user", f"c{self.a.pk}"))

    def test_cannot_ask_in_other_users_space(self):
        with fake() as rag:
            r = self.post_json(f"/c/{self.b.pk}/kb/api/ask/", {"question": "hi"})
        self.assertEqual(r.status_code, 403)
        rag.assert_not_called()

    def test_empty_and_long_questions(self):
        with fake() as rag:
            self.assertEqual(self.post_json(f"/c/{self.a.pk}/kb/api/ask/", {"question": " "}).status_code, 400)
            self.assertEqual(self.post_json(f"/c/{self.a.pk}/kb/api/ask/", {"question": "x" * 1001}).status_code, 400)
        rag.assert_not_called()

    def test_ai_turned_off_blocks_ask(self):
        self.a.ai_allowed = False
        self.a.save()
        with fake() as rag:
            r = self.post_json(f"/c/{self.a.pk}/kb/api/ask/", {"question": "hi"})
        self.assertEqual(r.status_code, 403)
        rag.assert_not_called()

    def test_service_down_gives_503(self):
        with mock.patch("kb.api.call_rag", side_effect=RagUnavailable("down")):
            r = self.post_json(f"/c/{self.a.pk}/kb/api/ask/", {"question": "hi"})
        self.assertEqual(r.status_code, 503)

    def test_wrong_service_key_message(self):
        with fake(401, {"detail": "Invalid service key"}):
            r = self.post_json(f"/c/{self.a.pk}/kb/api/ask/", {"question": "hi"})
        self.assertEqual(r.status_code, 502)
        self.assertIn("RAG_SERVICE_KEY", r.json()["detail"])

    def test_hourly_limit(self):
        with fake(200, {"answer": "ok", "sources": []}):
            for _ in range(60):
                self.post_json(f"/c/{self.a.pk}/kb/api/ask/", {"question": "hi"})
            r = self.post_json(f"/c/{self.a.pk}/kb/api/ask/", {"question": "hi"})
        self.assertEqual(r.status_code, 429)


class InterviewTests(KBTestBase):
    def test_interview_questions(self):
        with fake(200, {"questions": [{"question": "Why?", "tip": "Be honest"}], "parsed": True}) as rag:
            r = self.post_json(f"/c/{self.a.pk}/kb/api/interview/", {"topic": "kitchen hand", "count": 3})
        self.assertEqual(r.status_code, 200)
        self.assertEqual(rag.call_args[0][1], "/v1/interview-questions")
        self.assertEqual(rag.call_args[1]["json_body"], {"topic": "kitchen hand", "count": 3})

    def test_bad_count(self):
        with fake() as rag:
            r = self.post_json(f"/c/{self.a.pk}/kb/api/interview/", {"topic": "x", "count": 50})
        self.assertEqual(r.status_code, 400)
        rag.assert_not_called()


class DocumentTests(KBTestBase):
    def upload(self, name, content, cid=None, **extra):
        cid = cid or self.a.pk
        return self.client.post(f"/c/{cid}/kb/api/documents/",
                                {"file": SimpleUploadedFile(name, content), "title": "My CV", **extra})

    def test_upload_text(self):
        with fake(200, {"doc_id": "abc", "chunks": 2}) as rag:
            r = self.upload("cv.txt", b"Kitchen hand experience", kind="other")
        self.assertEqual(r.status_code, 200)
        self.assertEqual(rag.call_args[1]["data"]["shared"], "0")
        self.assertFalse(CVDocument.objects.exists())  # "other" documents are not CVs
        self.assertTrue(AuditLog.objects.filter(action="kb_document_uploaded").exists())

    def test_wrong_type_refused(self):
        with fake() as rag:
            self.assertEqual(self.upload("cv.exe", b"MZ").status_code, 400)
            self.assertEqual(self.upload("fake.pdf", b"not a pdf").status_code, 400)
            self.assertEqual(self.upload("bin.txt", b"\x00\x01").status_code, 400)
        rag.assert_not_called()

    def test_user_cannot_share(self):
        with fake() as rag:
            r = self.upload("tips.txt", b"tips", shared="1")
        self.assertEqual(r.status_code, 403)
        rag.assert_not_called()

    def test_admin_can_share(self):
        self.client.login(username="boss", password="x")
        with fake(200, {"doc_id": "abc", "chunks": 1, "shared": True}) as rag:
            r = self.upload("tips.txt", b"tips", shared="1")
        self.assertEqual(r.status_code, 200)
        self.assertEqual(rag.call_args[0][2], "admin")
        self.assertEqual(rag.call_args[1]["data"]["shared"], "1")

    def test_admin_viewing_user_is_logged(self):
        self.client.login(username="boss", password="x")
        with fake(200, {"documents": []}):
            self.client.get(f"/c/{self.a.pk}/kb/api/documents/")
        self.assertTrue(AuditLog.objects.filter(action="admin_viewed_records", candidate=self.a).exists())

    def test_delete_bad_id(self):
        with fake() as rag:
            r = self.client.delete(f"/c/{self.a.pk}/kb/api/documents/bad%20id!/")
        self.assertEqual(r.status_code, 400)
        rag.assert_not_called()


class ModelSettingsTests(KBTestBase):
    def test_user_refused(self):
        with fake() as rag:
            self.assertEqual(self.client.get("/kb/api/admin/model/").status_code, 403)
            self.assertEqual(self.client.post("/kb/api/admin/model/test/").status_code, 403)
        rag.assert_not_called()

    def test_admin_change_keeps_empty_key(self):
        self.client.login(username="boss", password="x")
        with fake(200, {"display_name": "DeepSeek"}) as rag:
            r = self.client.put("/kb/api/admin/model/", json.dumps({"model_id": "deepseek-chat", "api_key": ""}),
                                content_type="application/json")
        self.assertEqual(r.status_code, 200)
        self.assertEqual(rag.call_args[1]["json_body"], {"model_id": "deepseek-chat"})
        log = AuditLog.objects.get(action="kb_model_settings_changed")
        self.assertNotIn("api_key", log.detail)


def make_docx(text):
    import io

    import docx
    d = docx.Document()
    d.add_paragraph(text)
    buf = io.BytesIO()
    d.save(buf)
    return buf.getvalue()


class CVStoreTests(KBTestBase):
    """Many CVs per person, kept in step between the knowledge base and 'My profile & CVs'."""

    def upload(self, name, content, **extra):
        return self.client.post(f"/c/{self.a.pk}/kb/api/documents/",
                                {"file": SimpleUploadedFile(name, content), **extra})

    def test_upload_two_cvs_saves_both_in_profile(self):
        with fake(200, {"doc_id": "doc1", "chunks": 1}) as rag:
            r1 = self.upload("kitchen.docx", make_docx("Kitchen helper at Joes Catering"), kind="cv",
                             title="Kitchen CV", tags="kitchen hand")
        with fake(200, {"doc_id": "doc2", "chunks": 1}):
            r2 = self.upload("cleaning.txt", b"Cleaning and housekeeping", kind="cv", title="Cleaning CV")
        self.assertEqual((r1.status_code, r2.status_code), (200, 200))
        sent = rag.call_args[1]
        self.assertEqual(sent["data"]["kind"], "cv")
        self.assertIn(b"Joes Catering", sent["files"]["file"][1])  # Word text is read in Django, sent as text
        cvs = {cv.title: cv for cv in self.a.cvs.all()}
        self.assertEqual(set(cvs), {"Kitchen CV", "Cleaning CV"})
        self.assertEqual(cvs["Kitchen CV"].kb_doc_id, "doc1")
        self.assertEqual(cvs["Kitchen CV"].best_for, "kitchen hand")
        self.assertTrue(cvs["Kitchen CV"].uploaded_file.name.endswith(".docx"))
        self.assertEqual(self.b.cvs.count(), 0)

    def test_cover_letter_kind(self):
        with fake(200, {"doc_id": "doc3", "chunks": 1}):
            self.upload("letter.txt", b"Dear Hiring Manager", kind="cover_letter", title="My letter")
        self.assertTrue(self.a.cvs.get().is_cover_letter)

    def test_fake_docx_refused(self):
        with fake() as rag:
            r = self.upload("cv.docx", b"not a zip", kind="cv")
        self.assertEqual(r.status_code, 400)
        rag.assert_not_called()

    def test_delete_in_kb_removes_profile_cv(self):
        cv = CVDocument(candidate=self.a, title="Old CV", text="x", kb_doc_id="doc9")
        cv._kb_skip = True
        cv.save()
        with fake(200, {"deleted": "doc9"}):
            r = self.client.delete(f"/c/{self.a.pk}/kb/api/documents/doc9/")
        self.assertEqual(r.status_code, 200)
        self.assertFalse(CVDocument.objects.filter(pk=cv.pk).exists())

    def test_saving_a_profile_cv_puts_it_in_kb(self):
        with mock.patch("kb.services.call_rag", return_value=(200, {"doc_id": "new1", "chunks": 1})) as rag:
            cv = CVDocument.objects.create(candidate=self.a, title="Retail CV", text="Retail assistant")
        cv.refresh_from_db()
        self.assertEqual(cv.kb_doc_id, "new1")
        args = rag.call_args[0]
        self.assertEqual(args[:4], ("POST", "/v1/documents", "user", f"c{self.a.pk}"))
        self.assertEqual(rag.call_args[1]["data"]["kind"], "cv")

    def test_editing_a_profile_cv_replaces_it_in_kb(self):
        with mock.patch("kb.services.call_rag", return_value=(200, {"doc_id": "v1"})):
            cv = CVDocument.objects.create(candidate=self.a, title="CV", text="one")
        cv.refresh_from_db()
        with mock.patch("kb.services.call_rag", side_effect=[(200, {}), (200, {"doc_id": "v2"})]) as rag:
            cv.text = "two"
            cv.save()
        self.assertEqual(rag.call_args_list[0][0][:2], ("DELETE", "/v1/documents/v1"))
        cv.refresh_from_db()
        self.assertEqual(cv.kb_doc_id, "v2")

    def test_deleting_a_profile_cv_removes_it_from_kb(self):
        cv = CVDocument(candidate=self.a, title="CV", text="x", kb_doc_id="d5")
        cv._kb_skip = True
        cv.save()
        with mock.patch("kb.services.call_rag", return_value=(200, {})) as rag:
            CVDocument.objects.get(pk=cv.pk).delete()
        self.assertEqual(rag.call_args[0][:4], ("DELETE", "/v1/documents/d5", "user", f"c{self.a.pk}"))

    def test_service_down_never_breaks_saving_a_cv(self):
        with mock.patch("kb.services.call_rag", side_effect=RagUnavailable("down")):
            cv = CVDocument.objects.create(candidate=self.a, title="CV", text="x")
        cv.refresh_from_db()
        self.assertEqual(cv.kb_doc_id, "")

    def test_sync_copies_missing_cvs(self):
        for title in ("A1", "A2"):
            cv = CVDocument(candidate=self.a, title=title, text="text")
            cv._kb_skip = True
            cv.save()
        with mock.patch("kb.services.is_running", return_value=True), \
                mock.patch("kb.services.call_rag", return_value=(200, {"doc_id": "s1"})):
            r = self.client.post(f"/c/{self.a.pk}/kb/api/sync-cvs/")
        self.assertEqual(r.json()["added"], 2)
        self.assertFalse(self.a.cvs.filter(kb_doc_id="").exists())

    def test_sync_other_users_space_refused(self):
        self.assertEqual(self.client.post(f"/c/{self.b.pk}/kb/api/sync-cvs/").status_code, 403)


TAILORED = {"cv": "ANISH\n**PROFILE**\n- Kitchen helper", "cover_letter": "Dear Hiring Manager",
            "email": "Subject: Application", "sources": [{"title": "Kitchen CV"}]}


class TailorTests(KBTestBase):
    def test_pasted_job_creates_job_and_documents(self):
        with mock.patch("kb.services.call_rag", return_value=(200, TAILORED)) as rag:
            r = self.client.post(f"/c/{self.a.pk}/kb/tailor/", {
                "title": "Kitchen Hand", "company": "Cafe", "description": "We need a kitchen hand for busy shifts."})
        job = Job.objects.get(candidate=self.a)
        self.assertRedirects(r, f"/c/{self.a.pk}/jobs/{job.pk}/", fetch_redirect_response=False)
        app = Application.objects.get(job=job)
        self.assertEqual(app.cv_text, "ANISH\nPROFILE\n- Kitchen helper")  # markdown bold removed
        self.assertEqual(app.cover_letter, "Dear Hiring Manager")
        body = rag.call_args[1]["json_body"]
        self.assertEqual(body["job_title"], "Kitchen Hand")
        self.assertIn("Name: A", body["profile"])
        self.assertEqual(rag.call_args[0][:4], ("POST", "/v1/tailor", "user", f"c{self.a.pk}"))
        self.assertTrue(AuditLog.objects.filter(action="documents_generated_kb").exists())

    def test_saved_job_and_downloads(self):
        job = Job.objects.create(candidate=self.a, title="Cleaner", fingerprint="f1", description="Clean offices")
        with mock.patch("kb.services.call_rag", return_value=(200, TAILORED)):
            self.client.post(f"/c/{self.a.pk}/kb/tailor/", {"job_id": job.pk})
        app = Application.objects.get(job=job)
        pdf = self.client.get(f"/c/{self.a.pk}/applications/{app.pk}/cv.pdf")
        self.assertEqual(pdf["Content-Type"], "application/pdf")
        self.assertTrue(pdf.content.startswith(b"%PDF"))
        docx_resp = self.client.get(f"/c/{self.a.pk}/applications/{app.pk}/cover-letter.docx")
        self.assertTrue(docx_resp.content.startswith(b"PK"))

    def test_job_page_has_kb_button(self):
        job = Job.objects.create(candidate=self.a, title="Cleaner", fingerprint="f2")
        self.assertContains(self.client.get(f"/c/{self.a.pk}/jobs/{job.pk}/"), "Create from my knowledge base")

    def test_no_cv_yet_message(self):
        with mock.patch("kb.services.call_rag",
                        return_value=(404, {"detail": "No CV in your knowledge base yet; upload at least one CV first"})):
            r = self.client.post(f"/c/{self.a.pk}/kb/tailor/", {
                "title": "Kitchen Hand", "description": "We need a kitchen hand for busy shifts."}, follow=True)
        self.assertContains(r, "upload at least one CV first")
        self.assertFalse(Application.objects.exists())

    def test_service_down_message(self):
        with mock.patch("kb.services.call_rag", side_effect=RagUnavailable("down")):
            r = self.client.post(f"/c/{self.a.pk}/kb/tailor/", {
                "title": "Kitchen Hand", "description": "We need a kitchen hand for busy shifts."}, follow=True)
        self.assertContains(r, "not running right now")

    def test_ai_off_blocks_tailor(self):
        self.a.ai_allowed = False
        self.a.save()
        with mock.patch("kb.services.call_rag") as rag:
            r = self.client.post(f"/c/{self.a.pk}/kb/tailor/", {
                "title": "Kitchen Hand", "description": "We need a kitchen hand for busy shifts."}, follow=True)
        self.assertContains(r, "AI is turned off")
        rag.assert_not_called()

    def test_needs_title_and_advert(self):
        with mock.patch("kb.services.call_rag") as rag:
            self.client.post(f"/c/{self.a.pk}/kb/tailor/", {"title": "", "description": "short"})
        rag.assert_not_called()
        self.assertFalse(Job.objects.exists())

    def test_cannot_use_other_users_job_or_space(self):
        job_b = Job.objects.create(candidate=self.b, title="Nurse aide", fingerprint="f3")
        with mock.patch("kb.services.call_rag") as rag:
            self.assertEqual(self.client.post(f"/c/{self.b.pk}/kb/tailor/", {"job_id": job_b.pk}).status_code, 403)
            self.client.post(f"/c/{self.a.pk}/kb/tailor/", {"job_id": job_b.pk})
        rag.assert_not_called()
        self.assertFalse(Application.objects.exists())

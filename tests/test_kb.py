"""Knowledge base tests. The RAG service is always faked, so these run without it."""
import json
from unittest import mock

from django.contrib.auth.models import User
from django.core.cache import cache
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase

from agent.models import AuditLog, Candidate
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
            r = self.upload("cv.txt", b"Kitchen hand experience")
        self.assertEqual(r.status_code, 200)
        self.assertEqual(rag.call_args[1]["data"]["shared"], "0")
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

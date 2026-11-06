"""Local AI (Ollama on the laptop) tests. Ollama is always faked."""
import json
from unittest import mock

import requests
from django.contrib.auth.models import User
from django.test import TestCase

from agent import services
from agent.models import AuditLog, Candidate, Job, SystemSettings


class FakeResp:
    def __init__(self, status=200, data=None):
        self.status_code, self._data = status, data or {}

    def json(self):
        return self._data

    def raise_for_status(self):
        if self.status_code >= 400:
            raise requests.HTTPError(str(self.status_code))


class LocalAITests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user("a", password="x")
        self.c = Candidate.objects.create(user=self.user, full_name="Anish", ai_provider="local",
                                          availability="Mon-Fri")
        self.admin = User.objects.create_user("boss", password="x", is_staff=True, is_superuser=True)

    def set_model(self, name="llama3.2:latest"):
        s = SystemSettings.load()
        s.ollama_model = name
        s.save()

    def test_no_model_chosen_means_basic_mode(self):
        self.assertEqual(services.candidate_key(self.c), "")
        self.assertEqual(services.ai_mode(self.c), "")

    def test_local_key_and_label(self):
        self.set_model()
        self.assertEqual(services.candidate_key(self.c), services.LOCAL_PREFIX + "llama3.2:latest")
        self.assertEqual(services.ai_mode(self.c), "Local AI (llama3.2:latest)")

    def test_ai_off_by_admin_wins(self):
        self.set_model()
        self.c.ai_allowed = False
        self.assertEqual(services.candidate_key(self.c), "")

    def test_ask_goes_to_ollama_with_rules(self):
        self.set_model()
        with mock.patch("agent.services.requests.post",
                        return_value=FakeResp(200, {"message": {"content": "<think>hmm</think> Hello"}})) as post:
            out = services.ask_claude("Hi", services.candidate_key(self.c), max_tokens=50)
        self.assertEqual(out, "Hello")
        body = post.call_args[1]["json"]
        self.assertEqual(body["model"], "llama3.2:latest")
        self.assertIn("Never invent employers", body["messages"][0]["content"])
        self.assertTrue(post.call_args[0][0].endswith("/api/chat"))

    def test_ollama_down_falls_back_to_basic(self):
        self.set_model()
        job = Job.objects.create(candidate=self.c, title="Kitchen Hand", fingerprint="f")
        with mock.patch("agent.services.requests.post", side_effect=requests.ConnectionError("down")):
            docs = services.generate_documents(self.c, job)
        self.assertIn("Kitchen Hand", docs["cover_letter"])  # basic version still made

    def test_generate_documents_with_local_ai(self):
        self.set_model()
        job = Job.objects.create(candidate=self.c, title="Kitchen Hand", fingerprint="f")
        text = "===CV===\nANISH\n===COVER LETTER===\nDear Manager\n===EMAIL===\nSubject: Hi"
        with mock.patch("agent.services.requests.post", return_value=FakeResp(200, {"message": {"content": text}})):
            docs = services.generate_documents(self.c, job)
        self.assertEqual((docs["cv"], docs["cover_letter"]), ("ANISH", "Dear Manager"))

    def test_missing_model_message(self):
        self.set_model("nope")
        with mock.patch("agent.services.requests.post", return_value=FakeResp(404)):
            ok, msg = services.test_ai_key(services.candidate_key(self.c))
        self.assertFalse(ok)
        self.assertIn("ollama pull nope", msg)

    def test_list_models(self):
        data = {"models": [{"name": "qwen2.5:7b"}, {"name": "llama3.2:latest"}]}
        with mock.patch("agent.services.requests.get", return_value=FakeResp(200, data)):
            self.assertEqual(services.list_ollama_models(), (True, ["llama3.2:latest", "qwen2.5:7b"]))
        with mock.patch("agent.services.requests.get", side_effect=requests.ConnectionError()):
            ok, msg = services.list_ollama_models()
        self.assertFalse(ok)
        self.assertIn("Ollama app running", msg)

    def test_user_chooses_provider_in_settings(self):
        self.client.login(username="a", password="x")
        self.client.post(f"/c/{self.c.pk}/settings/", {"action": "save", "ai_provider": "claude"})
        self.c.refresh_from_db()
        self.assertEqual(self.c.ai_provider, "claude")
        page = self.client.get(f"/c/{self.c.pk}/settings/")
        self.assertContains(page, "Local AI on this laptop (Ollama, free)")

    def test_admin_picks_model_and_switches_everyone(self):
        other = Candidate.objects.create(user=User.objects.create_user("b", password="x"), full_name="Saru")
        self.client.login(username="boss", password="x")
        with mock.patch("agent.services.requests.get",
                        return_value=FakeResp(200, {"models": [{"name": "llama3.2:latest"}]})):
            page = self.client.get("/manage/settings/")
        self.assertContains(page, "llama3.2:latest")
        self.client.post("/manage/settings/", {"action": "save_local_ai", "ollama_model": "llama3.2:latest"})
        self.assertEqual(SystemSettings.load().ollama_model, "llama3.2:latest")
        self.client.post("/manage/settings/", {"action": "local_for_all"})
        other.refresh_from_db()
        self.assertEqual(other.ai_provider, "local")
        self.assertTrue(AuditLog.objects.filter(action="local_ai_for_all").exists())

    def test_user_cannot_open_system_settings(self):
        self.client.login(username="a", password="x")
        self.assertEqual(self.client.post("/manage/settings/", {"action": "local_for_all"}).status_code, 403)

    def test_kb_ollama_endpoints_admin_only(self):
        self.client.login(username="a", password="x")
        self.assertEqual(self.client.get("/kb/api/admin/ollama/").status_code, 403)
        self.client.login(username="boss", password="x")
        with mock.patch("kb.api.call_rag", return_value=(200, {"ok": True, "models": ["llama3.2:latest"]})) as rag:
            r = self.client.get("/kb/api/admin/ollama/")
        self.assertEqual(r.json()["models"], ["llama3.2:latest"])
        self.assertEqual(rag.call_args[0][:3], ("GET", "/v1/admin/ollama", "admin"))
        with mock.patch("kb.api.call_rag", return_value=(200, {"display_name": "Ollama"})) as rag:
            r = self.client.post("/kb/api/admin/model/preset/", json.dumps({"preset": "ollama", "model": "llama3.2:latest"}),
                                 content_type="application/json")
        self.assertEqual(r.status_code, 200)
        self.assertEqual(rag.call_args[1]["json_body"], {"preset": "ollama", "model": "llama3.2:latest"})
        with mock.patch("kb.api.call_rag") as rag:
            r = self.client.post("/kb/api/admin/model/preset/", json.dumps({"preset": "ollama"}),
                                 content_type="application/json")
        self.assertEqual(r.status_code, 400)
        rag.assert_not_called()

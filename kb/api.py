"""
api.py - JSON endpoints used by the Knowledge Base pages (thin proxy to the RAG service)
========================================================================================

Taken from CyberQuest (apps/kb/api.py) and changed for the job agent.

Who can do what:
    * every user, in their OWN space: ask, interview questions, list / upload / delete their documents
    * the admin (is_staff): the same in any user's space (logged), plus upload / delete SHARED
      documents and change the AI model settings
    * a user whose AI access is turned off by the admin cannot ask or make interview questions
      (uploading and listing still work: that never leaves the laptop)
Every error is returned as JSON: {"detail": "<English message>"}.

Safety kept from CyberQuest:
    * uploads are checked by content, not only by name (a PDF must start with %PDF-,
      a .txt/.md file must be UTF-8 text with no binary bytes)
    * questions are limited per user per hour, so nobody can use up the AI credit by mistake
"""

from __future__ import annotations

import json
import re
from functools import wraps

from django.core.cache import cache
from django.core.exceptions import PermissionDenied
from django.http import Http404, JsonResponse
from django.views.decorators.http import require_http_methods

from agent.models import AuditLog
from agent.views import get_candidate

from . import services
from .services import RagUnavailable, call_rag, owner_of, role_of

MAX_UPLOAD_BYTES = 20 * 1024 * 1024
ASK_LIMIT_PER_HOUR = 60
ALLOWED_EXTENSIONS = (".pdf", ".txt", ".md")
DOC_ID_RE = re.compile(r"^[A-Za-z0-9_-]{1,64}$")
MODEL_FIELDS = {
    "display_name": str,
    "base_url": str,
    "model_id": str,
    "api_key": str,
    "temperature": float,
    "max_tokens": int,
    "timeout": int,
}


def error(message: str, status: int) -> JsonResponse:
    """A JSON error in the one format the pages understand."""
    return JsonResponse({"detail": message}, status=status)


def kb_api(admin_only=False):
    """Signed-in users only; answers with JSON 401/403/404, never a redirect.
    Views that take cid get the checked Candidate as request.kb_candidate."""

    def decorator(view):
        @wraps(view)
        def wrapped(request, *args, **kwargs):
            if not request.user.is_authenticated:
                return error("Please sign in again.", 401)
            if admin_only and not request.user.is_staff:
                AuditLog.log("access_denied", "Knowledge base admin endpoint", actor=request.user)
                return error("You do not have permission to do this.", 403)
            if "cid" in kwargs:
                try:
                    request.kb_candidate = get_candidate(request, kwargs["cid"])
                except PermissionDenied:
                    return error("You do not have permission to do this.", 403)
                except Http404:
                    return error("That page was not found.", 404)
            return view(request, *args, **kwargs)

        return wrapped

    return decorator


def _json_body(request) -> dict | None:
    """The JSON object sent by the page, or None when it is missing or broken."""
    try:
        data = json.loads(request.body or b"{}")
    except ValueError:
        return None
    return data if isinstance(data, dict) else None


def _friendly(status: int, data, role: str) -> tuple[str, int]:
    """Turn an error answer of the RAG service into an English message and a status for the browser."""
    detail = data.get("detail") if isinstance(data, dict) else None
    detail = detail if isinstance(detail, str) else ""
    if status == 401:
        return "The knowledge base service refused the connection. Ask the admin to check RAG_SERVICE_KEY.", 502
    if status == 403:
        return "You do not have permission to do this.", 403
    if status == 422:
        return "Please check what you typed and try again.", 400
    if status == 413:
        return "That file is too large (20 MB maximum).", 413
    if status >= 500:
        if role == "admin" and detail:
            return detail, 502
        return "The AI model did not answer. Please try again in a moment.", 502
    return detail or f"The knowledge base service reported a problem (error {status}).", status


def _over_ask_limit(user) -> bool:
    """Count one question for this user; True when the hourly limit is already used up."""
    key = f"kb-ask-{user.pk}"
    if cache.add(key, 1, timeout=3600):
        return False
    try:
        count = cache.incr(key)
    except ValueError:  # the key expired between add() and incr()
        cache.set(key, 1, timeout=3600)
        return False
    return count > ASK_LIMIT_PER_HOUR


def _content_ok(name: str, data: bytes) -> bool:
    """A PDF must really be a PDF; a text file must really be text (not a renamed program)."""
    if name.lower().endswith(".pdf"):
        return data.startswith(b"%PDF-")
    if b"\x00" in data:
        return False
    try:
        data.decode("utf-8")
    except UnicodeDecodeError:
        return False
    return True


def _owner(request) -> str:
    candidate = getattr(request, "kb_candidate", None)
    return owner_of(candidate) if candidate is not None else "c0"


def _forward(request, method: str, path: str, json_body=None, **kwargs) -> JsonResponse:
    """Call the RAG service as the right role and owner; return its answer or a clear English error."""
    role = role_of(request.user)
    try:
        status, data = call_rag(method, path, role, _owner(request), json_body=json_body, **kwargs)
    except RagUnavailable:
        return error("The knowledge base service is not running right now. Please try again later.", 503)
    if status >= 400:
        message, out_status = _friendly(status, data, role)
        return error(message, out_status)
    if not isinstance(data, dict):
        return error("The knowledge base service sent an answer the page cannot read.", 502)
    return JsonResponse(data)


def _ai_blocked(request):
    if not request.kb_candidate.ai_allowed:
        return error("AI is turned off for this account. Ask the admin to turn it on.", 403)
    if _over_ask_limit(request.user):
        return error("You have asked a lot of questions this hour. Please try again later.", 429)
    return None


@kb_api()
@require_http_methods(["POST"])
def ask(request, cid):
    """Ask a question; the answer comes with its sources."""
    body = _json_body(request)
    if body is None:
        return error("The request was not valid. Please reload the page and try again.", 400)
    question = body.get("question")
    question = question.strip() if isinstance(question, str) else ""
    if not question:
        return error("Please type a question first.", 400)
    if len(question) > 1000:
        return error("Your question is too long (1000 characters maximum).", 400)
    blocked = _ai_blocked(request)
    if blocked:
        return blocked
    response = _forward(request, "POST", "/v1/ask", {"question": question})
    if response.status_code == 200:
        data = json.loads(response.content)
        data["answer"] = services.plain_text(data.get("answer", ""))
        data.setdefault("sources", [])
        for source in data["sources"]:
            if isinstance(source, dict):
                source["snippet"] = services.plain_text(source.get("snippet", ""))
        return JsonResponse(data)
    return response


@kb_api()
@require_http_methods(["POST"])
def interview(request, cid):
    """Practice interview questions (with honest answer tips) from the person's documents."""
    body = _json_body(request)
    if body is None:
        return error("The request was not valid. Please reload the page and try again.", 400)
    topic = body.get("topic")
    topic = topic.strip() if isinstance(topic, str) else ""
    if not topic:
        return error("Please type a job or topic first.", 400)
    if len(topic) > 300:
        return error("The topic is too long (300 characters maximum).", 400)
    try:
        count = int(body.get("count", 5))
    except (TypeError, ValueError):
        return error("The number of questions must be a whole number from 1 to 15.", 400)
    if not 1 <= count <= 15:
        return error("The number of questions must be a whole number from 1 to 15.", 400)
    blocked = _ai_blocked(request)
    if blocked:
        return blocked
    return _forward(request, "POST", "/v1/interview-questions", {"topic": topic, "count": count})


@kb_api()
@require_http_methods(["GET", "POST"])
def documents(request, cid):
    """GET: list this person's documents and the shared ones. POST: upload one (pdf, txt or md)."""
    if request.method == "GET":
        return _forward(request, "GET", "/v1/documents")
    upload = request.FILES.get("file")
    if upload is None:
        return error("Please choose a file to upload.", 400)
    if not upload.name.lower().endswith(ALLOWED_EXTENSIONS):
        return error("Only PDF, TXT and Markdown (.md) files can be uploaded.", 400)
    if upload.size > MAX_UPLOAD_BYTES:
        return error("That file is too large (20 MB maximum).", 413)
    shared = request.POST.get("shared") == "1"
    if shared and not request.user.is_staff:
        return error("Only the admin can share documents with everyone.", 403)
    content = upload.read()
    if not _content_ok(upload.name, content):
        AuditLog.log("upload_rejected", f"Knowledge base: {upload.name[:80]}", actor=request.user,
                     candidate=request.kb_candidate)
        return error("This file's content does not match its type (PDF, TXT or Markdown).", 400)
    title = request.POST.get("title", "").strip()[:120]
    tags = request.POST.get("tags", "").strip()[:120]
    response = _forward(
        request,
        "POST",
        "/v1/documents",
        files={"file": (upload.name, content, upload.content_type or "application/octet-stream")},
        data={"title": title, "tags": tags, "shared": "1" if shared else "0"},
    )
    if response.status_code == 200:
        where = "shared knowledge base" if shared else "knowledge base"
        AuditLog.log("kb_document_uploaded", f"{title or upload.name} ({where})", actor=request.user,
                     candidate=None if shared else request.kb_candidate)
    return response


@kb_api()
@require_http_methods(["DELETE"])
def document_delete(request, cid, doc_id):
    """Remove one document. Users delete their own; shared documents only by the admin (checked by the service)."""
    if not DOC_ID_RE.match(doc_id):
        return error("That document id is not valid.", 400)
    response = _forward(request, "DELETE", f"/v1/documents/{doc_id}")
    if response.status_code == 200:
        AuditLog.log("kb_document_deleted", doc_id, actor=request.user, candidate=request.kb_candidate)
    return response


@kb_api(admin_only=True)
@require_http_methods(["GET", "PUT"])
def model_settings(request):
    """Admin: read or change the AI model settings of the RAG service."""
    if request.method == "GET":
        return _forward(request, "GET", "/v1/admin/model")
    body = _json_body(request)
    if body is None:
        return error("The request was not valid. Please reload the page and try again.", 400)
    changes = {}
    for name, kind in MODEL_FIELDS.items():
        value = body.get(name)
        if value in (None, ""):
            continue  # empty = keep the current value (an empty API key keeps the old key)
        try:
            changes[name] = kind(value.strip() if isinstance(value, str) else value)
        except (TypeError, ValueError):
            return error(f"The value for {name.replace('_', ' ')} is not valid.", 400)
    response = _forward(request, "PUT", "/v1/admin/model", changes)
    if response.status_code == 200:
        AuditLog.log("kb_model_settings_changed", ", ".join(sorted(changes)) or "no changes", actor=request.user)
    return response


@kb_api(admin_only=True)
@require_http_methods(["POST"])
def model_test(request):
    """Admin: check that the AI model answers."""
    return _forward(request, "POST", "/v1/admin/model/test")

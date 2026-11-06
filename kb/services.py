"""
services.py - The only place that talks to the Knowledge Base (RAG) service
==========================================================================

Taken from CyberQuest (apps/kb/services.py) and changed for the job agent:
each user (Candidate) has a private knowledge base, called "c<candidate id>" in the
service, and the admin can also manage one shared part. The service address and key
come from RAG_BASE_URL and RAG_SERVICE_KEY in .env.
"""

from __future__ import annotations

import logging
import re

import requests
from django.conf import settings

logger = logging.getLogger(__name__)

CONNECT_TIMEOUT = 5  # seconds to reach the service
READ_TIMEOUT = 180  # the AI model can be slow (interview questions)

NOT_FOUND_EN = "I couldn't find this in the knowledge base."


class RagUnavailable(Exception):
    """The RAG service could not be reached or sent something that is not JSON."""


def role_of(user) -> str:
    """The admin (is_staff) is "admin" in the service; everyone else is "user"."""
    return "admin" if getattr(user, "is_staff", False) else "user"


def owner_of(candidate) -> str:
    """The name of this person's private knowledge base inside the service."""
    return f"c{candidate.pk}"


def call_rag(method: str, path: str, role: str, owner: str, json_body=None, **kwargs) -> tuple[int, object]:
    """Send one request to the RAG service. Returns (status code, decoded JSON).

    Raises RagUnavailable when the service is down, too slow or answers with non-JSON.
    """
    url = f"{settings.RAG_BASE_URL.rstrip('/')}{path}"
    headers = {"X-Service-Key": settings.RAG_SERVICE_KEY or "", "X-User-Role": role, "X-Owner": owner}
    try:
        response = requests.request(
            method, url, headers=headers, json=json_body, timeout=(CONNECT_TIMEOUT, READ_TIMEOUT), **kwargs
        )
    except requests.RequestException as exc:
        logger.warning("KB service request failed: %s %s (%s)", method, path, type(exc).__name__)
        raise RagUnavailable(str(exc)) from exc
    try:
        data = response.json()
    except ValueError as exc:
        logger.warning("KB service sent a non-JSON reply: %s %s (HTTP %s)", method, path, response.status_code)
        raise RagUnavailable("not JSON") from exc
    return response.status_code, data


def is_running() -> bool:
    """Used by System health: True when the service answers /health."""
    try:
        r = requests.get(f"{settings.RAG_BASE_URL.rstrip('/')}/health", timeout=3)
        return r.status_code == 200 and r.json().get("ok") is True
    except (requests.RequestException, ValueError):
        return False


def remove_candidate_documents(candidate) -> bool:
    """Delete one person's private documents (when the admin deletes the user). False if the service is down."""
    try:
        status, _ = call_rag("DELETE", "/v1/owner", "admin", owner_of(candidate))
    except RagUnavailable:
        return False
    return status == 200


_BOLD = re.compile(r"(\*\*|__)(.+?)\1")
_HEADING = re.compile(r"^\s{0,3}#{1,6}\s+", re.M)


def plain_text(answer):
    """The page shows answers as plain text (safe textContent), so remove Markdown marks
    such as **bold** and '# headings'. Lists ('- item') and source numbers [1] stay."""
    if not isinstance(answer, str):
        return answer
    return _HEADING.sub("", _BOLD.sub(r"\2", answer))


# ------------------------------------------------------------------ CVs in the knowledge base
KIND_OF_CATEGORY = {True: "cover_letter", False: "cv"}


class KBError(Exception):
    """A clear English message for the person (service down, no CV yet, AI failed ...)."""


def _message(status: int, data) -> str:
    detail = data.get("detail") if isinstance(data, dict) else ""
    if status == 401:
        return "The knowledge base service refused the connection. Ask the admin to check RAG_SERVICE_KEY."
    if status == 404 and isinstance(detail, str) and detail:
        return detail
    if status >= 500:
        return "The AI model did not answer. Please try again in a moment."
    return detail if isinstance(detail, str) and detail else f"The knowledge base reported a problem (error {status})."


def upload_text(candidate, title: str, text: str, tags: str = "", kind: str = "other", role: str = "user") -> str:
    """Store plain text in this person's private knowledge base. Returns the new doc_id. Raises KBError."""
    try:
        status, data = call_rag(
            "POST", "/v1/documents", role, owner_of(candidate),
            files={"file": (f"{(title or 'document')[:60]}.txt", (text or "").encode("utf-8"), "text/plain")},
            data={"title": title[:120], "tags": tags[:120], "kind": kind, "shared": "0"},
        )
    except RagUnavailable as exc:
        raise KBError("The knowledge base service is not running right now. Please try again later.") from exc
    if status != 200 or not isinstance(data, dict) or "doc_id" not in data:
        raise KBError(_message(status, data))
    return data["doc_id"]


def delete_doc(candidate, doc_id: str) -> bool:
    """Delete one of this person's documents (candidate object or candidate id). False if it failed."""
    owner = f"c{candidate}" if isinstance(candidate, int) else owner_of(candidate)
    try:
        status, _ = call_rag("DELETE", f"/v1/documents/{doc_id}", "user", owner)
    except RagUnavailable:
        return False
    return status in (200, 404)


def index_cv(cv) -> bool:
    """Put (or put again, after an edit) one saved CV into its owner's knowledge base. Best effort."""
    from agent.models import CVDocument  # pylint: disable=import-outside-toplevel

    if not (cv.text or "").strip():
        return False
    if cv.kb_doc_id:
        delete_doc(cv.candidate, cv.kb_doc_id)
    try:
        doc_id = upload_text(cv.candidate, cv.title, cv.text, cv.best_for, KIND_OF_CATEGORY[cv.is_cover_letter])
    except KBError:
        if cv.kb_doc_id:
            CVDocument.objects.filter(pk=cv.pk).update(kb_doc_id="")
        return False
    CVDocument.objects.filter(pk=cv.pk).update(kb_doc_id=doc_id)  # update(): no save signal, no loop
    cv.kb_doc_id = doc_id
    return True


def profile_facts(candidate) -> str:
    """True facts from the profile that a CV header and cover letter need."""
    return (
        f"Name: {candidate.full_name}\nPhone: {candidate.phone}\nEmail: {candidate.email}\n"
        f"Location: {candidate.location}\nAvailability: {candidate.availability}\n"
        f"Extra true facts: {candidate.extra_notes}\n"
        f"Answered questions:\n{candidate.answered_facts() or '(none)'}"
    )[:6000]


def tailor_documents(candidate, job) -> dict:
    """CV, cover letter and email for this job, written from the person's own knowledge base. Raises KBError."""
    if not candidate.ai_allowed:
        raise KBError("AI is turned off for this account. Ask the admin to turn it on.")
    body = {"job_title": (job.title or "Job")[:255], "company": (job.company or "")[:255],
            "job_ad": (job.description or "")[:15000], "profile": profile_facts(candidate)}
    try:
        status, data = call_rag("POST", "/v1/tailor", "user", owner_of(candidate), json_body=body)
    except RagUnavailable as exc:
        raise KBError("The knowledge base service is not running right now. Please try again later.") from exc
    if status != 200 or not isinstance(data, dict):
        raise KBError(_message(status, data))
    return {k: plain_text(data.get(k, "")) for k in ("cv", "cover_letter", "email")} | {
        "sources": data.get("sources", [])}


def prepare_application_from_kb(job, actor=None):
    """Like agent.workflow.prepare_application, but the documents come from the knowledge base (DeepSeek)."""
    from agent.models import Application, AuditLog  # pylint: disable=import-outside-toplevel

    candidate = job.candidate
    docs = tailor_documents(candidate, job)
    app, _ = Application.objects.update_or_create(
        job=job, defaults={"candidate": candidate, "cv_text": docs["cv"],
                           "cover_letter": docs["cover_letter"], "email_draft": docs["email"]})
    used = ", ".join(sorted({s.get("title", "") for s in docs["sources"] if isinstance(s, dict)}))
    AuditLog.log("documents_generated_kb", f"{job} (from: {used or 'knowledge base'})"[:4000], actor=actor,
                 candidate=candidate)
    return app

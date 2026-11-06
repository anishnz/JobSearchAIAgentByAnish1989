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

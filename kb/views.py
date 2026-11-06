"""views.py - The two Knowledge Base pages (Ask, Manage). The data comes from kb.api."""

from django.contrib.auth.decorators import login_required
from django.shortcuts import render

from agent.views import get_candidate


@login_required
def ask(request, cid):
    """Ask a question about your own documents (and the shared job-search tips)."""
    candidate = get_candidate(request, cid)
    return render(request, "kb/ask.html", {"c": candidate, "active": "kb"})


@login_required
def manage(request, cid):
    """Upload, list and delete documents, practice interview questions. Admin also: shared documents, AI model."""
    candidate = get_candidate(request, cid)
    return render(request, "kb/manage.html",
                  {"c": candidate, "active": "kb", "is_admin": request.user.is_staff})

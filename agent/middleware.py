"""Personal links: anishcv.localhost:8010 (on the laptop) or /u/anishcv (from any device)."""
from .models import Candidate


class PortalMiddleware:
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        request.portal = None
        host = request.get_host().split(":")[0].lower()
        parts = host.split(".")
        if len(parts) >= 2 and not host.replace(".", "").isdigit():
            label = parts[0]
            if label not in ("www", "localhost"):
                request.portal = Candidate.objects.filter(slug=label).select_related("user").first()
        return self.get_response(request)

from .models import Candidate, SystemSettings


def site(request):
    own = None
    if getattr(request, "user", None) is not None and request.user.is_authenticated:
        own = Candidate.objects.filter(user=request.user).first()
    return {"site_title": SystemSettings.load().site_title, "own_candidate": own,
            "portal": getattr(request, "portal", None)}

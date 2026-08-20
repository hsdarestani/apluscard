from functools import lru_cache
from hashlib import sha256
from pathlib import Path

from django.http import JsonResponse
from django.views.decorators.http import require_GET


_RELEASE_SUFFIXES = {".py", ".html", ".js", ".css", ".json", ".svg"}


@lru_cache(maxsize=1)
def get_release_version():
    """Return a deterministic fingerprint of the deployed application source."""
    project_root = Path(__file__).resolve().parent.parent
    digest = sha256()
    candidates = []

    for root in (project_root / "cards", project_root / "config", project_root / "templates"):
        if not root.exists():
            continue
        for path in root.rglob("*"):
            if not path.is_file() or path.suffix.lower() not in _RELEASE_SUFFIXES:
                continue
            if "__pycache__" in path.parts:
                continue
            candidates.append(path)

    for path in sorted(candidates, key=lambda item: item.as_posix()):
        try:
            relative = path.relative_to(project_root).as_posix()
            payload = path.read_bytes()
        except OSError:
            continue
        digest.update(relative.encode("utf-8"))
        digest.update(b"\0")
        digest.update(payload)
        digest.update(b"\0")

    return digest.hexdigest()[:16]


@require_GET
def deployment_version(request):
    response = JsonResponse({"version": get_release_version()})
    response["Cache-Control"] = "no-store, no-cache, must-revalidate, max-age=0"
    response["Pragma"] = "no-cache"
    response["Expires"] = "0"
    return response

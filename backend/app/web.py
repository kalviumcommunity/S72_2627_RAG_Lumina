"""Serve the built single-page app (frontend/dist) from the API process.

Hashed files under /assets are cached for a year; index.html, the service worker and the manifest
are always revalidated so a new build reaches users on the next load. Unknown paths fall back to
index.html so deep links such as /admin/documents/<id> work after a refresh.
"""

from __future__ import annotations

from pathlib import Path

from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse

# Stricter than a typical SPA policy: no inline scripts (the theme bootstrap is an external file),
# same-origin API only, blob: for the PDF worker and rendered pages.
WEB_CSP = (
    "default-src 'self'; script-src 'self'; style-src 'self' 'unsafe-inline'; "
    "img-src 'self' data: blob:; font-src 'self' data:; connect-src 'self'; "
    "worker-src 'self' blob:; manifest-src 'self'; object-src 'none'; base-uri 'self'; "
    "form-action 'self'; frame-ancestors 'none'"
)
_NO_CACHE = {"index.html", "sw.js", "registerSW.js", "manifest.webmanifest"}
_RESERVED = ("api/", "docs", "openapi.json")


def mount_web(app: FastAPI, dist: Path) -> bool:
    index = dist / "index.html"
    if not index.is_file():
        return False
    root = dist.resolve()

    @app.api_route("/{path:path}", methods=["GET", "HEAD"], include_in_schema=False)
    async def spa(path: str) -> FileResponse:
        if path.startswith(_RESERVED):
            raise HTTPException(status_code=404)
        candidate = (root / path).resolve() if path else index
        if path and (not candidate.is_relative_to(root) or not candidate.is_file()):
            # Missing files with an extension are real 404s; everything else is a client route.
            if Path(path).suffix:
                raise HTTPException(status_code=404)
            candidate = index
        headers = {"Content-Security-Policy": WEB_CSP}
        if candidate.name in _NO_CACHE or candidate == index:
            headers["Cache-Control"] = "no-cache"
        elif path.startswith("assets/"):
            headers["Cache-Control"] = "public, max-age=31536000, immutable"
        media_type = "text/javascript" if candidate.suffix == ".mjs" else None
        return FileResponse(candidate, headers=headers, media_type=media_type)

    return True

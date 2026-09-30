"""The API process serves the built web app with SPA fallback, caching rules and a strict CSP."""

from __future__ import annotations

from pathlib import Path

from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.web import WEB_CSP, mount_web


def make_client(tmp_path: Path) -> TestClient:
    (tmp_path / "assets").mkdir()
    (tmp_path / "index.html").write_text("<!doctype html><div id=root></div>", encoding="utf-8")
    (tmp_path / "assets" / "index-abc.js").write_text("console.log(1)", encoding="utf-8")
    (tmp_path / "assets" / "pdf.worker-x.mjs").write_text("//", encoding="utf-8")
    (tmp_path / "sw.js").write_text("//", encoding="utf-8")
    app = FastAPI()

    @app.get("/api/v1/ping")
    async def ping() -> dict[str, str]:
        return {"ok": "yes"}

    assert mount_web(app, tmp_path)
    return TestClient(app)


def test_client_routes_fall_back_to_index(tmp_path: Path) -> None:
    client = make_client(tmp_path)
    for path in ("/", "/admin/documents/123", "/admin/audit"):
        response = client.get(path)
        assert response.status_code == 200
        assert "id=root" in response.text
        assert response.headers["cache-control"] == "no-cache"
        assert response.headers["content-security-policy"] == WEB_CSP


def test_hashed_assets_are_cached_and_mjs_is_javascript(tmp_path: Path) -> None:
    client = make_client(tmp_path)
    js = client.get("/assets/index-abc.js")
    assert js.status_code == 200
    assert "immutable" in js.headers["cache-control"]
    worker = client.get("/assets/pdf.worker-x.mjs")
    assert worker.headers["content-type"].startswith("text/javascript")
    assert client.get("/sw.js").headers["cache-control"] == "no-cache"
    assert client.head("/assets/index-abc.js").status_code == 200


def test_api_routes_win_and_unknown_api_paths_are_404(tmp_path: Path) -> None:
    client = make_client(tmp_path)
    assert client.get("/api/v1/ping").json() == {"ok": "yes"}
    assert client.get("/api/v1/nope").status_code == 404
    assert client.get("/assets/missing.js").status_code == 404


def test_path_traversal_is_not_served(tmp_path: Path) -> None:
    (tmp_path.parent / "secret.txt").write_text("secret", encoding="utf-8")
    client = make_client(tmp_path)
    response = client.get("/..%2Fsecret.txt")
    assert "secret" not in response.text


def test_nothing_is_mounted_without_a_build(tmp_path: Path) -> None:
    assert mount_web(FastAPI(), tmp_path / "missing") is False

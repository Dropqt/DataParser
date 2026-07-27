"""Provera nove verzije — bez mreže, sa lažnim odgovorima GitHub-a."""

from __future__ import annotations

import io
import json
import urllib.error

import pytest

from eturista import update

LOCAL = "a" * 40
REMOTE = "b" * 40


@pytest.fixture(autouse=True)
def known_local_revision(monkeypatch):
    monkeypatch.setattr(update, "local_revision", lambda: LOCAL)


def fake_response(payload: dict):
    class _Response(io.BytesIO):
        def __enter__(self):
            return self

        def __exit__(self, *_exc):
            self.close()

    return _Response(json.dumps(payload).encode("utf-8"))


def patch_urlopen(monkeypatch, payload=None, error: Exception | None = None):
    def _urlopen(_request, timeout=None):
        if error is not None:
            raise error
        return fake_response(payload)

    monkeypatch.setattr(update.urllib.request, "urlopen", _urlopen)


def test_up_to_date(monkeypatch):
    patch_urlopen(monkeypatch, {"status": "identical", "ahead_by": 0, "commits": []})
    info = update.check_for_update()
    assert info is not None
    assert not info.available
    assert info.describe() == "Program je ažuran."


def test_behind_reports_commit_count_and_message(monkeypatch):
    patch_urlopen(monkeypatch, {
        "status": "ahead",
        "ahead_by": 3,
        "commits": [
            {"sha": "c" * 40, "commit": {"message": "prva"}},
            {"sha": REMOTE, "commit": {"message": "Popravljen unos datuma\n\ndetalji"}},
        ],
    })
    info = update.check_for_update()
    assert info.available
    assert info.behind_by == 3
    assert info.remote == REMOTE
    assert "zaostaješ 3 commit-a" in info.describe()
    assert "Popravljen unos datuma" in info.describe()
    assert "detalji" not in info.describe()   # samo prvi red poruke


def test_single_commit_uses_singular(monkeypatch):
    patch_urlopen(monkeypatch, {
        "status": "ahead", "ahead_by": 1,
        "commits": [{"sha": REMOTE, "commit": {"message": "sitnica"}}],
    })
    assert "zaostaješ 1 commit." in update.check_for_update().describe()


def test_local_ahead_is_not_an_update(monkeypatch):
    """Lokalno gurnut commit više ne sme da izgleda kao da fali nova verzija."""
    patch_urlopen(monkeypatch, {"status": "behind", "ahead_by": 0, "commits": []})
    info = update.check_for_update()
    assert not info.available


def test_diverged_is_reported(monkeypatch):
    patch_urlopen(monkeypatch, {
        "status": "diverged", "ahead_by": 2,
        "commits": [{"sha": REMOTE, "commit": {"message": "nesto"}}],
    })
    info = update.check_for_update()
    assert info.available and info.diverged
    assert "lokalnih izmena" in info.describe()


def test_no_network_returns_none(monkeypatch):
    patch_urlopen(monkeypatch, error=urllib.error.URLError("nema mreže"))
    assert update.check_for_update() is None


def test_unknown_local_revision_skips_check(monkeypatch):
    monkeypatch.setattr(update, "local_revision", lambda: None)
    assert update.check_for_update() is None


def test_falls_back_when_compare_fails(monkeypatch):
    """Ako lokalni commit nije gurnut, compare vraća 404 — padamo na poređenje sha."""
    calls = []

    def _urlopen(request, timeout=None):
        calls.append(request.full_url)
        if "/compare/" in request.full_url:
            raise urllib.error.HTTPError(request.full_url, 404, "Not Found", {}, None)
        return fake_response({"sha": REMOTE, "commit": {"message": "novije"}})

    monkeypatch.setattr(update.urllib.request, "urlopen", _urlopen)

    info = update.check_for_update()
    assert info is not None and info.available
    assert info.remote == REMOTE
    assert any("/compare/" in url for url in calls)


def test_fallback_detects_identical(monkeypatch):
    def _urlopen(request, timeout=None):
        if "/compare/" in request.full_url:
            raise urllib.error.HTTPError(request.full_url, 404, "Not Found", {}, None)
        return fake_response({"sha": LOCAL, "commit": {"message": "isti"}})

    monkeypatch.setattr(update.urllib.request, "urlopen", _urlopen)
    assert not update.check_for_update().available


def test_can_be_disabled_from_env(monkeypatch):
    monkeypatch.setenv("ETURISTA_PROVERA_AZURIRANJA", "false")
    assert update.is_enabled() is False
    monkeypatch.setenv("ETURISTA_PROVERA_AZURIRANJA", "ne")
    assert update.is_enabled() is False
    monkeypatch.delenv("ETURISTA_PROVERA_AZURIRANJA")
    assert update.is_enabled() is True


def test_request_sends_user_agent(monkeypatch):
    """GitHub odbija zahteve bez User-Agent zaglavlja."""
    seen = {}

    def _urlopen(request, timeout=None):
        seen.update(request.headers)
        return fake_response({"status": "identical", "ahead_by": 0, "commits": []})

    monkeypatch.setattr(update.urllib.request, "urlopen", _urlopen)
    update.check_for_update()
    assert any("user-agent" in key.lower() for key in seen)


def test_compare_url_points_at_github():
    info = update.UpdateInfo(behind_by=2, local=LOCAL, remote=REMOTE)
    assert info.compare_url.startswith("https://github.com/Dropqt/DataParser/compare/")


def test_fallback_does_not_alarm_when_local_is_ahead(monkeypatch):
    """Nepokrenut commit lokalno ne sme da izgleda kao da fali nova verzija."""
    def _urlopen(request, timeout=None):
        if "/compare/" in request.full_url:
            raise urllib.error.HTTPError(request.full_url, 404, "Not Found", {}, None)
        return fake_response({"sha": REMOTE, "commit": {"message": "stariji"}})

    monkeypatch.setattr(update.urllib.request, "urlopen", _urlopen)
    monkeypatch.setattr(update, "_git_contains", lambda sha: True)

    assert not update.check_for_update().available

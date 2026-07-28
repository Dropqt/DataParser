"""Provera da li na GitHub-u postoji novija verzija programa.

Repo je javan, pa nije potreban nikakav token. Šalje se običan GET ka GitHub API-ju i
ne prenosi se ništa o korisniku ni o gostima.

Poredi se **lokalni commit** sa granom ``main`` preko ``compare`` API-ja. Time se dobija
i tačan broj commit-a zaostatka, i nema lažne uzbune kad si lokalno ispred (npr. radiš na
nečemu što još nije gurnuto).

Ovo samo **javlja** da postoji novija verzija - ne instalira ništa.
"""

from __future__ import annotations

import json
import os
import subprocess
import urllib.error
import urllib.request
from dataclasses import dataclass
from pathlib import Path

from .config import app_dir

GITHUB_REPO = "Dropqt/DataParser"
BRANCH = "main"

_API = f"https://api.github.com/repos/{GITHUB_REPO}"
_HEADERS = {
    # GitHub odbija zahteve bez User-Agent zaglavlja.
    "User-Agent": f"eturista-prijava ({GITHUB_REPO})",
    "Accept": "application/vnd.github+json",
}

#: Fajl koji se upisuje pri pakovanju, jer spakovan .exe nema uz sebe git istoriju.
REVISION_FILE = "revision.txt"

DEFAULT_TIMEOUT = 5.0


@dataclass(frozen=True)
class UpdateInfo:
    behind_by: int
    local: str
    remote: str
    last_message: str = ""
    diverged: bool = False

    @property
    def available(self) -> bool:
        return self.behind_by > 0

    @property
    def compare_url(self) -> str:
        return f"https://github.com/{GITHUB_REPO}/compare/{self.local[:12]}...{BRANCH}"

    def describe(self) -> str:
        if not self.available:
            return "Program je ažuran."
        commits = "commit" if self.behind_by == 1 else "commit-a"
        text = f"Dostupna je novija verzija - zaostaješ {self.behind_by} {commits}."
        if self.last_message:
            text += f"\nPoslednja izmena: {self.last_message}"
        if self.diverged:
            text += "\n(Imaš i lokalnih izmena kojih nema na GitHub-u.)"
        return text


def is_enabled() -> bool:
    """Provera se može isključiti sa ETURISTA_PROVERA_AZURIRANJA=false u .env."""
    raw = os.getenv("ETURISTA_PROVERA_AZURIRANJA", "").strip().lower()
    return raw not in {"0", "false", "ne", "no"}


def local_revision() -> str | None:
    """Commit na kom je ova kopija programa.

    Prvo se gleda ``revision.txt`` (upisuje se pri pakovanju u .exe), pa tek onda git -
    spakovana aplikacija nema git uz sebe.
    """
    baked = app_dir() / REVISION_FILE
    if baked.exists():
        try:
            value = baked.read_text(encoding="utf-8").strip()
            if value:
                return value[:40]
        except OSError:
            pass

    try:
        result = subprocess.run(
            ["git", "rev-parse", "HEAD"],
            cwd=app_dir(),
            capture_output=True,
            text=True,
            timeout=5,
        )
    except (OSError, subprocess.SubprocessError):
        return None

    if result.returncode != 0:
        return None
    return result.stdout.strip() or None


def _get_json(url: str, timeout: float) -> dict | None:
    request = urllib.request.Request(url, headers=_HEADERS)
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            return json.loads(response.read().decode("utf-8"))
    except (urllib.error.URLError, urllib.error.HTTPError, TimeoutError, OSError, ValueError):
        # Nema mreže, GitHub ne odgovara, prekoračen limit zahteva - sve isto:
        # provera ažuriranja nikad ne sme da smeta pokretanju programa.
        return None


def check_for_update(timeout: float = DEFAULT_TIMEOUT) -> UpdateInfo | None:
    """Vrati stanje u odnosu na ``main``, ili None ako se ne može utvrditi."""
    local = local_revision()
    if not local:
        return None

    data = _get_json(f"{_API}/compare/{local}...{BRANCH}", timeout)

    if data is None or "status" not in data:
        # Lokalni commit GitHub ne poznaje (nije gurnut) - padamo na prosto poređenje.
        return _fallback(local, timeout)

    remote = (data.get("commits") or [{}])[-1].get("sha") or local
    message = ""
    commits = data.get("commits") or []
    if commits:
        message = (commits[-1].get("commit", {}).get("message") or "").splitlines()[0]

    return UpdateInfo(
        behind_by=int(data.get("ahead_by") or 0),
        local=local,
        remote=remote,
        last_message=message,
        diverged=data.get("status") == "diverged",
    )


def _git_contains(commit: str) -> bool:
    """Da li lokalna istorija već sadrži taj commit.

    Rešava najčešći lažni alarm: radiš na nečemu što još nije gurnuto, pa je lokalni
    commit nepoznat GitHub-u - a ti si zapravo *ispred* main-a, ne iza njega.
    """
    try:
        result = subprocess.run(
            ["git", "merge-base", "--is-ancestor", commit, "HEAD"],
            cwd=app_dir(),
            capture_output=True,
            timeout=5,
        )
    except (OSError, subprocess.SubprocessError):
        return False
    return result.returncode == 0


def _fallback(local: str, timeout: float) -> UpdateInfo | None:
    """Kad compare ne prolazi (lokalni commit nije gurnut): uporedi poslednji commit."""
    data = _get_json(f"{_API}/commits/{BRANCH}", timeout)
    if data is None or not data.get("sha"):
        return None

    remote = data["sha"]
    if remote == local or _git_contains(remote):
        return UpdateInfo(behind_by=0, local=local, remote=remote)

    message = (data.get("commit", {}).get("message") or "").splitlines()[0]
    # Ne znamo koliko commit-a je razlika, ali znamo da main ima nešto što mi nemamo.
    return UpdateInfo(behind_by=1, local=local, remote=remote, last_message=message)


def update_hint() -> str:
    """Kako da korisnik povuče novu verziju."""
    if (app_dir() / ".git").exists():
        return "Ažuriranje:  git pull  pa ponovo pokreni program."
    return f"Preuzmi novu verziju sa: https://github.com/{GITHUB_REPO}"

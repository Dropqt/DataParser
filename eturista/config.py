"""Podešavanja iz .env i putanje do foldera."""

from __future__ import annotations

import os
import subprocess
import sys
from dataclasses import dataclass
from datetime import date
from pathlib import Path

from dotenv import load_dotenv


def app_dir() -> Path:
    """Folder pored aplikacije — tu žive .env, baza, vaučeri i screenshot-ovi.

    Kad je spakovano PyInstaller-om ``__file__`` pokazuje u privremeni raspakovani
    folder, pa se mora gledati gde stoji sam .exe.
    """
    if getattr(sys, "frozen", False):
        return Path(sys.executable).resolve().parent
    return Path(__file__).resolve().parent.parent


def _path_from_env(key: str, default: Path) -> Path:
    raw = os.getenv(key, "").strip()
    return Path(raw).expanduser() if raw else default


@dataclass(frozen=True)
class Config:
    portal_url: str
    pdf_dir: Path
    screenshot_dir: Path
    db_path: Path
    year: int
    headless: bool

    @classmethod
    def load(cls) -> "Config":
        root = app_dir()
        load_dotenv(root / ".env")

        raw_year = os.getenv("ETURISTA_GODINA", "").strip()
        return cls(
            portal_url=os.getenv("ETURISTA_URL", "https://www.portal.eturista.gov.rs").rstrip("/"),
            pdf_dir=_path_from_env("ETURISTA_PDF_DIR", root / "vauceri"),
            screenshot_dir=_path_from_env("ETURISTA_SCREENSHOT_DIR", root / "screenshots"),
            db_path=_path_from_env("ETURISTA_DB", root / "eturista.db"),
            year=int(raw_year) if raw_year.isdigit() else date.today().year,
            headless=os.getenv("ETURISTA_HEADLESS", "").strip().lower() in {"1", "true", "da", "yes"},
        )

    def ensure_dirs(self) -> None:
        self.pdf_dir.mkdir(parents=True, exist_ok=True)
        self.screenshot_dir.mkdir(parents=True, exist_ok=True)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)


def env_leak_warning() -> str | None:
    """Vrati upozorenje ako je .env ušao u git — repo je javan, pa ovo košta ništa.

    Vraća None kad je sve u redu (nema .env, nije git repo, ili .env nije praćen).
    """
    root = app_dir()
    if not (root / ".env").exists() or not (root / ".git").exists():
        return None
    try:
        result = subprocess.run(
            ["git", "ls-files", "--error-unmatch", ".env"],
            cwd=root,
            capture_output=True,
            timeout=5,
        )
    except (OSError, subprocess.SubprocessError):
        return None

    if result.returncode == 0:
        return (
            "UPOZORENJE: fajl .env sa lozinkama je u git indeksu i može da završi na GitHub-u.\n"
            "Skloni ga sa:  git rm --cached .env  pa promeni lozinke naloga."
        )
    return None

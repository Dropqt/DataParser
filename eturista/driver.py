"""Pravljenje Chrome drajvera i preuzimanje fajlova.

Dve stvari koje su u prvoj turi bile pogrešne i ovde su rešene:

1. **PDF se otvarao u pregledaču umesto da se snimi.** Bez
   ``plugins.always_open_pdf_externally`` browser prikaže vaučer u ugrađenom PDF
   vieweru i nikakav fajl ne stigne na disk — zato preimenovanje nikad nije radilo.
2. **Preimenovanje "najskorijeg fajla u ~/Downloads".** To je pogađanje: uhvati tuđi
   fajl, ili uhvati nedovršen download. Ovde se pamti stanje foldera pre klika i čeka
   se da se pojavi tačno jedan nov, završen fajl.
"""

from __future__ import annotations

import shutil
import tempfile
import time
from pathlib import Path

from selenium import webdriver
from selenium.common.exceptions import WebDriverException
from selenium.webdriver.chrome.options import Options

from .errors import ErrorKind, PortalError

#: Nazivi Chrome/Chromium izvršnih fajlova, redom kojim ih tražimo.
_CHROME_BINARIES = (
    "google-chrome",
    "google-chrome-stable",
    "chrome",
    "chromium",
    "chromium-browser",
)

#: Nastavci koje Chrome koristi dok download traje.
_PARTIAL_SUFFIXES = (".crdownload", ".part", ".tmp", ".partial")


def find_chrome_binary() -> str | None:
    """Nađi Chrome ili Chromium na sistemu. None znači "neka Selenium sam traži"."""
    for name in _CHROME_BINARIES:
        path = shutil.which(name)
        if path:
            return path
    return None


class BrowserSession:
    """Jedan browser sa svojim profilom i svojim folderom za preuzimanje.

    Svaka sesija ima **zaseban** profil i download folder, pa paralelni režim (2-3
    naloga odjednom) ne traži nikakve izmene — samo se napravi više sesija.
    """

    def __init__(
        self,
        download_dir: Path,
        headless: bool = False,
        window_size: tuple[int, int] = (1400, 1000),
    ) -> None:
        self.download_dir = Path(download_dir)
        self.download_dir.mkdir(parents=True, exist_ok=True)
        self.headless = headless
        self.window_size = window_size
        self._profile_dir: Path | None = None
        self.driver: webdriver.Chrome | None = None

    # -- životni ciklus ---------------------------------------------------

    def start(self) -> webdriver.Chrome:
        options = Options()

        binary = find_chrome_binary()
        if binary:
            options.binary_location = binary

        self._profile_dir = Path(tempfile.mkdtemp(prefix="eturista-profil-"))
        options.add_argument(f"--user-data-dir={self._profile_dir}")
        options.add_argument(f"--window-size={self.window_size[0]},{self.window_size[1]}")
        options.add_argument("--no-first-run")
        options.add_argument("--no-default-browser-check")
        options.add_argument("--disable-notifications")
        if self.headless:
            options.add_argument("--headless=new")

        options.add_experimental_option(
            "prefs",
            {
                "download.default_directory": str(self.download_dir),
                "download.prompt_for_download": False,
                "download.directory_upgrade": True,
                "savefile.default_directory": str(self.download_dir),
                # Bez ovoga Chrome prikaže PDF u vieweru i fajl nikad ne stigne na disk.
                "plugins.always_open_pdf_externally": True,
                "profile.default_content_setting_values.automatic_downloads": 1,
                "credentials_enable_service": False,
                "profile.password_manager_enabled": False,
            },
        )
        options.add_experimental_option("excludeSwitches", ["enable-automation"])

        try:
            self.driver = webdriver.Chrome(options=options)
        except WebDriverException as exc:
            raise PortalError(
                ErrorKind.BROWSER_CRASHED,
                "Ne mogu da pokrenem Chrome — proveri da je instaliran",
                str(exc),
            ) from exc

        self.driver.set_page_load_timeout(60)
        return self.driver

    def quit(self) -> None:
        if self.driver is not None:
            try:
                self.driver.quit()
            except WebDriverException:
                pass
            self.driver = None
        if self._profile_dir is not None:
            shutil.rmtree(self._profile_dir, ignore_errors=True)
            self._profile_dir = None

    def __enter__(self) -> "BrowserSession":
        self.start()
        return self

    def __exit__(self, *_exc: object) -> None:
        self.quit()

    # -- preuzimanje ------------------------------------------------------

    def snapshot_downloads(self) -> set[Path]:
        """Zapamti šta je u download folderu pre nego što kliknemo na preuzimanje."""
        return set(self.download_dir.glob("*"))

    def wait_for_download(
        self,
        before: set[Path],
        timeout: float = 60.0,
        settle: float = 0.4,
    ) -> Path:
        """Sačekaj nov, **završen** fajl i vrati njegovu putanju.

        Završen znači: nije ``.crdownload``, postoji, i veličina mu se ne menja ``settle``
        sekundi zaredom (Chrome ume da ukloni ``.crdownload`` pre poslednjeg upisa).
        """
        deadline = time.monotonic() + timeout
        stable_size: int | None = None
        stable_since: float | None = None

        while time.monotonic() < deadline:
            new_files = [
                path for path in self.download_dir.glob("*")
                if path not in before and path.is_file()
            ]
            finished = [p for p in new_files if p.suffix.lower() not in _PARTIAL_SUFFIXES]

            if finished:
                newest = max(finished, key=lambda p: p.stat().st_mtime)
                size = newest.stat().st_size
                now = time.monotonic()
                if size > 0 and size == stable_size:
                    if stable_since is not None and now - stable_since >= settle:
                        return newest
                else:
                    stable_size, stable_since = size, now

            time.sleep(0.2)

        in_progress = [p.name for p in self.download_dir.glob("*") if p not in before]
        raise PortalError(
            ErrorKind.PDF_DOWNLOAD_FAILED,
            "Vaučer nije preuzet u predviđenom vremenu",
            f"u folderu: {in_progress or 'ništa novo'}",
        )


def unique_path(directory: Path, filename: str) -> Path:
    """Putanja koja ne gazi postojeći fajl: ime.pdf → ime (2).pdf → ime (3).pdf …"""
    candidate = directory / filename
    if not candidate.exists():
        return candidate
    stem, suffix = candidate.stem, candidate.suffix
    for counter in range(2, 1000):
        candidate = directory / f"{stem} ({counter}){suffix}"
        if not candidate.exists():
            return candidate
    raise PortalError(ErrorKind.PDF_DOWNLOAD_FAILED, f"Previše fajlova sa imenom {filename}")

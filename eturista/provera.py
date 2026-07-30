"""Provera da li na ovom računaru ima sve što aplikaciji treba.

Zove je ``postavi.bat`` posle instalacije, i korisnik ručno kad nešto neće da radi.
Logika stoji ovde, a ne u `.bat` fajlu, iz dva razloga: `.bat` se ne može testirati,
a ista provera onda radi i na Linux-u i na Windows-u.

Ispis je namerno **bez kvačica i bez znakova van ASCII-ja**: izlazi u CMD prozor, koji
koristi staru kodnu stranu, pa bi se "š" i "ć" prikazali kao smeće. Isto pravilo važi
i za `.bat` fajlove u ovom repou.

Modul ne sme da uveze PySide6 ni selenium na vrhu - upravo njihovo odsustvo je jedan
od nalaza koje treba prijaviti, a ne pad sa trejsbekom.
"""

from __future__ import annotations

import importlib.util
import shutil
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path

#: Najstariji Python na kom aplikacija radi. Isto piše i u postavi.bat.
MIN_PYTHON = (3, 10)

#: Biblioteke koje moraju da postoje, i zašto - da poruka kaže šta se gubi bez njih.
_REQUIRED = (
    ("PySide6", "prozor aplikacije"),
    ("selenium", "upravljanje Chrome-om"),
    ("dotenv", "citanje .env fajla"),
    ("pypdf", "citanje PDF vaucera"),
    ("reportlab", "sloj sa potpisom"),
    ("PIL", "obrada slike potpisa"),
)


@dataclass(frozen=True)
class Nalaz:
    """Jedan red izveštaja."""

    naziv: str
    ok: bool
    poruka: str
    #: Neobavezan nalaz ne obara izlazni kod - program radi i bez njega.
    obavezno: bool = True

    @property
    def oznaka(self) -> str:
        if self.ok:
            return "[u redu]"
        return "[GRESKA]" if self.obavezno else "[pazi]  "


def proveri_python() -> Nalaz:
    verzija = ".".join(str(broj) for broj in sys.version_info[:3])
    if sys.version_info >= MIN_PYTHON:
        return Nalaz("Python", True, verzija)
    trazeno = ".".join(str(broj) for broj in MIN_PYTHON)
    return Nalaz(
        "Python", False,
        f"{verzija} je prestar, treba {trazeno} ili noviji - https://www.python.org/downloads/",
    )


def proveri_biblioteke() -> Nalaz:
    """Da li se biblioteke uopšte vide iz ovog Pythona.

    ``find_spec`` umesto ``import``: uvoz PySide6 traje sekundama i povlači Qt, a ovde
    je pitanje samo da li je paket instaliran.
    """
    fale = [
        f"{ime} ({zasto})"
        for ime, zasto in _REQUIRED
        if importlib.util.find_spec(ime) is None
    ]
    if not fale:
        return Nalaz("Biblioteke", True, f"svih {len(_REQUIRED)} na broju")
    return Nalaz(
        "Biblioteke", False,
        "fale: " + ", ".join(fale) + "  -> pokreni postavi.bat ponovo",
    )


def proveri_chrome() -> Nalaz:
    from .driver import find_chrome_binary

    putanja = find_chrome_binary()
    if putanja:
        return Nalaz("Chrome", True, putanja)
    return Nalaz(
        "Chrome", False,
        "nije nadjen - aplikacija prijavljuje goste kroz Chrome i bez njega ne radi. "
        "https://www.google.com/chrome/",
    )


def proveri_git() -> Nalaz:
    """Git nije nužan za rad, ali bez njega azuriraj.bat i provera verzije ćute."""
    putanja = shutil.which("git")
    if putanja:
        return Nalaz("Git", True, putanja, obavezno=False)
    return Nalaz(
        "Git", False,
        "nije nadjen - azuriraj.bat i provera nove verzije nece raditi. "
        "https://git-scm.com/download/win",
        obavezno=False,
    )


def proveri_env() -> Nalaz:
    """Da li ima .env i bar jedan popunjen nalog."""
    from .accounts import load_accounts
    from .config import Config, app_dir

    putanja = app_dir() / ".env"
    if not putanja.is_file():
        return Nalaz(
            "Nalozi", False,
            "nema .env fajla - pokreni aplikaciju pa Alatke -> Podesavanja",
            obavezno=False,
        )

    Config.load()  # ucita .env u okruzenje
    nalozi = load_accounts()
    if not nalozi:
        return Nalaz(
            "Nalozi", False,
            "u .env nema nijednog popunjenog naloga - Alatke -> Podesavanja",
            obavezno=False,
        )
    return Nalaz("Nalozi", True, ", ".join(n.label for n in nalozi), obavezno=False)


def proveri_foldere() -> Nalaz:
    """Da li folderi za vaučere, screenshot-ove i bazu mogu da se naprave i pišu."""
    from .config import Config

    config = Config.load()
    try:
        config.ensure_dirs()
    except OSError as exc:
        return Nalaz("Folderi", False, f"ne mogu da se naprave: {exc}")

    for folder in (config.pdf_dir, config.screenshot_dir):
        proba = folder / ".proba-upisa"
        try:
            proba.write_text("", encoding="utf-8")
            proba.unlink()
        except OSError:
            return Nalaz("Folderi", False, f"nema prava upisa u {folder}")
    return Nalaz("Folderi", True, str(config.pdf_dir))


def pripremi_drajver() -> Nalaz:
    """Natera Selenium da skine chromedriver dok korisnik sigurno ima internet.

    Bez ovoga se drajver skida pri prvom pokretanju ture - tridesetak sekundi tišine
    baš kad je najmanje zgodno.
    """
    import tempfile

    from .driver import BrowserSession

    session = BrowserSession(download_dir=Path(tempfile.mkdtemp()), headless=True)
    try:
        session.start()
        return Nalaz("Chrome drajver", True, "preuzet i radi", obavezno=False)
    except Exception as exc:
        return Nalaz(
            "Chrome drajver", False,
            f"jos nije preuzet ({exc}) - prvo pokretanje trazi internet",
            obavezno=False,
        )
    finally:
        session.quit()


def proveri_sistem(sa_drajverom: bool = False) -> list[Nalaz]:
    biblioteke = proveri_biblioteke()
    nalazi = [proveri_python(), biblioteke]

    # Sve ispod ovoga uvozi selenium ili dotenv. Kad njih nema, provera bi pukla sa
    # trejsbekom umesto da kaze sta fali - a upravo to je nalaz koji korisniku treba.
    if not biblioteke.ok:
        nalazi.append(
            Nalaz("Ostalo", False, "ne proverava se dok biblioteke ne budu instalirane",
                  obavezno=False)
        )
        return nalazi

    nalazi += [proveri_chrome(), proveri_git(), proveri_foldere(), proveri_env()]
    if sa_drajverom:
        nalazi.append(pripremi_drajver())
    return nalazi


def ispisi(nalazi: list[Nalaz]) -> int:
    """Ispiši izveštaj. Vrati 0 kad je sve obavezno u redu, inače 1."""
    print("Provera sistema")
    print("=" * 66)
    for nalaz in nalazi:
        print(f"{nalaz.oznaka} {nalaz.naziv:15} {nalaz.poruka}")
    print("=" * 66)

    problemi = [n for n in nalazi if not n.ok and n.obavezno]
    upozorenja = [n for n in nalazi if not n.ok and not n.obavezno]

    if problemi:
        print(f"Nesto nedostaje ({len(problemi)}). Aplikacija jos ne moze da radi.")
    elif upozorenja:
        print("Sve bitno je na broju. Ono sto je oznaceno sa [pazi] moze i kasnije.")
    else:
        print("Sve je na broju.")
    return 1 if problemi else 0

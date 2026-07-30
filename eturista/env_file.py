"""Čitanje i upis .env fajla, uz čuvanje komentara.

.env je jedino mesto gde stoje lozinke, pa se nikad ne piše preko njega u mestu:
upisuje se u privremeni fajl u istom folderu, pa se atomično zameni. Ako upis pukne
nasred posla, original ostaje onakav kakav je bio.

Komentari se čuvaju zato što su oni pravo uputstvo - `.env.example` objašnjava svaki
ključ, i ta objašnjenja ne smeju da nestanu čim se jednom snimi iz aplikacije.
"""

from __future__ import annotations

import os
import re
from pathlib import Path

from dotenv import dotenv_values, load_dotenv

from .accounts import MAX_ACCOUNTS
from .config import app_dir

#: Red oblika ``KLJUC=vrednost``. Vodeći ``#`` namerno nije dozvoljen, da se
#: zakomentarisani primeri iz .env.example ne bi prepisivali.
_ASSIGNMENT = re.compile(r"^\s*(?:export\s+)?([A-Za-z_][A-Za-z0-9_]*)\s*=")

#: Ključevi koji nisu vezani za nalog, redom kojim stoje u .env.example.
GENERAL_KEYS = (
    "ETURISTA_URL",
    "ETURISTA_PDF_DIR",
    "ETURISTA_EMAIL",
    "ETURISTA_SCREENSHOT_DIR",
    "ETURISTA_POTPIS_VISINA",
    "ETURISTA_POTPIS_POMAK_X",
    "ETURISTA_POTPIS_POMAK_Y",
    "ETURISTA_POTPIS_MAX_SIRINA",
    "ETURISTA_DB",
    "ETURISTA_GODINA",
    "ETURISTA_HEADLESS",
    "ETURISTA_PROVERA_AZURIRANJA",
)


def account_keys(i: int) -> tuple[str, str, str, str]:
    """Ključevi jednog naloga: naziv, korisnik, lozinka, potpis."""
    return (
        f"ETURISTA_NALOG{i}_NAZIV",
        f"ETURISTA_NALOG{i}_USER",
        f"ETURISTA_NALOG{i}_PASS",
        f"ETURISTA_NALOG{i}_POTPIS",
    )


#: Svi ključevi kojima aplikacija upravlja. Dijalog uvek upisuje sve, i prazne - da bi
#: ``reload()`` mogao da pregazi i ono što je korisnik obrisao.
MANAGED_KEYS = tuple(
    key for i in range(1, MAX_ACCOUNTS + 1) for key in account_keys(i)
) + GENERAL_KEYS


def env_path() -> Path:
    return app_dir() / ".env"


def example_path() -> Path:
    return app_dir() / ".env.example"


def read_env(path: Path | None = None) -> dict[str, str]:
    """Vrednosti iz .env fajla. Nepostojeći fajl daje prazan rečnik."""
    path = path or env_path()
    if not path.is_file():
        return {}
    return {key: (value or "") for key, value in dotenv_values(path).items()}


def _quote(value: str) -> str:
    """Vrednost onako kako se sme upisati u .env.

    Navodnici se stavljaju samo kad zatreba - inače bi ceo fajl posle prvog snimanja
    izgledao drugačije nego .env.example, pa bi se poređenje sa primerom izgubilo.

    Razmaci se čuvaju od slova do slova: lozinka sme da ima i dva razmaka zaredom, a
    tiho "sređivanje" bi napravilo prijavu koja ne radi bez ijedne poruke. Skidaju se
    samo prelomi reda, koje jedan red u .env ionako ne može da ponese.
    """
    value = value.replace("\r", "").replace("\n", "")
    if value != value.strip() or any(ch in value for ch in "#\"'\\"):
        return '"' + value.replace("\\", "\\\\").replace('"', '\\"') + '"'
    return value


def merge_lines(lines: list[str], values: dict[str, str]) -> list[str]:
    """Ugradi vrednosti u postojeće redove, ne dirajući komentare.

    Red sa poznatim ključem se menja u mestu; sve ostalo - komentari, prazni redovi,
    tuđi ključevi - prepisuje se doslovno. Ključ koga nema se dopisuje na kraj.

    Ako se isti ključ u fajlu pojavi više puta, menjaju se **sve** pojave. Menjati samo
    prvu bi bilo gore nego ne dirati ništa: ``dotenv`` čita poslednju, pa bi se snimila
    nova vrednost a program bi i dalje radio sa starom.
    """
    out: list[str] = []
    written: set[str] = set()

    for line in lines:
        match = _ASSIGNMENT.match(line)
        key = match.group(1) if match else None
        if key is not None and key in values:
            out.append(f"{key}={_quote(values[key])}")
            written.add(key)
        else:
            out.append(line)

    missing = [key for key in values if key not in written]
    if missing:
        out.append("")
        out.append("# ---- Dodato iz aplikacije ----")
        out.extend(f"{key}={_quote(values[key])}" for key in missing)
    return out


def write_env(values: dict[str, str], path: Path | None = None) -> Path:
    """Upiši vrednosti u .env, čuvajući komentare.

    Kad .env još ne postoji, kreće se od .env.example da bi se dobila i sva
    objašnjenja. Piše se u privremeni fajl pa ``os.replace``, koji je u istom
    folderu atomičan - prekid usred upisa ne ostavlja polupisan fajl sa lozinkama.
    """
    path = path or env_path()
    source = path if path.is_file() else example_path()
    lines = source.read_text(encoding="utf-8").splitlines() if source.is_file() else []

    merged = merge_lines(lines, values)
    tmp = path.with_name(path.name + ".tmp")
    try:
        tmp.write_text("\n".join(merged) + "\n", encoding="utf-8", newline="\n")
        os.replace(tmp, path)
    except OSError:
        tmp.unlink(missing_ok=True)
        raise

    try:
        # Lozinke - neka fajl čita samo vlasnik. Na Windows-u nema efekta i ne smeta.
        os.chmod(path, 0o600)
    except OSError:
        pass
    return path


def create_if_missing(path: Path | None = None) -> Path:
    """Napravi .env iz .env.example ako ga nema. Postojeći se ne dira."""
    path = path or env_path()
    if not path.is_file():
        write_env({}, path)
    return path


def reload(path: Path | None = None) -> None:
    """Ponovo učitaj .env preko onoga što je već u okruženju.

    ``override=True`` je ovde suština: ``load_dotenv`` podrazumevano **ne** menja
    promenljivu koja već stoji u ``os.environ``. Bez toga bi program posle snimanja
    novih podešavanja i dalje radio sa starom lozinkom, a da se ništa ne požali.
    """
    load_dotenv(path or env_path(), override=True)

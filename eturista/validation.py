"""Provera JMBG-a i parsiranje datuma boravka.

Ovo je najvažniji deo za "evidenciju grešaka": većina pogrešnih JMBG-ova su tipfeleri,
a tipfeler se skoro uvek vidi po kontrolnoj cifri - dakle uhvatimo ga ovde, pre nego što
browser uopšte krene, i red pocrveni odmah pri lepljenju iz Excela.
"""

from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass
from datetime import date, timedelta

from .errors import ErrorKind, ValidationError

# ---------------------------------------------------------------------------
# JMBG
# ---------------------------------------------------------------------------

JMBG_LENGTH = 13

#: Kontrolne težine za cifre 1-12 (videti `jmbg_check_digit`).
_WEIGHTS = (7, 6, 5, 4, 3, 2, 7, 6, 5, 4, 3, 2)

#: Granica za razlikovanje 19xx od 20xx godišta. Cifre GGG su godina po modulu 1000:
#: 800-999 -> 1800-1999, 000-799 -> 2000-2799.
_YEAR_PIVOT = 800

_REGIONS: dict[range, str] = {
    range(0, 10): "stranac / posebno",
    range(10, 20): "Bosna i Hercegovina",
    range(20, 30): "Crna Gora",
    range(30, 40): "Hrvatska",
    range(41, 50): "Severna Makedonija",
    range(50, 60): "Slovenija",
    range(70, 80): "centralna Srbija",
    range(80, 90): "Vojvodina",
    range(90, 100): "Kosovo",
}


@dataclass(frozen=True)
class JmbgInfo:
    """Rezultat uspešne provere JMBG-a."""

    jmbg: str
    birth_date: date
    region_code: int
    region_name: str
    is_female: bool
    #: Popunjeno kad smo morali da popravimo unos (npr. Excel je pojeo vodeću nulu).
    note: str = ""

    @property
    def gender_label(self) -> str:
        return "Ž" if self.is_female else "M"


def jmbg_check_digit(first_twelve: str) -> int:
    """Izračunaj 13. (kontrolnu) cifru JMBG-a iz prvih dvanaest.

    m = 11 - ((7(a+g) + 6(b+h) + 5(c+i) + 4(d+j) + 3(e+k) + 2(f+l)) mod 11)
    Ako je m između 1 i 9 kontrolna cifra je m; ako je 10 ili 11, kontrolna cifra je 0.
    """
    if len(first_twelve) != 12 or not first_twelve.isdigit():
        raise ValueError("Očekujem tačno 12 cifara")
    total = sum(w * int(d) for w, d in zip(_WEIGHTS, first_twelve))
    m = 11 - (total % 11)
    return m if 1 <= m <= 9 else 0


def _region_name(code: int) -> str:
    for span, name in _REGIONS.items():
        if code in span:
            return name
    return "nepoznata oblast"


def clean_jmbg(raw: str) -> tuple[str, str]:
    """Očisti JMBG kako stiže iz Excela i vrati (očišćen, napomena).

    Rešava dve stvari koje se u praksi stalno dešavaju:

    * Excel čuva JMBG kao broj pa pojede vodeću nulu - gosti rođeni 1-9. u mesecu
      stignu sa 12 cifara. Ako dodavanje nule daje ispravan JMBG, popravljamo ćutke
      i beležimo napomenu.
    * Excel prikaže dugačak broj u naučnoj notaciji (``1,01991E+12``). Tu se cifre
      nepovratno gube, pa se to mora vratiti korisniku kao greška.
    """
    text = (raw or "").strip()
    if not text:
        return "", ""

    if re.search(r"[eE]\+?\d+", text):
        raise ValidationError(
            ErrorKind.JMBG_INVALID_LOCAL,
            "JMBG je iz Excela stigao kao naučna notacija - formatiraj kolonu kao Tekst pa kopiraj ponovo",
        )

    digits = re.sub(r"\D", "", text)
    if not digits:
        raise ValidationError(ErrorKind.JMBG_INVALID_LOCAL, f"JMBG ne sadrži cifre: {text!r}")

    if len(digits) == JMBG_LENGTH - 1:
        candidate = "0" + digits
        if _has_valid_check_digit(candidate):
            return candidate, "dodata vodeća nula (Excel ju je pojeo)"

    return digits, ""


def _has_valid_check_digit(jmbg: str) -> bool:
    return (
        len(jmbg) == JMBG_LENGTH
        and jmbg.isdigit()
        and jmbg_check_digit(jmbg[:12]) == int(jmbg[12])
    )


def validate_jmbg(raw: str) -> JmbgInfo:
    """Proveri JMBG i vrati podatke iz njega. Baca ValidationError uz jasnu poruku."""
    jmbg, note = clean_jmbg(raw)

    if not jmbg:
        raise ValidationError(ErrorKind.MISSING_FIELD, "JMBG nije unet")

    if len(jmbg) != JMBG_LENGTH:
        raise ValidationError(
            ErrorKind.JMBG_INVALID_LOCAL,
            f"JMBG ima {len(jmbg)} cifara umesto {JMBG_LENGTH}",
        )

    day, month = int(jmbg[0:2]), int(jmbg[2:4])
    yyy = int(jmbg[4:7])
    year = 1000 + yyy if yyy >= _YEAR_PIVOT else 2000 + yyy

    try:
        birth = date(year, month, day)
    except ValueError:
        raise ValidationError(
            ErrorKind.JMBG_INVALID_LOCAL,
            f"JMBG sadrži nepostojeći datum rođenja ({jmbg[0:2]}.{jmbg[2:4]}.{year})",
        ) from None

    if birth > date.today():
        raise ValidationError(
            ErrorKind.JMBG_INVALID_LOCAL,
            f"Datum rođenja iz JMBG-a je u budućnosti ({birth:%d.%m.%Y})",
        )

    expected = jmbg_check_digit(jmbg[:12])
    if expected != int(jmbg[12]):
        raise ValidationError(
            ErrorKind.JMBG_INVALID_LOCAL,
            f"Pogrešna kontrolna cifra - poslednja treba da bude {expected}, a piše {jmbg[12]}",
        )

    region = int(jmbg[7:9])
    return JmbgInfo(
        jmbg=jmbg,
        birth_date=birth,
        region_code=region,
        region_name=_region_name(region),
        is_female=int(jmbg[9:12]) >= 500,
        note=note,
    )


# ---------------------------------------------------------------------------
# Datum boravka
# ---------------------------------------------------------------------------

#: Jedan datum: 5.10 / 05.10. / 5-10-2026 / 05/10/26 …
_ONE_DATE = re.compile(r"^(\d{1,2})\s*[.\-/]\s*(\d{1,2})(?:\s*[.\-/]\s*(\d{2,4}))?\.?$")

#: Kandidati za razdvajanje opsega, od najjasnijeg ka najdvosmislenijem.
_RANGE_SEPARATORS = ("–", "—", " do ", " Do ", " DO ", ";", ",", "/", " - ", "-")

#: Duži boravak od ovoga je skoro sigurno greška u unosu, ne prava rezervacija.
_MAX_NIGHTS = 120

#: Koliko noćenja se podrazumeva kad kolona "Dana" ostane prazna.
DEFAULT_DAYS = 5


@dataclass(frozen=True)
class Stay:
    """Raspon boravka gosta."""

    arrival: date
    departure: date
    #: Tekst kako je stigao iz Excela - čuvamo ga da bismo mogli da vratimo original.
    raw: str = ""

    @property
    def nights(self) -> int:
        return (self.departure - self.arrival).days

    def format(self) -> str:
        """Nedvosmislen prikaz koji ide nazad u Excel."""
        return f"{self.arrival:%d.%m.%Y}-{self.departure:%d.%m.%Y}"

    def __str__(self) -> str:
        return self.format()


def _parse_one_date(text: str, default_year: int) -> date | None:
    match = _ONE_DATE.match(text.strip())
    if not match:
        return None

    day, month = int(match.group(1)), int(match.group(2))
    raw_year = match.group(3)

    if raw_year is None:
        year = default_year
    elif len(raw_year) <= 2:
        year = 2000 + int(raw_year)
    else:
        year = int(raw_year)

    try:
        return date(year, month, day)
    except ValueError:
        return None


def _split_candidates(text: str) -> list[tuple[str, str]]:
    """Svi razumni načini da se tekst preseče na dva dela, boljim redom prvo."""
    out: list[tuple[str, str]] = []
    for sep in _RANGE_SEPARATORS:
        start = 0
        while (idx := text.find(sep, start)) != -1:
            out.append((text[:idx], text[idx + len(sep):]))
            start = idx + 1
    return out


def parse_stay(raw: str, default_year: int | None = None) -> Stay:
    """Parsiraj ``05.10-10.10``, ``5.10.2026 - 10.10.2026``, ``05/10 do 10/10`` …

    Godina se uzima iz teksta ako je ima, inače ``default_year``. Ako je datum odlaska
    ispred datuma dolaska, pretpostavlja se prelazak u narednu godinu (28.12-03.01).
    """
    text = (raw or "").strip()
    if not text:
        raise ValidationError(ErrorKind.MISSING_FIELD, "Datum boravka nije unet")

    year = default_year or date.today().year

    best: tuple[int, date, date] | None = None
    for left, right in _split_candidates(text):
        arrival = _parse_one_date(left, year)
        departure = _parse_one_date(right, year)
        if arrival is None or departure is None:
            continue
        # Presek gde obe strane imaju isti oblik je skoro uvek onaj pravi
        # ("05-10-2026 - 10-10-2026" ima tri crtice, samo jedna je razdvajač).
        score = (left.count(".") + left.count("-") + left.count("/")) == (
            right.count(".") + right.count("-") + right.count("/")
        )
        if best is None or score > best[0]:
            best = (int(score), arrival, departure)
            if score:
                break

    if best is None:
        raise ValidationError(
            ErrorKind.DATE_INVALID,
            f"Ne mogu da pročitam datum iz {text!r} - očekujem npr. 05.10-10.10",
        )

    _, arrival, departure = best
    rolled_over = False

    if departure < arrival:
        try:
            departure = departure.replace(year=departure.year + 1)
        except ValueError:  # 29. februar
            departure = departure.replace(year=departure.year + 1, day=28)
        rolled_over = True

    nights = (departure - arrival).days
    if nights <= 0:
        raise ValidationError(
            ErrorKind.DATE_INVALID,
            f"Datum odlaska mora biti posle dolaska ({arrival:%d.%m.%Y} → {departure:%d.%m.%Y})",
        )
    if nights > _MAX_NIGHTS:
        # Prelazak u narednu godinu smo pretpostavili sami; ako ispadne besmisleno dug
        # boravak, verovatnija je obična zamena mesta datuma nego novogodišnji boravak.
        if rolled_over:
            raise ValidationError(
                ErrorKind.DATE_INVALID,
                f"Datum odlaska je pre datuma dolaska ({text})",
            )
        raise ValidationError(
            ErrorKind.DATE_INVALID,
            f"Boravak od {nights} noćenja deluje kao greška u unosu ({arrival:%d.%m.%Y} → {departure:%d.%m.%Y})",
        )

    return Stay(arrival=arrival, departure=departure, raw=text)


def parse_arrival(raw: str, default_year: int | None = None) -> date:
    """Pročitaj jedan datum dolaska: ``05.10``, ``5.10.2026``, ``05/10``…"""
    text = (raw or "").strip()
    if not text:
        raise ValidationError(ErrorKind.MISSING_FIELD, "Datum dolaska nije unet")

    arrival = _parse_one_date(text, default_year or date.today().year)
    if arrival is None:
        raise ValidationError(
            ErrorKind.DATE_INVALID,
            f"Ne mogu da pročitam datum dolaska iz {text!r} - očekujem npr. 05.10 ili 05.10.2026",
        )
    return arrival


def parse_days(raw: str, default: int = DEFAULT_DAYS) -> int:
    """Pročitaj broj noćenja. Prazno polje znači ``default``.

    Prima i "5", i "5 dana", i "5 noćenja" - u tabeli se lako omakne da se dopiše reč.
    """
    text = (raw or "").strip()
    if not text:
        return default

    # Minus se traži posebno: `\d+` bi u "-3" uhvatio 3 i tiho pretvorio grešku u boravak.
    digits = re.search(r"-?\d+", text)
    if not digits:
        raise ValidationError(
            ErrorKind.DATE_INVALID,
            f"Broj dana nije broj: {text!r}",
        )

    days = int(digits.group())
    if days <= 0:
        raise ValidationError(ErrorKind.DATE_INVALID, "Broj dana mora biti bar 1")
    if days > _MAX_NIGHTS:
        raise ValidationError(
            ErrorKind.DATE_INVALID,
            f"Boravak od {days} noćenja deluje kao greška u unosu",
        )
    return days


def stay_from_days(arrival: date, days: int, raw: str = "") -> Stay:
    """Napravi raspon boravka od datuma dolaska i broja noćenja.

    Pet dana znači pet noćenja: 05.10 → 10.10, isto kao stari zapis ``05.10-10.10``.
    """
    return Stay(arrival=arrival, departure=arrival + timedelta(days=days), raw=raw)


def resolve_stay(
    date_raw: str,
    days_raw: str = "",
    default_year: int | None = None,
    default_days: int = DEFAULT_DAYS,
) -> Stay:
    """Odredi boravak iz kolona *Dolazak* i *Dana*.

    Ako u koloni sa datumom ipak stoji stari zapis sa opsegom (``05.10-10.10``), koristi
    se on - tako stare liste iz prve ture rade bez prepravke, a kolona *Dana* se ignoriše.
    """
    text = (date_raw or "").strip()
    if not text:
        raise ValidationError(ErrorKind.MISSING_FIELD, "Datum dolaska nije unet")

    if _looks_like_range(text, default_year):
        return parse_stay(text, default_year)

    arrival = parse_arrival(text, default_year)
    return stay_from_days(arrival, parse_days(days_raw, default_days), raw=text)


def _looks_like_range(text: str, default_year: int | None) -> bool:
    """Da li tekst sadrži dva datuma, a ne jedan."""
    if _parse_one_date(text, default_year or date.today().year) is not None:
        return False
    year = default_year or date.today().year
    return any(
        _parse_one_date(left, year) is not None and _parse_one_date(right, year) is not None
        for left, right in _split_candidates(text)
    )


# ---------------------------------------------------------------------------
# Imena
# ---------------------------------------------------------------------------

def clean_name(raw: str) -> str:
    """Skini višak razmaka i normalizuj Unicode (Excel ume da pošalje razložene znake)."""
    text = unicodedata.normalize("NFC", (raw or "").strip())
    return re.sub(r"\s+", " ", text)


def validate_name(raw: str, field_label: str) -> str:
    name = clean_name(raw)
    if not name:
        raise ValidationError(ErrorKind.MISSING_FIELD, f"{field_label} nije uneto")
    if any(ch.isdigit() for ch in name):
        raise ValidationError(
            ErrorKind.MISSING_FIELD,
            f"{field_label} sadrži cifre ({name!r}) - proveri da kolone nisu pomerene",
        )
    return name


# ---------------------------------------------------------------------------
# E-mail - po njemu se vaučeri razvrstavaju u foldere
# ---------------------------------------------------------------------------

#: Namerno labava provera. Posao ovoga nije da presudi da li adresa postoji, nego da
#: uhvati ono što očigledno nije e-mail - pomerenu kolonu, ime umesto adrese, dva
#: nalepljena maila u jednoj ćeliji.
_EMAIL_RE = re.compile(r"^[^@\s,;]+@[^@\s,;]+\.[A-Za-z]{2,}$")

#: Znaci koje Windows ne prima u imenu foldera. Na Linux-u smeta samo ``/``, ali naziv
#: mora biti isti na oba sistema - inače isti spisak gostiju pravi različite foldere.
_LOSI_ZA_FOLDER = '<>:"/\\|?*'


def validate_email(raw: str) -> str:
    """Vrati očišćen e-mail, ili prazan string ako ćelija nije popunjena.

    Prazno **nije greška** - takav gost ide u podrazumevani folder.
    """
    email = (raw or "").strip().strip("<>").lower()
    if not email:
        return ""
    if not _EMAIL_RE.match(email):
        raise ValidationError(
            ErrorKind.EMAIL_INVALID,
            f"E-mail ne izgleda ispravno ({email!r})",
        )
    return email


def email_folder(email: str) -> str:
    """Naziv foldera za datu adresu.

    Adresa se koristi kakva jeste, jer se folder gleda ljudskim okom i traži po imenu.
    Menjaju se samo znaci koje Windows ne prima, i tačke na kraju - Windows ih tiho
    odseca, pa bi folder posle imao drugo ime nego što kod misli.
    """
    naziv = "".join("_" if znak in _LOSI_ZA_FOLDER else znak for znak in email.strip())
    naziv = naziv.rstrip(" .")
    return naziv or "bez_adrese"


#: Znaci koje NFKD ne razlaže (đ, ђ i ćirilica uopšte) moraju ručno.
_TRANSLIT = {
    "đ": "dj", "ђ": "dj", "љ": "lj", "њ": "nj", "џ": "dz",
    "а": "a", "б": "b", "в": "v", "г": "g", "д": "d", "е": "e", "ж": "z",
    "з": "z", "и": "i", "ј": "j", "к": "k", "л": "l", "м": "m", "н": "n",
    "о": "o", "п": "p", "р": "r", "с": "s", "т": "t", "ћ": "c", "у": "u",
    "ф": "f", "х": "h", "ц": "c", "ч": "c", "ш": "s",
}


def latinize(text: str) -> str:
    """Ćirilica i dijakritika → ASCII. Koristi se samo za nazive PDF fajlova.

    Windows i Linux se razlikuju po tome kako pamte ne-ASCII nazive fajlova, pa se
    vaučeri imenuju čistim ASCII-jem da bi radili svuda: Đorđević → DJORDJEVIC.
    """
    lowered = "".join(_TRANSLIT.get(ch, ch) for ch in (text or "").lower())
    stripped = unicodedata.normalize("NFKD", lowered).encode("ascii", "ignore").decode()
    return re.sub(r"[^A-Za-z0-9]+", "_", stripped).strip("_")

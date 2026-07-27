"""Prenos podataka između Excela i aplikacije.

Excel (i LibreOffice) stavljaju u clipboard obične redove razdvojene tabovima, pa je
Ctrl+V ovde samo parsiranje TSV-a. Posao je u tome da se pogodi *koja kolona je šta*,
jer glavni Excel ne mora da ima kolone istim redom kao aplikacija.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

from .models import EXPORT_HEADERS, Guest
from .validation import latinize

# --- prepoznavanje zaglavlja ------------------------------------------------

_HEADER_ALIASES: dict[str, tuple[str, ...]] = {
    "surname": ("prezime", "prez", "surname", "lastname", "last_name"),
    "given_name": ("ime", "name", "firstname", "first_name", "given"),
    "jmbg": ("jmbg", "jmb", "maticni", "maticni_broj", "mb", "licni_broj"),
    "date": ("datum", "datumi", "date", "boravak", "termin", "od_do", "period", "noci"),
}

#: Kolone tipa "Ime i prezime" — jedna ćelija sa oba imena.
_FULL_NAME_HEADERS = ("ime_i_prezime", "imeiprezime", "gost", "putnik", "prezime_i_ime", "full_name")

# --- prepoznavanje po sadržaju ----------------------------------------------

_DATEISH = re.compile(r"\d{1,2}\s*[.\-/]\s*\d{1,2}")
_LETTER = re.compile(r"[^\W\d_]", re.UNICODE)


@dataclass
class ColumnMapping:
    """Koja kolona iz clipboard-a je koje polje. ``None`` znači da je nema."""

    surname: int | None = None
    given_name: int | None = None
    jmbg: int | None = None
    date: int | None = None
    full_name: int | None = None
    from_header: bool = False

    @property
    def is_usable(self) -> bool:
        has_name = self.full_name is not None or (self.surname is not None and self.given_name is not None)
        return has_name and self.jmbg is not None

    def describe(self) -> str:
        parts = []
        if self.full_name is not None:
            parts.append(f"ime+prezime→{self.full_name + 1}")
        else:
            if self.given_name is not None:
                parts.append(f"ime→{self.given_name + 1}")
            if self.surname is not None:
                parts.append(f"prezime→{self.surname + 1}")
        if self.jmbg is not None:
            parts.append(f"JMBG→{self.jmbg + 1}")
        if self.date is not None:
            parts.append(f"datum→{self.date + 1}")
        source = "iz zaglavlja" if self.from_header else "po sadržaju"
        return f"kolone ({source}): " + ", ".join(parts)


@dataclass
class PasteResult:
    guests: list[Guest] = field(default_factory=list)
    mapping: ColumnMapping = field(default_factory=ColumnMapping)
    warnings: list[str] = field(default_factory=list)
    skipped_rows: int = 0

    @property
    def ok(self) -> bool:
        return bool(self.guests)


# ---------------------------------------------------------------------------
# parsiranje
# ---------------------------------------------------------------------------

def split_rows(text: str) -> list[list[str]]:
    """Razbij clipboard tekst na redove i ćelije."""
    rows: list[list[str]] = []
    for line in (text or "").replace("\r\n", "\n").replace("\r", "\n").split("\n"):
        if not line.strip():
            continue
        cells = [_unquote(cell) for cell in line.split("\t")]
        rows.append(cells)
    return rows


def _unquote(cell: str) -> str:
    cell = cell.strip()
    if len(cell) >= 2 and cell[0] == '"' and cell[-1] == '"':
        cell = cell[1:-1].replace('""', '"')
    return cell.strip()


def _normalize_header(cell: str) -> str:
    return re.sub(r"_+", "_", latinize(cell)).strip("_").lower()


def _looks_like_jmbg(cell: str) -> bool:
    digits = re.sub(r"\D", "", cell)
    return len(digits) in (12, 13) and not _DATEISH.search(cell)


def _looks_like_date(cell: str) -> bool:
    return bool(_DATEISH.search(cell)) and not _looks_like_jmbg(cell)


def _looks_like_text(cell: str) -> bool:
    return bool(_LETTER.search(cell))


def detect_header(row: list[str]) -> ColumnMapping | None:
    """Prepoznaj zaglavlje. Vrati None ako prvi red izgleda kao podaci."""
    if any(_looks_like_jmbg(cell) for cell in row):
        return None

    mapping = ColumnMapping(from_header=True)
    matched = 0
    for index, cell in enumerate(row):
        name = _normalize_header(cell)
        if not name:
            continue
        if name in _FULL_NAME_HEADERS:
            mapping.full_name = index
            matched += 1
            continue
        for field_name, aliases in _HEADER_ALIASES.items():
            if name in aliases and getattr(mapping, field_name) is None:
                setattr(mapping, field_name, index)
                matched += 1
                break

    return mapping if matched >= 2 else None


def detect_by_content(rows: list[list[str]]) -> ColumnMapping:
    """Pogodi kolone brojanjem kako sadržaj izgleda niz svaku kolonu."""
    width = max((len(row) for row in rows), default=0)
    jmbg_score = [0] * width
    date_score = [0] * width
    text_score = [0] * width
    upper_score = [0] * width

    for row in rows:
        for index in range(width):
            cell = row[index] if index < len(row) else ""
            if not cell:
                continue
            if _looks_like_jmbg(cell):
                jmbg_score[index] += 1
            elif _looks_like_date(cell):
                date_score[index] += 1
            elif _looks_like_text(cell):
                text_score[index] += 1
                if cell == cell.upper():
                    upper_score[index] += 1

    mapping = ColumnMapping()
    if width and max(jmbg_score) > 0:
        mapping.jmbg = jmbg_score.index(max(jmbg_score))
    if width and max(date_score) > 0:
        mapping.date = date_score.index(max(date_score))

    text_columns = [i for i in range(width) if text_score[i] > 0 and i not in (mapping.jmbg, mapping.date)]

    if len(text_columns) == 1:
        mapping.full_name = text_columns[0]
    elif len(text_columns) >= 2:
        first, second = text_columns[0], text_columns[1]
        # Podrazumevani redosled je ime pa prezime — isti kao u primer_gosti.xlsx.
        mapping.given_name, mapping.surname = first, second
        # Ali stare liste su prezime pisale verzalom ("PETROVIĆ Marko"); ako je baš
        # prva kolona VERZAL a druga nije, redosled je obrnut.
        if _all_caps(upper_score, text_score, first) and not _all_caps(upper_score, text_score, second):
            mapping.surname, mapping.given_name = first, second

    return mapping


def _all_caps(upper_score: list[int], text_score: list[int], column: int) -> bool:
    return text_score[column] > 0 and upper_score[column] == text_score[column]


def _split_full_name(cell: str) -> tuple[str, str]:
    """Razdvoji "Marko Petrović" na (ime, prezime).

    Podrazumeva se ime pa prezime. Izuzetak je stari zapis gde je prezime verzalom
    ("PETROVIĆ Marko") — tu je prva reč prezime.
    """
    parts = cell.split()
    if not parts:
        return "", ""
    if len(parts) == 1:
        return parts[0], ""
    if parts[0] == parts[0].upper() and parts[-1] != parts[-1].upper():
        return " ".join(parts[1:]), parts[0]
    return parts[0], " ".join(parts[1:])


def parse_clipboard(text: str, default_year: int | None = None, start_row: int = 1) -> PasteResult:
    """Pretvori clipboard tekst u listu gostiju, sa već izvršenom validacijom."""
    result = PasteResult()
    # Prazne redove izbacuje split_rows, pa ih ovde prebrojimo da bi korisnik video
    # da broj zalepljenih redova nije isti kao broj gostiju.
    normalized = (text or "").replace("\r\n", "\n").replace("\r", "\n")
    result.skipped_rows = sum(1 for line in normalized.split("\n") if line and not line.strip())

    rows = split_rows(text)
    if not rows:
        result.warnings.append("Clipboard je prazan.")
        return result

    mapping = detect_header(rows[0])
    if mapping is not None:
        rows = rows[1:]
        # Zaglavlje ume da pokrije samo deo kolona; ostalo dopuni po sadržaju.
        if rows and not mapping.is_usable:
            guessed = detect_by_content(rows)
            for name in ("surname", "given_name", "jmbg", "date", "full_name"):
                if getattr(mapping, name) is None:
                    setattr(mapping, name, getattr(guessed, name))
    else:
        mapping = detect_by_content(rows)

    result.mapping = mapping

    if not rows:
        result.warnings.append("Nema redova sa podacima — zalepljeno je samo zaglavlje.")
        return result

    if not mapping.is_usable:
        result.warnings.append(
            "Ne mogu da prepoznam kolone. Očekujem prezime, ime, JMBG i datum — "
            "proveri da si kopirao prave kolone iz Excela."
        )
        return result

    if mapping.date is None:
        result.warnings.append("Kolona sa datumom nije nađena — datume ćeš morati da uneseš ručno.")

    def cell(row: list[str], index: int | None) -> str:
        return row[index] if index is not None and index < len(row) else ""

    for row in rows:
        if mapping.full_name is not None:
            given_name, surname = _split_full_name(cell(row, mapping.full_name))
        else:
            surname = cell(row, mapping.surname)
            given_name = cell(row, mapping.given_name)

        guest = Guest(
            row=start_row + len(result.guests),
            surname_raw=surname,
            given_name_raw=given_name,
            jmbg_raw=cell(row, mapping.jmbg),
            date_raw=cell(row, mapping.date),
        )
        guest.validate(default_year)
        result.guests.append(guest)

    if mapping.full_name is not None:
        result.warnings.append(
            "Ime i prezime su bili u istoj koloni — prva reč je uzeta kao ime. "
            "Proveri redove pre pokretanja."
        )

    return result


# ---------------------------------------------------------------------------
# izvoz
# ---------------------------------------------------------------------------

def to_clipboard(guests: list[Guest], include_header: bool = True) -> str:
    """Napravi TSV za Ctrl+C nazad u glavni Excel."""
    lines: list[str] = []
    if include_header:
        lines.append("\t".join(EXPORT_HEADERS))
    for guest in guests:
        lines.append("\t".join(_escape(value) for value in guest.export_row()))
    return "\n".join(lines)


def _escape(value: str) -> str:
    """Tab i novi red u ćeliji bi razbili TSV, pa ih menjamo razmakom."""
    return re.sub(r"[\t\r\n]+", " ", value or "").strip()

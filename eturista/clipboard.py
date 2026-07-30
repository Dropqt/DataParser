"""Prenos podataka između Excela i aplikacije.

Excel (i LibreOffice) stavljaju u clipboard obične redove razdvojene tabovima, pa je
Ctrl+V ovde samo parsiranje TSV-a. Posao je u tome da se pogodi *koja kolona je šta*,
jer glavni Excel ne mora da ima kolone istim redom kao aplikacija.

Isto Ctrl+V radi i za tekst iz Worda. Wordova tabela stiže kao TSV, kao i iz Excela,
ali spisak gostiju ume da bude i običan pasus ili numerisana lista - tu nema kolona,
pa se svaka reč prepoznaje po obliku (:func:`_read_free_text_row`).
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

from .models import EXPORT_HEADERS, Guest
from .validation import DEFAULT_DAYS, latinize, month_from_name

# --- prepoznavanje zaglavlja ------------------------------------------------

_HEADER_ALIASES: dict[str, tuple[str, ...]] = {
    "surname": ("prezime", "prez", "surname", "lastname", "last_name"),
    "given_name": ("ime", "name", "firstname", "first_name", "given"),
    "jmbg": ("jmbg", "jmb", "maticni", "maticni_broj", "mb", "licni_broj"),
    "date": ("dolazak", "datum", "datum_dolaska", "datumi", "date", "od", "termin",
             "boravak", "period", "od_do"),
    "days": ("dana", "broj_dana", "dani", "noci", "nocenja", "broj_nocenja", "days", "nights"),
    "email": ("email", "e_mail", "mail", "e_posta", "eposta", "adresa", "e_adresa"),
}

#: Kolone tipa "Ime i prezime" - jedna ćelija sa oba imena.
_FULL_NAME_HEADERS = ("ime_i_prezime", "imeiprezime", "gost", "putnik", "prezime_i_ime", "full_name")

# --- prepoznavanje po sadržaju ----------------------------------------------

_DATEISH = re.compile(r"\d{1,2}\s*[.\-/]\s*\d{1,2}")
_LETTER = re.compile(r"[^\W\d_]", re.UNICODE)

#: Broj pa reč - kandidat za datum sa nazivom meseca (``29.sep.2026``). Da li je reč
#: zaista mesec presuđuje ``month_from_name``, pa "5 dana" ne prolazi kao datum.
_DATE_BY_NAME_ISH = re.compile(r"\b\d{1,2}\s*[.\-/ ]\s*([^\W\d_]{3,})", re.UNICODE)


@dataclass
class ColumnMapping:
    """Koja kolona iz clipboard-a je koje polje. ``None`` znači da je nema."""

    surname: int | None = None
    given_name: int | None = None
    jmbg: int | None = None
    date: int | None = None
    days: int | None = None
    email: int | None = None
    full_name: int | None = None
    from_header: bool = False
    #: Zalepljen je tekst bez kolona (Word), pa se ne gleda pozicija nego oblik reči.
    free_text: bool = False

    @property
    def is_usable(self) -> bool:
        if self.free_text:
            return True
        has_name = self.full_name is not None or (self.surname is not None and self.given_name is not None)
        return has_name and self.jmbg is not None

    def describe(self) -> str:
        if self.free_text:
            return "slobodan tekst iz Worda - polja prepoznata po obliku, ne po koloni"

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
            parts.append(f"dolazak→{self.date + 1}")
        if self.days is not None:
            parts.append(f"dana→{self.days + 1}")
        if self.email is not None:
            parts.append(f"e-mail→{self.email + 1}")
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

#: Nevidljivi znaci koje lepljenje iz Worda donese u tekst. Tvrdi razmak mora da postane
#: običan (inače ``strip()`` i ``split()`` ne rade), a razmak nulte širine da nestane -
#: on se ne vidi ni u ćeliji ni u poruci o grešci, pa bi ispao neobjašnjiv problem.
_INVISIBLE = str.maketrans({
    "\u00a0": " ",   # tvrdi razmak (Word ga stavlja sam)
    "\u202f": " ",   # uski tvrdi razmak
    "\u200b": "",    # razmak nulte širine
    "\ufeff": "",    # BOM, stigne sa kopiranjem sa sajta
})

#: Meki prelom reda: Shift+Enter u Wordu (\v), prelom stranice i Unicode prelomi.
_SOFT_BREAK = re.compile("[\v\f\u2028\u2029]+")


def _lines(text: str) -> list[str]:
    """Clipboard tekst u redove, sa počišćenim nevidljivim znacima iz Worda.

    Meki prelom se u tabeli tretira drugačije nego u pasusu: u redu sa tabovima on je
    prelom *unutar ćelije* (drugi red adrese), a u pasusu je novi gost.
    """
    normalized = (text or "").translate(_INVISIBLE).replace("\r\n", "\n").replace("\r", "\n")
    lines: list[str] = []
    for line in normalized.split("\n"):
        if "\t" in line:
            lines.append(_SOFT_BREAK.sub(" ", line))
        else:
            lines.extend(_SOFT_BREAK.split(line))
    return lines


def split_rows(text: str) -> list[list[str]]:
    """Razbij clipboard tekst na redove i ćelije."""
    rows: list[list[str]] = []
    for line in _lines(text):
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


def _has_named_month(cell: str) -> bool:
    """Ćelija oblika ``29.sep.2026`` - broj, pa naziv meseca."""
    return any(month_from_name(m.group(1)) is not None for m in _DATE_BY_NAME_ISH.finditer(cell))


def _looks_like_date(cell: str) -> bool:
    return (bool(_DATEISH.search(cell)) or _has_named_month(cell)) and not _looks_like_jmbg(cell)


def _looks_like_days(cell: str) -> bool:
    """Mali ceo broj - kandidat za kolonu sa brojem noćenja."""
    text = cell.strip()
    return text.isdigit() and 1 <= int(text) <= 120


def _looks_like_text(cell: str) -> bool:
    return bool(_LETTER.search(cell))


def _looks_like_email(cell: str) -> bool:
    """Ćelija sa @ između dva neprazna dela - dovoljno da se kolona prepozna.

    Ovde se ne presuđuje da li je adresa ispravna (to radi ``validate_email``), samo
    da li kolona uopšte drži mejlove.
    """
    text = cell.strip()
    if text.count("@") != 1:
        return False
    levo, _, desno = text.partition("@")
    return bool(levo) and "." in desno


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
    days_score = [0] * width
    text_score = [0] * width
    upper_score = [0] * width
    email_score = [0] * width
    columns: list[list[str]] = [[] for _ in range(width)]

    for row in rows:
        for index in range(width):
            cell = row[index] if index < len(row) else ""
            if not cell:
                continue
            columns[index].append(cell)
            # E-mail se proverava prvi: ćelija sa @ ne može biti ništa drugo, a bez
            # ovoga bi je _looks_like_text pokupio kao ime ili prezime.
            if _looks_like_email(cell):
                email_score[index] += 1
            elif _looks_like_jmbg(cell):
                jmbg_score[index] += 1
            elif _looks_like_date(cell):
                date_score[index] += 1
            elif _looks_like_days(cell):
                days_score[index] += 1
            elif _looks_like_text(cell):
                text_score[index] += 1
                if cell == cell.upper():
                    upper_score[index] += 1

    mapping = ColumnMapping()
    if width and max(jmbg_score) > 0:
        mapping.jmbg = jmbg_score.index(max(jmbg_score))
    if width and max(date_score) > 0:
        mapping.date = date_score.index(max(date_score))
    if width and max(email_score) > 0:
        mapping.email = email_score.index(max(email_score))

    # Kolona sa malim brojevima je broj noćenja - osim ako je to samo redni broj
    # (1, 2, 3, …), što se lako pomeša ako se iz Excela kopira i kolona sa numeracijom.
    # Numeracija ide *ispred* gosta, a broj noćenja iza JMBG-a, pa se sve levo od
    # JMBG-a odbacuje: kod dva zalepljena reda "1, 2" se ne razlikuje od "1 noć, 2 noći".
    day_candidates = [
        i for i in range(width)
        if days_score[i] > 0
        and not _is_running_index(columns[i])
        and (mapping.jmbg is None or i > mapping.jmbg)
    ]
    if day_candidates:
        mapping.days = max(day_candidates, key=lambda i: days_score[i])

    taken = (mapping.jmbg, mapping.date, mapping.days, mapping.email)
    text_columns = [i for i in range(width) if text_score[i] > 0 and i not in taken]

    if len(text_columns) == 1:
        mapping.full_name = text_columns[0]
    elif len(text_columns) >= 2:
        first, second = text_columns[0], text_columns[1]
        # Podrazumevani redosled je ime pa prezime - isti kao u primer_gosti.xlsx.
        mapping.given_name, mapping.surname = first, second
        # Ali stare liste su prezime pisale verzalom ("PETROVIĆ Marko"); ako je baš
        # prva kolona VERZAL a druga nije, redosled je obrnut.
        if _all_caps(upper_score, text_score, first) and not _all_caps(upper_score, text_score, second):
            mapping.surname, mapping.given_name = first, second

    return mapping


def _is_running_index(values: list[str]) -> bool:
    """Da li je kolona samo numeracija redova: 1, 2, 3, …"""
    if len(values) < 3 or not all(value.strip().isdigit() for value in values):
        return False
    numbers = [int(value) for value in values]
    return numbers == list(range(numbers[0], numbers[0] + len(numbers)))


def _all_caps(upper_score: list[int], text_score: list[int], column: int) -> bool:
    return text_score[column] > 0 and upper_score[column] == text_score[column]


# ---------------------------------------------------------------------------
# slobodan tekst - spisak iz Worda koji nije tabela
# ---------------------------------------------------------------------------

#: Numeracija ili nabrajanje na početku reda: "1.", "2)", "- ", "• ". Nije podatak.
_LIST_MARKER = re.compile("^\\s*(?:\\d{1,3}\\s*[.)]\\s+|[-*\u2022\u00b7\u2013\u2014]\\s+)")

#: Reč koja u Wordu samo kaže šta sledi ("JMBG: 010…", "dolazak 05.10"). Da nema ovog
#: spiska, takve reči bi završile u imenu gosta.
_LABELS = frozenset({
    "jmbg", "jmb", "mb", "maticni", "maticni_broj", "broj", "br", "licni_broj",
    "ime", "prezime", "ime_i_prezime", "gost", "putnik", "gospodin", "gospodja",
    "dolazak", "datum", "datum_dolaska", "termin", "boravak", "period", "od", "do",
    "email", "e_mail", "mail", "e_posta", "eposta", "adresa", "e_adresa",
    "tel", "telefon", "kontakt",
})

#: Reč uz koju stoji broj noćenja ("5 dana", "7 noćenja").
_DAYS_WORDS = frozenset({"dana", "dan", "noc", "noci", "nocenja", "nocenje", "days", "nights"})

#: Reč sastavljena samo od cifara i razdvajača - kandidat za JMBG. Traži se ovako, a ne
#: preko ``_looks_like_jmbg``, jer bi "010199-071012-1" tamo ispalo kao datum.
_DIGIT_TOKEN = re.compile("^[\\d\\s.\u2013\u2014/-]+$")


#: Broj koji sme da počne datum sa nazivom meseca, sa tačkom ili bez ("29." / "29").
_DAY_TOKEN = re.compile(r"^(\d{1,2})(\.?)$")

#: Godina na kraju takvog datuma ("2026", "26", "2026.").
_YEAR_TOKEN = re.compile(r"^(\d{2,4})\.?$")


def _tokens(line: str) -> list[str]:
    """Red slobodnog teksta na reči, bez numeracije liste i bez zareza."""
    return [word for word in re.split(r"[\s,;|]+", _LIST_MARKER.sub("", line.strip())) if word]


def _join_named_dates(words: list[str]) -> list[str]:
    """Spoji ``29. septembra 2026`` u jednu reč, da bi se pročitalo kao datum.

    U tabeli je datum cela ćelija, ali u pasusu iz Worda stiže kao tri odvojene reči.
    Spaja se samo kad je nedvosmisleno: broj **sa tačkom** pa mesec, ili broj pa mesec
    pa godina. Inače bi ``1 Maja Petrović`` ispalo kao 1. maj - posle ``latinize()``
    je "maja" i žensko ime i genitiv od *maj*.
    """
    out: list[str] = []
    i = 0
    while i < len(words):
        day = _DAY_TOKEN.match(words[i])
        naredna = words[i + 1] if i + 1 < len(words) else ""
        if day is not None and month_from_name(naredna) is not None:
            mesec = naredna.strip(".,")
            year = _YEAR_TOKEN.match(words[i + 2]) if i + 2 < len(words) else None
            if year is not None:
                out.append(f"{day.group(1)}.{mesec}.{year.group(1)}")
                i += 3
                continue
            if day.group(2):  # tačka posle dana - "29. septembra", godina se podrazumeva
                out.append(f"{day.group(1)}.{mesec}")
                i += 2
                continue
        out.append(words[i])
        i += 1
    return out


def _read_free_text_row(line: str) -> dict[str, str]:
    """Izvuci polja gosta iz reda koji nije tabela nego rečenica.

    Word ume da bude bilo šta - numerisana lista, nabrajanje sa crticama, red sa
    labelama - pa se ne gleda pozicija reči nego njen oblik: JMBG po broju cifara,
    datum po tački, mejl po @, broj noćenja po tome što stoji posle datuma, a sve
    što je ostalo od slova je ime i prezime.
    """
    jmbg = email = ""
    dates: list[str] = []
    names: list[str] = []
    #: (redni broj reči, broj) - po položaju se posle presuđuje šta je numeracija
    #: reda (pre imena), a šta broj noćenja (posle datuma).
    numbers: list[tuple[int, str]] = []
    date_at: list[int] = []
    days_at: list[int] = []

    for index, word in enumerate(_join_named_dates(_tokens(line))):
        cell = word.strip(":.,;()[]<>\"'")
        if not cell:
            continue
        if not email and _looks_like_email(cell):
            email = cell
        elif not jmbg and _DIGIT_TOKEN.match(cell) and len(re.sub(r"\D", "", cell)) in (12, 13):
            jmbg = cell
        elif _DATEISH.search(cell) or _has_named_month(cell):
            dates.append(cell)
            date_at.append(index)
        elif _looks_like_days(cell):
            numbers.append((index, cell))
        elif _normalize_header(cell) in _DAYS_WORDS:
            days_at.append(index)
        elif _normalize_header(cell) in _LABELS:
            continue
        elif _looks_like_text(cell):
            names.append(cell)

    given_name, surname = _split_full_name(" ".join(names))
    return {
        "given_name": given_name,
        "surname": surname,
        "jmbg": jmbg,
        # Dva datuma u redu su stari zapis "od-do"; resolve_stay ga i dalje čita.
        "date": "-".join(dates[:2]) if len(dates) > 1 else (dates[0] if dates else ""),
        "days": _pick_days(numbers, date_at, days_at),
        "email": email,
    }


def _pick_days(numbers: list[tuple[int, str]], date_at: list[int], days_at: list[int]) -> str:
    """Koji goli broj u redu je broj noćenja.

    Broj uz reč "dana" je siguran. Inače je to broj *posle* datuma; broj pre imena je
    skoro uvek numeracija reda ("3  Marko Petrović …"), pa se ne dira.
    """
    for position in days_at:
        for index, value in numbers:
            if abs(index - position) == 1:
                return value
    if date_at:
        for index, value in numbers:
            if index > date_at[-1]:
                return value
    return ""


def _split_full_name(cell: str) -> tuple[str, str]:
    """Razdvoji "Marko Petrović" na (ime, prezime).

    Podrazumeva se ime pa prezime. Izuzetak je stari zapis gde je prezime verzalom
    ("PETROVIĆ Marko") - tu je prva reč prezime.
    """
    parts = cell.split()
    if not parts:
        return "", ""
    if len(parts) == 1:
        return parts[0], ""
    if parts[0] == parts[0].upper() and parts[-1] != parts[-1].upper():
        return " ".join(parts[1:]), parts[0]
    return parts[0], " ".join(parts[1:])


def _fill_from_free_text(
    rows: list[list[str]], result: PasteResult, default_year: int | None, start_row: int
) -> bool:
    """Pokušaj da pročitaš goste iz teksta bez kolona. Vrati True ako je uspelo.

    Uslov je da bar jedan red ima JMBG - bez toga je zalepljeno nešto što nije spisak
    gostiju (naslov, pasus teksta), pa je poštenije reći "ne prepoznajem" nego napraviti
    goste od proizvoljnih reči.
    """
    read = [_read_free_text_row(" ".join(cells)) for cells in rows]
    if not any(item["jmbg"] for item in read):
        return False

    skipped = 0
    for item in read:
        # Red bez JMBG-a i bez datuma je naslov ili prazna priča između gostiju.
        if not item["jmbg"] and not (item["given_name"] and item["date"]):
            skipped += 1
            continue
        guest = Guest(
            row=start_row + len(result.guests),
            surname_raw=item["surname"],
            given_name_raw=item["given_name"],
            jmbg_raw=item["jmbg"],
            arrival_raw=item["date"],
            days_raw=item["days"],
            email_raw=item["email"],
        )
        guest.validate(default_year)
        result.guests.append(guest)

    result.mapping = ColumnMapping(free_text=True)
    result.skipped_rows += skipped
    result.warnings.append(
        "Zalepljen je tekst bez kolona (Word), pa su ime, JMBG i datum prepoznati po "
        "obliku. Proveri redove pre pokretanja."
    )
    if skipped == 1:
        result.warnings.append("1 red nije ličio na gosta i preskočen je.")
    elif skipped:
        result.warnings.append(f"{skipped} redova nije ličilo na gosta i preskočeni su.")
    return True


def parse_clipboard(text: str, default_year: int | None = None, start_row: int = 1) -> PasteResult:
    """Pretvori clipboard tekst u listu gostiju, sa već izvršenom validacijom."""
    result = PasteResult()
    # Prazne redove izbacuje split_rows, pa ih ovde prebrojimo da bi korisnik video
    # da broj zalepljenih redova nije isti kao broj gostiju.
    result.skipped_rows = sum(1 for line in _lines(text) if line and not line.strip())

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
            for name in ("surname", "given_name", "jmbg", "date", "days", "email", "full_name"):
                if getattr(mapping, name) is None:
                    setattr(mapping, name, getattr(guessed, name))
    else:
        mapping = detect_by_content(rows)

    result.mapping = mapping

    if not rows:
        result.warnings.append("Nema redova sa podacima - zalepljeno je samo zaglavlje.")
        return result

    if not mapping.is_usable:
        # Nema upotrebljivih kolona - ali to ne mora da znači da nema podataka. Spisak
        # iz Worda često nije tabela nego pasus ili numerisana lista, pa se pre odustajanja
        # svaki red pročita kao rečenica.
        if _fill_from_free_text(rows, result, default_year, start_row):
            return result
        result.warnings.append(
            "Ne mogu da prepoznam kolone. Očekujem prezime, ime, JMBG i datum - "
            "proveri da si kopirao prave kolone iz Excela."
        )
        return result

    if mapping.date is None:
        result.warnings.append(
            "Kolona sa datumom dolaska nije nađena - datume ćeš morati da uneseš ručno."
        )
    if mapping.days is None:
        result.warnings.append(
            f"Kolona sa brojem dana nije nađena - svima je upisano {DEFAULT_DAYS} noćenja."
        )

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
            arrival_raw=cell(row, mapping.date),
            days_raw=cell(row, mapping.days),
            email_raw=cell(row, mapping.email),
        )
        guest.validate(default_year)
        result.guests.append(guest)

    if mapping.full_name is not None:
        result.warnings.append(
            "Ime i prezime su bili u istoj koloni - prva reč je uzeta kao ime. "
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

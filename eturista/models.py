"""Model gosta i njegovog statusa kroz turu."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, datetime
from enum import Enum
from pathlib import Path

from .errors import ErrorKind, GuestError, ValidationError
from .validation import JmbgInfo, Stay, clean_name, latinize, parse_stay, validate_jmbg, validate_name


class Status(str, Enum):
    """Stanje jednog gosta. Vrednost se pamti u bazi — ne menjaj postojeće stringove."""

    PENDING = "PENDING"
    RUNNING = "RUNNING"
    OK = "OK"
    ERROR = "ERROR"
    SKIPPED = "SKIPPED"

    @property
    def label(self) -> str:
        """Tekst koji ide u STATUS kolonu pri kopiranju u Excel."""
        return _STATUS_LABELS[self]

    @property
    def is_final(self) -> bool:
        return self in {Status.OK, Status.SKIPPED}


_STATUS_LABELS: dict[Status, str] = {
    Status.PENDING: "ČEKA",
    Status.RUNNING: "U TOKU",
    Status.OK: "OK",
    Status.ERROR: "GREŠKA",
    Status.SKIPPED: "PRESKOČEN",
}

#: Zaglavlje koje ide u clipboard pri Ctrl+C, i redosled kolona u tabeli.
#: Mora da se poklapa sa kolonama A-G u primer/primer_gosti.xlsx, da bi se rezultat ture
#: lepio nazad preko gostiju bez pomeranja kolona.
EXPORT_HEADERS = ("Ime", "Prezime", "JMBG", "Datum", "STATUS", "RAZLOG", "PDF")


@dataclass
class Guest:
    """Jedan gost. Sirova polja su ono što je zalepljeno iz Excela; ``validate()``
    ih pretvara u ``jmbg_info`` / ``stay`` ili postavlja grešku.
    """

    row: int
    surname_raw: str = ""
    given_name_raw: str = ""
    jmbg_raw: str = ""
    date_raw: str = ""

    # popunjava validate()
    surname: str = ""
    given_name: str = ""
    jmbg_info: JmbgInfo | None = None
    stay: Stay | None = None

    status: Status = Status.PENDING
    error: GuestError | None = None
    pdf_path: str | None = None
    attempts: int = 0
    selected: bool = True
    note: str = ""

    db_id: int | None = None
    updated_at: datetime | None = None

    # -- izvedeno ---------------------------------------------------------

    @property
    def jmbg(self) -> str:
        return self.jmbg_info.jmbg if self.jmbg_info else self.jmbg_raw.strip()

    @property
    def full_name(self) -> str:
        return f"{self.surname or self.surname_raw} {self.given_name or self.given_name_raw}".strip()

    @property
    def date_display(self) -> str:
        """Nedvosmislen datum ako je parsiran, inače original iz Excela."""
        return self.stay.format() if self.stay else self.date_raw.strip()

    @property
    def pdf_display(self) -> str:
        """Samo naziv vaučera — cela putanja se ne vidi u koloni, a i ne treba u Excelu."""
        return Path(self.pdf_path).name if self.pdf_path else ""

    @property
    def is_ready(self) -> bool:
        """Da li gost sme da uđe u turu."""
        return self.jmbg_info is not None and self.stay is not None and bool(self.surname and self.given_name)

    def pdf_name(self, year: int) -> str:
        """Naziv PDF vaučera: 2026_PETROVIC_MARKO.pdf (čist ASCII zbog Windows-a)."""
        surname = latinize(self.surname or self.surname_raw).upper() or "NEPOZNATO"
        given = latinize(self.given_name or self.given_name_raw).upper() or "NEPOZNATO"
        return f"{year}_{surname}_{given}.pdf"

    # -- validacija -------------------------------------------------------

    def validate(self, default_year: int | None = None) -> bool:
        """Proveri sirova polja. Vrati True ako je gost spreman za prijavu.

        Poziva se pri lepljenju iz Excela i posle svake izmene u tabeli, pa red
        pocrveni odmah — bez čekanja da browser uopšte krene.
        """
        self.jmbg_info = None
        self.stay = None
        self.note = ""

        try:
            self.surname = validate_name(self.surname_raw, "Prezime")
            self.given_name = validate_name(self.given_name_raw, "Ime")
            self.jmbg_info = validate_jmbg(self.jmbg_raw)
            self.stay = parse_stay(self.date_raw, default_year)
        except ValidationError as exc:
            self.mark_error(exc.as_guest_error())
            return False

        if self.jmbg_info.note:
            self.note = self.jmbg_info.note
            self.jmbg_raw = self.jmbg_info.jmbg

        # Gost koji je ranije pao zbog podataka dobija novu šansu čim se podaci poprave.
        if self.status is Status.ERROR and self.error and self.error.kind.is_data_problem:
            self.status = Status.PENDING
            self.error = None
        return True

    # -- prelazi stanja ---------------------------------------------------

    def mark_running(self) -> None:
        self.status = Status.RUNNING
        self.error = None
        self.attempts += 1
        self.updated_at = datetime.now()

    def mark_ok(self, pdf_path: str | None = None) -> None:
        self.status = Status.OK
        self.error = None
        if pdf_path:
            self.pdf_path = pdf_path
        self.updated_at = datetime.now()

    def mark_error(self, error: GuestError) -> None:
        self.status = Status.ERROR
        self.error = error
        self.updated_at = datetime.now()

    def mark_skipped(self, reason: str = "") -> None:
        self.status = Status.SKIPPED
        if reason:
            self.error = GuestError(ErrorKind.UNKNOWN, reason)
        self.updated_at = datetime.now()

    def reset(self) -> None:
        """Vrati na početak da bi gost mogao ponovo u turu."""
        self.status = Status.PENDING
        self.error = None
        self.updated_at = None

    # -- izvoz ------------------------------------------------------------

    @property
    def reason(self) -> str:
        """Kolona RAZLOG. Napomena o ispravci se prikazuje kad nema greške."""
        if self.error:
            return self.error.text
        return self.note

    def export_row(self) -> tuple[str, ...]:
        """Red za Ctrl+C nazad u glavni Excel, redosledom EXPORT_HEADERS."""
        return (
            self.given_name or self.given_name_raw,
            self.surname or self.surname_raw,
            self.jmbg,
            self.date_display,
            self.status.label,
            self.reason,
            self.pdf_display,
        )


@dataclass
class Batch:
    """Jedna tura — grupa gostiju koja se prijavljuje kroz jedan nalog."""

    guests: list[Guest] = field(default_factory=list)
    account_label: str = ""
    db_id: int | None = None
    created_at: date = field(default_factory=date.today)

    def __len__(self) -> int:
        return len(self.guests)

    def pending(self) -> list[Guest]:
        """Gosti koje treba obraditi: označeni, ispravni i još nisu gotovi."""
        return [
            g for g in self.guests
            if g.selected and g.is_ready and not g.status.is_final and g.status is not Status.RUNNING
        ]

    def counts(self) -> dict[Status, int]:
        counts = dict.fromkeys(Status, 0)
        for guest in self.guests:
            counts[guest.status] += 1
        return counts

    def summary(self) -> str:
        counts = self.counts()
        done = counts[Status.OK]
        failed = counts[Status.ERROR]
        return f"{done}/{len(self.guests)} prijavljeno · {failed} grešaka"

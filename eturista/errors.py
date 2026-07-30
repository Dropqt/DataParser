"""Taksonomija grešaka.

Svaka greška ima *tip* (za logiku i statistiku) i *poruku na srpskom* (za tabelu i Excel).
Poenta je da u koloni RAZLOG piše "JMBG odbijen na portalu", a ne "NoSuchElementException".
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum


class ErrorKind(str, Enum):
    """Tipovi grešaka. Vrednost se pamti u bazi, pa ne menjaj postojeće stringove."""

    # --- greške u podacima (uhvaćene pre nego što browser uopšte krene) ---
    JMBG_INVALID_LOCAL = "JMBG_INVALID_LOCAL"
    DATE_INVALID = "DATE_INVALID"
    MISSING_FIELD = "MISSING_FIELD"
    #: E-mail po kom se vaučeri razvrstavaju u foldere ne izgleda kao adresa.
    EMAIL_INVALID = "EMAIL_INVALID"

    # --- greške koje javlja portal ---
    JMBG_REJECTED_PORTAL = "JMBG_REJECTED_PORTAL"
    PORTAL_VALIDATION = "PORTAL_VALIDATION"
    DUPLICATE = "DUPLICATE"
    #: Registracija za vaučere još nije otvorena - portal drži izbor prijave zaključan.
    #: Ovo nije greška u podacima nego u trenutku: ista je za sve goste, pa prekida turu.
    RESERVATION_LOCKED = "RESERVATION_LOCKED"
    #: Kliknuto je „Sačuvaj“ ali nema dokaza da je rezervacija stvarno sačuvana.
    #: Namerno **nije** retryable: ponovni pokušaj bi lako napravio duplu rezervaciju,
    #: a portal ne nudi način da se ona poništi iz aplikacije.
    RESERVATION_NOT_SAVED = "RESERVATION_NOT_SAVED"

    # --- greške sesije ---
    LOGIN_FAILED = "LOGIN_FAILED"
    SESSION_EXPIRED = "SESSION_EXPIRED"

    # --- tehničke greške ---
    SELECTOR_NOT_FOUND = "SELECTOR_NOT_FOUND"
    TIMEOUT = "TIMEOUT"
    PDF_DOWNLOAD_FAILED = "PDF_DOWNLOAD_FAILED"
    BROWSER_CRASHED = "BROWSER_CRASHED"
    UNKNOWN = "UNKNOWN"

    @property
    def label(self) -> str:
        """Kratak opis na srpskom, za kolonu RAZLOG kad nema konkretnije poruke."""
        return _LABELS[self]

    @property
    def is_data_problem(self) -> bool:
        """True za greške koje korisnik može da popravi ispravkom podataka u tabeli."""
        return self in _DATA_PROBLEMS

    @property
    def is_retryable(self) -> bool:
        """True za greške koje ima smisla pokušati ponovo bez ikakve izmene."""
        return self in _RETRYABLE


_LABELS: dict[ErrorKind, str] = {
    ErrorKind.JMBG_INVALID_LOCAL: "JMBG nije ispravan",
    ErrorKind.DATE_INVALID: "Datum nije ispravan",
    ErrorKind.MISSING_FIELD: "Nedostaje obavezno polje",
    ErrorKind.EMAIL_INVALID: "E-mail nije ispravan",
    ErrorKind.JMBG_REJECTED_PORTAL: "Portal je odbio JMBG",
    ErrorKind.PORTAL_VALIDATION: "Portal je odbio podatke",
    ErrorKind.DUPLICATE: "Gost je već prijavljen",
    ErrorKind.RESERVATION_LOCKED: "Portal još nije otvorio rezervacije",
    ErrorKind.LOGIN_FAILED: "Prijava na nalog nije uspela",
    ErrorKind.SESSION_EXPIRED: "Sesija je istekla",
    ErrorKind.SELECTOR_NOT_FOUND: "Element nije nađen - portal je verovatno promenjen",
    ErrorKind.TIMEOUT: "Portal nije odgovorio na vreme",
    ErrorKind.PDF_DOWNLOAD_FAILED: "Vaučer nije preuzet",
    ErrorKind.BROWSER_CRASHED: "Browser je pukao",
    ErrorKind.UNKNOWN: "Nepoznata greška",
}

_DATA_PROBLEMS = frozenset({
    ErrorKind.JMBG_INVALID_LOCAL,
    ErrorKind.DATE_INVALID,
    ErrorKind.MISSING_FIELD,
    ErrorKind.EMAIL_INVALID,
    ErrorKind.JMBG_REJECTED_PORTAL,
    ErrorKind.PORTAL_VALIDATION,
})

_RETRYABLE = frozenset({
    ErrorKind.TIMEOUT,
    ErrorKind.SESSION_EXPIRED,
    ErrorKind.BROWSER_CRASHED,
    ErrorKind.PDF_DOWNLOAD_FAILED,
})


@dataclass(frozen=True)
class GuestError:
    """Greška vezana za jednog gosta - ono što ide u kolonu RAZLOG i u bazu."""

    kind: ErrorKind
    message: str = ""
    detail: str = ""
    screenshot: str | None = None

    @property
    def text(self) -> str:
        """Tekst za prikaz. Konkretna poruka ako postoji, inače opšti opis tipa."""
        return self.message or self.kind.label

    def __str__(self) -> str:
        return self.text


class PortalError(Exception):
    """Izuzetak koji nose slojevi za rad sa portalom; runner ga pretvara u GuestError."""

    def __init__(self, kind: ErrorKind, message: str = "", detail: str = "") -> None:
        self.kind = kind
        self.message = message or kind.label
        self.detail = detail
        super().__init__(self.message)

    def as_guest_error(self, screenshot: str | None = None) -> GuestError:
        return GuestError(self.kind, self.message, self.detail, screenshot)


class ValidationError(Exception):
    """Podaci gosta nisu ispravni. Baca se iz validation.py, hvata se pri lepljenju."""

    def __init__(self, kind: ErrorKind, message: str) -> None:
        self.kind = kind
        self.message = message
        super().__init__(message)

    def as_guest_error(self) -> GuestError:
        return GuestError(self.kind, self.message)

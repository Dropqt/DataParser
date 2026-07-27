"""Forma za prijavu gosta na rezervaciju smeštaja."""

from __future__ import annotations

from datetime import date as _date

from selenium.common.exceptions import WebDriverException

from ..errors import ErrorKind, PortalError
from ..models import Guest
from ..validation import Stay
from . import selectors as S
from .base_page import BasePage

#: Putanja forme u odnosu na osnovni URL portala. Potvrđeno na portalu 27.07.2026.
RESERVATION_PATH = "/vauceri/rezervacija-smestaja"


def format_date(date: _date) -> str:
    """Datum onako kako ga portal sam upiše kad se izabere iz kalendara: ``15.7.2026``.

    **Bez vodeće nule** — provereno tako što je datum izabran iz portalovog kalendara i
    pročitano šta je ostalo u polju. Nije ``strftime``: ``%-d`` radi samo na Linux-u a
    ``%#d`` samo na Windows-u, a aplikacija se pakuje za oba (faza 7).

    Bitno je i zbog provere u ``BasePage.fill``, koja posle upisa čita polje nazad i
    poredi cifre — ``15.07.2026`` i ``15.7.2026`` joj nisu isti broj.
    """
    return f"{date.day}.{date.month}.{date.year}"


class ReservationPage(BasePage):
    def __init__(self, driver, base_url: str, timeout: float = 15.0) -> None:
        super().__init__(driver, timeout)
        self.base_url = base_url.rstrip("/")

    @property
    def url(self) -> str:
        return f"{self.base_url}{RESERVATION_PATH}"

    def open(self) -> None:
        try:
            self.driver.get(self.url)
        except WebDriverException as exc:
            raise PortalError(ErrorKind.TIMEOUT, "Forma rezervacije se ne otvara", str(exc)) from exc

    def reload(self) -> None:
        """Tvrd refresh — koristi se posle greške da se forma očisti za sledećeg gosta."""
        try:
            self.driver.get(self.url)
        except WebDriverException:
            try:
                self.driver.refresh()
            except WebDriverException:
                pass

    # -- koraci -----------------------------------------------------------

    def fill_identity(self, guest: Guest) -> None:
        """Ime, prezime i JMBG. Ovaj deo forme je otvoren i van sezone vaučera."""
        self.fill(S.GUEST_FIRST_NAME, guest.given_name)
        self.fill(S.GUEST_LAST_NAME, guest.surname)
        self.fill(S.GUEST_JMBG, guest.jmbg)

    def field_error(self) -> str | None:
        """Poruka koju je portal ispisao ispod polja, ako je ima.

        Angular validira JMBG čim se izađe iz polja, pa se greška vidi pre slanja forme.
        Vraća tekst greške ili None.
        """
        self._blur()
        message = self.text_of(S.FIELD_ERROR)
        return message or None

    def _blur(self) -> None:
        """Skini fokus sa poslednjeg polja da bi Angular pokrenuo validaciju."""
        try:
            self.driver.execute_script("document.activeElement && document.activeElement.blur();")
        except WebDriverException:
            pass

    def fill_dates(self, stay: Stay) -> None:
        """Datum dolaska i odlaska — 3. korak forme.

        Polja jesu deo kalendara (``mat-date-range-input``), ali primaju i običan unos,
        pa se kuca direktno i kalendar se ne otvara.
        """
        self.fill(S.DATE_FROM, format_date(stay.arrival))
        self.fill(S.DATE_TO, format_date(stay.departure))

    def submit(self) -> None:
        """Sačuvaj rezervaciju. ZAKLJUČANO do otvaranja registracije."""
        self.click(S.SUBMIT_RESERVATION)

    def wait_for_confirmation(self) -> str:
        """Sačekaj potvrdu da je rezervacija prošla. ZAKLJUČANO do otvaranja."""
        element = self.find(S.CONFIRMATION)
        return (element.text or "").strip()

    def next_step(self) -> None:
        """Dugme za sledeći korak.

        Svaki korak ima svoje dugme i sva su u DOM-u, ali neaktivna imaju
        ``visibility: hidden`` — zato se traži **vidljivo**, inače bi se uvek klikalo
        dugme prvog koraka.
        """
        element = self.find_optional(S.NEXT_BUTTON, timeout=self.timeout, visible=True)
        if element is None:
            raise PortalError(
                ErrorKind.SELECTOR_NOT_FOUND,
                f"{S.NEXT_BUTTON.description} nije nađeno na stranici",
            )
        self._click_element(element, S.NEXT_BUTTON)

    def select_scheme(self) -> None:
        """Drugi korak: čekiraj prijavu ugostitelja pod kojom se gost prijavljuje.

        Ako je registracija za vaučere još zaključana, portal drži čekboks onemogućenim
        (tooltip: „Rezervacija smeštaja je zaključana.“). To nije greška u podacima nego
        u trenutku — ista je za svakog gosta, pa se javlja jasno i tura se prekida.
        """
        if self.is_present(S.SCHEME_ROW_LOCKED):
            raise PortalError(
                ErrorKind.RESERVATION_LOCKED,
                "Portal još nije otvorio rezervacije smeštaja",
                "izbor prijave ugostitelja je onemogućen na drugom koraku forme",
            )
        self.click(S.SCHEME_ROW)

    # -- ceo tok za jednog gosta ------------------------------------------

    def register(self, guest: Guest) -> None:
        """Prijavi jednog gosta kroz sva tri koraka forme.

        Redosled je namerno takav da se JMBG proveri **pre** nego što se bilo šta pošalje —
        pogrešan JMBG tako ne troši ni jedan klik dalje.

            1. ime, prezime, JMBG
            2. izbor prijave ugostitelja  ← ovde je brava van sezone
            3. datum dolaska i odlaska, pa „Sačuvaj“
        """
        self.fill_identity(guest)

        error = self.field_error()
        if error:
            raise PortalError(
                ErrorKind.JMBG_REJECTED_PORTAL,
                f"Portal je odbio podatke: {error}",
                f"gost {guest.full_name}, JMBG {guest.jmbg}",
            )

        if guest.stay is None:
            raise PortalError(ErrorKind.DATE_INVALID, "Datum boravka nije određen")

        self.next_step()      # 1. → 2.
        self.select_scheme()
        self.next_step()      # 2. → 3.

        self.fill_dates(guest.stay)
        self.submit()
        self.wait_for_confirmation()

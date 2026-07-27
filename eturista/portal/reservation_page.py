"""Forma za prijavu gosta na rezervaciju smeštaja."""

from __future__ import annotations

from selenium.common.exceptions import WebDriverException

from ..errors import ErrorKind, PortalError
from ..models import Guest
from ..validation import Stay
from . import selectors as S
from .base_page import BasePage

#: Putanja forme u odnosu na osnovni URL portala.
RESERVATION_PATH = "/vauceri/rezervacija-smestaja"

#: Format u kom se datum kuca u polje. Potvrđuje se pri inspekciji portala —
#: ako portal očekuje drugačije, menja se samo ova konstanta.
DATE_INPUT_FORMAT = "%d.%m.%Y"


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
        """Datum dolaska i odlaska.

        ZAKLJUČANO do otvaranja registracije za vaučere — vidi ``selectors.DATE_FROM``.
        Ako je polje datepicker a ne obično tekstualno polje, ovde se dodaje otvaranje
        kalendara; to se vidi tek pri inspekciji žive forme.
        """
        self.fill(S.DATE_FROM, stay.arrival.strftime(DATE_INPUT_FORMAT))
        self.fill(S.DATE_TO, stay.departure.strftime(DATE_INPUT_FORMAT))

    def submit(self) -> None:
        """Sačuvaj rezervaciju. ZAKLJUČANO do otvaranja registracije."""
        self.click(S.SUBMIT_RESERVATION)

    def wait_for_confirmation(self) -> str:
        """Sačekaj potvrdu da je rezervacija prošla. ZAKLJUČANO do otvaranja."""
        element = self.find(S.CONFIRMATION)
        return (element.text or "").strip()

    def next_step(self) -> None:
        """Dugme 'Dalje' u formi sa više koraka."""
        self.click(S.NEXT_BUTTON)

    # -- ceo tok za jednog gosta ------------------------------------------

    def register(self, guest: Guest) -> None:
        """Prijavi jednog gosta. Baca ``PortalError`` na prvom problemu.

        Redosled je namerno takav da se JMBG proveri **pre** nego što se bilo šta pošalje —
        pogrešan JMBG tako ne troši ni jedan klik dalje.
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

        self.fill_dates(guest.stay)
        self.submit()
        self.wait_for_confirmation()

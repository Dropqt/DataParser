"""Forma za prijavu gosta na rezervaciju smeštaja."""

from __future__ import annotations

import time
from datetime import date as _date

from selenium.common.exceptions import WebDriverException

from ..errors import ErrorKind, PortalError
from ..models import Guest
from ..validation import Stay
from . import selectors as S
from .base_page import BasePage

#: Putanja forme u odnosu na osnovni URL portala. Potvrđeno na portalu 27.07.2026.
RESERVATION_PATH = "/vauceri/rezervacija-smestaja"

#: Koliko čekamo da se učita tabela prijava ugostitelja. Stiže zasebnim zahtevom pošto
#: se drugi korak otvori - obično oko sekunde, ali pod opterećenjem portala i mnogo
#: duže, pa se ovde čeka posebno i mnogo velikodušnije nego na običan element.
SCHEME_TIMEOUT = 90.0

#: Koliko puta pokušavamo da čekiramo izbor prijave, uz proveru posle svakog klika.
SCHEME_CLICK_ATTEMPTS = 3

#: Koliko čekamo potvrdu da je rezervacija sačuvana. Kao i kod tabele prijava, čuvanje
#: ide kroz mrežu, pa pod opterećenjem portala ume da potraje.
SAVE_TIMEOUT = 90.0

#: Koliko dugo potvrda mora da izdrži da bismo joj verovali. Angular aktivira dugme za
#: štampu **čim se potvrdi dijalog**, dok snimanje na serveru još traje - klik u tom
#: procepu vrati „Greska u stampi rezervacije.pdf“ umesto vaučera.
SAVE_SETTLE = 2.0


def format_date(date: _date) -> str:
    """Datum onako kako ga portal sam upiše kad se izabere iz kalendara: ``15.7.2026``.

    **Bez vodeće nule** - provereno tako što je datum izabran iz portalovog kalendara i
    pročitano šta je ostalo u polju. Nije ``strftime``: ``%-d`` radi samo na Linux-u a
    ``%#d`` samo na Windows-u, a aplikacija se pakuje za oba (faza 7).

    Bitno je i zbog provere u ``BasePage.fill``, koja posle upisa čita polje nazad i
    poredi cifre - ``15.07.2026`` i ``15.7.2026`` joj nisu isti broj.
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
        """Tvrd refresh - koristi se posle greške da se forma očisti za sledećeg gosta."""
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
        """Datum dolaska i odlaska - 3. korak forme.

        Polja jesu deo kalendara (``mat-date-range-input``), ali primaju i običan unos,
        pa se kuca direktno i kalendar se ne otvara.
        """
        self.fill(S.DATE_FROM, format_date(stay.arrival))
        self.fill(S.DATE_TO, format_date(stay.departure))

    def submit(self) -> None:
        """Sačuvaj rezervaciju - klik na „Сачувај“ pa potvrda u dijalogu.

        Portal posle klika otvori dijalog „Да ли сте сигурни да желите да сачувате
        резервацију смештаја?“. Dok se on ne potvrdi, **ništa nije sačuvano** - a
        „Одштампај резервацију“ svejedno odštampa potvrdu iz sadržaja forme, pa se lako
        pomisli da je tura prošla. Zato se potvrda ne preskače.
        """
        self.click(S.SUBMIT_RESERVATION)
        self.confirm_save_dialog()

    def confirm_save_dialog(self) -> bool:
        """Klikni „Да“ u dijalogu za potvrdu. Vraća False ako dijaloga nema.

        Dijalog se traži kratko: ako ga portal jednog dana ukloni, čuvanje ide pravo i
        nema šta da se potvrđuje. Da li je rezervacija stvarno sačuvana ne zaključuje se
        odavde nego iz :meth:`wait_until_saved`.

        Ne proverava se da li je dijalog posle nestao: Angular ostavi prazan
        ``mat-dialog-container`` u DOM-u i posle zatvaranja, pa bi provera po prisustvu
        uvek javljala da je dijalog još otvoren.
        """
        dugme = self.find_optional(S.SAVE_DIALOG_CONFIRM, timeout=5.0, visible=True)
        if dugme is None:
            return False
        self._click_element(dugme, S.SAVE_DIALOG_CONFIRM)
        return True

    def wait_until_saved(self, timeout: float = SAVE_TIMEOUT) -> None:
        """Sačekaj dokaz da je rezervacija stvarno sačuvana.

        **Portal ne ispisuje nikakvu poruku o uspehu** - provereno probnom turom
        29.07.2026: posle potvrde u dijalogu nema ni snackbar-a, ni ``role=alert``, ni
        bilo kakvog teksta. Zato se ne traži poruka nego posledica: dugme „Одштампај
        резервацију“ je onemogućeno dok rezervacija nije sačuvana, pa je njegovo
        aktiviranje jedini pouzdan znak. Isto je viđeno i obrnuto - pre potvrde dijaloga
        dugme je bilo onemogućeno.

        Ovo se **ne sme** preskočiti: portal na klik svejedno odštampa potvrdu iz
        sadržaja forme, pa bi bez ove provere na disk legao uredan vaučer za rezervaciju
        koja ne postoji.
        """
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            if self._saved_marker() and self._marker_holds(SAVE_SETTLE):
                return
            time.sleep(0.3)

        raise PortalError(
            ErrorKind.RESERVATION_NOT_SAVED,
            "Nema potvrde da je rezervacija sačuvana",
            f"čekano {timeout:.0f} s - dugme za štampu se nije aktiviralo i zadržalo",
        )

    def _marker_holds(self, trajanje: float) -> bool:
        """Da li potvrda **ostaje** tu, a ne da je samo bljesnula.

        Dugme za štampu se aktivira čim se potvrdi dijalog, pre nego što snimanje na
        serveru prođe. Klik u tom procepu vrati fajl sa greškom umesto vaučera, pa se
        traži da znak izdrži pre nego što se krene na preuzimanje.
        """
        kraj = time.monotonic() + trajanje
        while time.monotonic() < kraj:
            if not self._saved_marker():
                return False
            time.sleep(0.4)
        return True

    def _saved_marker(self) -> bool:
        """Ima li ijednog znaka da je čuvanje prošlo.

        Dva su, jer se portali razlikuju: poruka o uspehu (ako je portal ikad počne
        prikazivati - vidi ``CONFIRMATION``) ili aktivirano dugme za štampu.
        """
        if self.find_optional(S.CONFIRMATION, timeout=0.5) is not None:
            return True

        element = self.find_optional(S.VOUCHER_DOWNLOAD, timeout=0.5)
        if element is None:
            return False
        try:
            return element.is_enabled()
        except WebDriverException:
            # Strana se promenila pod nogama - element iz prethodne strane je otišao.
            # To nije greška nego znak da još nismo stigli; sledeći krug gleda novi.
            return False

    def next_step(self) -> None:
        """Dugme za sledeći korak.

        Svaki korak ima svoje dugme i sva su u DOM-u, ali neaktivna imaju
        ``visibility: hidden`` - zato se traži **vidljivo**, inače bi se uvek klikalo
        dugme prvog koraka.
        """
        element = self.find_optional(S.NEXT_BUTTON, timeout=self.timeout, visible=True)
        if element is None:
            raise PortalError(
                ErrorKind.SELECTOR_NOT_FOUND,
                f"{S.NEXT_BUTTON.description} nije nađeno na stranici",
            )
        self._click_element(element, S.NEXT_BUTTON)

    def wait_for_scheme(self, timeout: float = SCHEME_TIMEOUT) -> None:
        """Sačekaj da se tabela prijava ugostitelja stvarno učita.

        Tabela ne dolazi sa stranicom nego **zasebnim zahtevom**, pošto se drugi korak
        otvori. Pod opterećenjem portala to ume da potraje mnogo duže od uobičajenih 15
        sekundi koliko se čeka na običan element, pa se ovde čeka posebno i duže.

        Ovo mora da prođe **pre** provere da li je izbor zaključan: dok tabele nema,
        ``SCHEME_ROW_LOCKED`` se ne nalazi, pa bi zaključan portal izgledao kao otvoren.
        """
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            if self.find_optional(S.SCHEME_ROW, timeout=1.0) is not None:
                return
            time.sleep(0.5)

        raise PortalError(
            ErrorKind.TIMEOUT,
            "Tabela prijava ugostitelja se nije učitala",
            f"čekano {timeout:.0f} s na drugom koraku forme",
        )

    def select_scheme(self) -> None:
        """Drugi korak: čekiraj prijavu ugostitelja pod kojom se gost prijavljuje.

        Ako je registracija za vaučere još zaključana, portal drži čekboks onemogućenim
        (tooltip: „Rezervacija smeštaja je zaključana.“). To nije greška u podacima nego
        u trenutku - ista je za svakog gosta, pa se javlja jasno i tura se prekida.

        Posle klika se **proverava da je kvačica stvarno postavljena**. Klik na
        ``mat-checkbox`` prebacuje stanje, pa slepo ponavljanje ne bi bilo ispravljanje
        nego skidanje kvačice; a bez kvačice portal odbija da pređe na treći korak i
        greška ispliva tek na datumima, gde ništa ne znači.
        """
        self.wait_for_scheme()

        if self.is_present(S.SCHEME_ROW_LOCKED, timeout=1.0):
            raise PortalError(
                ErrorKind.RESERVATION_LOCKED,
                "Portal još nije otvorio rezervacije smeštaja",
                "izbor prijave ugostitelja je onemogućen na drugom koraku forme",
            )

        for _ in range(SCHEME_CLICK_ATTEMPTS):
            self.click(S.SCHEME_ROW)
            if self.find_optional(S.SCHEME_ROW_CHECKED, timeout=3.0) is not None:
                return

        raise PortalError(
            ErrorKind.PORTAL_VALIDATION,
            "Izbor prijave ugostitelja se ne čekira",
            f"kliknuto {SCHEME_CLICK_ATTEMPTS} puta, kvačica se nije pojavila",
        )

    # -- ceo tok za jednog gosta ------------------------------------------

    def register(self, guest: Guest) -> None:
        """Prijavi jednog gosta kroz sva tri koraka forme.

        Redosled je namerno takav da se JMBG proveri **pre** nego što se bilo šta pošalje -
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
        self.wait_until_saved()

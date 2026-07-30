"""Osnova za sve stranice portala.

Sve čekanje ide kroz ``WebDriverWait`` - nema ``time.sleep()``. Stara skripta je čekala
fiksnih 1-5 sekundi po koraku, što je istovremeno i sporo (čeka i kad je stranica spremna)
i nepouzdano (ne čeka dovoljno kad portal zaškripi).
"""

from __future__ import annotations

import time
from pathlib import Path

from selenium.common.exceptions import (
    ElementClickInterceptedException,
    ElementNotInteractableException,
    StaleElementReferenceException,
    TimeoutException,
    WebDriverException,
)
from selenium.webdriver.remote.webdriver import WebDriver
from selenium.webdriver.remote.webelement import WebElement
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.support.ui import WebDriverWait

from ..errors import ErrorKind, PortalError
from .selectors import Locator, LocatorState

#: Koliko čekamo da se element pojavi pre nego što odustanemo.
DEFAULT_TIMEOUT = 15.0

#: Kratko čekanje za elemente koje očekujemo da najčešće NEMA (poruke o grešci).
PROBE_TIMEOUT = 1.5


class BasePage:
    def __init__(self, driver: WebDriver, timeout: float = DEFAULT_TIMEOUT) -> None:
        self.driver = driver
        self.timeout = timeout

    # -- pronalaženje -----------------------------------------------------

    def find(self, locator: Locator, timeout: float | None = None) -> WebElement:
        """Nađi element probajući redom sve kandidate iz lokatora.

        Baca ``PortalError(SELECTOR_NOT_FOUND)`` sa opisom na srpskom - nikad goli
        ``NoSuchElementException``, da bi u koloni RAZLOG pisalo nešto upotrebljivo.
        """
        if not locator.is_ready:
            raise PortalError(
                ErrorKind.SELECTOR_NOT_FOUND,
                f"{locator.description}: selektor još nije podešen",
                f"{locator.name} je označen kao {LocatorState.LOCKED.value}",
            )

        element = self._first_match(locator, timeout if timeout is not None else self.timeout)
        if element is None:
            raise PortalError(
                ErrorKind.SELECTOR_NOT_FOUND,
                f"{locator.description} nije nađeno na stranici",
                f"{locator.name}: isprobano {len(locator.candidates)} selektora",
            )
        return element

    def find_optional(
        self, locator: Locator, timeout: float = PROBE_TIMEOUT, *, visible: bool = False
    ) -> WebElement | None:
        """Kao ``find``, ali vraća None umesto da baca. Za elemente kojih najčešće nema."""
        if not locator.is_ready:
            return None
        return self._first_match(locator, timeout, visible=visible)

    def is_visible(self, locator: Locator, timeout: float = PROBE_TIMEOUT) -> bool:
        """Da li je element ne samo u DOM-u nego i na ekranu.

        Forma rezervacije je stepper: polja svih koraka postoje u DOM-u sve vreme, ali
        su sakrivena dok se ne dođe do njihovog koraka. ``is_present`` bi zato rekao da
        polje za datum postoji i kad smo tek na prvom koraku.
        """
        return self.find_optional(locator, timeout, visible=True) is not None

    def _first_match(
        self, locator: Locator, timeout: float, *, visible: bool = False
    ) -> WebElement | None:
        # Ukupan budžet se deli na kandidate: prvi dobija najviše vremena jer je
        # najverovatniji, ostali samo brzu proveru.
        # Namerno ``visibility_of_any_elements_located``, ne ``visibility_of_element_located``:
        # ovaj drugi gleda samo *prvi* element koji odgovara selektoru i čeka da baš on
        # postane vidljiv. Forma rezervacije ima po jedno dugme „dalje“ u svakom koraku;
        # kad smo na drugom koraku, prvo u DOM-u je sakriveno dugme prvog koraka, pa bi
        # se čekalo do isteka vremena umesto da se uzme ono vidljivo.
        condition = (
            EC.visibility_of_any_elements_located if visible else EC.presence_of_element_located
        )
        deadline = time.monotonic() + max(timeout, 0.0)
        for index, (by, value) in enumerate(locator.candidates):
            remaining = deadline - time.monotonic()
            if remaining <= 0 and index > 0:
                break
            slice_timeout = max(remaining if index == 0 else min(remaining, 1.0), 0.1)
            try:
                found = WebDriverWait(self.driver, slice_timeout).until(condition((by, value)))
            except (TimeoutException, WebDriverException):
                continue
            return found[0] if visible else found
        return None

    def is_present(self, locator: Locator, timeout: float = PROBE_TIMEOUT) -> bool:
        return self.find_optional(locator, timeout) is not None

    def text_of(self, locator: Locator, timeout: float = PROBE_TIMEOUT) -> str:
        element = self.find_optional(locator, timeout)
        if element is None:
            return ""
        try:
            return (element.text or "").strip()
        except StaleElementReferenceException:
            return ""

    # -- interakcija ------------------------------------------------------

    def fill(self, locator: Locator, value: str, timeout: float | None = None) -> None:
        """Upiši vrednost i proveri da je stvarno ušla.

        Angular ume da odbije ili preformatira unos (maske za JMBG i datume), pa se
        posle upisa čita nazad - bolje da ovde padne nego da se pošalje prazno polje.

        Polje ume da **postoji a da ne prima unos**. Dva razloga, oba viđena na portalu:

        * korak wizard-a se otvara uz animaciju, pa je sadržaj u DOM-u pre nego što
          postane interaktivan;
        * ``mat-date-range-input`` drži unutrašnja polja (``Датум од`` / ``Датум до``)
          **nevidljivim dok se polje ne aktivira** - dok se ne fokusira, vidi se samo
          skupljeni natpis „Период резервације“.

        Zato se pre svakog pokušaja polje fokusira, pa se upis ponavlja dok ne prođe.
        Ako ni to ne uspe, vrednost se upisuje kroz JavaScript uz ``input``/``change``
        događaje, da je Angular pokupi kao da je otkucana.
        """
        limit = self.timeout if timeout is None else timeout
        deadline = time.monotonic() + limit

        while True:
            element = self.find(locator, timeout)
            self._focus(element)
            try:
                WebDriverWait(self.driver, 1.0).until(EC.element_to_be_clickable(element))
            except TimeoutException:
                pass  # provera ispod je merodavna

            try:
                element.clear()
                element.send_keys(value)
                break
            except (ElementNotInteractableException, StaleElementReferenceException) as exc:
                if time.monotonic() >= deadline:
                    if self._set_value_via_js(locator, value):
                        break
                    raise PortalError(
                        ErrorKind.SELECTOR_NOT_FOUND,
                        f"{locator.description} ne prima unos",
                        str(exc),
                    ) from exc
                time.sleep(0.2)

        written = (element.get_attribute("value") or "").strip()
        if written and _digits(written) != _digits(value) and written != value:
            raise PortalError(
                ErrorKind.PORTAL_VALIDATION,
                f"{locator.description}: portal je promenio uneto ({value!r} → {written!r})",
            )

    def _focus(self, element: WebElement) -> None:
        """Dovuci polje u vidno polje i fokusiraj ga.

        Material otkrije unutrašnja polja ``mat-date-range-input``-a tek kad se grupa
        fokusira; bez ovoga su ``displayed=False`` i Selenium odbija da kuca u njih.
        """
        try:
            self.driver.execute_script(
                "arguments[0].scrollIntoView({block: 'center'}); arguments[0].focus();",
                element,
            )
        except WebDriverException:
            pass  # fokus je pomoć, ne uslov - upis ispod svejedno pokušava

    def _set_value_via_js(self, locator: Locator, value: str) -> bool:
        """Poslednja linija odbrane: upiši vrednost i javi Angular-u da se promenila.

        Bez ``input``/``change`` događaja Angular ne vidi izmenu i polje ostane
        „netaknuto“, pa forma odbije da se pošalje. Vraća True ako je vrednost legla.
        """
        try:
            element = self.find(locator, timeout=2.0)
            self.driver.execute_script(
                """
                const [el, v] = arguments;
                el.value = v;
                el.dispatchEvent(new Event('input', {bubbles: true}));
                el.dispatchEvent(new Event('change', {bubbles: true}));
                el.dispatchEvent(new Event('blur', {bubbles: true}));
                """,
                element,
                value,
            )
            return (element.get_attribute("value") or "").strip() != ""
        except (WebDriverException, PortalError):
            return False

    def click(self, locator: Locator, timeout: float | None = None) -> None:
        """Klikni, sa jednim pokušajem preko JavaScript-a ako nešto prekriva dugme."""
        self._click_element(self.find(locator, timeout), locator)

    def _click_element(self, element: WebElement, locator: Locator) -> None:
        """Klik na već pronađen element. ``locator`` služi samo za poruku o grešci."""
        try:
            WebDriverWait(self.driver, self.timeout).until(EC.element_to_be_clickable(element))
        except TimeoutException:
            pass  # svejedno pokušavamo - provera ispod je merodavna

        try:
            element.click()
        except (ElementClickInterceptedException, ElementNotInteractableException):
            # Angular Material overlay (snackbar, tooltip) ume da prekrije dugme.
            try:
                self.driver.execute_script("arguments[0].click();", element)
            except WebDriverException as exc:
                raise PortalError(
                    ErrorKind.SELECTOR_NOT_FOUND,
                    f"Ne mogu da kliknem: {locator.description}",
                    str(exc),
                ) from exc
        except StaleElementReferenceException as exc:
            raise PortalError(
                ErrorKind.TIMEOUT,
                f"Stranica se promenila pre klika na: {locator.description}",
                str(exc),
            ) from exc

    # -- čekanje ----------------------------------------------------------

    def wait_until_gone(self, locator: Locator, timeout: float | None = None) -> None:
        wait = timeout if timeout is not None else self.timeout
        try:
            WebDriverWait(self.driver, wait).until_not(
                EC.presence_of_element_located(locator.primary)
            )
        except TimeoutException as exc:
            raise PortalError(
                ErrorKind.TIMEOUT,
                f"{locator.description} se ne sklanja sa ekrana",
            ) from exc

    def wait_for(self, locator: Locator, timeout: float | None = None) -> WebElement:
        return self.find(locator, timeout)

    # -- dijagnostika -----------------------------------------------------

    def screenshot(self, directory: Path, name: str) -> str | None:
        """Snimi ekran u trenutku greške. Vraća putanju ili None ako ni to ne uspe."""
        try:
            directory.mkdir(parents=True, exist_ok=True)
            path = directory / f"{name}.png"
            self.driver.save_screenshot(str(path))
            return str(path)
        except (WebDriverException, OSError):
            return None


def _digits(text: str) -> str:
    return "".join(ch for ch in text if ch.isdigit())

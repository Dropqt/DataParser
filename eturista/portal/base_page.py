"""Osnova za sve stranice portala.

Sve čekanje ide kroz ``WebDriverWait`` — nema ``time.sleep()``. Stara skripta je čekala
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

        Baca ``PortalError(SELECTOR_NOT_FOUND)`` sa opisom na srpskom — nikad goli
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

    def find_optional(self, locator: Locator, timeout: float = PROBE_TIMEOUT) -> WebElement | None:
        """Kao ``find``, ali vraća None umesto da baca. Za elemente kojih najčešće nema."""
        if not locator.is_ready:
            return None
        return self._first_match(locator, timeout)

    def _first_match(self, locator: Locator, timeout: float) -> WebElement | None:
        # Ukupan budžet se deli na kandidate: prvi dobija najviše vremena jer je
        # najverovatniji, ostali samo brzu proveru.
        deadline = time.monotonic() + max(timeout, 0.0)
        for index, (by, value) in enumerate(locator.candidates):
            remaining = deadline - time.monotonic()
            if remaining <= 0 and index > 0:
                break
            slice_timeout = max(remaining if index == 0 else min(remaining, 1.0), 0.1)
            try:
                return WebDriverWait(self.driver, slice_timeout).until(
                    EC.presence_of_element_located((by, value))
                )
            except (TimeoutException, WebDriverException):
                continue
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
        posle upisa čita nazad — bolje da ovde padne nego da se pošalje prazno polje.
        """
        element = self.find(locator, timeout)
        try:
            element.clear()
            element.send_keys(value)
        except (ElementNotInteractableException, StaleElementReferenceException) as exc:
            raise PortalError(
                ErrorKind.SELECTOR_NOT_FOUND,
                f"{locator.description} ne prima unos",
                str(exc),
            ) from exc

        written = (element.get_attribute("value") or "").strip()
        if written and _digits(written) != _digits(value) and written != value:
            raise PortalError(
                ErrorKind.PORTAL_VALIDATION,
                f"{locator.description}: portal je promenio uneto ({value!r} → {written!r})",
            )

    def click(self, locator: Locator, timeout: float | None = None) -> None:
        """Klikni, sa jednim pokušajem preko JavaScript-a ako nešto prekriva dugme."""
        element = self.find(locator, timeout)
        try:
            WebDriverWait(self.driver, self.timeout).until(EC.element_to_be_clickable(element))
        except TimeoutException:
            pass  # svejedno pokušavamo — provera ispod je merodavna

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

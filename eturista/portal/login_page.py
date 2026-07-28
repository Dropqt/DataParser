"""Prijava na nalog."""

from __future__ import annotations

from selenium.common.exceptions import TimeoutException, WebDriverException
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.support.ui import WebDriverWait

from ..accounts import Account
from ..errors import ErrorKind, PortalError
from . import selectors as S
from .base_page import BasePage


class LoginPage(BasePage):
    def __init__(self, driver, base_url: str, timeout: float = 15.0) -> None:
        super().__init__(driver, timeout)
        self.base_url = base_url.rstrip("/")

    def open(self) -> None:
        try:
            self.driver.get(self.base_url)
        except WebDriverException as exc:
            raise PortalError(
                ErrorKind.TIMEOUT,
                f"Portal se ne otvara ({self.base_url})",
                str(exc),
            ) from exc

    def login(self, account: Account) -> None:
        """Prijavi se. Baca ``PortalError(LOGIN_FAILED)`` ako ne prođe."""
        self.fill(S.LOGIN_USERNAME, account.username)
        self.fill(S.LOGIN_PASSWORD, account.password)
        self.click(S.LOGIN_SUBMIT)

        if not self._wait_until_submitted():
            message = self.text_of(S.LOGIN_ERROR, timeout=1.0)
            raise PortalError(
                ErrorKind.LOGIN_FAILED,
                f"Prijava na nalog '{account.label}' nije uspela"
                + (f": {message}" if message else " - proveri korisničko ime i lozinku"),
            )

    def _wait_until_submitted(self) -> bool:
        """Prijava je prošla kad polje za korisničko ime više nije na stranici.

        Ovo je pouzdanije od traženja nekog elementa "posle prijave", jer ne zavisi od
        toga kako izgleda početna strana naloga - a ona se menja između sezona.
        """
        try:
            WebDriverWait(self.driver, self.timeout).until(
                EC.invisibility_of_element_located(S.LOGIN_USERNAME.primary)
            )
            return True
        except TimeoutException:
            return False

    def is_logged_in(self) -> bool:
        """Provera da sesija nije istekla - koristi se između gostiju."""
        if S.LOGGED_IN_MARKER.is_ready:
            return self.is_present(S.LOGGED_IN_MARKER, timeout=2.0)
        # Dok marker nije potvrđen na živom portalu, oslanjamo se na to da forma za
        # prijavu nije ponovo iskočila.
        return not self.is_present(S.LOGIN_USERNAME, timeout=1.0)

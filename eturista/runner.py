"""Orkestracija jedne ture: prijava na nalog pa gost po gost.

Pravila po dogovoru:

* Greška **nikad ne prekida turu** — gost pocrveni, snimi se screenshot, uradi se tvrd
  refresh forme i ide se na sledećeg. (Stara skripta je imala ``break`` pa je jedna
  greška gubila ostatak liste.)
* Svaki gost se snima u bazu **odmah po obradi**, pa nagli prekid ne gubi napredak.
* Istekla sesija nije greška gosta — pokuša se ponovna prijava pa se gost ponovi.

Jedinica rada je **sesija** = (nalog, sopstveni browser, lista gostiju). Paralelni režim
je zato samo pokretanje više Runner-a odjednom, bez ijedne izmene u ovom fajlu.
"""

from __future__ import annotations

import threading
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Callable

from selenium.common.exceptions import WebDriverException

from .accounts import Account
from .config import Config
from .driver import BrowserSession
from .errors import ErrorKind, GuestError, PortalError
from .models import Batch, Guest, Status
from .portal import selectors as S
from .portal.login_page import LoginPage
from .portal.reservation_page import ReservationPage
from .portal.voucher_page import VoucherPage
from .store import Store


@dataclass
class RunOptions:
    #: Koliko puta ukupno pokušati gosta kod greške koja ima smisla da se ponovi.
    max_attempts: int = 2
    #: Preuzimanje vaučera. Isključi dok selektor za vaučer nije potvrđen.
    download_vouchers: bool = True
    #: Snimanje ekrana pri svakoj grešci.
    screenshots: bool = True


@dataclass
class Reporter:
    """Kuke ka GUI-ju. Sve su opcione — runner radi i bez ijedne."""

    on_message: Callable[[str, str], None] | None = None
    on_guest_started: Callable[[Guest], None] | None = None
    on_guest_finished: Callable[[Guest], None] | None = None
    on_progress: Callable[[int, int], None] | None = None

    def message(self, text: str, level: str = "INFO") -> None:
        if self.on_message:
            self.on_message(text, level)

    def started(self, guest: Guest) -> None:
        if self.on_guest_started:
            self.on_guest_started(guest)

    def finished(self, guest: Guest) -> None:
        if self.on_guest_finished:
            self.on_guest_finished(guest)

    def progress(self, done: int, total: int) -> None:
        if self.on_progress:
            self.on_progress(done, total)


@dataclass
class RunResult:
    total: int = 0
    succeeded: int = 0
    failed: int = 0
    stopped: bool = False
    fatal: str = ""
    errors: list[tuple[Guest, GuestError]] = field(default_factory=list)

    def summary(self) -> str:
        if self.fatal:
            return f"Tura prekinuta: {self.fatal}"
        prefix = "Zaustavljeno" if self.stopped else "Gotovo"
        return f"{prefix} — {self.succeeded} prijavljeno, {self.failed} grešaka (od {self.total})"


class Runner:
    def __init__(
        self,
        config: Config,
        account: Account,
        batch: Batch,
        store: Store | None = None,
        options: RunOptions | None = None,
        reporter: Reporter | None = None,
        stop_event: threading.Event | None = None,
    ) -> None:
        self.config = config
        self.account = account
        self.batch = batch
        self.store = store
        self.options = options or RunOptions()
        self.reporter = reporter or Reporter()
        self.stop_event = stop_event or threading.Event()

        self.session: BrowserSession | None = None
        self.login_page: LoginPage | None = None
        self.reservation_page: ReservationPage | None = None
        self.voucher_page: VoucherPage | None = None

    # -- javni ulaz -------------------------------------------------------

    def run(self) -> RunResult:
        guests = self.batch.pending()
        result = RunResult(total=len(guests))

        if not guests:
            self.reporter.message("Nema gostiju za prijavu.", "WARN")
            return result

        self.config.ensure_dirs()
        self._persist_batch()

        try:
            self._open_browser()
            self._login()
        except PortalError as exc:
            result.fatal = exc.message
            self.reporter.message(exc.message, "ERROR")
            self._log_db(exc.message, "ERROR")
            self._close_browser()
            return result

        try:
            for index, guest in enumerate(guests, start=1):
                if self.stop_event.is_set():
                    result.stopped = True
                    self.reporter.message("Zaustavljeno na zahtev korisnika.", "WARN")
                    break

                self.reporter.message(
                    f"[{index}/{len(guests)}] {guest.full_name} ({guest.jmbg})"
                )
                self._process_guest(guest)

                if guest.status is Status.OK:
                    result.succeeded += 1
                else:
                    result.failed += 1
                    if guest.error:
                        result.errors.append((guest, guest.error))

                self.reporter.progress(index, len(guests))
        finally:
            self._close_browser()

        self.reporter.message(result.summary(), "INFO")
        self._log_db(result.summary())
        return result

    # -- browser i prijava ------------------------------------------------

    def _open_browser(self) -> None:
        self.session = BrowserSession(
            download_dir=self.config.pdf_dir / "_preuzimanje",
            headless=self.config.headless,
        )
        driver = self.session.start()
        self.login_page = LoginPage(driver, self.config.portal_url)
        self.reservation_page = ReservationPage(driver, self.config.portal_url)
        self.voucher_page = VoucherPage(driver, self.session)

    def _close_browser(self) -> None:
        if self.session is not None:
            self.session.quit()
            self.session = None

    def _login(self) -> None:
        assert self.login_page is not None
        self.reporter.message(f"Prijava na nalog: {self.account.label}")
        self.login_page.open()
        self.login_page.login(self.account)
        self.reporter.message("Prijava uspela.")

    def _relogin(self) -> bool:
        try:
            self._login()
            return True
        except PortalError as exc:
            self.reporter.message(f"Ponovna prijava nije uspela: {exc.message}", "ERROR")
            return False

    # -- jedan gost -------------------------------------------------------

    def _process_guest(self, guest: Guest) -> None:
        assert self.reservation_page is not None

        for attempt in range(1, self.options.max_attempts + 1):
            guest.mark_running()
            self.reporter.started(guest)
            self._save_guest(guest)

            try:
                self.reservation_page.open()
                self.reservation_page.register(guest)
                pdf = self._download_voucher(guest)
                guest.mark_ok(pdf)
                self.reporter.message(f"    ✓ prijavljen{f' → {Path(pdf).name}' if pdf else ''}")
                break

            except PortalError as exc:
                error = self._classify(exc)

                if error.kind is ErrorKind.SESSION_EXPIRED and attempt < self.options.max_attempts:
                    self.reporter.message("    sesija istekla — prijavljujem se ponovo", "WARN")
                    if self._relogin():
                        continue

                if error.kind.is_retryable and attempt < self.options.max_attempts:
                    self.reporter.message(f"    {error.text} — pokušavam ponovo", "WARN")
                    self._recover()
                    continue

                guest.mark_error(self._with_screenshot(guest, error))
                self.reporter.message(f"    ✗ {error.text}", "ERROR")
                self._recover()
                break

            except WebDriverException as exc:
                error = GuestError(ErrorKind.BROWSER_CRASHED, "Browser je prekinuo rad", str(exc))
                guest.mark_error(error)
                self.reporter.message(f"    ✗ {error.text}", "ERROR")
                break

        self._save_guest(guest)
        self.reporter.finished(guest)

    def _classify(self, exc: PortalError) -> GuestError:
        """Prepoznaj istekli sesiju: forma je nestala jer nas je portal izbacio."""
        if exc.kind is ErrorKind.SELECTOR_NOT_FOUND and self.login_page is not None:
            if self.login_page.is_present(S.LOGIN_USERNAME, timeout=1.0):
                return GuestError(
                    ErrorKind.SESSION_EXPIRED,
                    "Portal je vratio na prijavu — sesija je istekla",
                    exc.detail,
                )
        return exc.as_guest_error()

    def _with_screenshot(self, guest: Guest, error: GuestError) -> GuestError:
        if not self.options.screenshots or self.reservation_page is None:
            return error
        stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
        name = f"{stamp}_red{guest.row}_{error.kind.value}"
        path = self.reservation_page.screenshot(self.config.screenshot_dir, name)
        return GuestError(error.kind, error.message, error.detail, path) if path else error

    def _download_voucher(self, guest: Guest) -> str | None:
        """Preuzmi vaučer ako je preuzimanje uopšte podešeno.

        Dok je ``VOUCHER_DOWNLOAD`` zaključan, gost se i dalje računa kao prijavljen —
        samo bez PDF-a. Tako tura može da radi i pre nego što se taj deo portala otvori.
        """
        if not self.options.download_vouchers or self.voucher_page is None:
            return None
        if not self.voucher_page.is_available:
            return None
        return self.voucher_page.download(guest, self.config.pdf_dir, self.config.year)

    def _recover(self) -> None:
        """Tvrd refresh forme — sledeći gost kreće od čistog stanja."""
        if self.reservation_page is not None:
            self.reservation_page.reload()

    # -- baza -------------------------------------------------------------

    def _persist_batch(self) -> None:
        if self.store is not None:
            self.batch.account_label = self.account.label
            self.store.save_batch(self.batch)

    def _save_guest(self, guest: Guest) -> None:
        if self.store is not None and self.batch.db_id is not None:
            self.store.save_guest(self.batch.db_id, guest)

    def _log_db(self, message: str, level: str = "INFO") -> None:
        if self.store is not None:
            self.store.log(message, level, batch_id=self.batch.db_id)


# ---------------------------------------------------------------------------
# Provera selektora  (run.py --proveri-selektore)
# ---------------------------------------------------------------------------

@dataclass
class SelectorCheck:
    locator: S.Locator
    found: bool
    matched_by: str = ""


def verify_selectors(config: Config, account: Account) -> list[SelectorCheck]:
    """Prijavi se, otvori formu i proveri koji selektori zaista razrešavaju element.

    Ovo je prvo što se pokreće na dan otvaranja registracije: odmah se vidi šta radi,
    šta je puklo posle update-a portala i šta je još zaključano.
    """
    from .portal.base_page import BasePage

    results: list[SelectorCheck] = []
    session = BrowserSession(download_dir=config.pdf_dir / "_preuzimanje", headless=config.headless)
    driver = session.start()

    try:
        login = LoginPage(driver, config.portal_url)
        login.open()

        # Selektori sa strane za prijavu se proveravaju dok smo još na njoj.
        page = BasePage(driver)
        for locator in (S.LOGIN_USERNAME, S.LOGIN_PASSWORD, S.LOGIN_SUBMIT):
            results.append(_check(page, locator))

        login.login(account)

        reservation = ReservationPage(driver, config.portal_url)
        reservation.open()

        checked = {S.LOGIN_USERNAME, S.LOGIN_PASSWORD, S.LOGIN_SUBMIT}
        for locator in S.REGISTRY:
            if locator not in checked:
                results.append(_check(reservation, locator))
    finally:
        session.quit()

    return results


def _check(page, locator: S.Locator) -> SelectorCheck:
    for by, value in locator.candidates:
        try:
            if page.driver.find_elements(by, value):
                return SelectorCheck(locator, True, f"{by}={value}")
        except WebDriverException:
            continue
    return SelectorCheck(locator, False)

"""Niti koje voze Selenium, da se prozor ne zamrzne.

Selenium blokira sekundama po koraku. Kad bi to radilo u GUI niti, aplikacija bi izgledala
kao da je pukla i dugme "Zaustavi" ne bi radilo. Zato sve ide u ``QThread``, a nazad se
javlja isključivo Qt signalima — oni se sami prebacuju u GUI nit.
"""

from __future__ import annotations

import threading

from PySide6.QtCore import QThread, Signal

from ..accounts import Account
from ..config import Config
from ..models import Batch
from ..runner import Reporter, RunOptions, Runner, verify_selectors
from ..store import Store


class RunWorker(QThread):
    """Prijava jedne ture."""

    message = Signal(str, str)      # tekst, nivo
    guest_updated = Signal(object)  # Guest
    progress = Signal(int, int)     # obrađeno, ukupno
    done = Signal(object)           # RunResult

    def __init__(
        self,
        config: Config,
        account: Account,
        batch: Batch,
        store: Store | None = None,
        options: RunOptions | None = None,
        parent=None,
    ) -> None:
        super().__init__(parent)
        self.config = config
        self.account = account
        self.batch = batch
        self.store = store
        self.options = options or RunOptions()
        self._stop = threading.Event()

    def stop(self) -> None:
        self._stop.set()
        self.message.emit("Zaustavljam posle tekućeg gosta…", "WARN")

    def run(self) -> None:  # izvršava se u radnoj niti
        reporter = Reporter(
            on_message=lambda text, level: self.message.emit(text, level),
            on_guest_started=self.guest_updated.emit,
            on_guest_finished=self.guest_updated.emit,
            on_progress=lambda done, total: self.progress.emit(done, total),
        )
        runner = Runner(
            self.config,
            self.account,
            self.batch,
            store=self.store,
            options=self.options,
            reporter=reporter,
            stop_event=self._stop,
        )
        try:
            result = runner.run()
        except Exception as exc:  # nikad ne rušimo GUI zbog greške u niti
            self.message.emit(f"Neočekivana greška: {exc}", "ERROR")
            from ..runner import RunResult
            result = RunResult(fatal=str(exc))
        self.done.emit(result)


class SelectorCheckWorker(QThread):
    """Provera koji selektori i dalje važe na živom portalu."""

    message = Signal(str, str)
    done = Signal(object)  # list[SelectorCheck] ili None ako je puklo

    def __init__(self, config: Config, account: Account, parent=None) -> None:
        super().__init__(parent)
        self.config = config
        self.account = account

    def run(self) -> None:
        self.message.emit(f"Prijava na nalog {self.account.label} radi provere selektora…", "INFO")
        try:
            self.done.emit(verify_selectors(self.config, self.account))
        except Exception as exc:
            self.message.emit(f"Provera nije uspela: {exc}", "ERROR")
            self.done.emit(None)


class UpdateCheckWorker(QThread):
    """Provera da li na GitHub-u ima novija verzija.

    Ide u zasebnu nit da mreža ne bi odlagala pojavljivanje prozora. Ako nema interneta
    ili GitHub ne odgovori, tiho se odustaje — provera nikad ne sme da smeta radu.
    """

    done = Signal(object)  # UpdateInfo ili None

    def run(self) -> None:
        from ..update import check_for_update

        try:
            self.done.emit(check_for_update())
        except Exception:
            self.done.emit(None)

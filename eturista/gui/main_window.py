"""Glavni prozor aplikacije."""

from __future__ import annotations

from datetime import datetime
from pathlib import Path

from PySide6.QtCore import Qt
from PySide6.QtGui import QAction, QKeySequence
from PySide6.QtWidgets import (
    QAbstractItemView,
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QHBoxLayout,
    QLabel,
    QListWidget,
    QListWidgetItem,
    QMainWindow,
    QMessageBox,
    QPlainTextEdit,
    QProgressBar,
    QPushButton,
    QSplitter,
    QVBoxLayout,
    QWidget,
)

from ..accounts import Account, load_accounts
from ..config import Config, app_dir, env_leak_warning
from ..models import Batch, Status
from ..portal import selectors as S
from ..runner import RunOptions
from ..store import Store
from .guest_table import GuestTable, open_in_system
from .table_model import GuestTableModel
from .worker import RunWorker, SelectorCheckWorker

_LEVEL_COLORS = {"ERROR": "#d1242f", "WARN": "#bf8700", "INFO": ""}


class MainWindow(QMainWindow):
    def __init__(self, config: Config) -> None:
        super().__init__()
        self.config = config
        self.config.ensure_dirs()

        self.store = Store(config.db_path)
        self.batch = Batch()
        self.model = GuestTableModel(self.batch.guests, year=config.year)
        self.worker: RunWorker | None = None
        self.check_worker: SelectorCheckWorker | None = None

        self.setWindowTitle("eTurista — prijava gostiju")
        self.resize(1180, 760)

        self._build_ui()
        self._build_menu()
        self._load_accounts()
        self._startup_checks()
        self._update_status()

    # ------------------------------------------------------------------ UI

    def _build_ui(self) -> None:
        self.account_box = QComboBox()
        self.account_box.setMinimumWidth(170)

        self.paste_button = QPushButton("Nalepi iz Excela")
        self.paste_button.setToolTip("Ctrl+V — kopiraj grupu gostiju iz glavnog Excela")
        self.paste_button.clicked.connect(self._paste)

        self.copy_button = QPushButton("Kopiraj rezultat")
        self.copy_button.setToolTip("Ctrl+C — vrati redove u glavni Excel, sa STATUS kolonom")
        self.copy_button.clicked.connect(self._copy)

        self.start_button = QPushButton("▶  Pokreni turu")
        self.start_button.setDefault(True)
        self.start_button.clicked.connect(self._start)

        self.stop_button = QPushButton("■  Zaustavi")
        self.stop_button.setEnabled(False)
        self.stop_button.clicked.connect(self._stop)

        toolbar = QHBoxLayout()
        toolbar.setContentsMargins(10, 8, 10, 4)
        toolbar.addWidget(QLabel("Nalog:"))
        toolbar.addWidget(self.account_box)
        toolbar.addSpacing(16)
        toolbar.addWidget(self.paste_button)
        toolbar.addWidget(self.copy_button)
        toolbar.addStretch(1)
        toolbar.addWidget(self.start_button)
        toolbar.addWidget(self.stop_button)

        self.table = GuestTable(self.model)
        self.table.pasted.connect(self._on_pasted)
        self.table.copied.connect(lambda n: self._log(f"Kopirano {n} redova u clipboard."))
        self.table.guests_removed.connect(lambda n: self._update_status())
        self.model.dataChanged.connect(lambda *_: self._update_status())

        self.log_view = QPlainTextEdit()
        self.log_view.setReadOnly(True)
        self.log_view.setMaximumBlockCount(2000)
        self.log_view.setPlaceholderText("Tok rada se ispisuje ovde…")

        splitter = QSplitter(Qt.Vertical)
        splitter.addWidget(self.table)
        splitter.addWidget(self.log_view)
        splitter.setSizes([520, 190])

        central = QWidget()
        layout = QVBoxLayout(central)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addLayout(toolbar)
        layout.addWidget(splitter, 1)
        self.setCentralWidget(central)

        self.progress = QProgressBar()
        self.progress.setMaximumWidth(220)
        self.progress.setVisible(False)
        self.status_label = QLabel()
        self.statusBar().addWidget(self.status_label, 1)
        self.statusBar().addPermanentWidget(self.progress)

    def _build_menu(self) -> None:
        files = self.menuBar().addMenu("&Datoteka")
        files.addAction(self._action("Nova tura", self._new_batch, QKeySequence.New))
        files.addAction(self._action("Otvori raniju turu…", self._open_batch, QKeySequence.Open))
        files.addSeparator()
        files.addAction(self._action("Izlaz", self.close, QKeySequence.Quit))

        edit = self.menuBar().addMenu("&Uređivanje")
        edit.addAction(self._action("Nalepi iz Excela", self._paste, QKeySequence.Paste))
        edit.addAction(self._action("Kopiraj rezultat", self._copy, QKeySequence.Copy))
        edit.addSeparator()
        edit.addAction(self._action("Označi sve", lambda: self._select_all(True)))
        edit.addAction(self._action("Skini oznaku sa svih", lambda: self._select_all(False)))
        edit.addAction(self._action("Vrati greške u red", self._retry_failed))

        tools = self.menuBar().addMenu("&Alatke")
        tools.addAction(self._action("Otvori folder sa vaučerima", self._open_pdf_dir))
        tools.addAction(self._action("Otvori folder sa screenshot-ovima", self._open_shot_dir))
        tools.addSeparator()
        tools.addAction(self._action("Proveri selektore na portalu…", self._check_selectors))
        tools.addAction(self._action("Stanje selektora", self._show_selector_states))

        help_menu = self.menuBar().addMenu("&Pomoć")
        help_menu.addAction(self._action("Kako se koristi", self._show_help))

    def _action(self, text: str, slot, shortcut=None) -> QAction:
        action = QAction(text, self)
        action.triggered.connect(slot)
        if shortcut is not None:
            action.setShortcut(shortcut)
        return action

    # -------------------------------------------------------------- pokretanje

    def _load_accounts(self) -> None:
        self.accounts: list[Account] = load_accounts()
        self.account_box.clear()
        self.account_box.addItems([account.label for account in self.accounts])
        self.account_box.setEnabled(bool(self.accounts))

    def _startup_checks(self) -> None:
        warning = env_leak_warning()
        if warning:
            self._log(warning, "ERROR")
            QMessageBox.warning(self, "Lozinke u gitu", warning)

        if not self.accounts:
            path = app_dir() / ".env"
            message = (
                f"Nema podešenih naloga.\n\nNapravi fajl:\n{path}\n\n"
                "po uzoru na .env.example, pa restartuj program."
            )
            self._log("Nema podešenih naloga — vidi .env.example", "WARN")
            QMessageBox.information(self, "Nalozi nisu podešeni", message)

        locked = S.locked()
        if locked:
            names = ", ".join(locator.description for locator in locked)
            self._log(
                f"Zaključano do otvaranja registracije ({len(locked)}): {names}", "WARN"
            )

    # ------------------------------------------------------------------ akcije

    def _paste(self) -> None:
        self.table.paste_from_clipboard(self.config.year)

    def _on_pasted(self, result) -> None:
        for warning in result.warnings:
            self._log(warning, "WARN")

        if not result.guests:
            QMessageBox.warning(
                self,
                "Nije prepoznato",
                "\n".join(result.warnings)
                or "Clipboard je prazan — kopiraj redove iz Excela pa probaj ponovo.",
            )
            return

        bad = sum(1 for guest in result.guests if guest.status is Status.ERROR)
        self._log(
            f"Zalepljeno {len(result.guests)} gostiju ({result.mapping.describe()})"
            + (f" — {bad} sa neispravnim podacima" if bad else "")
        )
        self._update_status()

    def _copy(self) -> None:
        if not self.model.guests:
            return
        self.table.copy_to_clipboard(only_selected=bool(self.table.selected_rows()))

    def _select_all(self, selected: bool) -> None:
        self.model.set_all_selected(selected)
        self._update_status()

    def _retry_failed(self) -> None:
        count = 0
        for guest in self.model.guests:
            if guest.status is Status.ERROR and not (guest.error and guest.error.kind.is_data_problem):
                guest.reset()
                count += 1
        self.model.refresh_all()
        self._log(f"Vraćeno u red: {count} gostiju.")
        self._update_status()

    def _new_batch(self) -> None:
        if self._is_running():
            return
        if self.model.guests and QMessageBox.question(
            self, "Nova tura", "Obrisati tekuću listu gostiju?"
        ) != QMessageBox.Yes:
            return
        self.batch = Batch()
        self.model.set_guests(self.batch.guests)
        self.log_view.clear()
        self._update_status()

    def _open_batch(self) -> None:
        if self._is_running():
            return
        rows = self.store.list_batches()
        if not rows:
            QMessageBox.information(self, "Ranije ture", "Još nema sačuvanih tura.")
            return

        dialog = _BatchPicker(rows, self)
        if dialog.exec() != QDialog.Accepted or dialog.chosen_id is None:
            return

        loaded = self.store.load_batch(dialog.chosen_id, self.config.year)
        if loaded is None:
            return
        self.batch = loaded
        self.model.set_guests(self.batch.guests)
        if loaded.account_label:
            index = self.account_box.findText(loaded.account_label)
            if index >= 0:
                self.account_box.setCurrentIndex(index)
        self._log(f"Učitana tura #{loaded.db_id}: {loaded.summary()}")
        self._update_status()

    # ------------------------------------------------------------------- tura

    def _start(self) -> None:
        if self._is_running():
            return
        if not self.accounts:
            QMessageBox.warning(self, "Nema naloga", "Podesi naloge u .env fajlu.")
            return

        pending = self.batch.pending()
        if not pending:
            invalid = [g for g in self.model.guests if g.selected and not g.is_ready]
            if invalid:
                QMessageBox.warning(
                    self,
                    "Nema koga da prijavim",
                    f"{len(invalid)} označenih gostiju ima neispravne podatke.\n"
                    "Popravi crvene redove pa probaj ponovo.",
                )
            else:
                QMessageBox.information(self, "Nema koga da prijavim",
                                        "Označi bar jednog gosta koji još nije prijavljen.")
            return

        account = self.accounts[self.account_box.currentIndex()]
        locked = S.locked()
        if locked and QMessageBox.question(
            self,
            "Deo portala je zaključan",
            f"{len(locked)} selektora još nije podešeno "
            f"({', '.join(l.description for l in locked)}).\n\n"
            "Tura će verovatno pasti na tom koraku. Svejedno pokrenuti?",
            QMessageBox.Yes | QMessageBox.No,
            QMessageBox.No,
        ) != QMessageBox.Yes:
            return

        self.batch.account_label = account.label
        self.store.save_batch(self.batch)

        self._log(f"— Tura #{self.batch.db_id} · nalog {account.label} · {len(pending)} gostiju —")
        self._set_running(True)
        self.progress.setRange(0, len(pending))
        self.progress.setValue(0)
        self.progress.setVisible(True)

        self.worker = RunWorker(
            self.config, account, self.batch, store=self.store,
            options=RunOptions(download_vouchers=True),
        )
        self.worker.message.connect(self._log)
        self.worker.guest_updated.connect(self._on_guest_updated)
        self.worker.progress.connect(self._on_progress)
        self.worker.done.connect(self._on_done)
        self.worker.start()

    def _stop(self) -> None:
        if self.worker is not None:
            self.worker.stop()
            self.stop_button.setEnabled(False)

    def _on_guest_updated(self, guest) -> None:
        row = self.model.index_of(guest)
        if row >= 0:
            self.model.refresh_row(row)

    def _on_progress(self, done: int, total: int) -> None:
        self.progress.setRange(0, total)
        self.progress.setValue(done)
        self._update_status()

    def _on_done(self, result) -> None:
        self._set_running(False)
        self.progress.setVisible(False)
        self.model.refresh_all()
        self._update_status()

        if result.fatal:
            QMessageBox.critical(self, "Tura prekinuta", result.fatal)
            return

        if result.errors:
            details = "\n".join(
                f"red {guest.row}: {guest.full_name} — {error.text}"
                for guest, error in result.errors
            )
            box = QMessageBox(QMessageBox.Warning, "Tura završena", result.summary(), parent=self)
            box.setInformativeText("Crveni redovi su ostali neprijavljeni.")
            box.setDetailedText(details)
            box.exec()
        else:
            QMessageBox.information(self, "Tura završena", result.summary())

    def _is_running(self) -> bool:
        if self.worker is not None and self.worker.isRunning():
            QMessageBox.information(self, "Tura je u toku", "Sačekaj da se tura završi ili je zaustavi.")
            return True
        return False

    def _set_running(self, running: bool) -> None:
        self.start_button.setEnabled(not running)
        self.stop_button.setEnabled(running)
        self.paste_button.setEnabled(not running)
        self.account_box.setEnabled(not running and bool(self.accounts))
        self.table.setEditTriggers(
            QAbstractItemView.NoEditTriggers if running
            else QAbstractItemView.DoubleClicked | QAbstractItemView.EditKeyPressed
        )

    # ----------------------------------------------------------------- alatke

    def _open_pdf_dir(self) -> None:
        open_in_system(self.config.pdf_dir)

    def _open_shot_dir(self) -> None:
        open_in_system(self.config.screenshot_dir)

    def _check_selectors(self) -> None:
        if self._is_running() or not self.accounts:
            if not self.accounts:
                QMessageBox.warning(self, "Nema naloga", "Podesi naloge u .env fajlu.")
            return
        account = self.accounts[self.account_box.currentIndex()]
        self._log(f"Provera selektora preko naloga {account.label}…")
        self.check_worker = SelectorCheckWorker(self.config, account)
        self.check_worker.message.connect(self._log)
        self.check_worker.done.connect(self._on_selectors_checked)
        self.check_worker.start()

    def _on_selectors_checked(self, checks) -> None:
        if not checks:
            return
        found = [c for c in checks if c.found]
        missing = [c for c in checks if not c.found]
        lines = [f"✓ {c.locator.description} — {c.matched_by}" for c in found]
        lines += [f"✗ {c.locator.description} ({c.locator.name})" for c in missing]

        box = QMessageBox(
            QMessageBox.Information,
            "Provera selektora",
            f"Radi: {len(found)} · Ne radi: {len(missing)}",
            parent=self,
        )
        box.setDetailedText("\n".join(lines))
        box.exec()
        for line in lines:
            self._log(line, "INFO" if line.startswith("✓") else "WARN")

    def _show_selector_states(self) -> None:
        lines = [
            f"{locator.state.value:14} {locator.name:20} {locator.description}"
            for locator in S.REGISTRY
        ]
        box = QMessageBox(QMessageBox.Information, "Stanje selektora", S.summary(), parent=self)
        box.setDetailedText("\n".join(lines))
        box.exec()

    def _show_help(self) -> None:
        QMessageBox.information(
            self,
            "Kako se koristi",
            "1. U glavnom Excelu označi grupu gostiju (prezime, ime, JMBG, datum) i Ctrl+C.\n"
            "2. Ovde Ctrl+V — redovi se pojave u tabeli. Crveni imaju neispravan JMBG ili datum;\n"
            "   ispravi ih dvoklikom na ćeliju.\n"
            "3. Izaberi nalog i klikni Pokreni turu.\n"
            "4. Zeleno = prijavljen, crveno = pao. Prelaskom miša preko reda vidi se razlog.\n"
            "5. Kad se završi, Ctrl+C i zalepi nazad u glavni Excel — dobijaš i STATUS kolonu.\n\n"
            f"Vaučeri se snimaju u: {self.config.pdf_dir}",
        )

    # ------------------------------------------------------------------ ostalo

    def _log(self, text: str, level: str = "INFO") -> None:
        color = _LEVEL_COLORS.get(level, "")
        stamp = datetime.now().strftime("%H:%M:%S")
        safe = (
            text.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
            .replace("\n", "<br>")
        )
        style = f' style="color:{color}"' if color else ""
        self.log_view.appendHtml(f'<span style="color:gray">{stamp}</span> <span{style}>{safe}</span>')

    def _update_status(self) -> None:
        counts = self.batch.counts()
        total = len(self.model.guests)
        selected = sum(1 for guest in self.model.guests if guest.selected)
        self.status_label.setText(
            f"Gostiju: {total} (označeno {selected}) · "
            f"prijavljeno {counts[Status.OK]} · grešaka {counts[Status.ERROR]} · "
            f"čeka {counts[Status.PENDING]}   |   vaučeri: {self.config.pdf_dir}"
        )

    def closeEvent(self, event) -> None:
        if self.worker is not None and self.worker.isRunning():
            if QMessageBox.question(
                self, "Tura je u toku", "Prekinuti turu i zatvoriti program?"
            ) != QMessageBox.Yes:
                event.ignore()
                return
            self.worker.stop()
            self.worker.wait(15000)
        self.store.close()
        event.accept()


class _BatchPicker(QDialog):
    """Izbor ranije ture."""

    def __init__(self, rows, parent=None) -> None:
        super().__init__(parent)
        self.setWindowTitle("Otvori raniju turu")
        self.resize(520, 340)
        self.chosen_id: int | None = None

        self.list = QListWidget()
        for row in rows:
            label = (
                f"#{row['id']}  {row['created_at']}  ·  nalog: {row['account_label'] or '—'}  ·  "
                f"{row['ukupno']} gostiju, {row['uspesno'] or 0} prijavljeno, {row['gresaka'] or 0} grešaka"
            )
            item = QListWidgetItem(label)
            item.setData(Qt.UserRole, int(row["id"]))
            self.list.addItem(item)
        self.list.setCurrentRow(0)
        self.list.itemDoubleClicked.connect(lambda _: self.accept())

        buttons = QDialogButtonBox(QDialogButtonBox.Open | QDialogButtonBox.Cancel)
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)

        layout = QVBoxLayout(self)
        layout.addWidget(self.list)
        layout.addWidget(buttons)

    def accept(self) -> None:
        item = self.list.currentItem()
        if item is not None:
            self.chosen_id = int(item.data(Qt.UserRole))
        super().accept()

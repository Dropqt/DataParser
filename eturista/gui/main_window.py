"""Glavni prozor aplikacije."""

from __future__ import annotations

from datetime import datetime
from pathlib import Path

from PySide6.QtCore import Qt, QTimer
from PySide6.QtGui import QAction, QKeySequence
from PySide6.QtWidgets import (
    QAbstractItemView,
    QApplication,
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QFileDialog,
    QHBoxLayout,
    QLabel,
    QLineEdit,
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
from ..config import Config, env_leak_warning
from ..models import Batch, Status
from ..portal import selectors as S
from ..potpis import Raspored, potpisi_folder
from ..runner import RunOptions
from ..store import Store
from .guest_table import GuestTable, open_in_system
from .settings_dialog import SettingsDialog
from .table_model import GuestTableModel
from .worker import RunWorker, SelectorCheckWorker, UpdateCheckWorker

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
        self.update_worker: UpdateCheckWorker | None = None

        self.setWindowTitle("eTurista - prijava gostiju")
        # Široko taman da sve kolone stanu bez vodoravnog klizača.
        self.resize(1360, 780)

        self._build_ui()
        self._build_menu()
        self._load_accounts()
        # Odloženo za posle prvog crtanja: provere umeju da otvore dijalog, a on ne sme
        # da iskoči pre nego što se glavni prozor uopšte pojavi.
        QTimer.singleShot(0, self._startup_checks)
        self._update_status()
        self._check_for_update(quiet=True)

    # ------------------------------------------------------------------ UI

    def _build_ui(self) -> None:
        self.account_box = QComboBox()
        self.account_box.setMinimumWidth(170)

        # Vaučeri se razvrstavaju u foldere po adresi na koju se šalju. Većina gostiju
        # ide na istu, pa se ona kuca ovde jednom, a u koloni E-mail samo izuzeci.
        self.email_box = QLineEdit(self.config.default_email)
        self.email_box.setPlaceholderText("vauceri@primer.rs")
        self.email_box.setToolTip(
            "Vaučeri se snimaju u folder sa ovim imenom.\n"
            "Gost koji u koloni E-mail ima svoju adresu ide u svoj folder.\n"
            "Prazno = svi vaučeri idu zajedno, bez foldera."
        )
        self.email_box.setMinimumWidth(190)
        self.email_box.textChanged.connect(lambda *_: self._update_status())

        self.add_button = QPushButton("＋  Dodaj red")
        self.add_button.setToolTip("Ins - prazan red za ručni unos, bez Excela")
        self.add_button.clicked.connect(self._add_row)

        self.paste_button = QPushButton("Nalepi iz Excela")
        self.paste_button.setToolTip("Ctrl+V - kopiraj grupu gostiju iz glavnog Excela")
        self.paste_button.clicked.connect(self._paste)

        self.copy_button = QPushButton("Kopiraj rezultat")
        self.copy_button.setToolTip("Ctrl+C - vrati redove u glavni Excel, sa STATUS kolonom")
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
        toolbar.addSpacing(12)
        toolbar.addWidget(QLabel("Vaučeri na:"))
        toolbar.addWidget(self.email_box)
        toolbar.addSpacing(16)
        toolbar.addWidget(self.add_button)
        toolbar.addWidget(self.paste_button)
        toolbar.addWidget(self.copy_button)
        toolbar.addStretch(1)
        toolbar.addWidget(self.start_button)
        toolbar.addWidget(self.stop_button)

        self.table = GuestTable(self.model)
        self.table.pasted.connect(self._on_pasted)
        self.table.copied.connect(lambda n: self._log(f"Kopirano {n} redova u clipboard."))
        self.table.guests_removed.connect(lambda n: self._update_status())
        # Red se može dodati i tasterom u samoj tabeli, mimo dugmeta - i tad statusna
        # traka mora da se osveži.
        self.table.row_added.connect(lambda n: self._update_status())
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
        edit.addAction(self._action("Dodaj prazan red", self._add_row, QKeySequence(Qt.Key_Insert)))
        edit.addAction(self._action("Nalepi iz Excela", self._paste, QKeySequence.Paste))
        edit.addAction(self._action("Kopiraj rezultat", self._copy, QKeySequence.Copy))
        edit.addSeparator()
        edit.addAction(self._action("Označi sve", lambda: self._select_all(True)))
        edit.addAction(self._action("Skini oznaku sa svih", lambda: self._select_all(False)))
        edit.addAction(self._action("Vrati greške u red", self._retry_failed))

        tools = self.menuBar().addMenu("&Alatke")
        # Prečica se piše doslovno: QKeySequence.Preferences nije mapirana na Windows-u.
        tools.addAction(self._action("Podešavanja…", self._settings, QKeySequence("Ctrl+,")))
        tools.addSeparator()
        tools.addAction(self._action("Otvori folder sa vaučerima", self._open_pdf_dir))
        tools.addAction(self._action("Otvori folder sa screenshot-ovima", self._open_shot_dir))
        tools.addSeparator()
        tools.addAction(self._action("Potpiši vaučere u folderu…", self._sign_folder))
        tools.addSeparator()
        tools.addAction(self._action("Proveri selektore na portalu…", self._check_selectors))
        tools.addAction(self._action("Stanje selektora", self._show_selector_states))

        help_menu = self.menuBar().addMenu("&Pomoć")
        help_menu.addAction(self._action("Kako se koristi", self._show_help))
        # Lambda namerno: QAction.triggered šalje `checked` kao prvi argument, što bi
        # se poklopilo sa `quiet` i pravilo zabunu.
        help_menu.addAction(
            self._action("Proveri ima li nove verzije", lambda: self._check_for_update(quiet=False))
        )

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

    def _settings(self) -> None:
        """Podešavanja iz .env - unos u polja umesto ručnog uređivanja fajla."""
        if self._is_running():
            QMessageBox.information(
                self, "Tura je u toku", "Sačekaj da se tura završi pa onda menjaj podešavanja."
            )
            return
        dialog = SettingsDialog(self.config, self)
        if dialog.exec() != QDialog.Accepted:
            return
        self._apply_settings()

    def _apply_settings(self) -> None:
        """Primeni novi .env bez restarta.

        ``env_file.reload`` gazi ono što je već u okruženju - bez toga bi program i
        dalje radio sa starom lozinkom, a da se ništa ne požali.
        """
        from ..env_file import reload as reload_env

        old_db = self.config.db_path
        reload_env()
        self.config = Config.load()  # Config je frozen, pa se pravi nov objekat
        self.config.ensure_dirs()
        self.model.year = self.config.year

        chosen = self.account_box.currentText()
        self._load_accounts()
        if (index := self.account_box.findText(chosen)) >= 0:
            self.account_box.setCurrentIndex(index)

        if not self.email_box.text().strip():
            self.email_box.setText(self.config.default_email)

        self._update_status()
        self._log("Podešavanja su sačuvana.")

        if self.config.db_path != old_db:
            # Store je vezan za bazu pri otvaranju, a u njoj ume da stoji započeta
            # tura - tiha zamena bi je izgubila.
            QMessageBox.information(
                self, "Podešavanja",
                "Nova baza počinje da važi od sledećeg pokretanja programa.",
            )

    def _startup_checks(self) -> None:
        warning = env_leak_warning()
        if warning:
            self._log(warning, "ERROR")
            QMessageBox.warning(self, "Lozinke u gitu", warning)

        if not self.accounts:
            self._log("Nema podešenih naloga", "WARN")
            answer = QMessageBox.question(
                self, "Nalozi nisu podešeni",
                "Nema podešenih naloga, pa tura ne može da se pokrene.\n\n"
                "Otvoriti podešavanja i uneti ih sada?",
            )
            if answer == QMessageBox.Yes:
                self._settings()

        locked = S.locked()
        if locked:
            names = ", ".join(locator.description for locator in locked)
            self._log(
                f"Zaključano do otvaranja registracije ({len(locked)}): {names}", "WARN"
            )

    # ------------------------------------------------------------------ akcije

    def _add_row(self) -> None:
        """Prazan red za ručni unos. Fokus ide u tabelu da se odmah kuca."""
        self.table.setFocus()
        self.table.add_row()
        self._update_status()

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
                or "Clipboard je prazan - kopiraj redove iz Excela pa probaj ponovo.",
            )
            return

        bad = sum(1 for guest in result.guests if guest.status is Status.ERROR)
        self._log(
            f"Zalepljeno {len(result.guests)} gostiju ({result.mapping.describe()})"
            + (f" - {bad} sa neispravnim podacima" if bad else "")
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
            QMessageBox.warning(self, "Nema naloga", "Podesi naloge u Alatke -> Podešavanja.")
            return

        pending = self.batch.pending()
        if not pending:
            # Prazan red je nepopunjen, ne pogrešan - o njemu se ne javlja kao o grešci.
            invalid = [
                g for g in self.model.guests if g.selected and not g.is_ready and not g.is_blank
            ]
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

        if account.signature is None and QMessageBox.question(
            self,
            "Nalog nema potpis",
            f"Nalog {account.label} nema podešen potpis, pa će vaučeri ostati "
            "nepotpisani.\n\nPodesi potpis u Alatke -> Podešavanja, ili ih posle potpiši "
            "kroz Alatke → Potpiši vaučere u folderu.\n\nSvejedno pokrenuti?",
            QMessageBox.Yes | QMessageBox.No,
            QMessageBox.No,
        ) != QMessageBox.Yes:
            return

        default_email = self.email_box.text().strip().lower()

        self.batch.account_label = account.label
        self.store.save_batch(self.batch)

        self._log(f"- Tura #{self.batch.db_id} · nalog {account.label} · {len(pending)} gostiju -")
        self._log(self._describe_voucher_dirs(pending, default_email))
        self._set_running(True)
        self.progress.setRange(0, len(pending))
        self.progress.setValue(0)
        self.progress.setVisible(True)

        self.worker = RunWorker(
            self.config, account, self.batch, store=self.store,
            options=RunOptions(download_vouchers=True, default_email=default_email),
        )
        self.worker.message.connect(self._log)
        self.worker.guest_updated.connect(self._on_guest_updated)
        self.worker.progress.connect(self._on_progress)
        self.worker.done.connect(self._on_done)
        self.worker.start()

    def _describe_voucher_dirs(self, guests, default_email: str) -> str:
        """Kratak pregled u koje foldere idu vaučeri, pre nego što tura krene.

        Bolje da se pogrešna adresa vidi u logu na početku nego da se traži gde je
        30 PDF-ova završilo.
        """
        from collections import Counter

        brojac = Counter(
            guest.voucher_dir(self.config.pdf_dir, default_email).name for guest in guests
        )
        koren = self.config.pdf_dir.name
        delovi = [
            f"{folder}: {broj}" if folder != koren else f"bez foldera: {broj}"
            for folder, broj in brojac.most_common()
        ]
        return "Vaučeri → " + " · ".join(delovi)

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
                f"red {guest.row}: {guest.full_name} - {error.text}"
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

    def _sign_folder(self) -> None:
        """Naknadno potpisivanje vaučera preuzetih pre nego što je ovo postojalo.

        Potpis se uzima iz naloga izabranog u traci. Već potpisani se preskaču, pa alat
        sme da se pusti i dvaput preko istog foldera.
        """
        if self._is_running():
            return
        if not self.accounts:
            QMessageBox.warning(self, "Nema naloga", "Podesi naloge u Alatke -> Podešavanja.")
            return

        account = self.accounts[self.account_box.currentIndex()]
        if account.signature is None:
            QMessageBox.warning(
                self,
                "Nalog nema potpis",
                f"Nalog {account.label} nema podešen potpis.\n\n"
                "Podesi potpis u Alatke -> Podešavanja.",
            )
            return

        folder = QFileDialog.getExistingDirectory(
            self, "Folder sa vaučerima", str(self.config.pdf_dir)
        )
        if not folder:
            return

        self._log(f"Potpisivanje vaučera u {folder} · nalog {account.label}…")
        QApplication.setOverrideCursor(Qt.WaitCursor)
        try:
            potpisano, preskoceno, greske = potpisi_folder(
                Path(folder), account.signature, Raspored.iz_env()
            )
        finally:
            QApplication.restoreOverrideCursor()

        self._log(
            f"Potpisano {potpisano} · već potpisanih {preskoceno} · grešaka {len(greske)}",
            "WARN" if greske else "INFO",
        )
        for pdf, razlog in greske:
            self._log(f"  {pdf.name}: {razlog}", "WARN")

        box = QMessageBox(
            QMessageBox.Warning if greske else QMessageBox.Information,
            "Potpisivanje vaučera",
            f"Potpisano: {potpisano}\nVeć potpisanih: {preskoceno}\nGrešaka: {len(greske)}",
            parent=self,
        )
        if greske:
            box.setDetailedText("\n".join(f"{pdf.name}: {razlog}" for pdf, razlog in greske))
        box.exec()

    def _check_selectors(self) -> None:
        if self._is_running() or not self.accounts:
            if not self.accounts:
                QMessageBox.warning(self, "Nema naloga", "Podesi naloge u Alatke -> Podešavanja.")
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
        lines = [f"✓ {c.locator.description} - {c.matched_by}" for c in found]
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

    def _check_for_update(self, quiet: bool = False) -> None:
        """Pitaj GitHub ima li novijih izmena na main grani.

        ``quiet`` se koristi pri pokretanju: ćuti ako je sve u redu ili ako nema mreže,
        i javi se samo kad stvarno ima nove verzije.
        """
        from ..update import is_enabled

        if quiet and not is_enabled():
            return
        if self.update_worker is not None and self.update_worker.isRunning():
            return

        self._quiet_update_check = quiet
        self.update_worker = UpdateCheckWorker(self)
        self.update_worker.done.connect(self._on_update_checked)
        self.update_worker.start()

    def _on_update_checked(self, info) -> None:
        from ..update import update_hint

        quiet = getattr(self, "_quiet_update_check", True)

        if info is None:
            self._log("Provera nove verzije nije uspela (nema mreže ili GitHub ne odgovara).", "WARN")
            if not quiet:
                QMessageBox.information(
                    self, "Provera verzije",
                    "Ne mogu da proverim - nema veze sa GitHub-om.",
                )
            return

        if not info.available:
            self._log("Program je ažuran.")
            if not quiet:
                QMessageBox.information(self, "Provera verzije", "Program je ažuran.")
            return

        self._log(info.describe().replace("\n", " · "), "WARN")
        self._log(update_hint(), "WARN")

        box = QMessageBox(QMessageBox.Information, "Nova verzija", info.describe(), parent=self)
        box.setInformativeText(update_hint())
        box.setDetailedText(f"Lokalno:  {info.local}\nNa GitHub-u: {info.remote}\n\n{info.compare_url}")
        box.exec()

    def _show_help(self) -> None:
        QMessageBox.information(
            self,
            "Kako se koristi",
            "1. U glavnom Excelu označi grupu gostiju (prezime, ime, JMBG, datum) i Ctrl+C.\n"
            "2. Ovde Ctrl+V - redovi se pojave u tabeli. Crveni imaju neispravan JMBG ili datum;\n"
            "   ispravi ih dvoklikom na ćeliju.\n"
            "3. Izaberi nalog i klikni Pokreni turu.\n"
            "4. Zeleno = prijavljen, crveno = pao. Prelaskom miša preko reda vidi se razlog.\n"
            "5. Kad se završi, Ctrl+C i zalepi nazad u glavni Excel - dobijaš i STATUS kolonu.\n\n"
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
        if self.update_worker is not None and self.update_worker.isRunning():
            self.update_worker.wait(2000)
        self._remember_email()
        self.store.close()
        event.accept()

    def _remember_email(self) -> None:
        """Zapamti adresu iz trake u .env - README to obećava od početka.

        Fajl se ovde ne pravi ako ga nema; samo se ažurira postojeći. Zatvaranje
        programa ne sme da padne zbog toga što .env nije upisiv.
        """
        from ..env_file import env_path, write_env

        address = self.email_box.text().strip().lower()
        if address == self.config.default_email or not env_path().is_file():
            return
        try:
            write_env({"ETURISTA_EMAIL": address})
        except OSError:
            pass


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
                f"#{row['id']}  {row['created_at']}  ·  nalog: {row['account_label'] or '-'}  ·  "
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

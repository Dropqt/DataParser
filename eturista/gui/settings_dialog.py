"""Podešavanja iz .env, bez otvaranja fajla u Notepad-u.

Do sada se `.env` uređivao rukom, a svaka poruka o grešci se završavala sa "pa
restartuj program". Ovde se sve unosi u polja, snima se uz očuvanje komentara
(:mod:`eturista.env_file`), i primenjuje odmah.
"""

from __future__ import annotations

from dataclasses import replace
from pathlib import Path

from PySide6.QtWidgets import (
    QCheckBox,
    QDialog,
    QDialogButtonBox,
    QFileDialog,
    QFormLayout,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QScrollArea,
    QTabWidget,
    QVBoxLayout,
    QWidget,
)

from .. import env_file
from ..accounts import MAX_ACCOUNTS, Account
from ..config import Config, app_dir
from .worker import LoginCheckWorker

#: Vrednosti koje ``.env`` čita kao "da". Ista lista kao u ``Config.load``.
_TRUE = {"1", "true", "da", "yes"}


class _PathRow(QWidget):
    """Polje sa putanjom i dugmetom za izbor - isti obrazac za fajl i za folder."""

    def __init__(self, placeholder: str, folder: bool, filter: str = "", parent=None) -> None:
        super().__init__(parent)
        self.folder = folder
        self.filter = filter

        self.edit = QLineEdit()
        self.edit.setPlaceholderText(placeholder)
        button = QPushButton("Izaberi…")
        button.clicked.connect(self._choose)

        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(self.edit)
        layout.addWidget(button)

    def _choose(self) -> None:
        start = self.edit.text().strip() or str(app_dir())
        if self.folder:
            chosen = QFileDialog.getExistingDirectory(self, "Izaberi folder", start)
        else:
            chosen, _ = QFileDialog.getOpenFileName(self, "Izaberi fajl", start, self.filter)
        if not chosen:
            return
        # Putanja unutar foldera aplikacije se pamti relativno, pa .env ostane
        # prenosiv između računara.
        path = Path(chosen)
        try:
            path = path.relative_to(app_dir())
        except ValueError:
            pass
        self.edit.setText(str(path))

    def text(self) -> str:
        return self.edit.text().strip()

    def setText(self, value: str) -> None:
        self.edit.setText(value)


class _AccountBox(QGroupBox):
    """Jedan nalog: naziv, korisnik, lozinka, potpis."""

    def __init__(self, index: int, parent=None) -> None:
        super().__init__(f"Nalog {index}", parent)
        self.index = index

        self.naziv = QLineEdit()
        self.naziv.setPlaceholderText(f"nalog {index}")
        self.korisnik = QLineEdit()

        self.lozinka = QLineEdit()
        self.lozinka.setEchoMode(QLineEdit.Password)
        self.prikazi = QPushButton("Prikaži")
        self.prikazi.setCheckable(True)
        self.prikazi.setToolTip("Prikaži lozinku dok se kuca")
        self.prikazi.toggled.connect(self._toggle_password)

        lozinka_red = QHBoxLayout()
        lozinka_red.setContentsMargins(0, 0, 0, 0)
        lozinka_red.addWidget(self.lozinka)
        lozinka_red.addWidget(self.prikazi)
        lozinka_widget = QWidget()
        lozinka_widget.setLayout(lozinka_red)

        self.potpis = _PathRow(
            "prazno = vaučeri ovog naloga ostaju nepotpisani",
            folder=False,
            filter="Slike (*.png *.jpg *.jpeg)",
        )

        layout = QFormLayout(self)
        layout.addRow("Naziv:", self.naziv)
        layout.addRow("Korisnik:", self.korisnik)
        layout.addRow("Lozinka:", lozinka_widget)
        layout.addRow("Potpis:", self.potpis)

    def _toggle_password(self, shown: bool) -> None:
        self.lozinka.setEchoMode(QLineEdit.Normal if shown else QLineEdit.Password)
        self.prikazi.setText("Sakrij" if shown else "Prikaži")

    def load(self, values: dict[str, str]) -> None:
        naziv, user, password, signature = env_file.account_keys(self.index)
        self.naziv.setText(values.get(naziv, ""))
        self.korisnik.setText(values.get(user, ""))
        self.lozinka.setText(values.get(password, ""))
        self.potpis.setText(values.get(signature, ""))

    def values(self) -> dict[str, str]:
        naziv, user, password, signature = env_file.account_keys(self.index)
        return {
            naziv: self.naziv.text().strip(),
            user: self.korisnik.text().strip(),
            password: self.lozinka.text(),
            signature: self.potpis.text(),
        }

    def as_account(self) -> Account | None:
        """Nalog sklopljen iz polja - za proveru prijave, pre nego što se snimi."""
        user, password = self.korisnik.text().strip(), self.lozinka.text()
        if not user or not password:
            return None
        label = self.naziv.text().strip() or f"nalog {self.index}"
        return Account(label=label, username=user, password=password)


class SettingsDialog(QDialog):
    """Sva podešavanja iz .env na jednom mestu."""

    def __init__(self, config: Config, parent=None) -> None:
        super().__init__(parent)
        self.config = config
        self.setWindowTitle("Podešavanja")
        self.resize(640, 520)
        self.login_worker: LoginCheckWorker | None = None

        self.tabs = QTabWidget()
        self.tabs.addTab(self._accounts_tab(), "Nalozi")
        self.tabs.addTab(self._folders_tab(), "Folderi")
        self.tabs.addTab(self._vouchers_tab(), "Vaučeri")
        self.tabs.addTab(self._other_tab(), "Ostalo")

        buttons = QDialogButtonBox(QDialogButtonBox.Save | QDialogButtonBox.Cancel)
        buttons.button(QDialogButtonBox.Save).setText("Sačuvaj")
        buttons.button(QDialogButtonBox.Cancel).setText("Odustani")
        self.check_button = buttons.addButton("Proveri prijavu", QDialogButtonBox.ActionRole)
        self.check_button.setToolTip("Prijavi se na portal izabranim nalogom, bez snimanja")
        self.check_button.clicked.connect(self._check_login)
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)

        layout = QVBoxLayout(self)
        layout.addWidget(self.tabs)
        layout.addWidget(buttons)

        self._load()

    # ------------------------------------------------------------------ tabovi

    def _accounts_tab(self) -> QWidget:
        self.account_boxes = [_AccountBox(i) for i in range(1, MAX_ACCOUNTS + 1)]

        inner = QWidget()
        inner_layout = QVBoxLayout(inner)
        hint = QLabel(
            "Nalog bez korisničkog imena ili lozinke se preskače, pa sva tri slota "
            "mogu da stoje pripremljena."
        )
        hint.setWordWrap(True)
        inner_layout.addWidget(hint)
        for box in self.account_boxes:
            inner_layout.addWidget(box)
        inner_layout.addStretch(1)

        area = QScrollArea()
        area.setWidgetResizable(True)
        area.setWidget(inner)
        return area

    def _folders_tab(self) -> QWidget:
        self.pdf_dir = _PathRow(str(app_dir() / "vauceri"), folder=True)
        self.shot_dir = _PathRow(str(app_dir() / "screenshots"), folder=True)
        self.db_path = _PathRow(str(app_dir() / "eturista.db"), folder=False, filter="SQLite baza (*.db)")

        tab = QWidget()
        layout = QFormLayout(tab)
        layout.addRow("Vaučeri:", self.pdf_dir)
        layout.addRow("Screenshot-ovi:", self.shot_dir)
        layout.addRow("Baza:", self.db_path)
        note = QLabel("Prazno polje znači podrazumevanu putanju, ispisanu sivim.")
        note.setWordWrap(True)
        layout.addRow(note)
        return tab

    def _vouchers_tab(self) -> QWidget:
        self.email = QLineEdit()
        self.email.setPlaceholderText("vauceri@primer.rs")
        self.email.setToolTip(
            "Vaučeri se snimaju u folder sa ovim imenom.\n"
            "Prazno = svi vaučeri idu zajedno, bez foldera."
        )
        self.year = QLineEdit()
        self.year.setPlaceholderText(str(self.config.year))

        self.potpis_visina = QLineEdit()
        self.potpis_visina.setPlaceholderText("12.0")
        self.potpis_x = QLineEdit()
        self.potpis_x.setPlaceholderText("26.4")
        self.potpis_y = QLineEdit()
        self.potpis_y.setPlaceholderText("14.5")
        self.potpis_sirina = QLineEdit()
        self.potpis_sirina.setPlaceholderText("50.0")

        tab = QWidget()
        layout = QFormLayout(tab)
        layout.addRow("Vaučeri na:", self.email)
        layout.addRow("Godina u nazivu PDF-a:", self.year)
        layout.addRow(QLabel("<b>Položaj potpisa u vaučeru</b> (mm, od natpisa POTPIS UGOSTITELJA)"))
        layout.addRow("Visina:", self.potpis_visina)
        layout.addRow("Pomak levo-desno:", self.potpis_x)
        layout.addRow("Pomak naniže:", self.potpis_y)
        layout.addRow("Najveća širina:", self.potpis_sirina)
        note = QLabel(
            "Podrazumevane vrednosti su izmerene na pravom vaučeru. Pre menjanja pogledaj "
            "gde bi potpis pao:  run.py --kalibracija PDF"
        )
        note.setWordWrap(True)
        layout.addRow(note)
        return tab

    def _other_tab(self) -> QWidget:
        self.url = QLineEdit()
        self.url.setPlaceholderText("https://www.portal.eturista.gov.rs")
        self.headless = QCheckBox("Browser radi bez prozora")
        self.headless.setToolTip("Za normalan rad ostavi isključeno - tura se tada vidi")
        self.update_check = QCheckBox("Pri pokretanju proveri ima li nove verzije")

        tab = QWidget()
        layout = QFormLayout(tab)
        layout.addRow("Adresa portala:", self.url)
        layout.addRow(self.headless)
        layout.addRow(self.update_check)
        return tab

    # ------------------------------------------------------------- vrednosti

    def _load(self) -> None:
        """Popuni polja: prvo primer (podrazumevano), pa preko njega pravi .env."""
        values = env_file.read_env(env_file.example_path())
        values.update(env_file.read_env())

        for box in self.account_boxes:
            box.load(values)

        self.pdf_dir.setText(values.get("ETURISTA_PDF_DIR", ""))
        self.shot_dir.setText(values.get("ETURISTA_SCREENSHOT_DIR", ""))
        self.db_path.setText(values.get("ETURISTA_DB", ""))

        self.email.setText(values.get("ETURISTA_EMAIL", ""))
        self.year.setText(values.get("ETURISTA_GODINA", ""))
        self.potpis_visina.setText(values.get("ETURISTA_POTPIS_VISINA", ""))
        self.potpis_x.setText(values.get("ETURISTA_POTPIS_POMAK_X", ""))
        self.potpis_y.setText(values.get("ETURISTA_POTPIS_POMAK_Y", ""))
        self.potpis_sirina.setText(values.get("ETURISTA_POTPIS_MAX_SIRINA", ""))

        self.url.setText(values.get("ETURISTA_URL", ""))
        self.headless.setChecked(values.get("ETURISTA_HEADLESS", "").strip().lower() in _TRUE)
        # Provera ažuriranja je uključena dok se izričito ne isključi.
        self.update_check.setChecked(
            values.get("ETURISTA_PROVERA_AZURIRANJA", "").strip().lower()
            not in {"0", "false", "ne", "no"}
        )

    def values(self) -> dict[str, str]:
        """Svih 24 ključa - i prazni, da bi ``reload()`` obrisao ono što je izbačeno."""
        values: dict[str, str] = {}
        for box in self.account_boxes:
            values.update(box.values())

        values["ETURISTA_PDF_DIR"] = self.pdf_dir.text()
        values["ETURISTA_SCREENSHOT_DIR"] = self.shot_dir.text()
        values["ETURISTA_DB"] = self.db_path.text()
        values["ETURISTA_EMAIL"] = self.email.text().strip().lower()
        values["ETURISTA_GODINA"] = self.year.text().strip()
        values["ETURISTA_POTPIS_VISINA"] = self.potpis_visina.text().strip()
        values["ETURISTA_POTPIS_POMAK_X"] = self.potpis_x.text().strip()
        values["ETURISTA_POTPIS_POMAK_Y"] = self.potpis_y.text().strip()
        values["ETURISTA_POTPIS_MAX_SIRINA"] = self.potpis_sirina.text().strip()
        values["ETURISTA_URL"] = self.url.text().strip()
        values["ETURISTA_HEADLESS"] = "true" if self.headless.isChecked() else "false"
        values["ETURISTA_PROVERA_AZURIRANJA"] = "true" if self.update_check.isChecked() else "false"
        return values

    # ---------------------------------------------------------------- radnje

    def _current_account(self) -> _AccountBox | None:
        """Prvi nalog koji je popunjen - onaj koji se proverava."""
        return next((box for box in self.account_boxes if box.as_account() is not None), None)

    def _check_login(self) -> None:
        if self.login_worker is not None:
            return
        box = self._current_account()
        if box is None:
            QMessageBox.warning(
                self, "Nema šta da se proveri",
                "Popuni korisničko ime i lozinku bar jednog naloga.",
            )
            return

        url = self.url.text().strip() or self.config.portal_url
        # Provera ide na vrednosti iz polja, ne na ono što je snimljeno - da bi se
        # lozinka isprobala pre nego što se upiše u .env.
        config = replace(self.config, portal_url=url.rstrip("/"), headless=True)

        self.check_button.setEnabled(False)
        self.check_button.setText("Proveravam…")
        self.login_worker = LoginCheckWorker(config, box.as_account(), self)
        self.login_worker.done.connect(self._on_login_checked)
        self.login_worker.start()

    def _on_login_checked(self, ok: bool, message: str) -> None:
        self.check_button.setEnabled(True)
        self.check_button.setText("Proveri prijavu")
        self.login_worker = None
        if ok:
            QMessageBox.information(self, "Prijava radi", message)
        else:
            QMessageBox.warning(self, "Prijava nije uspela", message)

    def accept(self) -> None:
        problem = self._problem()
        if problem:
            QMessageBox.warning(self, "Podešavanja nisu potpuna", problem)
            return
        try:
            env_file.write_env(self.values())
        except OSError as exc:
            QMessageBox.critical(
                self, "Snimanje nije uspelo",
                f"Ne mogu da upišem {env_file.env_path()}\n\n{exc}",
            )
            return
        super().accept()

    def _problem(self) -> str | None:
        """Poruka o tome šta je nedovršeno, ili ``None`` kad je sve u redu."""
        for box in self.account_boxes:
            user, password = box.korisnik.text().strip(), box.lozinka.text()
            if bool(user) != bool(password):
                return (
                    f"Nalog {box.index} ima samo jedno od korisničkog imena i lozinke.\n"
                    "Popuni oba, ili isprazni oba - tada se nalog preskače."
                )

        year = self.year.text().strip()
        if year and not year.isdigit():
            return f"Godina mora biti broj, a piše {year!r}."

        for label, field in (
            ("Visina", self.potpis_visina), ("Pomak levo-desno", self.potpis_x),
            ("Pomak naniže", self.potpis_y), ("Najveća širina", self.potpis_sirina),
        ):
            text = field.text().strip().replace(",", ".")
            if not text:
                continue
            try:
                float(text)
            except ValueError:
                return f"Polje '{label}' mora biti broj u milimetrima, a piše {field.text()!r}."
        return None

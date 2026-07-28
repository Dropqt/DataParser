"""Testovi tabele i prozora - bez ekrana (offscreen) i bez browsera."""

from __future__ import annotations

import pytest
from PySide6.QtCore import Qt
from PySide6.QtGui import QGuiApplication
from PySide6.QtWidgets import QApplication

from eturista.config import Config
from eturista.gui.main_window import MainWindow
from eturista.gui.table_model import COL_SELECTED, COLUMNS, GuestTableModel
from eturista.models import EXPORT_HEADERS, Guest, Status

from .conftest import make_jmbg

YEAR = 2026
A = make_jmbg("010199071012")
B = make_jmbg("150398871001")
BAD = A[:12] + str((int(A[12]) + 1) % 10)

COL = {column.key: index for index, column in enumerate(COLUMNS)}


@pytest.fixture(scope="session")
def qt_app():
    app = QApplication.instance() or QApplication([])
    yield app


@pytest.fixture
def config(tmp_path):
    cfg = Config(
        portal_url="http://127.0.0.1:1",
        pdf_dir=tmp_path / "vauceri",
        screenshot_dir=tmp_path / "screenshots",
        db_path=tmp_path / "eturista.db",
        year=YEAR,
        headless=True,
    )
    cfg.ensure_dirs()
    return cfg


@pytest.fixture
def window(qt_app, config, monkeypatch):
    # Bez ovoga bi svaki GUI test išao na mrežu da pita GitHub za novu verziju.
    monkeypatch.setenv("ETURISTA_PROVERA_AZURIRANJA", "false")
    # Podešeni nalozi -> nema dijaloga pri pokretanju koji bi blokirao test.
    monkeypatch.setenv("ETURISTA_NALOG1_NAZIV", "mileta")
    monkeypatch.setenv("ETURISTA_NALOG1_USER", "test")
    monkeypatch.setenv("ETURISTA_NALOG1_PASS", "test123")
    monkeypatch.setenv("ETURISTA_NALOG2_NAZIV", "majka")
    monkeypatch.setenv("ETURISTA_NALOG2_USER", "test2")
    monkeypatch.setenv("ETURISTA_NALOG2_PASS", "test234")

    win = MainWindow(config)
    yield win
    win.store.close()
    win.deleteLater()


def set_clipboard(text: str) -> None:
    QGuiApplication.clipboard().setText(text)


# --- model ------------------------------------------------------------------

def make_model() -> GuestTableModel:
    guests = []
    for index, (surname, given, jmbg) in enumerate(
        [("Petrović", "Marko", A), ("Ilić", "Jovan", B)], start=1
    ):
        guest = Guest(row=index, surname_raw=surname, given_name_raw=given,
                      jmbg_raw=jmbg, arrival_raw="05.10")
        guest.validate(YEAR)
        guests.append(guest)
    return GuestTableModel(guests, year=YEAR)


def test_model_shows_normalized_arrival(qt_app):
    model = make_model()
    assert model.data(model.index(0, COL["arrival"]), Qt.DisplayRole) == "05.10.2026"


def test_model_shows_raw_arrival_while_editing(qt_app):
    model = make_model()
    assert model.data(model.index(0, COL["arrival"]), Qt.EditRole) == "05.10"


def test_model_fills_in_default_days(qt_app):
    """Prazna kolona Dana se u tabeli vidi kao 5, ali original ostaje prazan."""
    model = make_model()
    assert model.data(model.index(0, COL["days"]), Qt.DisplayRole) == "5"
    assert model.data(model.index(0, COL["days"]), Qt.EditRole) == ""


def test_model_shows_computed_stay(qt_app):
    model = make_model()
    assert model.data(model.index(0, COL["stay"]), Qt.DisplayRole) == "05.10.2026-10.10.2026"


def test_editing_days_recomputes_stay(qt_app):
    model = make_model()
    assert model.setData(model.index(0, COL["days"]), "7", Qt.EditRole)
    assert model.guests[0].stay.nights == 7
    assert model.data(model.index(0, COL["stay"]), Qt.DisplayRole) == "05.10.2026-12.10.2026"


def test_editing_days_to_nonsense_marks_row_red(qt_app):
    model = make_model()
    assert model.setData(model.index(0, COL["days"]), "0", Qt.EditRole)
    assert model.guests[0].status is Status.ERROR
    assert "bar 1" in model.guests[0].error.text


def test_row_color_follows_status(qt_app):
    model = make_model()
    pending = model.data(model.index(0, 1), Qt.BackgroundRole)
    assert pending is None

    model.guests[0].mark_ok()
    green = model.data(model.index(0, 1), Qt.BackgroundRole)
    assert green is not None and green.green() > green.red()

    model.guests[1].mark_error(model.guests[1].error or _error())
    red = model.data(model.index(1, 1), Qt.BackgroundRole)
    assert red is not None and red.red() > red.green()


def _error():
    from eturista.errors import ErrorKind, GuestError
    return GuestError(ErrorKind.TIMEOUT, "Isteklo vreme")


def test_editing_jmbg_revalidates_immediately(qt_app):
    model = make_model()
    index = model.index(0, COL["jmbg"])

    assert model.setData(index, BAD, Qt.EditRole)
    assert model.guests[0].status is Status.ERROR
    assert "kontrolna cifra" in model.guests[0].error.text

    # ispravka vraća red u normalu bez ponovnog lepljenja
    assert model.setData(index, A, Qt.EditRole)
    assert model.guests[0].status is Status.PENDING
    assert model.guests[0].error is None


def test_checkbox_toggles_selection(qt_app):
    model = make_model()
    index = model.index(0, COL_SELECTED)
    assert model.data(index, Qt.CheckStateRole) == Qt.Checked

    model.setData(index, Qt.Unchecked.value, Qt.CheckStateRole)
    assert model.guests[0].selected is False


def test_removing_rows_renumbers(qt_app):
    model = make_model()
    model.remove_rows([0])
    assert [g.row for g in model.guests] == [1]
    assert model.guests[0].surname == "Ilić"


def test_tooltip_reports_error_and_screenshot(qt_app):
    from eturista.errors import ErrorKind, GuestError

    model = make_model()
    model.guests[0].mark_error(
        GuestError(ErrorKind.JMBG_REJECTED_PORTAL, "Portal je odbio JMBG", screenshot="/tmp/a.png")
    )
    tip = model.data(model.index(0, 1), Qt.ToolTipRole)
    assert "Portal je odbio JMBG" in tip
    assert "/tmp/a.png" in tip


# --- prozor -----------------------------------------------------------------

def test_paste_from_excel_fills_table(window):
    set_clipboard(
        "Ime\tPrezime\tJMBG\tDolazak\n"
        f"Marko\tPetrović\t{A}\t05.10\n"
        f"Jovan\tIlić\t{B}\t06.10\n"
    )
    window._paste()

    assert len(window.model.guests) == 2
    assert window.batch.guests is window.model.guests   # tabela i tura dele istu listu
    assert window.model.guests[0].surname == "Petrović"


def test_paste_appends_instead_of_replacing(window):
    set_clipboard(f"Marko\tPetrović\t{A}\t05.10\n")
    window._paste()
    set_clipboard(f"Jovan\tIlić\t{B}\t06.10\n")
    window._paste()

    assert len(window.model.guests) == 2
    assert [g.row for g in window.model.guests] == [1, 2]


def test_manual_row_is_added_empty_and_not_red(window):
    """Ručno dodat red je prazan, ali nije greška - tek se popunjava."""
    window._add_row()

    guest = window.model.guests[0]
    assert len(window.model.guests) == 1
    assert guest.is_blank
    assert guest.status is Status.PENDING
    assert guest.error is None
    assert window.model.data(window.model.index(0, COL["status"])) == Status.PENDING.label


def test_manual_row_turns_red_only_once_something_is_typed(window):
    window._add_row()
    model = window.model
    model.setData(model.index(0, COL["given_name"]), "Marko", Qt.EditRole)

    guest = model.guests[0]
    assert not guest.is_blank
    # sad jeste greška: ime postoji, ali JMBG i datum ne
    assert guest.status is Status.ERROR
    assert not guest.is_ready


def test_manual_row_becomes_ready_when_filled_in(window):
    window._add_row()
    model = window.model
    for key, value in (("given_name", "Marko"), ("surname", "Petrović"),
                       ("jmbg", A), ("arrival", "05.10")):
        model.setData(model.index(0, COL[key]), value, Qt.EditRole)

    guest = model.guests[0]
    assert guest.is_ready
    assert guest.error is None
    assert guest.stay.nights == 5     # prazna kolona Dana = 5 noćenja


def test_manual_rows_are_numbered_after_pasted_ones(window):
    set_clipboard(f"Marko\tPetrović\t{A}\t05.10\n")
    window._paste()
    window._add_row()

    assert [g.row for g in window.model.guests] == [1, 2]
    assert window.model.guests[1].is_blank


def test_blank_row_does_not_block_start(window):
    """Prazan red ne sme da javi „neispravni podaci“ kad se pokrene tura."""
    set_clipboard(f"Marko\tPetrović\t{A}\t05.10\n")
    window._paste()
    window._add_row()

    invalid = [g for g in window.model.guests if g.selected and not g.is_ready and not g.is_blank]
    assert invalid == []
    assert len(window.batch.pending()) == 1


def test_bad_jmbg_is_red_right_after_paste(window):
    set_clipboard(f"Marko\tPetrović\t{BAD}\t05.10\n")
    window._paste()

    guest = window.model.guests[0]
    assert guest.status is Status.ERROR
    color = window.model.data(window.model.index(0, 1), Qt.BackgroundRole)
    assert color.red() > color.green()


def test_copy_produces_excel_row_with_status(window):
    set_clipboard(f"Marko\tPetrović\t{A}\t05.10\n")
    window._paste()
    window.model.guests[0].mark_ok("2026_PETROVIC_MARKO.pdf")

    window._copy()
    header, row = QGuiApplication.clipboard().text().split("\n")

    assert header.split("\t") == list(EXPORT_HEADERS)
    cells = dict(zip(EXPORT_HEADERS, row.split("\t")))
    assert cells["STATUS"] == "OK"
    assert cells["PDF"] == "2026_PETROVIC_MARKO.pdf"


def test_update_check_is_skipped_when_disabled(window):
    """Isključena provera ne sme da pokrene nit ni da dodirne mrežu."""
    assert window.update_worker is None


def test_update_check_starts_when_enabled(qt_app, config, monkeypatch):
    monkeypatch.setenv("ETURISTA_NALOG1_NAZIV", "mileta")
    monkeypatch.setenv("ETURISTA_NALOG1_USER", "test")
    monkeypatch.setenv("ETURISTA_NALOG1_PASS", "test123")
    monkeypatch.setenv("ETURISTA_PROVERA_AZURIRANJA", "true")

    started = []
    from eturista.gui import main_window as module
    monkeypatch.setattr(
        module, "UpdateCheckWorker",
        lambda parent=None: type("_Fake", (), {
            "done": type("_Sig", (), {"connect": lambda self, slot: None})(),
            "start": lambda self: started.append(True),
            "isRunning": lambda self: False,
        })(),
    )

    win = MainWindow(config)
    try:
        assert started == [True]
    finally:
        win.store.close()
        win.deleteLater()


def test_accounts_are_loaded_into_dropdown(window):
    assert [window.account_box.itemText(i) for i in range(window.account_box.count())] == [
        "mileta", "majka"
    ]


def test_status_bar_counts_update(window):
    set_clipboard(
        f"Marko\tPetrović\t{A}\t05.10\n"
        f"Jovan\tIlić\t{BAD}\t06.10\n"
    )
    window._paste()
    text = window.status_label.text()
    assert "Gostiju: 2" in text
    assert "grešaka 1" in text


def test_retry_failed_resets_only_technical_errors(window):
    from eturista.errors import ErrorKind, GuestError

    set_clipboard(
        f"Marko\tPetrović\t{A}\t05.10\n"
        f"Jovan\tIlić\t{BAD}\t06.10\n"
    )
    window._paste()
    window.model.guests[0].mark_error(GuestError(ErrorKind.TIMEOUT, "Isteklo vreme"))

    window._retry_failed()

    # tehnička greška se vraća u red, pogrešan JMBG ostaje crven dok se ne ispravi
    assert window.model.guests[0].status is Status.PENDING
    assert window.model.guests[1].status is Status.ERROR


def test_select_all_toggles_every_row(window):
    set_clipboard(f"Marko\tPetrović\t{A}\t05.10\nIlić\tJovan\t{B}\t06.10\n")
    window._paste()

    window._select_all(False)
    assert not any(g.selected for g in window.model.guests)
    assert window.batch.pending() == []

    window._select_all(True)
    assert len(window.batch.pending()) == 2


# --- razvrstavanje vaučera po folderima --------------------------------------

def test_vouchers_go_to_folder_of_default_email(tmp_path):
    guest = Guest(row=1, given_name_raw="Marko", surname_raw="Petrović",
                  jmbg_raw=A, arrival_raw="05.10")
    guest.validate(YEAR)
    assert guest.voucher_dir(tmp_path, "vauceri@primer.rs") == tmp_path / "vauceri@primer.rs"


def test_own_email_beats_the_default(tmp_path):
    guest = Guest(row=1, given_name_raw="Ana", surname_raw="Anić",
                  jmbg_raw=B, arrival_raw="05.10", email_raw="ana@drugi.rs")
    guest.validate(YEAR)
    assert guest.voucher_dir(tmp_path, "vauceri@primer.rs") == tmp_path / "ana@drugi.rs"


def test_without_any_email_vouchers_stay_in_the_root(tmp_path):
    """Ko ne koristi razvrstavanje, dobija isto ponašanje kao pre."""
    guest = Guest(row=1, given_name_raw="Marko", surname_raw="Petrović",
                  jmbg_raw=A, arrival_raw="05.10")
    guest.validate(YEAR)
    assert guest.voucher_dir(tmp_path, "") == tmp_path


def test_toolbar_email_is_reported_before_the_run(window):
    set_clipboard(
        f"Marko\tPetrović\t{A}\t05.10\t5\t\n"
        f"Ana\tAnić\t{B}\t06.10\t5\tana@drugi.rs\n"
    )
    window._paste()
    window.email_box.setText("vauceri@primer.rs")

    opis = window._describe_voucher_dirs(window.model.guests, "vauceri@primer.rs")
    assert "vauceri@primer.rs: 1" in opis
    assert "ana@drugi.rs: 1" in opis

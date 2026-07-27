"""Tabela gostiju sa Ctrl+V iz Excela i Ctrl+C nazad u Excel."""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QAction, QGuiApplication, QKeySequence
from PySide6.QtWidgets import QAbstractItemView, QHeaderView, QMenu, QTableView

from ..clipboard import PasteResult, parse_clipboard, to_clipboard
from ..models import Guest
from .table_model import COL_SELECTED, COLUMNS, GuestTableModel


class GuestTable(QTableView):
    """Prikaz gostiju. Sav rad sa clipboard-om je ovde."""

    pasted = Signal(object)          # PasteResult
    copied = Signal(int)             # koliko redova
    guests_removed = Signal(int)

    def __init__(self, model: GuestTableModel, parent=None) -> None:
        super().__init__(parent)
        self.setModel(model)
        self._model = model

        self.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.setSelectionMode(QAbstractItemView.ExtendedSelection)
        self.setAlternatingRowColors(True)
        self.setSortingEnabled(False)
        self.setEditTriggers(
            QAbstractItemView.DoubleClicked | QAbstractItemView.EditKeyPressed
        )
        self.verticalHeader().setVisible(False)
        self.setContextMenuPolicy(Qt.CustomContextMenu)
        self.customContextMenuRequested.connect(self._show_menu)

        header = self.horizontalHeader()
        for position, column in enumerate(COLUMNS):
            self.setColumnWidth(position, column.width)
        header.setStretchLastSection(True)
        header.setSectionResizeMode(COL_SELECTED, QHeaderView.Fixed)

    # -- clipboard --------------------------------------------------------

    def paste_from_clipboard(self, default_year: int | None = None) -> PasteResult:
        """Nalepi goste iz Excela. Novi redovi se **dodaju** na postojeće."""
        text = QGuiApplication.clipboard().text()
        result = parse_clipboard(text, default_year, start_row=len(self._model.guests) + 1)
        if result.guests:
            self._model.append(result.guests)
            self.resizeRowsToContents()
        self.pasted.emit(result)
        return result

    def copy_to_clipboard(self, only_selected: bool = True) -> int:
        """Kopiraj u Excel sa STATUS/RAZLOG/PDF kolonama."""
        guests = self.selected_guests() if only_selected else list(self._model.guests)
        if not guests:
            guests = list(self._model.guests)
        if not guests:
            return 0
        QGuiApplication.clipboard().setText(to_clipboard(guests))
        self.copied.emit(len(guests))
        return len(guests)

    # -- izbor ------------------------------------------------------------

    def selected_rows(self) -> list[int]:
        return sorted({index.row() for index in self.selectionModel().selectedIndexes()})

    def selected_guests(self) -> list[Guest]:
        return [self._model.guests[row] for row in self.selected_rows()]

    def remove_selected(self) -> int:
        rows = self.selected_rows()
        if rows:
            self._model.remove_rows(rows)
            self.guests_removed.emit(len(rows))
        return len(rows)

    def reset_selected_status(self) -> int:
        """Vrati označene goste u red za ponovni pokušaj."""
        guests = self.selected_guests() or list(self._model.guests)
        for guest in guests:
            guest.reset()
        self._model.refresh_all()
        return len(guests)

    # -- tastatura --------------------------------------------------------

    def keyPressEvent(self, event) -> None:
        if event.matches(QKeySequence.Paste):
            self.paste_from_clipboard(self._model.year)
            return
        if event.matches(QKeySequence.Copy):
            self.copy_to_clipboard()
            return
        if event.key() in (Qt.Key_Delete, Qt.Key_Backspace) and not self.state() == QAbstractItemView.EditingState:
            self.remove_selected()
            return
        if event.key() == Qt.Key_Space:
            self._toggle_selected_checkboxes()
            return
        super().keyPressEvent(event)

    def _toggle_selected_checkboxes(self) -> None:
        guests = self.selected_guests()
        if not guests:
            return
        target = not all(guest.selected for guest in guests)
        for guest in guests:
            guest.selected = target
        self._model.refresh_all()

    # -- kontekstni meni --------------------------------------------------

    def _show_menu(self, position) -> None:
        menu = QMenu(self)
        guests = self.selected_guests()

        paste = QAction("Nalepi iz Excela\tCtrl+V", self)
        paste.triggered.connect(lambda: self.paste_from_clipboard(self._model.year))
        menu.addAction(paste)

        copy = QAction(f"Kopiraj {len(guests) or len(self._model.guests)} redova\tCtrl+C", self)
        copy.triggered.connect(lambda: self.copy_to_clipboard())
        menu.addAction(copy)

        menu.addSeparator()

        toggle = QAction("Uključi / isključi označene", self)
        toggle.triggered.connect(self._toggle_selected_checkboxes)
        menu.addAction(toggle)

        retry = QAction("Vrati u red za ponovni pokušaj", self)
        retry.triggered.connect(self.reset_selected_status)
        menu.addAction(retry)

        remove = QAction(f"Obriši {len(guests)} redova\tDel", self)
        remove.setEnabled(bool(guests))
        remove.triggered.connect(self.remove_selected)
        menu.addAction(remove)

        shot = next((g.error.screenshot for g in guests if g.error and g.error.screenshot), None)
        if shot:
            menu.addSeparator()
            open_shot = QAction("Otvori screenshot greške", self)
            open_shot.triggered.connect(lambda: open_in_system(Path(shot)))
            menu.addAction(open_shot)

        pdf = next((g.pdf_path for g in guests if g.pdf_path), None)
        if pdf:
            open_pdf = QAction("Otvori vaučer", self)
            open_pdf.triggered.connect(lambda: open_in_system(Path(pdf)))
            menu.addAction(open_pdf)

        menu.exec(self.viewport().mapToGlobal(position))


def open_in_system(path: Path) -> None:
    """Otvori fajl ili folder podrazumevanim programom (radi na Linuxu i Windows-u)."""
    try:
        if sys.platform.startswith("win"):
            import os
            os.startfile(str(path))  # type: ignore[attr-defined]
        elif sys.platform == "darwin":
            subprocess.Popen(["open", str(path)])
        else:
            subprocess.Popen(["xdg-open", str(path)])
    except (OSError, AttributeError):
        pass

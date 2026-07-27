"""Model tabele gostiju — ono što u aplikaciji izgleda kao mali Excel.

Boje redova su glavni način praćenja: zeleno je prijavljen, crveno je pao, žuto je u toku.
Nijanse su poluprovidne pa rade i u svetloj i u tamnoj temi.
"""

from __future__ import annotations

from dataclasses import dataclass

from PySide6.QtCore import QAbstractTableModel, QModelIndex, Qt
from PySide6.QtGui import QColor

from ..models import Guest, Status


@dataclass(frozen=True)
class Column:
    key: str
    title: str
    width: int
    editable: bool = False


COLUMNS: tuple[Column, ...] = (
    Column("selected", "", 34),
    Column("row", "#", 44),
    Column("given_name", "Ime", 120, editable=True),
    Column("surname", "Prezime", 135, editable=True),
    Column("jmbg", "JMBG", 125, editable=True),
    Column("arrival", "Dolazak", 95, editable=True),
    Column("days", "Dana", 52, editable=True),
    Column("stay", "Boravak", 170),
    Column("status", "Status", 90),
    Column("reason", "Razlog", 250),
    Column("pdf", "Vaučer", 190),
)

COL_SELECTED = 0
COL_STATUS = 8

#: Poluprovidne podloge — čitljive i na beloj i na tamnoj pozadini.
_ROW_COLORS: dict[Status, QColor | None] = {
    Status.OK: QColor(46, 160, 67, 55),
    Status.ERROR: QColor(218, 54, 51, 60),
    Status.RUNNING: QColor(255, 179, 0, 70),
    Status.SKIPPED: QColor(128, 128, 128, 45),
    Status.PENDING: None,
}

#: Blaga podloga za red koji ima napomenu ali nije greška (npr. popravljena vodeća nula).
_NOTE_COLOR = QColor(56, 139, 253, 40)


class GuestTableModel(QAbstractTableModel):
    def __init__(self, guests: list[Guest] | None = None, year: int | None = None) -> None:
        super().__init__()
        # Namerno `is None`, ne `or []`: prazna lista je falsy, pa bi `or` napravio novu
        # listu i model bi prestao da deli goste sa turom (Batch.guests).
        self.guests: list[Guest] = guests if guests is not None else []
        self.year = year

    # -- osnovno ----------------------------------------------------------

    def rowCount(self, parent: QModelIndex = QModelIndex()) -> int:
        return 0 if parent.isValid() else len(self.guests)

    def columnCount(self, parent: QModelIndex = QModelIndex()) -> int:
        return 0 if parent.isValid() else len(COLUMNS)

    def headerData(self, section: int, orientation: Qt.Orientation, role: int = Qt.DisplayRole):
        if role != Qt.DisplayRole:
            return None
        if orientation == Qt.Horizontal:
            return COLUMNS[section].title
        return None

    def flags(self, index: QModelIndex) -> Qt.ItemFlag:
        if not index.isValid():
            return Qt.NoItemFlags
        base = Qt.ItemIsEnabled | Qt.ItemIsSelectable
        column = COLUMNS[index.column()]
        if column.key == "selected":
            return base | Qt.ItemIsUserCheckable
        if column.editable:
            return base | Qt.ItemIsEditable
        return base

    # -- čitanje ----------------------------------------------------------

    def data(self, index: QModelIndex, role: int = Qt.DisplayRole):
        if not index.isValid():
            return None
        guest = self.guests[index.row()]
        column = COLUMNS[index.column()]

        if role == Qt.CheckStateRole and column.key == "selected":
            return Qt.Checked if guest.selected else Qt.Unchecked

        if role in (Qt.DisplayRole, Qt.EditRole):
            return self._text(guest, column.key, editing=role == Qt.EditRole)

        if role == Qt.BackgroundRole:
            color = _ROW_COLORS.get(guest.status)
            if color is None and guest.note:
                color = _NOTE_COLOR
            return color

        if role == Qt.ToolTipRole:
            return self._tooltip(guest)

        if role == Qt.TextAlignmentRole and column.key in ("row", "days", "status"):
            return int(Qt.AlignCenter)

        return None

    def _text(self, guest: Guest, key: str, editing: bool = False) -> str:
        if key == "selected":
            return ""
        if key == "row":
            return str(guest.row)
        if key == "surname":
            return guest.surname or guest.surname_raw
        if key == "given_name":
            return guest.given_name or guest.given_name_raw
        if key == "jmbg":
            return guest.jmbg
        if key == "arrival":
            # Pri izmeni prikazujemo original iz Excela da korisnik ne prepravlja
            # ono što je program već normalizovao.
            return guest.arrival_raw if editing else guest.arrival_display
        if key == "days":
            return guest.days_raw if editing else guest.days_display
        if key == "stay":
            return guest.stay_display
        if key == "status":
            return guest.status.label
        if key == "reason":
            return guest.reason
        if key == "pdf":
            return guest.pdf_display
        return ""

    def _tooltip(self, guest: Guest) -> str:
        lines: list[str] = []
        if guest.error:
            lines.append(guest.error.text)
            if guest.error.detail:
                lines.append(guest.error.detail)
            if guest.error.screenshot:
                lines.append(f"Screenshot: {guest.error.screenshot}")
        if guest.note:
            lines.append(guest.note)
        if guest.jmbg_info:
            info = guest.jmbg_info
            lines.append(
                f"Rođen(a) {info.birth_date:%d.%m.%Y} · {info.gender_label} · {info.region_name}"
            )
        if guest.stay:
            lines.append(f"{guest.stay.nights} noćenja")
        if guest.pdf_path:
            lines.append(f"Vaučer: {guest.pdf_path}")
        if guest.attempts:
            lines.append(f"Pokušaja: {guest.attempts}")
        return "\n".join(lines)

    # -- pisanje ----------------------------------------------------------

    def setData(self, index: QModelIndex, value, role: int = Qt.EditRole) -> bool:
        if not index.isValid():
            return False
        guest = self.guests[index.row()]
        column = COLUMNS[index.column()]

        if role == Qt.CheckStateRole and column.key == "selected":
            guest.selected = Qt.CheckState(value) == Qt.Checked
            self.dataChanged.emit(index, index, [Qt.CheckStateRole])
            return True

        if role != Qt.EditRole or not column.editable:
            return False

        text = str(value).strip()
        if column.key == "surname":
            guest.surname_raw = text
        elif column.key == "given_name":
            guest.given_name_raw = text
        elif column.key == "jmbg":
            guest.jmbg_raw = text
        elif column.key == "arrival":
            guest.arrival_raw = text
        elif column.key == "days":
            guest.days_raw = text
        else:
            return False

        # Ispravka podataka odmah menja boju reda — ne čeka se pokretanje ture.
        guest.validate(self.year)
        self.refresh_row(index.row())
        return True

    # -- izmene liste -----------------------------------------------------

    def set_guests(self, guests: list[Guest]) -> None:
        self.beginResetModel()
        self.guests = guests
        self.endResetModel()

    def append(self, guests: list[Guest]) -> None:
        if not guests:
            return
        start = len(self.guests)
        self.beginInsertRows(QModelIndex(), start, start + len(guests) - 1)
        self.guests.extend(guests)
        self.endInsertRows()
        self.renumber()

    def remove_rows(self, rows: list[int]) -> None:
        for row in sorted(set(rows), reverse=True):
            if 0 <= row < len(self.guests):
                self.beginRemoveRows(QModelIndex(), row, row)
                del self.guests[row]
                self.endRemoveRows()
        self.renumber()

    def clear(self) -> None:
        self.set_guests([])

    def renumber(self) -> None:
        """Redni brojevi moraju biti bez rupa — po njima se gost pamti u bazi."""
        for position, guest in enumerate(self.guests, start=1):
            guest.row = position
        self.refresh_all()

    def refresh_row(self, row: int) -> None:
        if 0 <= row < len(self.guests):
            self.dataChanged.emit(
                self.index(row, 0), self.index(row, len(COLUMNS) - 1)
            )

    def refresh_all(self) -> None:
        if self.guests:
            self.dataChanged.emit(
                self.index(0, 0), self.index(len(self.guests) - 1, len(COLUMNS) - 1)
            )

    def set_all_selected(self, selected: bool) -> None:
        for guest in self.guests:
            guest.selected = selected
        self.refresh_all()

    # -- pomoćno ----------------------------------------------------------

    def guest_at(self, row: int) -> Guest | None:
        return self.guests[row] if 0 <= row < len(self.guests) else None

    def index_of(self, guest: Guest) -> int:
        for position, candidate in enumerate(self.guests):
            if candidate is guest:
                return position
        return -1

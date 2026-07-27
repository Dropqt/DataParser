"""SQLite evidencija tura, gostiju i događaja.

Baza služi dvema stvarima:

* **Nastavak posle prekida** — ako program pukne ili se zatvori nasred ture od 30 gostiju,
  pri sledećem pokretanju se učita ista tura i nastavlja se od prvog neobrađenog. Bez ovoga
  bi ponovno pokretanje pravilo duplikate na portalu.
* **Evidencija grešaka** — ko je pao, zašto, koji je screenshot snimljen i koliko je puta
  pokušano. To je ono što se posle vraća u glavni Excel.
"""

from __future__ import annotations

import functools
import sqlite3
import threading
from datetime import date, datetime
from pathlib import Path

from .errors import ErrorKind, GuestError
from .models import Batch, Guest, Status

SCHEMA = """
CREATE TABLE IF NOT EXISTS batches (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    created_at    TEXT NOT NULL,
    account_label TEXT NOT NULL DEFAULT '',
    note          TEXT NOT NULL DEFAULT ''
);

CREATE TABLE IF NOT EXISTS guests (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    batch_id      INTEGER NOT NULL REFERENCES batches(id) ON DELETE CASCADE,
    row_no        INTEGER NOT NULL,
    surname       TEXT NOT NULL DEFAULT '',
    given_name    TEXT NOT NULL DEFAULT '',
    jmbg          TEXT NOT NULL DEFAULT '',
    date_raw      TEXT NOT NULL DEFAULT '',
    status        TEXT NOT NULL DEFAULT 'PENDING',
    error_kind    TEXT,
    error_message TEXT,
    error_detail  TEXT,
    screenshot    TEXT,
    pdf_path      TEXT,
    attempts      INTEGER NOT NULL DEFAULT 0,
    selected      INTEGER NOT NULL DEFAULT 1,
    updated_at    TEXT,
    UNIQUE (batch_id, row_no)
);

CREATE TABLE IF NOT EXISTS events (
    id       INTEGER PRIMARY KEY AUTOINCREMENT,
    ts       TEXT NOT NULL,
    batch_id INTEGER,
    guest_id INTEGER,
    level    TEXT NOT NULL DEFAULT 'INFO',
    message  TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS ix_guests_batch  ON guests (batch_id);
CREATE INDEX IF NOT EXISTS ix_events_batch  ON events (batch_id);
"""


def _locked(method):
    """Serijalizuj pristup bazi.

    GUI čita iz glavne niti dok radna nit upisuje rezultate, a paralelni režim će voziti
    više tura odjednom. Jedna veza sa ``check_same_thread=False`` to trpi samo ako se
    pozivi ne preklapaju — otud brava.
    """

    @functools.wraps(method)
    def wrapper(self, *args, **kwargs):
        with self._lock:
            return method(self, *args, **kwargs)

    return wrapper


class Store:
    """Tanak sloj oko SQLite-a. Koristi se kao kontekst menadžer ili sa ``close()``."""

    def __init__(self, db_path: Path | str) -> None:
        self._lock = threading.RLock()
        self.path = Path(db_path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._conn = sqlite3.connect(str(self.path), check_same_thread=False)
        self._conn.row_factory = sqlite3.Row
        self._conn.execute("PRAGMA foreign_keys = ON")
        # WAL: upis se odmah snima na disk, pa nagli prekid ne gubi poslednje goste.
        self._conn.execute("PRAGMA journal_mode = WAL")
        self._conn.executescript(SCHEMA)
        self._conn.commit()

    def __enter__(self) -> "Store":
        return self

    def __exit__(self, *_exc: object) -> None:
        self.close()

    @_locked
    def close(self) -> None:
        self._conn.close()

    # -- ture -------------------------------------------------------------

    @_locked
    def create_batch(self, account_label: str = "", note: str = "") -> int:
        cur = self._conn.execute(
            "INSERT INTO batches (created_at, account_label, note) VALUES (?, ?, ?)",
            (datetime.now().isoformat(timespec="seconds"), account_label, note),
        )
        self._conn.commit()
        return int(cur.lastrowid)

    @_locked
    def save_batch(self, batch: Batch) -> int:
        """Snimi celu turu. Pravi je ako još nema ``db_id``."""
        if batch.db_id is None:
            batch.db_id = self.create_batch(batch.account_label)
        else:
            self._conn.execute(
                "UPDATE batches SET account_label = ? WHERE id = ?",
                (batch.account_label, batch.db_id),
            )
        for guest in batch.guests:
            self.save_guest(batch.db_id, guest)
        self._conn.commit()
        return batch.db_id

    @_locked
    def save_guest(self, batch_id: int, guest: Guest, commit: bool = True) -> int:
        """Upiši gosta. Isti ``row_no`` u istoj turi se ažurira, ne duplira."""
        error = guest.error
        self._conn.execute(
            """
            INSERT INTO guests (batch_id, row_no, surname, given_name, jmbg, date_raw,
                                status, error_kind, error_message, error_detail,
                                screenshot, pdf_path, attempts, selected, updated_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT (batch_id, row_no) DO UPDATE SET
                surname = excluded.surname,
                given_name = excluded.given_name,
                jmbg = excluded.jmbg,
                date_raw = excluded.date_raw,
                status = excluded.status,
                error_kind = excluded.error_kind,
                error_message = excluded.error_message,
                error_detail = excluded.error_detail,
                screenshot = excluded.screenshot,
                pdf_path = excluded.pdf_path,
                attempts = excluded.attempts,
                selected = excluded.selected,
                updated_at = excluded.updated_at
            """,
            (
                batch_id,
                guest.row,
                guest.surname or guest.surname_raw,
                guest.given_name or guest.given_name_raw,
                guest.jmbg,
                guest.date_raw,
                guest.status.value,
                error.kind.value if error else None,
                error.message if error else None,
                error.detail if error else None,
                error.screenshot if error else None,
                guest.pdf_path,
                guest.attempts,
                int(guest.selected),
                (guest.updated_at or datetime.now()).isoformat(timespec="seconds"),
            ),
        )
        if commit:
            self._conn.commit()

        row = self._conn.execute(
            "SELECT id FROM guests WHERE batch_id = ? AND row_no = ?", (batch_id, guest.row)
        ).fetchone()
        guest.db_id = int(row["id"])
        return guest.db_id

    @_locked
    def load_batch(self, batch_id: int, default_year: int | None = None) -> Batch | None:
        header = self._conn.execute("SELECT * FROM batches WHERE id = ?", (batch_id,)).fetchone()
        if header is None:
            return None

        batch = Batch(
            db_id=batch_id,
            account_label=header["account_label"],
            created_at=_parse_date(header["created_at"]),
        )
        rows = self._conn.execute(
            "SELECT * FROM guests WHERE batch_id = ? ORDER BY row_no", (batch_id,)
        ).fetchall()
        batch.guests = [_row_to_guest(row, default_year) for row in rows]
        return batch

    @_locked
    def latest_batch(self, default_year: int | None = None) -> Batch | None:
        row = self._conn.execute("SELECT id FROM batches ORDER BY id DESC LIMIT 1").fetchone()
        return self.load_batch(int(row["id"]), default_year) if row else None

    @_locked
    def list_batches(self, limit: int = 50) -> list[sqlite3.Row]:
        """Pregled tura sa brojem gostiju i grešaka — za meni 'Otvori raniju turu'."""
        return self._conn.execute(
            """
            SELECT b.id, b.created_at, b.account_label,
                   COUNT(g.id)                                        AS ukupno,
                   SUM(CASE WHEN g.status = 'OK' THEN 1 ELSE 0 END)   AS uspesno,
                   SUM(CASE WHEN g.status = 'ERROR' THEN 1 ELSE 0 END) AS gresaka
            FROM batches b
            LEFT JOIN guests g ON g.batch_id = b.id
            GROUP BY b.id
            ORDER BY b.id DESC
            LIMIT ?
            """,
            (limit,),
        ).fetchall()

    @_locked
    def delete_batch(self, batch_id: int) -> None:
        self._conn.execute("DELETE FROM guests WHERE batch_id = ?", (batch_id,))
        self._conn.execute("DELETE FROM events WHERE batch_id = ?", (batch_id,))
        self._conn.execute("DELETE FROM batches WHERE id = ?", (batch_id,))
        self._conn.commit()

    # -- događaji ---------------------------------------------------------

    @_locked
    def log(self, message: str, level: str = "INFO", batch_id: int | None = None,
            guest_id: int | None = None) -> None:
        self._conn.execute(
            "INSERT INTO events (ts, batch_id, guest_id, level, message) VALUES (?, ?, ?, ?, ?)",
            (datetime.now().isoformat(timespec="seconds"), batch_id, guest_id, level, message),
        )
        self._conn.commit()

    @_locked
    def events(self, batch_id: int | None = None, limit: int = 500) -> list[sqlite3.Row]:
        if batch_id is None:
            return self._conn.execute(
                "SELECT * FROM events ORDER BY id DESC LIMIT ?", (limit,)
            ).fetchall()
        return self._conn.execute(
            "SELECT * FROM events WHERE batch_id = ? ORDER BY id DESC LIMIT ?", (batch_id, limit)
        ).fetchall()


# ---------------------------------------------------------------------------
# pretvaranje red ↔ Guest
# ---------------------------------------------------------------------------

def _parse_date(value: str | None) -> date:
    try:
        return datetime.fromisoformat(value).date() if value else date.today()
    except (TypeError, ValueError):
        return date.today()


def _row_to_guest(row: sqlite3.Row, default_year: int | None) -> Guest:
    guest = Guest(
        row=int(row["row_no"]),
        surname_raw=row["surname"] or "",
        given_name_raw=row["given_name"] or "",
        jmbg_raw=row["jmbg"] or "",
        date_raw=row["date_raw"] or "",
        pdf_path=row["pdf_path"],
        attempts=int(row["attempts"] or 0),
        selected=bool(row["selected"]),
        db_id=int(row["id"]),
    )
    # Ponovo validiramo umesto da čuvamo izvedena polja — tako popravka pravila
    # validacije odmah važi i za ranije snimljene ture.
    data_is_valid = guest.validate(default_year)
    stored = _status(row["status"])

    if row["error_kind"]:
        guest.error = GuestError(
            kind=_error_kind(row["error_kind"]),
            message=row["error_message"] or "",
            detail=row["error_detail"] or "",
            screenshot=row["screenshot"],
        )
        guest.status = stored
    elif data_is_valid:
        guest.status = stored
    # Ako validacija padne a baza nema zapisanu grešku, ostaje ERROR iz validacije.

    if guest.status is Status.RUNNING:
        # Program je pukao usred ovog gosta. Ne znamo da li je prijava prošla na portalu,
        # pa ga vraćamo u red ali sa jasnom napomenom da se proveri pre ponavljanja.
        guest.status = Status.PENDING
        guest.note = "prekinuto pri prethodnom pokretanju — proveri da nije već prijavljen"

    if row["updated_at"]:
        try:
            guest.updated_at = datetime.fromisoformat(row["updated_at"])
        except ValueError:
            pass
    return guest


def _status(value: str | None) -> Status:
    try:
        return Status(value)
    except ValueError:
        return Status.PENDING


def _error_kind(value: str | None) -> ErrorKind:
    try:
        return ErrorKind(value)
    except ValueError:
        return ErrorKind.UNKNOWN

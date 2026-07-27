import pytest

from eturista.errors import ErrorKind, GuestError
from eturista.models import Batch, Guest, Status
from eturista.store import Store
from eturista.validation import jmbg_check_digit

YEAR = 2026


def jmbg(first_twelve: str) -> str:
    return first_twelve + str(jmbg_check_digit(first_twelve))


A = jmbg("010199071012")
B = jmbg("150398871001")


@pytest.fixture
def store(tmp_path):
    with Store(tmp_path / "test.db") as s:
        yield s


def make_batch() -> Batch:
    guests = [
        Guest(row=1, surname_raw="Petrović", given_name_raw="Marko", jmbg_raw=A, arrival_raw="05.10-10.10"),
        Guest(row=2, surname_raw="Ilić", given_name_raw="Jovan", jmbg_raw=B, arrival_raw="06.10-12.10"),
    ]
    for guest in guests:
        guest.validate(YEAR)
    return Batch(guests=guests, account_label="mileta")


def test_save_and_load_round_trip(store):
    batch = make_batch()
    batch_id = store.save_batch(batch)

    loaded = store.load_batch(batch_id, YEAR)
    assert loaded is not None
    assert loaded.account_label == "mileta"
    assert [g.jmbg for g in loaded.guests] == [A, B]
    assert [g.row for g in loaded.guests] == [1, 2]
    assert loaded.guests[0].stay.nights == 5


def test_saving_twice_updates_instead_of_duplicating(store):
    batch = make_batch()
    batch_id = store.save_batch(batch)

    batch.guests[0].mark_ok("2026_PETROVIC_MARKO.pdf")
    store.save_batch(batch)

    loaded = store.load_batch(batch_id, YEAR)
    assert len(loaded.guests) == 2
    assert loaded.guests[0].status is Status.OK
    assert loaded.guests[0].pdf_path == "2026_PETROVIC_MARKO.pdf"


def test_error_survives_reload(store):
    batch = make_batch()
    batch.guests[1].mark_error(
        GuestError(ErrorKind.JMBG_REJECTED_PORTAL, "Portal je odbio JMBG", screenshot="s/1.png")
    )
    batch_id = store.save_batch(batch)

    guest = store.load_batch(batch_id, YEAR).guests[1]
    assert guest.status is Status.ERROR
    assert guest.error.kind is ErrorKind.JMBG_REJECTED_PORTAL
    assert guest.error.screenshot == "s/1.png"
    assert guest.error.text == "Portal je odbio JMBG"


def test_resume_returns_only_unfinished_guests(store):
    batch = make_batch()
    batch.guests[0].mark_ok()
    batch.guests[1].mark_error(GuestError(ErrorKind.TIMEOUT, "Isteklo vreme"))
    batch_id = store.save_batch(batch)

    loaded = store.load_batch(batch_id, YEAR)
    pending = loaded.pending()
    assert [g.row for g in pending] == [2]


def test_crash_mid_guest_is_requeued_with_warning(store):
    """RUNNING u bazi znači da je program pukao usred tog gosta."""
    batch = make_batch()
    batch.guests[0].mark_running()
    batch_id = store.save_batch(batch)

    guest = store.load_batch(batch_id, YEAR).guests[0]
    assert guest.status is Status.PENDING
    assert "prekinuto" in guest.note
    assert guest.attempts == 1


def test_invalid_data_stays_flagged_after_reload(store):
    bad = A[:12] + str((int(A[12]) + 1) % 10)
    guest = Guest(row=1, surname_raw="Petrović", given_name_raw="Marko", jmbg_raw=bad, arrival_raw="05.10-10.10")
    guest.validate(YEAR)
    batch = Batch(guests=[guest], account_label="majka")
    batch_id = store.save_batch(batch)

    loaded = store.load_batch(batch_id, YEAR).guests[0]
    assert loaded.status is Status.ERROR
    assert "kontrolna cifra" in loaded.error.text


def test_unselected_guests_are_not_in_pending(store):
    batch = make_batch()
    batch.guests[0].selected = False
    store.save_batch(batch)

    loaded = store.latest_batch(YEAR)
    assert [g.row for g in loaded.pending()] == [2]
    assert loaded.guests[0].selected is False


def test_latest_batch_returns_newest(store):
    store.save_batch(make_batch())
    second = make_batch()
    second.account_label = "majka"
    store.save_batch(second)

    assert store.latest_batch(YEAR).account_label == "majka"


def test_list_batches_reports_counts(store):
    batch = make_batch()
    batch.guests[0].mark_ok()
    batch.guests[1].mark_error(GuestError(ErrorKind.TIMEOUT, "Isteklo vreme"))
    store.save_batch(batch)

    row = store.list_batches()[0]
    assert row["ukupno"] == 2
    assert row["uspesno"] == 1
    assert row["gresaka"] == 1


def test_events_are_recorded(store):
    batch_id = store.save_batch(make_batch())
    store.log("Prijava uspela", batch_id=batch_id)
    store.log("Portal odbio JMBG", level="ERROR", batch_id=batch_id)

    events = store.events(batch_id)
    assert len(events) == 2
    assert events[0]["level"] == "ERROR"


def test_delete_batch_removes_guests(store):
    batch_id = store.save_batch(make_batch())
    store.delete_batch(batch_id)
    assert store.load_batch(batch_id, YEAR) is None
    assert store.latest_batch(YEAR) is None


def test_batch_summary(store):
    batch = make_batch()
    batch.guests[0].mark_ok()
    assert batch.summary() == "1/2 prijavljeno · 0 grešaka"

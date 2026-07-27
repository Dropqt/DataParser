"""End-to-end tok kroz lažni portal, sa pravim Chrome-om.

Ovi testovi pokrivaju ono što se u prvoj turi lomilo u praksi: greška koja prekine ceo
prolaz, izgubljen napredak posle pada, i vaučer koji nikad ne stigne na disk.

Pokretanje samo brzih testova:  pytest -m "not browser"
"""

from __future__ import annotations

import threading

import pytest

from eturista.accounts import Account
from eturista.config import Config
from eturista.errors import ErrorKind
from eturista.models import Batch, Guest, Status
from eturista.runner import Runner, RunOptions
from eturista.store import Store
from fake_portal.app import FakePortal, PortalState

from .conftest import make_jmbg

pytestmark = pytest.mark.browser

YEAR = 2026
A = make_jmbg("010199071012")   # Petrović Marko
B = make_jmbg("150398871001")   # Ilić Jovan
C = make_jmbg("010101750500")   # Anić Ana


@pytest.fixture
def portal():
    state = PortalState()
    with FakePortal(state) as running:
        yield running, state


@pytest.fixture
def config(portal, tmp_path):
    running, _ = portal
    cfg = Config(
        portal_url=running.base_url,
        pdf_dir=tmp_path / "vauceri",
        screenshot_dir=tmp_path / "screenshots",
        db_path=tmp_path / "eturista.db",
        year=YEAR,
        headless=True,
    )
    cfg.ensure_dirs()
    return cfg


@pytest.fixture
def account():
    return Account(label="test", username="test", password="test123")


def make_batch(*rows) -> Batch:
    guests = []
    for index, (surname, given, jmbg, dates) in enumerate(rows, start=1):
        guest = Guest(row=index, surname_raw=surname, given_name_raw=given,
                      jmbg_raw=jmbg, arrival_raw=dates)
        guest.validate(YEAR)
        guests.append(guest)
    return Batch(guests=guests)


DEFAULT_ROWS = (
    ("Petrović", "Marko", A, "05.10-10.10"),
    ("Ilić", "Jovan", B, "06.10-12.10"),
)


# ---------------------------------------------------------------------------

def test_happy_path_registers_everyone(unlocked_selectors, portal, config, account):
    running, state = portal
    batch = make_batch(*DEFAULT_ROWS)

    result = Runner(config, account, batch).run()

    assert result.fatal == ""
    assert (result.succeeded, result.failed) == (2, 0)
    assert all(g.status is Status.OK for g in batch.guests)

    # portal je stvarno primio podatke, ne samo da je klik prošao
    assert len(state.saved) == 2
    assert state.saved[0]["jmbg"] == A
    assert state.saved[0]["datumOd"] == "05.10.2026"
    assert state.saved[0]["datumDo"] == "10.10.2026"


def test_vouchers_are_downloaded_and_renamed(unlocked_selectors, portal, config, account):
    batch = make_batch(*DEFAULT_ROWS)
    Runner(config, account, batch).run()

    names = sorted(p.name for p in config.pdf_dir.glob("*.pdf"))
    assert names == ["2026_ILIC_JOVAN.pdf", "2026_PETROVIC_MARKO.pdf"]

    for guest in batch.guests:
        assert guest.pdf_path and guest.pdf_path.endswith(".pdf")

    # fajl je stvaran PDF, ne polupreuzet komad
    first = config.pdf_dir / "2026_PETROVIC_MARKO.pdf"
    assert first.read_bytes().startswith(b"%PDF")


def test_rejected_jmbg_does_not_stop_the_run(unlocked_selectors, portal, config, account):
    """Ovo je greška zbog koje je stara skripta gubila ostatak liste."""
    _, state = portal
    state.rejected_jmbgs = {B}

    batch = make_batch(
        ("Petrović", "Marko", A, "05.10-10.10"),
        ("Ilić", "Jovan", B, "06.10-12.10"),
        ("Anić", "Ana", C, "07.10-13.10"),
    )
    result = Runner(config, account, batch).run()

    assert (result.succeeded, result.failed) == (2, 1)
    assert [g.status for g in batch.guests] == [Status.OK, Status.ERROR, Status.OK]

    failed = batch.guests[1]
    assert failed.error.kind is ErrorKind.JMBG_REJECTED_PORTAL
    assert "evidenciji" in failed.error.text


def test_failure_saves_screenshot(unlocked_selectors, portal, config, account):
    _, state = portal
    state.rejected_jmbgs = {A}

    batch = make_batch(("Petrović", "Marko", A, "05.10-10.10"))
    Runner(config, account, batch).run()

    guest = batch.guests[0]
    assert guest.error.screenshot is not None
    assert list(config.screenshot_dir.glob("*.png"))


def test_wrong_password_fails_fast_without_touching_guests(unlocked_selectors, portal, config):
    batch = make_batch(*DEFAULT_ROWS)
    bad = Account(label="test", username="test", password="pogresna")

    result = Runner(config, bad, batch).run()

    assert "nije uspela" in result.fatal
    assert result.succeeded == 0
    assert all(g.status is Status.PENDING for g in batch.guests)


def test_expired_session_triggers_relogin(unlocked_selectors, portal, config, account):
    _, state = portal
    state.expire_after = 1   # sesija pada posle prvog gosta

    batch = make_batch(*DEFAULT_ROWS)
    result = Runner(config, account, batch).run()

    assert result.succeeded == 2
    assert state.login_attempts >= 2


def test_stop_event_halts_between_guests(unlocked_selectors, portal, config, account):
    batch = make_batch(
        ("Petrović", "Marko", A, "05.10-10.10"),
        ("Ilić", "Jovan", B, "06.10-12.10"),
        ("Anić", "Ana", C, "07.10-13.10"),
    )
    stop = threading.Event()

    def halt_after_first(guest):
        stop.set()

    from eturista.runner import Reporter
    result = Runner(
        config, account, batch,
        reporter=Reporter(on_guest_finished=halt_after_first),
        stop_event=stop,
    ).run()

    assert result.stopped
    assert result.succeeded == 1
    assert batch.guests[2].status is Status.PENDING


def test_progress_is_saved_and_run_resumes(unlocked_selectors, portal, config, account):
    """Prekid nasred ture pa ponovno pokretanje — bez duplikata na portalu."""
    _, state = portal
    rows = (
        ("Petrović", "Marko", A, "05.10-10.10"),
        ("Ilić", "Jovan", B, "06.10-12.10"),
        ("Anić", "Ana", C, "07.10-13.10"),
    )

    with Store(config.db_path) as store:
        batch = make_batch(*rows)
        stop = threading.Event()
        from eturista.runner import Reporter

        Runner(
            config, account, batch, store=store,
            reporter=Reporter(on_guest_finished=lambda g: stop.set()),
            stop_event=stop,
        ).run()

        assert len(state.saved) == 1
        batch_id = batch.db_id

    # nova sesija programa: učitaj istu turu i nastavi
    with Store(config.db_path) as store:
        resumed = store.load_batch(batch_id, YEAR)
        assert [g.status for g in resumed.guests] == [Status.OK, Status.PENDING, Status.PENDING]

        result = Runner(config, account, resumed, store=store).run()

    assert result.total == 2            # prvi gost se ne ponavlja
    assert len(state.saved) == 3        # portal je ukupno primio tri, ne četiri
    assert all(g.status is Status.OK for g in resumed.guests)


def test_invalid_data_never_reaches_the_portal(unlocked_selectors, portal, config, account):
    """Pogrešan JMBG se hvata lokalno — browser ni ne pokušava tog gosta."""
    _, state = portal
    bad = A[:12] + str((int(A[12]) + 1) % 10)

    batch = make_batch(
        ("Petrović", "Marko", bad, "05.10-10.10"),
        ("Ilić", "Jovan", B, "06.10-12.10"),
    )
    result = Runner(config, account, batch).run()

    assert result.total == 1
    assert len(state.saved) == 1
    assert batch.guests[0].status is Status.ERROR
    assert batch.guests[0].error.kind is ErrorKind.JMBG_INVALID_LOCAL


def test_locked_voucher_still_counts_guest_as_registered(portal, config, account):
    """Bez ``unlocked_selectors`` datumi i vaučer su zaključani.

    Dok je taj deo portala zatvoren, gost sme da prođe bez PDF-a — ali ne sme
    da se lažno prikaže kao uspešan ako sama rezervacija nije sačuvana.
    """
    batch = make_batch(("Petrović", "Marko", A, "05.10-10.10"))
    result = Runner(config, account, batch, options=RunOptions(max_attempts=1)).run()

    assert result.succeeded == 0
    assert batch.guests[0].error.kind is ErrorKind.SELECTOR_NOT_FOUND
    assert "nije podešen" in batch.guests[0].error.text


def test_selectors_resolve_against_mock_portal(unlocked_selectors, portal, config, account):
    """Ako neko promeni selektor a zaboravi lažni portal, ovo puca."""
    from eturista.runner import verify_selectors

    checks = verify_selectors(config, account)
    missing = [c.locator.name for c in checks if not c.found and not c.locator.optional]

    # Očekivano da fale:
    #  - CONFIRMATION i VOUCHER_DOWNLOAD postoje tek posle čuvanja rezervacije,
    #    a provera staje na praznoj formi;
    #  - LOGGED_IN_MARKER još nije potvrđen na živom portalu;
    #  - NEXT_BUTTON se koristi samo ako forma ima više koraka — lažni portal je
    #    jednostrani, a kakav je pravi znaćemo tek pri inspekciji (faza 5).
    assert set(missing) <= {"LOGGED_IN_MARKER", "CONFIRMATION", "VOUCHER_DOWNLOAD", "NEXT_BUTTON"}
    assert not [c for c in checks if c.locator.name == "GUEST_JMBG" and not c.found]

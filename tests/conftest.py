import os

import pytest

# Qt mora da zna da radi bez ekrana pre nego što se PySide6 uopšte uveze.
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from eturista.portal import selectors as S  # noqa: E402
from eturista.validation import jmbg_check_digit  # noqa: E402


def make_jmbg(first_twelve: str) -> str:
    """Ispravan JMBG od prvih 12 cifara - koristi se svuda u testovima."""
    return first_twelve + str(jmbg_check_digit(first_twelve))


@pytest.fixture
def unlocked_selectors():
    """Privremeno otključa selektore zaključane do otvaranja registracije.

    Lažni portal servira i datume i vaučer, pa se ceo tok može provozati sada. Na dan
    otvaranja se u ``selectors.py`` trajno menja stanje tih lokatora, pa ova fikstura
    prestaje da bude potrebna.
    """
    locked = [locator for locator in S.REGISTRY if locator.state is S.LocatorState.LOCKED]
    for locator in locked:
        locator.state = S.LocatorState.GUESS
    try:
        yield locked
    finally:
        for locator in locked:
            locator.state = S.LocatorState.LOCKED

"""Svi selektori portala na jednom mestu.

Zašto ovako:

* Kad portal izbaci update, menja se **samo ovaj fajl** — nigde drugde u kodu nema
  ni jednog CSS/XPath stringa.
* Svaki selektor ima **opis na srpskom**, pa u logu piše "Polje za JMBG gosta nije nađeno"
  umesto ``NoSuchElementException``.
* Svaki selektor ima **stanje** (potvrđen / pretpostavka / zaključan), pa
  ``run.py --proveri-selektore`` može da javi šta je još neprovereno.
* Dinamički Angular Material ID-jevi (``cdk-describedby-message-4`` iz prve ture) se
  **ne koriste** — taj broj se menja između build-ova portala i garantovano puca.

Redosled traženja: prvo ``primary``, pa redom ``fallbacks``.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum

from selenium.webdriver.common.by import By

Selector = tuple[str, str]


class LocatorState(str, Enum):
    #: Provereno na živom portalu iz ove sezone.
    CONFIRMED = "potvrđen"
    #: Radilo u prvoj turi ili je logična pretpostavka, ali nije provereno ove sezone.
    GUESS = "pretpostavka"
    #: Deo portala koji je zaključan do otvaranja registracije za vaučere.
    LOCKED = "zaključan"


# eq=False: lokatori se porede po identitetu (mogu u set), a ``state`` ostaje promenljiv
# da bi se zaključani selektor mogao otključati u testu ili privremeno pri inspekciji.
@dataclass(eq=False)
class Locator:
    name: str
    primary: Selector
    description: str
    fallbacks: tuple[Selector, ...] = ()
    state: LocatorState = LocatorState.GUESS
    #: Da li je element opcion (npr. poruka o grešci koje najčešće nema).
    optional: bool = False

    @property
    def candidates(self) -> tuple[Selector, ...]:
        return (self.primary, *self.fallbacks)

    @property
    def is_ready(self) -> bool:
        return self.state is not LocatorState.LOCKED

    def __str__(self) -> str:
        return self.description or self.name


REGISTRY: list[Locator] = []


def _loc(
    name: str,
    primary: Selector,
    description: str,
    *,
    fallbacks: tuple[Selector, ...] = (),
    state: LocatorState = LocatorState.GUESS,
    optional: bool = False,
) -> Locator:
    locator = Locator(name, primary, description, fallbacks, state, optional)
    REGISTRY.append(locator)
    return locator


# ---------------------------------------------------------------------------
# Prijava na nalog
# ---------------------------------------------------------------------------

LOGIN_USERNAME = _loc(
    "LOGIN_USERNAME",
    (By.ID, "username"),
    "Polje za korisničko ime",
    fallbacks=(
        (By.CSS_SELECTOR, 'input[formcontrolname="username"]'),
        (By.CSS_SELECTOR, 'input[name="username"]'),
        (By.CSS_SELECTOR, 'input[type="email"]'),
    ),
    state=LocatorState.GUESS,  # radilo u prvoj turi (2025)
)

LOGIN_PASSWORD = _loc(
    "LOGIN_PASSWORD",
    (By.ID, "passwordInput"),
    "Polje za lozinku",
    fallbacks=(
        (By.CSS_SELECTOR, 'input[formcontrolname="password"]'),
        (By.CSS_SELECTOR, 'input[type="password"]'),
    ),
    state=LocatorState.GUESS,  # radilo u prvoj turi (2025)
)

LOGIN_SUBMIT = _loc(
    "LOGIN_SUBMIT",
    (By.CSS_SELECTOR, 'button[type="submit"]'),
    "Dugme za prijavu",
    fallbacks=(
        (By.XPATH, "//button[contains(normalize-space(.), 'Prijav')]"),
        (By.XPATH, "//button[contains(normalize-space(.), 'Uloguj')]"),
    ),
    state=LocatorState.GUESS,  # radilo u prvoj turi (2025)
)

LOGIN_ERROR = _loc(
    "LOGIN_ERROR",
    (By.CSS_SELECTOR, ".alert-danger, .mat-error, mat-error"),
    "Poruka o neuspeloj prijavi",
    fallbacks=((By.CSS_SELECTOR, "[role='alert']"),),
    optional=True,
)

#: Element koji postoji samo kad je prijava prošla — po njemu znamo da smo ulogovani
#: i da sesija nije istekla. Tačan izbor se potvrđuje pri inspekciji portala.
LOGGED_IN_MARKER = _loc(
    "LOGGED_IN_MARKER",
    (By.CSS_SELECTOR, "[data-test='user-menu'], .user-menu, mat-toolbar"),
    "Znak da je nalog prijavljen",
    fallbacks=((By.XPATH, "//button[contains(., 'Odjav')]"),),
    state=LocatorState.LOCKED,
)


# ---------------------------------------------------------------------------
# Forma rezervacije — podaci gosta
# ---------------------------------------------------------------------------

GUEST_FIRST_NAME = _loc(
    "GUEST_FIRST_NAME",
    (By.CSS_SELECTOR, '[formcontrolname="ime"]'),
    "Polje za ime gosta",
    fallbacks=((By.CSS_SELECTOR, 'input[name="ime"]'),),
    state=LocatorState.GUESS,  # radilo u prvoj turi (2025)
)

GUEST_LAST_NAME = _loc(
    "GUEST_LAST_NAME",
    (By.CSS_SELECTOR, '[formcontrolname="prezime"]'),
    "Polje za prezime gosta",
    fallbacks=((By.CSS_SELECTOR, 'input[name="prezime"]'),),
    state=LocatorState.GUESS,  # radilo u prvoj turi (2025)
)

GUEST_JMBG = _loc(
    "GUEST_JMBG",
    (By.CSS_SELECTOR, '[formcontrolname="jmbg"]'),
    "Polje za JMBG gosta",
    fallbacks=((By.CSS_SELECTOR, 'input[name="jmbg"]'),),
    state=LocatorState.GUESS,  # radilo u prvoj turi (2025)
)

#: Angular Material prikazuje <mat-error> ispod polja kad validacija padne.
#: Prisustvo ovog elementa je jedini pouzdan znak da je portal odbio JMBG.
FIELD_ERROR = _loc(
    "FIELD_ERROR",
    (By.CSS_SELECTOR, "mat-error, .mat-error, .mat-mdc-form-field-error"),
    "Poruka o grešci ispod polja",
    optional=True,
    state=LocatorState.GUESS,  # radilo u prvoj turi (2025)
)


# ---------------------------------------------------------------------------
# Forma rezervacije — datumi  (ZAKLJUČANO do otvaranja registracije)
# ---------------------------------------------------------------------------

DATE_FROM = _loc(
    "DATE_FROM",
    (By.CSS_SELECTOR, '[formcontrolname="datumOd"]'),
    "Datum dolaska",
    fallbacks=(
        (By.CSS_SELECTOR, '[formcontrolname="datumDolaska"]'),
        (By.CSS_SELECTOR, 'input[name="datumOd"]'),
    ),
    state=LocatorState.LOCKED,
)

DATE_TO = _loc(
    "DATE_TO",
    (By.CSS_SELECTOR, '[formcontrolname="datumDo"]'),
    "Datum odlaska",
    fallbacks=(
        (By.CSS_SELECTOR, '[formcontrolname="datumOdlaska"]'),
        (By.CSS_SELECTOR, 'input[name="datumDo"]'),
    ),
    state=LocatorState.LOCKED,
)


# ---------------------------------------------------------------------------
# Navigacija kroz formu
# ---------------------------------------------------------------------------

#: Zamena za cdk-describedby-message-4 iz prve ture. Traži se po tekstu i po ikonici,
#: jer su oba stabilnija od generisanih ID-jeva.
NEXT_BUTTON = _loc(
    "NEXT_BUTTON",
    (By.XPATH, "//button[contains(normalize-space(.), 'Dalje') or contains(normalize-space(.), 'Sledeć')]"),
    "Dugme Dalje",
    fallbacks=(
        (By.XPATH, "//button[.//mat-icon[normalize-space()='navigate_next']]"),
        (By.CSS_SELECTOR, "button[aria-label*='alje']"),
    ),
)

SUBMIT_RESERVATION = _loc(
    "SUBMIT_RESERVATION",
    (By.XPATH, "//button[contains(normalize-space(.), 'Sačuvaj') or contains(normalize-space(.), 'Potvrdi')]"),
    "Dugme za čuvanje rezervacije",
    fallbacks=((By.CSS_SELECTOR, 'button[type="submit"]'),),
    state=LocatorState.LOCKED,
)

CONFIRMATION = _loc(
    "CONFIRMATION",
    # normalize-space(text()) gleda samo sopstveni tekst elementa — bez toga bi
    # <html> i <body> takođe "sadržali" reč i uvek bili prvi pogodak.
    (By.XPATH, "//*[contains(normalize-space(text()), 'uspešno')]"),
    "Potvrda da je rezervacija sačuvana",
    fallbacks=((By.CSS_SELECTOR, ".mat-snack-bar-container, simple-snack-bar"),),
    state=LocatorState.LOCKED,
)


# ---------------------------------------------------------------------------
# Vaučer  (ZAKLJUČANO do otvaranja registracije)
# ---------------------------------------------------------------------------

VOUCHER_DOWNLOAD = _loc(
    "VOUCHER_DOWNLOAD",
    (By.XPATH, "//button[contains(normalize-space(.), 'Preuzmi') or contains(normalize-space(.), 'Vaučer')]"),
    "Dugme za preuzimanje vaučera",
    fallbacks=((By.CSS_SELECTOR, "a[href$='.pdf']"),),
    state=LocatorState.LOCKED,
)


# ---------------------------------------------------------------------------

def by_state(state: LocatorState) -> list[Locator]:
    return [locator for locator in REGISTRY if locator.state is state]


def locked() -> list[Locator]:
    return by_state(LocatorState.LOCKED)


def summary() -> str:
    counts = {state: len(by_state(state)) for state in LocatorState}
    return " · ".join(f"{state.value}: {count}" for state, count in counts.items())

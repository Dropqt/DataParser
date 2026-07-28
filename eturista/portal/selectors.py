"""Svi selektori portala na jednom mestu.

Zašto ovako:

* Kad portal izbaci update, menja se **samo ovaj fajl** - nigde drugde u kodu nema
  ni jednog CSS/XPath stringa.
* Svaki selektor ima **opis na srpskom**, pa u logu piše "Polje za JMBG gosta nije nađeno"
  umesto ``NoSuchElementException``.
* Svaki selektor ima **stanje** (potvrđen / pretpostavka / zaključan), pa
  ``run.py --proveri-selektore`` može da javi šta je još neprovereno.
* Dinamički Angular Material ID-jevi (``cdk-describedby-message-4`` iz prve ture) se
  **ne koriste** - taj broj se menja između build-ova portala i garantovano puca.

Redosled traženja: prvo ``primary``, pa redom ``fallbacks``.

**Portal piše ćirilicom.** Dugme za prijavu nosi tekst ``Пријава на систем``, ne
``Prijava``. Zato se nijedan selektor ne oslanja na golo ``contains(., 'Sačuvaj')`` -
tekst se traži preko :func:`tekst_sadrzi`, koje pokriva oba pisma i ne gleda veličinu
slova (portal dosta toga prikazuje verzalom preko CSS-a, pa se u DOM-u nađe i jedno i
drugo).
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


# ---------------------------------------------------------------------------
# Traženje po tekstu - oba pisma, svejedno da li je verzal ili kurent
# ---------------------------------------------------------------------------

# XPath koji browser razume je 1.0 - nema ni ``lower-case()`` ni promenljive, pa se sve
# radi jednim ``translate()``. On u istom prolazu:
#   * spušta verzal u kurent  (SAČUVAJ → sačuvaj),
#   * i skida kvačice sa latinice  (sačuvaj → sacuvaj).
# Zato se varijante pišu bez kvačica i onda jedno „sacuvaj“ hvata i Sačuvaj i SACUVAJ.
# Ćirilica se ne preslovljava - piše se svojim slovima.
_KVAČICE = "ČĆŠŽĐ" + "čćšžđ"
_BEZ_KVAČICA = "ccszd" + "ccszd"

_OD = "АБВГДЂЕЖЗИЈКЛЉМНЊОПРСТЋУФХЦЧЏШ" + "ABCDEFGHIJKLMNOPRSTUVZ" + _KVAČICE
_NA = "абвгдђежзијклљмнњопрстћуфхцчџш" + "abcdefghijklmnoprstuvz" + _BEZ_KVAČICA

assert len(_OD) == len(_NA), "nizovi za translate() moraju biti iste dužine"


def tekst_sadrzi(*varijante: str, cvor: str = ".") -> str:
    """XPath uslov: ``cvor`` sadrži bilo koju varijantu.

    Ne gleda ni veličinu slova ni kvačice, pa se varijante pišu **malim slovima i bez
    kvačica** - ćirilicom (portal je ćirilični na javnoj strani) i latinicom (aplikacija
    iza prijave je latinična)::

        //button[{tekst_sadrzi('сачувај', 'sacuvaj')}]
    """
    for varijanta in varijante:
        if set(varijanta) & set(_KVAČICE):
            raise ValueError(
                f"varijanta {varijanta!r} ima kvačice - posle translate() ih tekst na "
                f"stranici više nema, pa se ovo nikad ne bi poklopilo. Piši 'sacuvaj'."
            )
    haystack = f"translate(normalize-space({cvor}), '{_OD}', '{_NA}')"
    return " or ".join(f"contains({haystack}, '{varijanta.lower()}')" for varijanta in varijante)


def dugme_sa_tekstom(*varijante: str) -> Selector:
    """Dugme (ili link koji izgleda kao dugme) sa datim tekstom, u oba pisma."""
    uslov = tekst_sadrzi(*varijante)
    return (By.XPATH, f"//button[{uslov}] | //a[contains(@class, 'btn') and ({uslov})]")


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
    # Kontrola se u Angular formi zove ``email``, iako je ID ``username`` - polje nema
    # ni ``name`` ni ``type``, pa ``input[type=email]`` ovde ne hvata ništa.
    fallbacks=(
        (By.CSS_SELECTOR, 'input[formcontrolname="email"]'),
        (By.CSS_SELECTOR, "form input.input-text:not([type=password])"),
    ),
    state=LocatorState.CONFIRMED,  # portal, 27.07.2026
)

LOGIN_PASSWORD = _loc(
    "LOGIN_PASSWORD",
    (By.ID, "passwordInput"),
    "Polje za lozinku",
    fallbacks=(
        (By.CSS_SELECTOR, 'input[formcontrolname="lozinka"]'),
        (By.CSS_SELECTOR, 'input[type="password"]'),
    ),
    state=LocatorState.CONFIRMED,  # portal, 27.07.2026
)

LOGIN_SUBMIT = _loc(
    "LOGIN_SUBMIT",
    (By.CSS_SELECTOR, 'button[type="submit"]'),
    "Dugme za prijavu",
    fallbacks=(
        (By.CSS_SELECTOR, "button.red-btn"),
        dugme_sa_tekstom("пријава", "prijava", "улогуј", "uloguj"),
    ),
    state=LocatorState.CONFIRMED,  # portal, 27.07.2026 - tekst je „Пријава на систем“
)

LOGIN_ERROR = _loc(
    "LOGIN_ERROR",
    (By.CSS_SELECTOR, ".alert-danger, .mat-error, mat-error"),
    "Poruka o neuspeloj prijavi",
    fallbacks=((By.CSS_SELECTOR, "[role='alert']"),),
    optional=True,
)

#: Element koji postoji samo kad je prijava prošla - po njemu znamo da smo ulogovani
#: i da sesija nije istekla. Tačan izbor se potvrđuje pri inspekciji portala.
LOGGED_IN_MARKER = _loc(
    "LOGGED_IN_MARKER",
    # Zaglavlje sa korisničkim nalogom postoji samo unutar aplikacije; javna strana sa
    # formom za prijavu nema ``mat-toolbar`` uopšte, pa je ovo čist signal.
    (By.CSS_SELECTOR, ".accountAndSettings"),
    "Znak da je nalog prijavljen",
    fallbacks=(
        (By.CSS_SELECTOR, "mat-toolbar.mat-primary .features-item"),
        (By.CSS_SELECTOR, "mat-toolbar.mat-primary"),
    ),
    # „Odjava“ je sakrivena u meniju iza ikonice, pa se ne može tražiti po tekstu.
    state=LocatorState.CONFIRMED,  # portal, 27.07.2026
)


# ---------------------------------------------------------------------------
# Forma rezervacije - podaci gosta
# ---------------------------------------------------------------------------

GUEST_FIRST_NAME = _loc(
    "GUEST_FIRST_NAME",
    (By.CSS_SELECTOR, '[formcontrolname="ime"]'),
    "Polje za ime gosta",
    fallbacks=((By.CSS_SELECTOR, 'input[name="ime"]'),),
    state=LocatorState.CONFIRMED,  # portal, 27.07.2026
)

GUEST_LAST_NAME = _loc(
    "GUEST_LAST_NAME",
    (By.CSS_SELECTOR, '[formcontrolname="prezime"]'),
    "Polje za prezime gosta",
    fallbacks=((By.CSS_SELECTOR, 'input[name="prezime"]'),),
    state=LocatorState.CONFIRMED,  # portal, 27.07.2026
)

GUEST_JMBG = _loc(
    "GUEST_JMBG",
    (By.CSS_SELECTOR, '[formcontrolname="jmbg"]'),
    "Polje za JMBG gosta",
    fallbacks=((By.CSS_SELECTOR, 'input[name="jmbg"]'),),
    state=LocatorState.CONFIRMED,  # portal, 27.07.2026
)

#: Angular Material prikazuje <mat-error> ispod polja kad validacija padne
#: (viđena poruka: „Obavezan podatak“). Prisustvo ovog elementa je jedini pouzdan
#: znak da je portal odbio JMBG.
#:
#: Traži se samo <mat-error> **sa tekstom**: portal drži i prazne mat-error čvorove za
#: polja koja trenutno nemaju grešku, pa bi golo ``mat-error`` znalo da vrati prazan
#: string i da ispadne da greške nema.
FIELD_ERROR = _loc(
    "FIELD_ERROR",
    (By.XPATH, "//mat-error[normalize-space(.) != '']"),
    "Poruka o grešci ispod polja",
    fallbacks=((By.CSS_SELECTOR, "mat-error, .mat-error"),),
    optional=True,
    state=LocatorState.CONFIRMED,  # portal, 27.07.2026
)


# ---------------------------------------------------------------------------
# Forma rezervacije - izbor prijave ugostitelja (2. korak)
# ---------------------------------------------------------------------------
#
# Drugi korak je tabela objekata koje ugostitelj ima prijavljene za šemu vaučera, sa
# čekboksom po redu. Bez čekiranog reda se ne ide na treći korak.
#
# **Ovde je brava.** Dok registracija nije otvorena, čekboks je onemogućen i portal na
# prelazak mišem javi „Rezervacija smeštaja je zaključana.“ - to je ono što se otključava
# na dan otvaranja.

#: Čekira se **sam ``mat-checkbox``**, ne ``input`` u njemu: pravi ``<input>`` nosi klasu
#: ``cdk-visually-hidden``, pa ga Selenium ne može kliknuti (probano - klik prođe bez
#: efekta, čekboks ostane prazan).
SCHEME_ROW = _loc(
    "SCHEME_ROW",
    (By.CSS_SELECTOR, "mat-checkbox.cbIzaberi .mat-checkbox-inner-container"),
    "Čekboks za izbor prijave ugostitelja",
    fallbacks=(
        (By.CSS_SELECTOR, "mat-checkbox.cbIzaberi"),
        (By.CSS_SELECTOR, "table.mat-table tbody tr mat-checkbox"),
    ),
    state=LocatorState.CONFIRMED,  # portal, 27.07.2026
)

#: Postoji samo dok je rezervacija zaključana - po njemu se prepoznaje da nema svrhe
#: pokretati turu, umesto da tura zapne na koraku koji se ne otvara.
SCHEME_ROW_LOCKED = _loc(
    "SCHEME_ROW_LOCKED",
    (By.CSS_SELECTOR, "mat-checkbox.cbIzaberi.mat-checkbox-disabled"),
    "Zaključan izbor prijave (registracija nije otvorena)",
    fallbacks=((By.CSS_SELECTOR, "mat-checkbox.cbIzaberi input[disabled]"),),
    optional=True,
    state=LocatorState.CONFIRMED,  # portal, 27.07.2026 - zaključano
)


# ---------------------------------------------------------------------------
# Forma rezervacije - datumi (3. korak)
# ---------------------------------------------------------------------------
#
# Nisu dva odvojena polja nego jedan ``mat-date-range-input`` sa dva ugnežđena input-a
# i zajedničkim kalendarom. Oba primaju kucanje (nisu ``readonly``), pa se popunjavaju
# obično preko ``send_keys`` - kalendar ne mora da se otvara.
#
# Format koji portal sam upiše kad se datum izabere iz kalendara je ``15.7.2026``,
# **bez vodeće nule**. Vidi ``reservation_page.format_date``.

DATE_FROM = _loc(
    "DATE_FROM",
    (By.CSS_SELECTOR, 'input[formcontrolname="datumSmestajaOd"]'),
    "Datum dolaska",
    fallbacks=(
        (By.CSS_SELECTOR, "mat-date-range-input input:first-of-type"),
        (By.CSS_SELECTOR, 'input[placeholder="Datum od"]'),
    ),
    state=LocatorState.CONFIRMED,  # portal, 27.07.2026
)

DATE_TO = _loc(
    "DATE_TO",
    (By.CSS_SELECTOR, 'input[formcontrolname="datumSmestajaDo"]'),
    "Datum odlaska",
    fallbacks=(
        (By.CSS_SELECTOR, "mat-date-range-input input:last-of-type"),
        (By.CSS_SELECTOR, 'input[placeholder="Datum do"]'),
    ),
    state=LocatorState.CONFIRMED,  # portal, 27.07.2026
)


# ---------------------------------------------------------------------------
# Navigacija kroz formu
# ---------------------------------------------------------------------------

#: Zamena za cdk-describedby-message-4 iz prve ture.
#:
#: Forma je ``mat-horizontal-stepper`` sa 3 koraka, a dugme za sledeći korak je okrugli
#: ``mat-mini-fab`` sa **samo ikonicom** - nema nikakav tekst, pa traženje po reči
#: „Dalje“ ovde ne bi našlo ništa. Klasa ``mat-stepper-next`` dolazi od direktive
#: ``matStepperNext`` i ne zavisi od prevoda.
NEXT_BUTTON = _loc(
    "NEXT_BUTTON",
    (By.CSS_SELECTOR, "button.mat-stepper-next"),
    "Dugme za sledeći korak",
    fallbacks=(
        (By.XPATH, "//button[.//mat-icon[normalize-space()='navigate_next']]"),
        dugme_sa_tekstom("даље", "dalje", "следећ", "sledec"),
    ),
    state=LocatorState.CONFIRMED,  # portal, 27.07.2026
)

#: Stoji ispod stepper-a, van koraka - vidi se iz svakog koraka. Nema ``type="submit"``,
#: pa se traži po tekstu („Sačuvaj“).
SUBMIT_RESERVATION = _loc(
    "SUBMIT_RESERVATION",
    dugme_sa_tekstom("сачувај", "sacuvaj", "потврди", "potvrdi"),
    "Dugme za čuvanje rezervacije",
    fallbacks=((By.CSS_SELECTOR, 'button[type="submit"]'),),
    # Element je nađen na živom portalu; da li klik zaista sačuva rezervaciju proverava
    # se tek probnom turom (faza 6) - dotad ovo znači samo „dugme postoji i nađe se“.
    state=LocatorState.CONFIRMED,  # portal, 27.07.2026
)

#: Jedino što se nije moglo videti bez stvarnog čuvanja rezervacije - ostaje zaključano
#: do probne ture (faza 6).
#:
#: Kad se do toga dođe, postoji i drugi, pouzdaniji znak: dugme „Odštampaj rezervaciju“
#: je onemogućeno sve dok rezervacija ne bude sačuvana, pa je njegovo aktiviranje samo
#: po sebi potvrda. Vidi ``VOUCHER_DOWNLOAD``.
CONFIRMATION = _loc(
    "CONFIRMATION",
    # cvor="text()" gleda samo sopstveni tekst elementa - bez toga bi <html> i <body>
    # takođe "sadržali" reč i uvek bili prvi pogodak.
    (By.XPATH, f"//*[{tekst_sadrzi('успешно', 'uspesno', cvor='text()')}]"),
    "Potvrda da je rezervacija sačuvana",
    fallbacks=((By.CSS_SELECTOR, ".mat-snack-bar-container, simple-snack-bar"),),
    state=LocatorState.LOCKED,
)


# ---------------------------------------------------------------------------
# Vaučer
# ---------------------------------------------------------------------------

#: Na portalu piše **„Odštampaj rezervaciju“** (ikonica ``cloud_download``), ne „Preuzmi“.
#: Dugme stoji pored „Sačuvaj“ i **onemogućeno je dok se rezervacija ne sačuva** - zato
#: se posle čuvanja čeka da postane aktivno, vidi ``voucher_page``.
VOUCHER_DOWNLOAD = _loc(
    "VOUCHER_DOWNLOAD",
    dugme_sa_tekstom("одштампај", "odstampaj", "штампај", "stampaj"),
    "Dugme za preuzimanje vaučera",
    fallbacks=(
        (By.XPATH, "//button[.//mat-icon[normalize-space()='cloud_download']]"),
        dugme_sa_tekstom("преузми", "preuzmi", "ваучер", "vaucer"),
        (By.CSS_SELECTOR, "a[href$='.pdf']"),
    ),
    state=LocatorState.CONFIRMED,  # portal, 27.07.2026
)


# ---------------------------------------------------------------------------

def by_state(state: LocatorState) -> list[Locator]:
    return [locator for locator in REGISTRY if locator.state is state]


def locked() -> list[Locator]:
    return by_state(LocatorState.LOCKED)


def summary() -> str:
    counts = {state: len(by_state(state)) for state in LocatorState}
    return " · ".join(f"{state.value}: {count}" for state, count in counts.items())

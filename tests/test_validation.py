from datetime import date

import pytest

from eturista.errors import ErrorKind, ValidationError
from eturista.validation import (
    clean_jmbg,
    jmbg_check_digit,
    latinize,
    parse_stay,
    validate_jmbg,
    validate_name,
)


def make_jmbg(first_twelve: str) -> str:
    """Napravi ispravan JMBG dodavanjem tačne kontrolne cifre."""
    return first_twelve + str(jmbg_check_digit(first_twelve))


# --- JMBG -------------------------------------------------------------------

@pytest.mark.parametrize(
    "first_twelve, birth, gender",
    [
        ("010199071012", date(1990, 1, 1), "M"),
        ("150398871001", date(1988, 3, 15), "M"),
        ("290200471005", date(2004, 2, 29), "M"),   # prestupna godina
        ("311297985000", date(1979, 12, 31), "M"),
        ("010101750500", date(2017, 1, 1), "Ž"),    # 500+ = žensko
    ],
)
def test_valid_jmbg_is_parsed(first_twelve, birth, gender):
    info = validate_jmbg(make_jmbg(first_twelve))
    assert info.birth_date == birth
    assert info.gender_label == gender


def test_check_digit_is_stable():
    for first_twelve in ("010199071012", "150398871001", "010101750500"):
        full = make_jmbg(first_twelve)
        assert jmbg_check_digit(full[:12]) == int(full[12])


def test_wrong_check_digit_is_rejected():
    good = make_jmbg("010199071012")
    bad = good[:12] + str((int(good[12]) + 1) % 10)
    with pytest.raises(ValidationError) as exc:
        validate_jmbg(bad)
    assert exc.value.kind is ErrorKind.JMBG_INVALID_LOCAL
    assert "kontrolna cifra" in exc.value.message


def test_wrong_length_is_rejected():
    with pytest.raises(ValidationError, match="cifara"):
        validate_jmbg("01019907101")


def test_impossible_birth_date_is_rejected():
    # 29.02.2007 — 2007 nije prestupna
    with pytest.raises(ValidationError, match="nepostojeći datum"):
        validate_jmbg(make_jmbg("290200771000"))


def test_empty_jmbg_reports_missing_field():
    with pytest.raises(ValidationError) as exc:
        validate_jmbg("   ")
    assert exc.value.kind is ErrorKind.MISSING_FIELD


def test_excel_eats_leading_zero():
    """Gost rođen 1-9. u mesecu stigne iz Excela sa 12 cifara."""
    full = make_jmbg("010199071012")
    cleaned, note = clean_jmbg(full[1:])
    assert cleaned == full
    assert "vodeća nula" in note


def test_scientific_notation_is_rejected_with_useful_message():
    with pytest.raises(ValidationError, match="Tekst"):
        clean_jmbg("1,01991E+12")


def test_separators_inside_jmbg_are_stripped():
    full = make_jmbg("010199071012")
    spaced = f"{full[:7]} {full[7:9]}-{full[9:]}"
    assert clean_jmbg(spaced)[0] == full


# --- datumi -----------------------------------------------------------------

@pytest.mark.parametrize(
    "raw, arrival, departure",
    [
        ("05.10-10.10", date(2026, 10, 5), date(2026, 10, 10)),
        ("5.10.2026 - 10.10.2026", date(2026, 10, 5), date(2026, 10, 10)),
        ("05.10.-10.10.", date(2026, 10, 5), date(2026, 10, 10)),
        ("05/10 do 10/10", date(2026, 10, 5), date(2026, 10, 10)),
        ("05-10-2026 - 10-10-2026", date(2026, 10, 5), date(2026, 10, 10)),
        ("05-10-10-10", date(2026, 10, 5), date(2026, 10, 10)),
        ("1.7-15.7", date(2026, 7, 1), date(2026, 7, 15)),
        ("05.10.26-10.10.26", date(2026, 10, 5), date(2026, 10, 10)),
    ],
)
def test_stay_formats(raw, arrival, departure):
    stay = parse_stay(raw, 2026)
    assert (stay.arrival, stay.departure) == (arrival, departure)


def test_stay_across_new_year():
    stay = parse_stay("28.12-03.01", 2026)
    assert stay.arrival == date(2026, 12, 28)
    assert stay.departure == date(2027, 1, 3)
    assert stay.nights == 6


def test_reversed_dates_report_reversal_not_absurd_length():
    with pytest.raises(ValidationError) as exc:
        parse_stay("10.10-05.10", 2026)
    assert "pre datuma dolaska" in exc.value.message


def test_same_day_is_rejected():
    with pytest.raises(ValidationError, match="posle dolaska"):
        parse_stay("05.10-05.10", 2026)


def test_garbage_date_is_rejected():
    with pytest.raises(ValidationError) as exc:
        parse_stay("bezveze", 2026)
    assert exc.value.kind is ErrorKind.DATE_INVALID


def test_empty_date_reports_missing_field():
    with pytest.raises(ValidationError) as exc:
        parse_stay("", 2026)
    assert exc.value.kind is ErrorKind.MISSING_FIELD


def test_stay_format_is_unambiguous():
    assert parse_stay("05.10-10.10", 2026).format() == "05.10.2026-10.10.2026"


# --- imena ------------------------------------------------------------------

def test_name_with_digits_is_rejected():
    with pytest.raises(ValidationError, match="cifre"):
        validate_name("Marko2", "Ime")


def test_name_whitespace_is_normalized():
    assert validate_name("  Ana   Marija ", "Ime") == "Ana Marija"


@pytest.mark.parametrize(
    "text, expected",
    [
        ("Đorđević", "djordjevic"),
        ("Šešelj", "seselj"),
        ("Ćirić", "ciric"),
        ("Petrović", "petrovic"),
        ("Петровић", "petrovic"),
        ("Ana Marija", "ana_marija"),
    ],
)
def test_latinize(text, expected):
    assert latinize(text) == expected


# --- dolazak + broj dana ----------------------------------------------------

from eturista.validation import (  # noqa: E402
    DEFAULT_DAYS,
    parse_arrival,
    parse_days,
    resolve_stay,
    stay_from_days,
)


def test_default_days_is_five():
    assert DEFAULT_DAYS == 5


@pytest.mark.parametrize(
    "raw, expected",
    [("05.10", date(2026, 10, 5)), ("5.10.2026", date(2026, 10, 5)),
     ("05/10", date(2026, 10, 5)), ("05.10.", date(2026, 10, 5)),
     ("05.10.26", date(2026, 10, 5))],
)
def test_parse_arrival_formats(raw, expected):
    assert parse_arrival(raw, 2026) == expected


@pytest.mark.parametrize("raw, expected", [("5", 5), ("7", 7), ("", 5), ("  10 ", 10),
                                           ("5 dana", 5), ("7 noćenja", 7)])
def test_parse_days_formats(raw, expected):
    assert parse_days(raw) == expected


@pytest.mark.parametrize("raw", ["0", "-3", "500", "abc"])
def test_parse_days_rejects_nonsense(raw):
    with pytest.raises(ValidationError):
        parse_days(raw)


def test_five_days_means_five_nights():
    """05.10 + 5 dana = 10.10 — isto kao stari zapis 05.10-10.10."""
    stay = stay_from_days(date(2026, 10, 5), 5)
    assert stay.departure == date(2026, 10, 10)
    assert stay.nights == 5
    assert stay.format() == parse_stay("05.10-10.10", 2026).format()


def test_resolve_stay_uses_days_column():
    stay = resolve_stay("05.10", "7", 2026)
    assert (stay.arrival, stay.departure) == (date(2026, 10, 5), date(2026, 10, 12))


def test_resolve_stay_defaults_when_days_missing():
    assert resolve_stay("05.10", "", 2026).nights == DEFAULT_DAYS


def test_resolve_stay_crosses_new_year():
    stay = resolve_stay("28.12", "7", 2026)
    assert stay.departure == date(2027, 1, 4)


def test_resolve_stay_accepts_old_range_and_ignores_days():
    """Stare liste imaju opseg u koloni sa datumom; kolona Dana se tad ne gleda."""
    stay = resolve_stay("05.10-10.10", "99", 2026)
    assert (stay.arrival, stay.departure) == (date(2026, 10, 5), date(2026, 10, 10))


def test_resolve_stay_requires_arrival():
    with pytest.raises(ValidationError) as exc:
        resolve_stay("", "5", 2026)
    assert exc.value.kind is ErrorKind.MISSING_FIELD


def test_resolve_stay_rejects_unreadable_arrival():
    with pytest.raises(ValidationError, match="datum dolaska"):
        resolve_stay("bezveze", "5", 2026)


def test_all_field_problems_are_reported_at_once():
    """Stajanje na prvoj grešci bi značilo popravi-pa-otkrij-sledeću."""
    from eturista.models import Guest

    guest = Guest(row=1, surname_raw="Marković", given_name_raw="Stefan",
                  jmbg_raw="0703007100339", arrival_raw="bezveze", days_raw="5")
    assert not guest.validate(2026)
    assert "kontrolna cifra" in guest.error.text
    assert "datum dolaska" in guest.error.text


def test_valid_fields_are_kept_even_when_another_fails():
    """Pokvaren JMBG ne sme da sakrije ispravno izračunat boravak."""
    from eturista.models import Guest

    guest = Guest(row=1, surname_raw="Marković", given_name_raw="Stefan",
                  jmbg_raw="0703007100339", arrival_raw="07.10", days_raw="7")
    assert not guest.validate(2026)
    assert guest.jmbg_info is None
    assert guest.stay is not None
    assert guest.stay_display == "07.10.2026-14.10.2026"

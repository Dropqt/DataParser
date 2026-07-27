"""Primer Excela mora da se slaže sa proverom u aplikaciji.

Ako se pravila validacije promene a primer ostane isti, korisnik bi u Excelu video zeleno
za nešto što aplikacija odbija (ili obrnuto). Ovaj test to sprečava.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from alati.napravi_primer_excel import SAMPLE, broken_jmbg, jmbg  # noqa: E402

from eturista.errors import ErrorKind, ValidationError  # noqa: E402
from eturista.validation import validate_jmbg  # noqa: E402


def test_broken_jmbg_really_is_broken():
    """Fiksna 'pokvarena' cifra bi za neke brojeve slučajno bila tačna."""
    for first_twelve in ("070300771003", "010199071012", "150398871001"):
        assert broken_jmbg(first_twelve) != jmbg(first_twelve)
        with pytest.raises(ValidationError, match="kontrolna cifra"):
            validate_jmbg(broken_jmbg(first_twelve))


@pytest.mark.parametrize("row", SAMPLE[:5])
def test_first_five_samples_are_valid(row):
    given_name, _, id_number, _, _ = row
    info = validate_jmbg(id_number)
    expected_female = given_name in {"Ana", "Milica", "Jelena"}
    assert info.is_female is expected_female, (
        f"{given_name}: pol iz JMBG-a ({info.gender_label}) ne odgovara imenu"
    )
    assert 1920 <= info.birth_date.year <= 2020


def test_sixth_sample_demonstrates_wrong_check_digit():
    _, _, id_number, _, _ = SAMPLE[5]
    with pytest.raises(ValidationError) as exc:
        validate_jmbg(id_number)
    assert exc.value.kind is ErrorKind.JMBG_INVALID_LOCAL
    assert "kontrolna cifra" in exc.value.message


def test_samples_are_ime_then_prezime():
    """Redosled u primeru mora da prati EXPORT_HEADERS, inače se lepljenje ne poklapa."""
    from eturista.models import EXPORT_HEADERS

    assert EXPORT_HEADERS[:5] == ("Ime", "Prezime", "JMBG", "Dolazak", "Dana")
    given_names = {row[0] for row in SAMPLE}
    assert given_names == {"Marko", "Ana", "Jovan", "Nikola", "Milica", "Stefan", "Jelena"}


def test_excel_default_days_matches_the_app():
    """Ako se podrazumevani broj noćenja promeni na jednom mestu, ovo puca."""
    from alati.napravi_primer_excel import DEFAULT_DAYS as EXCEL_DEFAULT

    from eturista.validation import DEFAULT_DAYS as APP_DEFAULT

    assert EXCEL_DEFAULT == APP_DEFAULT


def test_sample_arrivals_are_single_dates_not_ranges():
    """Šablon više ne koristi opseg 'od-do' nego datum dolaska + broj dana."""
    from eturista.validation import parse_arrival

    for _, _, _, arrival, _ in SAMPLE:
        assert "-" not in arrival
        parse_arrival(arrival, 2026)


def test_seventh_sample_demonstrates_excel_eating_leading_zero():
    _, _, id_number, _, _ = SAMPLE[6]
    assert len(id_number) == 12
    # Aplikacija ovo ćutke popravi; Excel samo javi da nema 13 cifara.
    info = validate_jmbg(id_number)
    assert len(info.jmbg) == 13
    assert "vodeća nula" in info.note


def test_generated_file_exists_and_opens():
    openpyxl = pytest.importorskip("openpyxl")
    path = Path(__file__).resolve().parent.parent / "primer" / "primer_gosti.xlsx"
    if not path.exists():
        pytest.skip("primer još nije generisan — pokreni alati/napravi_primer_excel.py")

    book = openpyxl.load_workbook(path)
    assert book.sheetnames == ["Gosti", "Uputstvo"]

    from eturista.models import EXPORT_HEADERS

    sheet = book["Gosti"]
    headers = [sheet.cell(row=1, column=i).value for i in range(1, len(EXPORT_HEADERS) + 1)]
    # Prve kolone moraju da odgovaraju izlazu iz aplikacije, da se lepljenje poklopi.
    assert tuple(headers) == EXPORT_HEADERS

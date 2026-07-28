"""Primer Excela mora da se slaže sa proverom u aplikaciji.

Ako se pravila validacije promene a primer ostane isti, korisnik bi u Excelu video zeleno
za nešto što aplikacija odbija (ili obrnuto). Ovaj test to sprečava.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from alati.napravi_primer_excel import (  # noqa: E402
    NALOZI,
    PRIMERI_SHEET,
    SAMPLE,
    broken_jmbg,
    jmbg,
)

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
        pytest.skip("primer još nije generisan - pokreni alati/napravi_primer_excel.py")

    book = openpyxl.load_workbook(path)
    assert book.sheetnames == [*NALOZI, PRIMERI_SHEET, "Uputstvo"]

    from eturista.models import EXPORT_HEADERS

    # Svaki radni list mora da ima isto zaglavlje kao izlaz iz aplikacije, da bi se
    # rezultat ture zalepio nazad bez pomeranja kolona - svejedno na kom je listu.
    for naziv in [*NALOZI, PRIMERI_SHEET]:
        sheet = book[naziv]
        headers = [sheet.cell(row=1, column=i).value for i in range(1, len(EXPORT_HEADERS) + 1)]
        assert tuple(headers) == EXPORT_HEADERS, f"list {naziv}"


def test_jmbg_column_is_text_for_the_whole_column():
    """Format mora da stoji na koloni, ne samo na redovima koji imaju formule.

    Ako stoji samo na ćelijama, prvi gost ispod poslednjeg formuliranog reda upada u
    ćeliju bez formata i Excel mu odmah pojede vodeću nulu.
    """
    openpyxl = pytest.importorskip("openpyxl")
    path = Path(__file__).resolve().parent.parent / "primer" / "primer_gosti.xlsx"
    if not path.exists():
        pytest.skip("primer još nije generisan - pokreni alati/napravi_primer_excel.py")

    from alati.napravi_primer_excel import col

    book = openpyxl.load_workbook(path)
    jmbg_col = col("JMBG")
    for naziv in [*NALOZI, PRIMERI_SHEET]:
        assert book[naziv].column_dimensions[jmbg_col].number_format == "@", f"list {naziv}"


def test_numeric_jmbg_cell_is_coloured():
    """Ćelija u koju je lepljenje uvalilo broj mora da se vidi u samoj JMBG koloni.

    Poruka u koloni PROVERA to već kaže, ali u nju se ne gleda dok se ne posumnja -
    a žuta ćelija usred kolone se primeti odmah.
    """
    openpyxl = pytest.importorskip("openpyxl")
    path = Path(__file__).resolve().parent.parent / "primer" / "primer_gosti.xlsx"
    if not path.exists():
        pytest.skip("primer još nije generisan - pokreni alati/napravi_primer_excel.py")

    from alati.napravi_primer_excel import col

    book = openpyxl.load_workbook(path)
    jmbg_col = col("JMBG")
    for naziv in [*NALOZI, PRIMERI_SHEET]:
        pravila = [
            rule
            for opseg in book[naziv].conditional_formatting
            if str(opseg.sqref).startswith(f"{jmbg_col}2:")
            for rule in opseg.rules
            for formula in rule.formula or []
            if "ISNUMBER" in formula
        ]
        assert pravila, f"list {naziv}: nema bojenja za JMBG upisan kao broj"
        # Bez stopIfTrue bi zeleno bojenje reda po statusu prekrilo upozorenje.
        assert pravila[0].stopIfTrue, f"list {naziv}: pravilo se prekriva bojenjem reda"


def test_formulas_never_point_at_a_single_cell():
    """Sve reference idu preko INDEX($X:$X;ROW()) - videti ``napravi_primer_excel.ref``.

    Obična referenca (``C2``) preživi kopiranje, ali ne i isecanje: kad se gost prebaci
    na list drugog naloga sa Ctrl+X, provera na starom listu počne da čita novi list, a
    čim se ti redovi obrišu, pukne u ``#REF!``. Zato u formulama ne sme da ostane nijedna
    adresa ćelije.
    """
    import re

    openpyxl = pytest.importorskip("openpyxl")
    path = Path(__file__).resolve().parent.parent / "primer" / "primer_gosti.xlsx"
    if not path.exists():
        pytest.skip("primer još nije generisan - pokreni alati/napravi_primer_excel.py")

    adresa = re.compile(r"\$?[A-Z]{1,2}\$?\d+")
    book = openpyxl.load_workbook(path)
    for naziv in [*NALOZI, PRIMERI_SHEET]:
        sheet = book[naziv]
        for row in sheet.iter_rows(min_row=2, max_row=6):
            for cell in row:
                if isinstance(cell.value, str) and cell.value.startswith("="):
                    assert not adresa.search(cell.value), f"{naziv}!{cell.coordinate}"
        # I bojenje: pravilo vezano za $J2 se pri seljenju pokvari isto kao formula,
        # samo što se to ne vidi - red prosto prestane da se boji.
        for opseg in sheet.conditional_formatting:
            for rule in opseg.rules:
                for formula in rule.formula or []:
                    assert not adresa.search(formula), f"{naziv}: {formula}"


def test_work_sheets_are_empty_and_examples_are_separate():
    """Listovi naloga se popunjavaju pravim gostima, pa ne smeju da nose primere."""
    openpyxl = pytest.importorskip("openpyxl")
    path = Path(__file__).resolve().parent.parent / "primer" / "primer_gosti.xlsx"
    if not path.exists():
        pytest.skip("primer još nije generisan - pokreni alati/napravi_primer_excel.py")

    book = openpyxl.load_workbook(path)
    for naziv in NALOZI:
        assert book[naziv]["A2"].value is None, f"list {naziv} nije prazan"
    assert book[PRIMERI_SHEET]["A2"].value == "Marko"

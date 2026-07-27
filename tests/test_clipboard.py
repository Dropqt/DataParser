from eturista.clipboard import parse_clipboard, split_rows, to_clipboard
from eturista.models import Status
from eturista.validation import jmbg_check_digit

YEAR = 2026


def jmbg(first_twelve: str) -> str:
    return first_twelve + str(jmbg_check_digit(first_twelve))


A = jmbg("010199071012")   # Petrović Marko
B = jmbg("150398871001")   # Ilić Jovan
C = jmbg("010101750500")   # Anić Ana


def test_split_rows_handles_crlf_and_quotes():
    rows = split_rows('a\tb\r\n"c"\t"d""e"\r\n\r\n')
    assert rows == [["a", "b"], ["c", 'd"e']]


def test_paste_with_header():
    text = (
        "Prezime\tIme\tJMBG\tDatum\n"
        f"Petrović\tMarko\t{A}\t05.10-10.10\n"
        f"Ilić\tJovan\t{B}\t06.10-12.10\n"
    )
    result = parse_clipboard(text, YEAR)
    assert result.mapping.from_header
    assert len(result.guests) == 2
    assert result.guests[0].surname == "Petrović"
    assert result.guests[0].given_name == "Marko"
    assert result.guests[0].stay.nights == 5
    assert all(g.status is Status.PENDING for g in result.guests)


def test_paste_with_shuffled_header_columns():
    text = (
        "JMBG\tDatum\tIme\tPrezime\n"
        f"{A}\t05.10-10.10\tMarko\tPetrović\n"
    )
    result = parse_clipboard(text, YEAR)
    guest = result.guests[0]
    assert (guest.surname, guest.given_name) == ("Petrović", "Marko")
    assert guest.jmbg == A


def test_paste_without_header_detects_by_content():
    """Bez zaglavlja se podrazumeva ime pa prezime — kao u primer_gosti.xlsx."""
    text = f"Marko\tPetrović\t{A}\t05.10-10.10\nJovan\tIlić\t{B}\t06.10-12.10\n"
    result = parse_clipboard(text, YEAR)
    assert not result.mapping.from_header
    assert result.mapping.jmbg == 2
    assert result.mapping.date == 3
    assert (result.guests[1].given_name, result.guests[1].surname) == ("Jovan", "Ilić")


def test_all_caps_first_column_is_treated_as_surname():
    """Stara lista je pisala prezime verzalom i stavljala ga prvo: 'PREZIME Ime'."""
    text = f"PETROVIĆ\tMarko\t{A}\t05.10-10.10\nILIĆ\tJovan\t{B}\t06.10-12.10\n"
    result = parse_clipboard(text, YEAR)
    assert result.guests[0].surname == "PETROVIĆ"
    assert result.guests[0].given_name == "Marko"


def test_all_caps_second_column_keeps_default_order():
    text = f"Marko\tPETROVIĆ\t{A}\t05.10-10.10\nJovan\tILIĆ\t{B}\t06.10-12.10\n"
    result = parse_clipboard(text, YEAR)
    assert result.guests[0].given_name == "Marko"
    assert result.guests[0].surname == "PETROVIĆ"


def test_single_name_column_is_split():
    text = f"Ime i prezime\tJMBG\tDatum\nMarko Petrović\t{A}\t05.10-10.10\n"
    result = parse_clipboard(text, YEAR)
    guest = result.guests[0]
    assert (guest.given_name, guest.surname) == ("Marko", "Petrović")
    assert any("istoj koloni" in w for w in result.warnings)


def test_single_name_column_with_caps_surname_first():
    text = f"Gost\tJMBG\tDatum\nPETROVIĆ Marko\t{A}\t05.10-10.10\n"
    result = parse_clipboard(text, YEAR)
    guest = result.guests[0]
    assert (guest.given_name, guest.surname) == ("Marko", "PETROVIĆ")


def test_invalid_jmbg_row_is_kept_but_marked():
    bad = A[:12] + str((int(A[12]) + 1) % 10)
    text = f"Prezime\tIme\tJMBG\tDatum\nPetrović\tMarko\t{bad}\t05.10-10.10\n"
    result = parse_clipboard(text, YEAR)
    guest = result.guests[0]
    assert guest.status is Status.ERROR
    assert "kontrolna cifra" in guest.error.text
    assert not guest.is_ready


def test_excel_dropped_leading_zero_is_repaired_on_paste():
    text = f"Prezime\tIme\tJMBG\tDatum\nPetrović\tMarko\t{A[1:]}\t05.10-10.10\n"
    result = parse_clipboard(text, YEAR)
    guest = result.guests[0]
    assert guest.status is Status.PENDING
    assert guest.jmbg == A
    assert "vodeća nula" in guest.note


def test_blank_rows_are_skipped():
    text = f"Petrović\tMarko\t{A}\t05.10-10.10\n\t\t\t\nIlić\tJovan\t{B}\t06.10-12.10\n"
    result = parse_clipboard(text, YEAR)
    assert len(result.guests) == 2
    assert result.skipped_rows == 1


def test_row_numbers_are_sequential():
    text = f"Petrović\tMarko\t{A}\t05.10-10.10\nIlić\tJovan\t{B}\t06.10-12.10\nAnić\tAna\t{C}\t07.10-13.10\n"
    result = parse_clipboard(text, YEAR)
    assert [g.row for g in result.guests] == [1, 2, 3]


def test_unrecognizable_paste_warns_instead_of_crashing():
    result = parse_clipboard("nesto\tsasvim\tdrugo\n", YEAR)
    assert not result.ok or not result.mapping.is_usable
    assert result.warnings


def test_export_round_trip_has_status_columns():
    text = f"Prezime\tIme\tJMBG\tDatum\nPetrović\tMarko\t{A}\t05.10-10.10\n"
    guests = parse_clipboard(text, YEAR).guests
    guests[0].mark_ok("2026_PETROVIC_MARKO.pdf")

    out = to_clipboard(guests)
    header, row = out.split("\n")
    assert header.split("\t") == ["Ime", "Prezime", "JMBG", "Datum", "STATUS", "RAZLOG", "PDF"]
    cells = row.split("\t")
    assert cells[0] == "Marko"
    assert cells[1] == "Petrović"
    assert cells[2] == A
    assert cells[3] == "05.10.2026-10.10.2026"
    assert cells[4] == "OK"
    assert cells[6] == "2026_PETROVIC_MARKO.pdf"


def test_export_shows_error_reason():
    bad = A[:12] + str((int(A[12]) + 1) % 10)
    guests = parse_clipboard(f"Petrović\tMarko\t{bad}\t05.10-10.10\n", YEAR).guests
    cells = to_clipboard(guests, include_header=False).split("\t")
    assert cells[4] == "GREŠKA"
    assert "kontrolna cifra" in cells[5]

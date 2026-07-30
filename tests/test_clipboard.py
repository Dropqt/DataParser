from eturista.clipboard import parse_clipboard, split_rows, to_clipboard
from eturista.models import EXPORT_HEADERS, Status
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
        "Ime\tPrezime\tJMBG\tDolazak\tDana\n"
        f"Marko\tPetrović\t{A}\t05.10\t5\n"
        f"Jovan\tIlić\t{B}\t06.10\t7\n"
    )
    result = parse_clipboard(text, YEAR)
    assert result.mapping.from_header
    assert len(result.guests) == 2
    assert result.guests[0].surname == "Petrović"
    assert result.guests[0].given_name == "Marko"
    assert result.guests[0].stay.nights == 5
    assert result.guests[1].stay.nights == 7
    assert all(g.status is Status.PENDING for g in result.guests)


def test_empty_days_column_falls_back_to_default():
    text = f"Ime\tPrezime\tJMBG\tDolazak\tDana\nMarko\tPetrović\t{A}\t05.10\t\n"
    guest = parse_clipboard(text, YEAR).guests[0]
    assert guest.stay.nights == 5
    assert guest.days_display == "5"


def test_days_column_is_detected_without_header():
    text = f"Marko\tPetrović\t{A}\t05.10\t7\nJovan\tIlić\t{B}\t06.10\t7\n"
    result = parse_clipboard(text, YEAR)
    assert result.mapping.days == 4
    assert result.guests[0].stay.nights == 7


def test_running_index_column_is_not_mistaken_for_days():
    """Kopirana numeracija redova 1,2,3 ne sme da postane broj noćenja."""
    text = (
        f"1\tMarko\tPetrović\t{A}\t05.10\n"
        f"2\tJovan\tIlić\t{B}\t06.10\n"
        f"3\tAna\tAnić\t{C}\t07.10\n"
    )
    result = parse_clipboard(text, YEAR)
    assert result.mapping.days is None
    assert all(g.stay.nights == 5 for g in result.guests)


def test_old_range_format_still_works():
    """Stare liste iz prve ture imaju opseg u koloni sa datumom."""
    text = f"Ime\tPrezime\tJMBG\tDatum\nMarko\tPetrović\t{A}\t05.10-12.10\n"
    guest = parse_clipboard(text, YEAR).guests[0]
    assert guest.stay.nights == 7
    assert guest.arrival_display == "05.10.2026"


def test_paste_with_shuffled_header_columns():
    text = (
        "JMBG\tDolazak\tIme\tPrezime\n"
        f"{A}\t05.10\tMarko\tPetrović\n"
    )
    result = parse_clipboard(text, YEAR)
    guest = result.guests[0]
    assert (guest.surname, guest.given_name) == ("Petrović", "Marko")
    assert guest.jmbg == A


def test_paste_without_header_detects_by_content():
    """Bez zaglavlja se podrazumeva ime pa prezime - kao u primer_gosti.xlsx."""
    text = f"Marko\tPetrović\t{A}\t05.10\nJovan\tIlić\t{B}\t06.10\n"
    result = parse_clipboard(text, YEAR)
    assert not result.mapping.from_header
    assert result.mapping.jmbg == 2
    assert result.mapping.date == 3
    assert (result.guests[1].given_name, result.guests[1].surname) == ("Jovan", "Ilić")


def test_all_caps_first_column_is_treated_as_surname():
    """Stara lista je pisala prezime verzalom i stavljala ga prvo: 'PREZIME Ime'."""
    text = f"PETROVIĆ\tMarko\t{A}\t05.10\nILIĆ\tJovan\t{B}\t06.10\n"
    result = parse_clipboard(text, YEAR)
    assert result.guests[0].surname == "PETROVIĆ"
    assert result.guests[0].given_name == "Marko"


def test_all_caps_second_column_keeps_default_order():
    text = f"Marko\tPETROVIĆ\t{A}\t05.10\nJovan\tILIĆ\t{B}\t06.10\n"
    result = parse_clipboard(text, YEAR)
    assert result.guests[0].given_name == "Marko"
    assert result.guests[0].surname == "PETROVIĆ"


def test_single_name_column_is_split():
    text = f"Ime i prezime\tJMBG\tDatum\nMarko Petrović\t{A}\t05.10\n"
    result = parse_clipboard(text, YEAR)
    guest = result.guests[0]
    assert (guest.given_name, guest.surname) == ("Marko", "Petrović")
    assert any("istoj koloni" in w for w in result.warnings)


def test_single_name_column_with_caps_surname_first():
    text = f"Gost\tJMBG\tDatum\nPETROVIĆ Marko\t{A}\t05.10\n"
    result = parse_clipboard(text, YEAR)
    guest = result.guests[0]
    assert (guest.given_name, guest.surname) == ("Marko", "PETROVIĆ")


def test_invalid_jmbg_row_is_kept_but_marked():
    bad = A[:12] + str((int(A[12]) + 1) % 10)
    text = f"Prezime\tIme\tJMBG\tDatum\nPetrović\tMarko\t{bad}\t05.10\n"
    result = parse_clipboard(text, YEAR)
    guest = result.guests[0]
    assert guest.status is Status.ERROR
    assert "kontrolna cifra" in guest.error.text
    assert not guest.is_ready


def test_excel_dropped_leading_zero_is_repaired_on_paste():
    text = f"Prezime\tIme\tJMBG\tDatum\nPetrović\tMarko\t{A[1:]}\t05.10\n"
    result = parse_clipboard(text, YEAR)
    guest = result.guests[0]
    assert guest.status is Status.PENDING
    assert guest.jmbg == A
    assert "vodeća nula" in guest.note


def test_blank_rows_are_skipped():
    text = f"Petrović\tMarko\t{A}\t05.10\n\t\t\t\nIlić\tJovan\t{B}\t06.10\n"
    result = parse_clipboard(text, YEAR)
    assert len(result.guests) == 2
    assert result.skipped_rows == 1


def test_row_numbers_are_sequential():
    text = f"Petrović\tMarko\t{A}\t05.10\nIlić\tJovan\t{B}\t06.10\nAnić\tAna\t{C}\t07.10\n"
    result = parse_clipboard(text, YEAR)
    assert [g.row for g in result.guests] == [1, 2, 3]


def test_unrecognizable_paste_warns_instead_of_crashing():
    result = parse_clipboard("nesto\tsasvim\tdrugo\n", YEAR)
    assert not result.ok or not result.mapping.is_usable
    assert result.warnings


def test_export_round_trip_has_status_columns():
    text = f"Prezime\tIme\tJMBG\tDatum\nPetrović\tMarko\t{A}\t05.10\n"
    guests = parse_clipboard(text, YEAR).guests
    guests[0].mark_ok("2026_PETROVIC_MARKO.pdf")

    out = to_clipboard(guests)
    header, row = out.split("\n")
    assert header.split("\t") == list(EXPORT_HEADERS)
    # Kolone se traže po nazivu, ne po broju - inače svaka nova kolona obori test
    # iz razloga koji nema veze sa onim što se proverava.
    cells = dict(zip(EXPORT_HEADERS, row.split("\t")))
    assert cells["Ime"] == "Marko"
    assert cells["Prezime"] == "Petrović"
    assert cells["JMBG"] == A
    assert cells["Dolazak"] == "05.10.2026"
    assert cells["Dana"] == "5"
    assert cells["E-mail"] == ""
    assert cells["STATUS"] == "OK"
    assert cells["PDF"] == "2026_PETROVIC_MARKO.pdf"


def test_export_shows_error_reason():
    bad = A[:12] + str((int(A[12]) + 1) % 10)
    guests = parse_clipboard(f"Marko\tPetrović\t{bad}\t05.10\t5\n", YEAR).guests
    cells = dict(zip(EXPORT_HEADERS, to_clipboard(guests, include_header=False).split("\t")))
    assert cells["STATUS"] == "GREŠKA"
    assert "kontrolna cifra" in cells["RAZLOG"]


# --- e-mail kolona ----------------------------------------------------------

def test_email_column_is_recognized_from_header():
    result = parse_clipboard(
        "Ime\tPrezime\tJMBG\tDolazak\tE-mail\n"
        f"Marko\tPetrović\t{A}\t05.10\tvauceri@primer.rs\n",
        YEAR,
    )
    assert result.guests[0].email == "vauceri@primer.rs"


def test_email_column_is_recognized_by_content():
    """Bez zaglavlja: ćelija sa @ ne može biti ništa drugo nego e-mail."""
    result = parse_clipboard(
        f"Marko\tPetrović\t{A}\t05.10\tvauceri@primer.rs\n"
        f"Jovan\tIlić\t{B}\t06.10\tvauceri@primer.rs\n",
        YEAR,
    )
    assert [g.email for g in result.guests] == ["vauceri@primer.rs"] * 2
    # i imena nisu pobrkana time što je stigla još jedna tekstualna kolona
    assert result.guests[0].given_name == "Marko"
    assert result.guests[0].surname == "Petrović"


def test_missing_email_column_is_fine():
    result = parse_clipboard(f"Marko\tPetrović\t{A}\t05.10\n", YEAR)
    assert result.guests[0].email == ""
    assert result.guests[0].is_ready


def test_nonsense_email_marks_the_row():
    """Sa zaglavljem se zna da je kolona e-mail, pa se pokvarena vrednost prijavi.

    Bez zaglavlja se takva ćelija ni ne prepozna kao e-mail (nema @), pa se i ne
    proverava - to je namerno: bolje ne prepoznati kolonu nego pogrešno je pripisati.
    """
    from eturista.errors import ErrorKind

    result = parse_clipboard(
        "Ime\tPrezime\tJMBG\tDolazak\tDana\tE-mail\n"
        f"Marko\tPetrović\t{A}\t05.10\t5\tmarko(at)primer.rs\n",
        YEAR,
    )
    guest = result.guests[0]
    assert guest.status is Status.ERROR
    assert guest.error.kind is ErrorKind.EMAIL_INVALID


# ---------------------------------------------------------------------------
# lepljenje iz Worda - tekst bez kolona
# ---------------------------------------------------------------------------

def test_word_paragraph_is_read_without_columns():
    """Spisak iz Worda često nije tabela nego pasus - polja se prepoznaju po obliku."""
    text = f"Marko Petrović {A} 05.10.2026\nJovan Ilić {B} 06.10.2026 7\n"
    result = parse_clipboard(text, YEAR)

    assert result.mapping.free_text
    assert [(g.given_name, g.surname) for g in result.guests] == [
        ("Marko", "Petrović"), ("Jovan", "Ilić"),
    ]
    assert [g.jmbg for g in result.guests] == [A, B]
    # Goli broj posle datuma je broj noćenja; gde ga nema važi podrazumevanih 5.
    assert [g.stay.nights for g in result.guests] == [5, 7]


def test_word_numbering_and_bullets_are_not_data():
    text = f"1. Marko Petrović {A} 05.10.2026\n- Jovan Ilić, {B}, 06.10.2026\n"
    result = parse_clipboard(text, YEAR)

    assert len(result.guests) == 2
    assert all(g.is_ready for g in result.guests)
    # Redni broj "1." ne sme da postane broj noćenja ni deo imena.
    assert result.guests[0].given_name == "Marko"
    assert result.guests[0].stay.nights == 5


def test_word_labels_stay_out_of_the_name():
    text = f"Marko Petrović - JMBG {A} - dolazak 05.10.2026 - 5 dana\n"
    guest = parse_clipboard(text, YEAR).guests[0]

    assert (guest.given_name, guest.surname) == ("Marko", "Petrović")
    assert guest.jmbg == A
    assert guest.stay.nights == 5


def test_word_soft_line_break_starts_a_new_guest():
    """Shift+Enter u Wordu daje \\v umesto novog reda - i to je novi gost."""
    text = f"Marko Petrović {A} 05.10.2026\vJovan Ilić {B} 06.10.2026"
    assert len(parse_clipboard(text, YEAR).guests) == 2


def test_nonbreaking_space_does_not_break_the_jmbg():
    """Word ume da ubaci tvrdi razmak; JMBG mora da prođe kao da ga nema."""
    text = f"Marko\tPetrović\t{A[:4]}\u00a0{A[4:]}\t05.10.2026\n"
    guest = parse_clipboard(text, YEAR).guests[0]
    assert guest.jmbg == A
    assert guest.is_ready


def test_free_text_without_any_jmbg_is_refused():
    """Bez ijednog JMBG-a zalepljeno nije spisak gostiju - bolje priznati nego izmišljati."""
    result = parse_clipboard("Poštovani, u prilogu šaljem spisak.\nPozdrav, Danica\n", YEAR)
    assert not result.guests
    assert any("Ne mogu da prepoznam" in w for w in result.warnings)


def test_free_text_skips_lines_that_are_not_guests():
    text = f"Spisak gostiju za oktobar\nMarko Petrović {A} 05.10.2026\n"
    result = parse_clipboard(text, YEAR)
    assert len(result.guests) == 1
    assert any("nije ličio" in w for w in result.warnings)


def test_leading_numbering_column_is_not_days_even_for_two_rows():
    """Numeracija stoji ispred gosta, broj noćenja iza JMBG-a - po tome se razlikuju."""
    text = f"1\tMarko\tPetrović\t{A}\t05.10\n2\tJovan\tIlić\t{B}\t06.10\n"
    result = parse_clipboard(text, YEAR)
    assert result.mapping.days is None
    assert all(g.stay.nights == 5 for g in result.guests)


# --- naziv meseca u datumu --------------------------------------------------

def test_month_name_column_is_recognized():
    """Kolona sa 29.sep.2026 mora da se prepozna kao Dolazak i bez zaglavlja."""
    text = f"Marko\tPetrović\t{A}\t29.sep.2026\t7\n"
    result = parse_clipboard(text, YEAR)

    assert result.mapping.date == 3
    guest = result.guests[0]
    assert guest.arrival_display == "29.09.2026"
    assert guest.stay.nights == 7


def test_days_cell_is_not_mistaken_for_a_date():
    """"5 dana" ima broj pa reč, ali reč nije mesec - ne sme da postane datum."""
    text = f"Marko\tPetrović\t{A}\t05.10.2026\t5 dana\n"
    result = parse_clipboard(text, YEAR)

    assert result.mapping.date == 3
    assert result.guests[0].stay.nights == 5


def test_word_paragraph_with_spaced_month_name():
    """U pasusu iz Worda datum stiže kao tri reči - moraju da se spoje."""
    text = f"Marko Petrović {A} 29. septembra 2026 7 dana\n"
    guest = parse_clipboard(text, YEAR).guests[0]

    assert (guest.given_name, guest.surname) == ("Marko", "Petrović")
    assert guest.stay.arrival.month == 9
    assert guest.stay.nights == 7


def test_word_paragraph_with_cyrillic_month_name():
    text = f"Marko Petrović {A} 29. септембра 2026\n"
    guest = parse_clipboard(text, YEAR).guests[0]

    assert guest.surname == "Petrović"
    assert guest.stay.arrival.month == 9


def test_guest_named_maja_keeps_her_name():
    """"maja" je genitiv od maj, ali Maja je i žensko ime - ime je preče."""
    text = f"Maja Petrović {A} 05.10.2026\n"
    guest = parse_clipboard(text, YEAR).guests[0]

    assert (guest.given_name, guest.surname) == ("Maja", "Petrović")
    assert guest.stay.arrival.month == 10

#!/usr/bin/env python3
"""Napravi primer Excel fajla sa gotovom proverom JMBG-a.

    .venv/bin/python alati/napravi_primer_excel.py

Rezultat: ``primer/primer_gosti.xlsx``

Excel radi **istu proveru kao aplikacija** — kontrolnu cifru po zvaničnoj formuli — pa se
tipfeler vidi već u glavnoj tabeli, pre nego što se bilo šta kopira u program. Formule su
namerno pisane bez LET() i drugih novijih funkcija, da rade i u starijem Excelu i u
LibreOffice-u.

Raspored kolona A-G je **isti kao izlaz iz aplikacije** (``models.EXPORT_HEADERS``), pa se
rezultat ture lepi preko A2 bez pomeranja ičega. H je provera JMBG-a, I-L su pomoćne
kolone iza nje i sakrivene su.
"""

from __future__ import annotations

import sys
from pathlib import Path

from openpyxl import Workbook
from openpyxl.formatting.rule import CellIsRule, FormulaRule
from openpyxl.styles import Alignment, Border, Font, PatternFill, Side
from openpyxl.utils import get_column_letter

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from eturista.validation import jmbg_check_digit  # noqa: E402

ROWS = 200  # dokle sežu formule i bojenje

#: Kolone A-G moraju da budu istim redom kao EXPORT_HEADERS u aplikaciji, da bi se
#: rezultat ture lepio nazad preko A2 bez pomeranja ičega.
HEADERS = [
    ("Ime", 14),
    ("Prezime", 16),
    ("JMBG", 15),
    ("Datum", 20),
    ("STATUS", 12),
    ("RAZLOG", 38),
    ("PDF", 26),
    ("PROVERA JMBG", 34),
]
#: Pomoćne kolone (sakrivene) — postoje samo da bi formula u H bila čitljiva.
HELPERS = [("zbir", 8), ("kontrolna", 10), ("godina", 8), ("dat.rođ.", 10)]

VISIBLE = "ABCDEFGH"
LAST_VISIBLE = "H"
FIRST_HELPER, LAST_HELPER = "I", "L"

GREEN = PatternFill("solid", start_color="FFC6EFCE")
RED = PatternFill("solid", start_color="FFFFC7CE")
GRAY = PatternFill("solid", start_color="FFE0E0E0")
BLUE = PatternFill("solid", start_color="FFDDEBF7")
HEADER = PatternFill("solid", start_color="FF44546A")

GREEN_TEXT = Font(color="FF006100")
RED_TEXT = Font(color="FF9C0006")

THIN = Side(style="thin", color="FFBFBFBF")
BOX = Border(left=THIN, right=THIN, top=THIN, bottom=THIN)


def jmbg(first_twelve: str) -> str:
    """Ispravan JMBG od prvih 12 cifara."""
    return first_twelve + str(jmbg_check_digit(first_twelve))


def broken_jmbg(first_twelve: str) -> str:
    """JMBG sa namerno pogrešnom kontrolnom cifrom — kao tipfeler u poslednjoj cifri.

    Cifra se pomera za jedan umesto da se upiše fiksna vrednost; fiksna bi za neke
    brojeve slučajno ispala tačna i primer ne bi pokazivao ništa.
    """
    correct = jmbg_check_digit(first_twelve)
    return first_twelve + str((correct + 1) % 10)


#: Izmišljeni primeri — ispravni po kontrolnoj cifri, ali ne pripadaju nikome.
#: Cifre su birane tako da izvedeni datum rođenja i pol odgovaraju imenu, jer se baš po
#: tom neslaganju najlakše primeti da je neko pogrešio cifru.
#: Poslednja dva reda su namerno pokvarena da se vidi kako provera reaguje.
#: Redom: ime, prezime, JMBG, datum.
SAMPLE = [
    #                            DD MM GGG RR BBB
    ("Marko", "Petrović", jmbg("010199071012"), "05.10-10.10"),    # 01.01.1990, M
    ("Ana", "Jovanović", jmbg("230799575544"), "05.10-10.10"),     # 23.07.1995, Ž
    ("Jovan", "Ilić", jmbg("150398871001"), "06.10-12.10"),        # 15.03.1988, M
    ("Nikola", "Đorđević", jmbg("110599270012"), "06.10-12.10"),   # 11.05.1992, M
    ("Milica", "Marković", jmbg("290200471505"), "07.10-14.10"),   # 29.02.2004, Ž
    # pokvarena poslednja cifra -> "Pogrešna kontrolna cifra"
    ("Stefan", "Nikolić", broken_jmbg("070300771003"), "07.10-14.10"),
    # 12 cifara, kao kad Excel pojede vodeću nulu -> "Nema 13 cifara"
    ("Jelena", "Simić", jmbg("030697875501")[1:], "08.10-15.10"),
]


def build_formulas(row: int) -> dict[str, str]:
    """Formule za jedan red. ``row`` je broj reda u Excelu (podaci kreću od 2)."""
    c = f"C{row}"

    def digit(position: int) -> str:
        return f"VALUE(MID({c},{position},1))"

    # Zvanična formula: 7(a+g) + 6(b+h) + 5(c+i) + 4(d+j) + 3(e+k) + 2(f+l)
    weighted = "+".join(
        f"{weight}*({digit(left)}+{digit(left + 6)})"
        for weight, left in zip((7, 6, 5, 4, 3, 2), range(1, 7))
    )

    year = f"IF(VALUE(MID({c},5,3))>=800,1000,2000)+VALUE(MID({c},5,3))"
    day, month = f"VALUE(MID({c},1,2))", f"VALUE(MID({c},3,2))"
    birth = f"DATE(K{row},{month},{day})"

    return {
        # I: zbir sa težinama
        f"I{row}": f'=IFERROR(IF(LEN({c})<>13,"",{weighted}),"")',
        # J: kontrolna cifra — ako ispadne 10 ili 11, ona je 0
        f"J{row}": f'=IF(I{row}="","",IF(11-MOD(I{row},11)>9,0,11-MOD(I{row},11)))',
        # K: godina rođenja (GGG je godina po modulu 1000; 800+ znači 19xx)
        f"K{row}": f'=IFERROR(IF(LEN({c})<>13,"",{year}),"")',
        # L: datum rođenja — prazno ako taj datum ne postoji.
        # Excel DATE ne greši na 31.02, nego prevrne na mart, pa se dan i mesec proveravaju.
        f"L{row}": (
            f'=IFERROR(IF(K{row}="","",'
            f'IF(AND(DAY({birth})={day},MONTH({birth})={month}),{birth},"")),"")'
        ),
        # H: poruka o ispravnosti — ista logika kao u aplikaciji
        f"H{row}": (
            f'=IF({c}="","",'
            f'IF(LEN({c})<>13,"Nema 13 cifara (ima "&LEN({c})&")",'
            f'IF(J{row}="","JMBG sadrži nešto što nije cifra",'
            f'IF(L{row}="","Nepostojeći datum rođenja",'
            f'IF(VALUE(MID({c},13,1))<>J{row},'
            f'"Pogrešna kontrolna cifra — treba "&J{row},'
            f'"✓ ispravan")))))'
        ),
    }


def build_guests_sheet(workbook: Workbook):
    sheet = workbook.active
    sheet.title = "Gosti"

    all_headers = HEADERS + HELPERS
    for index, (title, width) in enumerate(all_headers, start=1):
        cell = sheet.cell(row=1, column=index, value=title)
        cell.fill = HEADER
        cell.font = Font(bold=True, color="FFFFFFFF")
        cell.alignment = Alignment(horizontal="center", vertical="center")
        cell.border = BOX
        sheet.column_dimensions[get_column_letter(index)].width = width

    sheet.freeze_panes = "A2"
    sheet.auto_filter.ref = f"A1:{LAST_VISIBLE}{ROWS + 1}"

    for offset, (given, surname, id_number, dates) in enumerate(SAMPLE):
        row = offset + 2
        sheet[f"A{row}"] = given
        sheet[f"B{row}"] = surname
        sheet[f"C{row}"] = id_number
        sheet[f"D{row}"] = dates

    for row in range(2, ROWS + 2):
        for reference, formula in build_formulas(row).items():
            sheet[reference] = formula

        sheet[f"C{row}"].number_format = "@"      # tekst, da vodeća nula preživi
        sheet[f"E{row}"].alignment = Alignment(horizontal="center")
        for column in VISIBLE:
            sheet[f"{column}{row}"].border = BOX

    # Pomoćne kolone su tu samo da bi formula u H bila čitljiva — sakrivamo ih.
    sheet.column_dimensions.group(FIRST_HELPER, LAST_HELPER, hidden=True)

    _add_conditional_formatting(sheet)
    return sheet


def _add_conditional_formatting(sheet) -> None:
    span = f"H2:H{ROWS + 1}"
    sheet.conditional_formatting.add(
        span,
        FormulaRule(formula=['LEFT($H2,1)="✓"'], fill=GREEN, font=GREEN_TEXT, stopIfTrue=True),
    )
    sheet.conditional_formatting.add(
        span,
        FormulaRule(formula=['$H2<>""'], fill=RED, font=RED_TEXT),
    )

    # STATUS kolona — popunjava se lepljenjem rezultata iz aplikacije.
    status = f"E2:E{ROWS + 1}"
    for value, fill, font in (
        ("OK", GREEN, GREEN_TEXT),
        ("GREŠKA", RED, RED_TEXT),
        ("PRESKOČEN", GRAY, None),
        ("ČEKA", BLUE, None),
    ):
        rule = CellIsRule(operator="equal", formula=[f'"{value}"'], fill=fill)
        if font is not None:
            rule.font = font
        sheet.conditional_formatting.add(status, rule)

    # Red se blago oboji čim STATUS kaže da je gost pao — lakše se skenira lista.
    sheet.conditional_formatting.add(
        f"A2:D{ROWS + 1}",
        FormulaRule(formula=['$E2="GREŠKA"'], fill=RED),
    )
    sheet.conditional_formatting.add(
        f"A2:D{ROWS + 1}",
        FormulaRule(formula=['$E2="OK"'], fill=GREEN),
    )


def build_instructions_sheet(workbook: Workbook) -> None:
    sheet = workbook.create_sheet("Uputstvo")
    sheet.column_dimensions["A"].width = 4
    sheet.column_dimensions["B"].width = 110

    lines: list[tuple[str, str]] = [
        ("naslov", "Kako se koristi ova tabela"),
        ("", ""),
        ("podnaslov", "1. Unos gostiju"),
        ("", "Popunjavaj kolone A-D: Ime, Prezime, JMBG, Datum."),
        ("", "JMBG kolona je formatirana kao TEKST — bez toga Excel pojede vodeću nulu kod"),
        ("", "gostiju rođenih 1-9. u mesecu, pa umesto 13 ostane 12 cifara."),
        ("", "Datum piši kao 05.10-10.10 ili 05.10.2026-10.10.2026 — oba se prepoznaju."),
        ("", ""),
        ("podnaslov", "2. Provera JMBG-a (kolona H)"),
        ("", "Računa se automatski, po zvaničnoj formuli za kontrolnu cifru."),
        ("", "Zeleno '✓ ispravan' znači da broj matematički može da postoji."),
        ("", "Crveno kaže tačno šta ne valja, npr. 'Pogrešna kontrolna cifra — treba 8'."),
        ("", "Kolone I-L su pomoćne (sakrivene) — služe samo formuli u koloni H. Ne diraj ih."),
        ("", ""),
        ("napomena", "Provera hvata tipfelere, ali ne može da zna da li broj zaista pripada tom čoveku."),
        ("napomena", "To utvrđuje tek portal — i to se posle vidi u koloni RAZLOG."),
        ("", ""),
        ("podnaslov", "3. Slanje u aplikaciju"),
        ("", "Označi kolone A-D za grupu gostiju koju prijavljuješ (5, 10, 30 — koliko hoćeš),"),
        ("", "Ctrl+C, pa u aplikaciji Ctrl+V."),
        ("", ""),
        ("podnaslov", "4. Vraćanje rezultata"),
        ("", "Kad se tura završi, u aplikaciji Ctrl+C i ovde zalepi preko kolone A za te goste."),
        ("", "Popuniće se i E (STATUS), F (RAZLOG) i G (PDF). Bojenje je već podešeno:"),
        ("", "OK = zeleno, GREŠKA = crveno, PRESKOČEN = sivo."),
        ("", "Kolone H-L su formule i ostaju netaknute jer su desno od zalepljenog."),
        ("", ""),
        ("podnaslov", "Napomena"),
        ("", "Redovi 2-8 su izmišljeni primeri — obriši ih pre pravog rada."),
        ("", "Poslednja dva su namerno pokvarena da se vidi kako provera reaguje."),
    ]

    for index, (kind, text) in enumerate(lines, start=1):
        cell = sheet.cell(row=index, column=2, value=text)
        if kind == "naslov":
            cell.font = Font(bold=True, size=15)
        elif kind == "podnaslov":
            cell.font = Font(bold=True, size=11, color="FF44546A")
        elif kind == "napomena":
            cell.font = Font(italic=True, color="FF9C0006")


def main() -> None:
    workbook = Workbook()
    build_guests_sheet(workbook)
    build_instructions_sheet(workbook)

    target = Path(__file__).resolve().parent.parent / "primer" / "primer_gosti.xlsx"
    target.parent.mkdir(parents=True, exist_ok=True)
    workbook.save(target)
    print(f"Napravljeno: {target}")
    print(f"  {len(SAMPLE)} primera, formule do reda {ROWS + 1}")


if __name__ == "__main__":
    main()

#!/usr/bin/env python3
"""Napravi primer Excel fajla sa gotovom proverom JMBG-a.

    .venv/bin/python alati/napravi_primer_excel.py

Rezultat: ``primer/primer_gosti.xlsx``

Excel radi **istu proveru kao aplikacija** - kontrolnu cifru po zvaničnoj formuli - pa se
tipfeler vidi već u glavnoj tabeli, pre nego što se bilo šta kopira u program. Formule su
namerno pisane bez LET() i drugih novijih funkcija, da rade i u starijem Excelu i u
LibreOffice-u.

Raspored kolona je **isti kao izlaz iz aplikacije** (``models.EXPORT_HEADERS``), pa se
rezultat ture lepi preko A2 bez pomeranja ičega. Iza njih ide provera JMBG-a, pa pomoćne
kolone koje su sakrivene.

Slova kolona se nigde ne kucaju - izvode se iz ``HEADERS`` preko :func:`col`. Dodavanje
kolone je zato izmena na jednom mestu.
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

#: Po jedan radni list za svaki nalog - svako popunjava svoje goste bez mešanja.
#: Nazivi se poklapaju sa ``ETURISTA_NALOGx_NAZIV`` iz ``.env``, pa se odmah vidi
#: koji list ide uz koji nalog u padajućem meniju aplikacije.
NALOZI = ["Danica", "Mileta", "Zorica"]

#: Primeri stoje zasebno da radni listovi budu prazni i spremni za pravi unos.
PRIMERI_SHEET = "Primeri"

#: Prve kolone moraju da budu istim redom kao EXPORT_HEADERS u aplikaciji, da bi se
#: rezultat ture lepio nazad preko A2 bez pomeranja ičega. Test to i čuva.
HEADERS = [
    ("Ime", 14),
    ("Prezime", 16),
    ("JMBG", 15),
    ("Dolazak", 12),
    ("Dana", 7),
    ("E-mail", 26),
    ("STATUS", 12),
    ("RAZLOG", 38),
    ("PDF", 26),
    ("PROVERA JMBG", 34),
]
#: Pomoćne kolone (sakrivene) - postoje samo da bi formula za proveru bila čitljiva.
HELPERS = [("zbir", 8), ("kontrolna", 10), ("godina", 8), ("dat.rođ.", 10)]

_NAZIVI = [naziv for naziv, _ in HEADERS + HELPERS]


def col(naziv: str) -> str:
    """Slovo kolone po naslovu iz zaglavlja.

    Slova se nigde ne kucaju ručno: dovoljno je dodati kolonu u ``HEADERS`` i sve
    formule, bojenja i opsezi se pomere sami. Ranije su bila ukucana na desetak mesta,
    pa je svaka nova kolona značila lov po celom fajlu.
    """
    return get_column_letter(_NAZIVI.index(naziv) + 1)


VISIBLE = "".join(col(naziv) for naziv, _ in HEADERS)
LAST_VISIBLE = col(HEADERS[-1][0])
FIRST_HELPER, LAST_HELPER = col(HELPERS[0][0]), col(HELPERS[-1][0])

#: Kolone koje korisnik popunjava - do njih seže bojenje reda po statusu.
LAST_INPUT = col("E-mail")

#: Koliko noćenja se podrazumeva. Mora da odgovara validation.DEFAULT_DAYS.
DEFAULT_DAYS = 5

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
    """JMBG sa namerno pogrešnom kontrolnom cifrom - kao tipfeler u poslednjoj cifri.

    Cifra se pomera za jedan umesto da se upiše fiksna vrednost; fiksna bi za neke
    brojeve slučajno ispala tačna i primer ne bi pokazivao ništa.
    """
    correct = jmbg_check_digit(first_twelve)
    return first_twelve + str((correct + 1) % 10)


#: Izmišljeni primeri - ispravni po kontrolnoj cifri, ali ne pripadaju nikome.
#: Cifre su birane tako da izvedeni datum rođenja i pol odgovaraju imenu, jer se baš po
#: tom neslaganju najlakše primeti da je neko pogrešio cifru.
#: Poslednja dva reda su namerno pokvarena da se vidi kako provera reaguje.
#: Redom: ime, prezime, JMBG, datum.
#: Redom: ime, prezime, JMBG, datum dolaska, broj noćenja ("" = podrazumevanih 5).
SAMPLE = [
    #                            DD MM GGG RR BBB
    ("Marko", "Petrović", jmbg("010199071012"), "05.10.2026", ""),    # 01.01.1990, M
    ("Ana", "Jovanović", jmbg("230799575544"), "05.10.2026", ""),     # 23.07.1995, Ž
    ("Jovan", "Ilić", jmbg("150398871001"), "06.10.2026", 7),         # 15.03.1988, M
    ("Nikola", "Đorđević", jmbg("110599270012"), "06.10.2026", ""),   # 11.05.1992, M
    ("Milica", "Marković", jmbg("290200471505"), "07.10.2026", 10),   # 29.02.2004, Ž
    # pokvarena poslednja cifra -> "Pogrešna kontrolna cifra"
    ("Stefan", "Nikolić", broken_jmbg("070300771003"), "07.10.2026", ""),
    # 12 cifara, kao kad Excel pojede vodeću nulu -> "Nema 13 cifara"
    ("Jelena", "Simić", jmbg("030697875501")[1:], "08.10.2026", ""),
]


def build_formulas(row: int) -> dict[str, str]:
    """Formule za jedan red. ``row`` je broj reda u Excelu (podaci kreću od 2)."""
    c = f"{col('JMBG')}{row}"
    zbir, kontrolna = f"{col('zbir')}{row}", f"{col('kontrolna')}{row}"
    godina, rodjen = f"{col('godina')}{row}", f"{col('dat.rođ.')}{row}"

    def digit(position: int) -> str:
        return f"VALUE(MID({c},{position},1))"

    # Zvanična formula: 7(a+g) + 6(b+h) + 5(c+i) + 4(d+j) + 3(e+k) + 2(f+l)
    weighted = "+".join(
        f"{weight}*({digit(left)}+{digit(left + 6)})"
        for weight, left in zip((7, 6, 5, 4, 3, 2), range(1, 7))
    )

    year = f"IF(VALUE(MID({c},5,3))>=800,1000,2000)+VALUE(MID({c},5,3))"
    day, month = f"VALUE(MID({c},1,2))", f"VALUE(MID({c},3,2))"
    birth = f"DATE({godina},{month},{day})"

    return {
        # zbir sa težinama
        zbir: f'=IFERROR(IF(LEN({c})<>13,"",{weighted}),"")',
        # kontrolna cifra - ako ispadne 10 ili 11, ona je 0
        kontrolna: f'=IF({zbir}="","",IF(11-MOD({zbir},11)>9,0,11-MOD({zbir},11)))',
        # godina rođenja (GGG je godina po modulu 1000; 800+ znači 19xx)
        godina: f'=IFERROR(IF(LEN({c})<>13,"",{year}),"")',
        # datum rođenja - prazno ako taj datum ne postoji.
        # Excel DATE ne greši na 31.02, nego prevrne na mart, pa se dan i mesec proveravaju.
        rodjen: (
            f'=IFERROR(IF({godina}="","",'
            f'IF(AND(DAY({birth})={day},MONTH({birth})={month}),{birth},"")),"")'
        ),
        # broj noćenja se podrazumeva čim se upiše gost; prekucaj ako je drugačije
        f"{col('Dana')}{row}": f'=IF({col("Ime")}{row}="","",{DEFAULT_DAYS})',
        # poruka o ispravnosti JMBG-a - ista logika kao u aplikaciji
        f"{col('PROVERA JMBG')}{row}": (
            f'=IF({c}="","",'
            f'IF(LEN({c})<>13,"Nema 13 cifara (ima "&LEN({c})&")",'
            f'IF({kontrolna}="","JMBG sadrži nešto što nije cifra",'
            f'IF({rodjen}="","Nepostojeći datum rođenja",'
            f'IF(VALUE(MID({c},13,1))<>{kontrolna},'
            f'"Pogrešna kontrolna cifra - treba "&{kontrolna},'
            f'"✓ ispravan")))))'
        ),
    }


def build_guests_sheet(workbook: Workbook, title: str, with_samples: bool = False):
    """Jedan radni list sa gostima - zaglavlje, formule i bojenje.

    Pravi se po jedan za svaki nalog, pa svako popunjava svoje bez mešanja. Formule i
    bojenje su svuda isti; razlikuje se samo naziv lista i to da li nosi primere.
    """
    sheet = workbook.create_sheet(title)

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

    explicit_days: dict[int, int] = {}
    if with_samples:
        for offset, (given, surname, id_number, arrival, days) in enumerate(SAMPLE):
            row = offset + 2
            sheet[f"{col('Ime')}{row}"] = given
            sheet[f"{col('Prezime')}{row}"] = surname
            sheet[f"{col('JMBG')}{row}"] = id_number
            sheet[f"{col('Dolazak')}{row}"] = arrival
            if days:
                explicit_days[row] = int(days)

    for row in range(2, ROWS + 2):
        for reference, formula in build_formulas(row).items():
            sheet[reference] = formula

        # Gde je broj noćenja drugačiji od podrazumevanog, upisuje se preko formule -
        # isto što korisnik radi kad prekuca vrednost.
        if row in explicit_days:
            sheet[f"{col('Dana')}{row}"] = explicit_days[row]

        sheet[f"{col('JMBG')}{row}"].number_format = "@"   # tekst, da vodeća nula preživi
        sheet[f"{col('Dana')}{row}"].alignment = Alignment(horizontal="center")
        sheet[f"{col('STATUS')}{row}"].alignment = Alignment(horizontal="center")
        for column in VISIBLE:
            sheet[f"{column}{row}"].border = BOX

    # Pomoćne kolone su tu samo da bi formula za proveru bila čitljiva - sakrivamo ih.
    sheet.column_dimensions.group(FIRST_HELPER, LAST_HELPER, hidden=True)

    _add_conditional_formatting(sheet)
    return sheet


def _add_conditional_formatting(sheet) -> None:
    provera = col("PROVERA JMBG")
    span = f"{provera}2:{provera}{ROWS + 1}"
    sheet.conditional_formatting.add(
        span,
        FormulaRule(
            formula=[f'LEFT(${provera}2,1)="✓"'], fill=GREEN, font=GREEN_TEXT, stopIfTrue=True
        ),
    )
    sheet.conditional_formatting.add(
        span,
        FormulaRule(formula=[f'${provera}2<>""'], fill=RED, font=RED_TEXT),
    )

    # STATUS kolona - popunjava se lepljenjem rezultata iz aplikacije.
    status_col = col("STATUS")
    status = f"{status_col}2:{status_col}{ROWS + 1}"
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

    # Red se blago oboji čim STATUS kaže da je gost pao - lakše se skenira lista.
    uneti = f"{col('Ime')}2:{LAST_INPUT}{ROWS + 1}"
    sheet.conditional_formatting.add(
        uneti,
        FormulaRule(formula=[f'${status_col}2="GREŠKA"'], fill=RED),
    )
    sheet.conditional_formatting.add(
        uneti,
        FormulaRule(formula=[f'${status_col}2="OK"'], fill=GREEN),
    )


def build_instructions_sheet(workbook: Workbook) -> None:
    sheet = workbook.create_sheet("Uputstvo")
    sheet.column_dimensions["A"].width = 4
    sheet.column_dimensions["B"].width = 110

    lines: list[tuple[str, str]] = [
        ("naslov", "Kako se koristi ova tabela"),
        ("", ""),
        ("podnaslov", "0. Listovi"),
        ("", f"Po jedan list za svaki nalog: {', '.join(NALOZI)}."),
        ("", "Svako popunjava svoj list, pa se grupe ne mešaju i svako vidi samo svoje goste."),
        ("", f"Nazivi listova su isti kao nalozi u padajućem meniju aplikacije."),
        ("", f"List '{PRIMERI_SHEET}' su izmišljeni primeri - tu se vidi kako radi provera"),
        ("", "JMBG-a. Radni listovi su namerno prazni."),
        ("", ""),
        ("podnaslov", "1. Unos gostiju"),
        ("", f"Popunjavaj kolone {col('Ime')}-{LAST_INPUT}: Ime, Prezime, JMBG, Dolazak, Dana, E-mail."),
        ("", "JMBG kolona je formatirana kao TEKST - bez toga Excel pojede vodeću nulu kod"),
        ("", "gostiju rođenih 1-9. u mesecu, pa umesto 13 ostane 12 cifara."),
        ("", "Dolazak piši kao 05.10 ili 05.10.2026 - oba se prepoznaju."),
        ("", f"Dana se popunjava samo od sebe na {DEFAULT_DAYS}; prekucaj ako je boravak duži."),
        ("", "E-mail popunjavaj samo za goste čiji vaučeri idu na drugu adresu nego ostali -"),
        ("", "prazna ćelija znači adresu upisanu u aplikaciji. Po njoj se prave folderi sa vaučerima."),
        ("", f"'{DEFAULT_DAYS} dana' znači {DEFAULT_DAYS} noćenja: dolazak 05.10 -> odlazak 10.10."),
        ("", ""),
        ("podnaslov", f"2. Provera JMBG-a (kolona {col('PROVERA JMBG')})"),
        ("", "Računa se automatski, po zvaničnoj formuli za kontrolnu cifru."),
        ("", "Zeleno '✓ ispravan' znači da broj matematički može da postoji."),
        ("", "Crveno kaže tačno šta ne valja, npr. 'Pogrešna kontrolna cifra - treba 8'."),
        ("", f"Kolone {FIRST_HELPER}-{LAST_HELPER} su pomoćne (sakrivene) - služe samo formuli u "
         f"koloni {col('PROVERA JMBG')}. Ne diraj ih."),
        ("", ""),
        ("napomena", "Provera hvata tipfelere, ali ne može da zna da li broj zaista pripada tom čoveku."),
        ("napomena", "To utvrđuje tek portal - i to se posle vidi u koloni RAZLOG."),
        ("", ""),
        ("podnaslov", "3. Slanje u aplikaciju"),
        ("", f"Označi kolone {col('Ime')}-{LAST_INPUT} za grupu gostiju koju prijavljuješ "
         "(5, 10, 30 - koliko hoćeš),"),
        ("", "Ctrl+C, pa u aplikaciji Ctrl+V."),
        ("", ""),
        ("podnaslov", "4. Vraćanje rezultata"),
        ("", f"Kad se tura završi, u aplikaciji Ctrl+C i ovde zalepi preko kolone {col('Ime')} za te goste."),
        ("", f"Popuniće se i {col('STATUS')} (STATUS), {col('RAZLOG')} (RAZLOG) i {col('PDF')} (PDF). "
         "Bojenje je već podešeno:"),
        ("", "OK = zeleno, GREŠKA = crveno, PRESKOČEN = sivo."),
        ("", f"Kolone {col('PROVERA JMBG')}-{LAST_HELPER} su formule i ostaju netaknute jer su "
         "desno od zalepljenog."),
        ("", ""),
        ("podnaslov", "Napomena"),
        ("", f"Na listu '{PRIMERI_SHEET}' su izmišljeni gosti - ne pripadaju nikome."),
        ("", "Poslednja dva su namerno pokvarena da se vidi kako provera reaguje:"),
        ("", "jednom je pokvarena kontrolna cifra, drugom fali vodeća nula."),
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
    # openpyxl novu radnu svesku pravi sa jednim praznim listom; svoje prave
    # ``create_sheet``, pa se taj podrazumevani sklanja.
    workbook.remove(workbook.active)

    for naziv in NALOZI:
        build_guests_sheet(workbook, naziv)
    build_guests_sheet(workbook, PRIMERI_SHEET, with_samples=True)
    build_instructions_sheet(workbook)

    workbook.active = 0   # fajl se otvara na prvom nalogu, ne na primerima

    target = Path(__file__).resolve().parent.parent / "primer" / "primer_gosti.xlsx"
    target.parent.mkdir(parents=True, exist_ok=True)
    workbook.save(target)
    print(f"Napravljeno: {target}")
    print(f"  listovi: {', '.join(NALOZI)} (prazni) + {PRIMERI_SHEET} ({len(SAMPLE)} primera) + Uputstvo")
    print(f"  formule do reda {ROWS + 1}")


if __name__ == "__main__":
    main()

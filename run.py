#!/usr/bin/env python3
"""Ulazna tačka.

    python run.py                      # aplikacija
    python run.py --proveri-selektore  # provera da li selektori i dalje važe na portalu
    python run.py --provera-sistema    # ima li Python, biblioteke, Chrome, nalozi
    python run.py --lazni-portal       # lokalni lažni portal za probu, bez pravog sajta
    python run.py --pripremi-potpis U I  # screenshot potpisa -> providni PNG
    python run.py --kalibracija PDF    # gde bi potpis pao na ovom vaučeru
"""

from __future__ import annotations

import argparse
import sys


def _run_gui() -> int:
    from PySide6.QtWidgets import QApplication

    from eturista.config import Config
    from eturista.gui.main_window import MainWindow

    app = QApplication(sys.argv)
    app.setApplicationName("eTurista Prijava")

    window = MainWindow(Config.load())
    window.show()
    return app.exec()


#: Koliko selektora staje u red izveštaja. XPath koji hvata tekst u oba pisma je dugačak
#: nekoliko stotina znakova, pa bi bez skraćivanja pojeo ceo ekran - a ono što se iz
#: izveštaja čita je da li je selektor našao element, ne kako tačno glasi.
_SIRINA_SELEKTORA = 60


def _skrati(selektor: str | None) -> str:
    tekst = " ".join((selektor or "").split())
    if len(tekst) <= _SIRINA_SELEKTORA:
        return tekst
    return tekst[: _SIRINA_SELEKTORA - 1] + "…"


def _check_selectors(account_label: str | None) -> int:
    from eturista.accounts import find_account, load_accounts
    from eturista.config import Config
    from eturista.portal import selectors as S
    from eturista.runner import verify_selectors

    config = Config.load()
    accounts = load_accounts()
    if not accounts:
        print("Nema podešenih naloga - napravi .env po uzoru na .env.example.")
        return 2

    account = find_account(accounts, account_label) if account_label else accounts[0]
    if account is None:
        print(f"Nalog '{account_label}' ne postoji. Dostupni: {', '.join(a.label for a in accounts)}")
        return 2

    print(f"Portal: {config.portal_url}")
    print(f"Nalog:  {account.masked()}")
    print(f"Stanje selektora u kodu: {S.summary()}\n")

    checks = verify_selectors(config, account)
    for check in sorted(checks, key=lambda c: (c.found, c.locator.name)):
        mark = "✓" if check.found else "✗"
        extra = f"  [{_skrati(check.matched_by)}]" if check.found else ""
        print(f"{mark} {check.locator.state.value:14} {check.locator.name:20} {check.locator.description}{extra}")

    missing = [c for c in checks if not c.found and not c.locator.optional]
    print(f"\nRadi: {len(checks) - len(missing)} · Ne razrešava se: {len(missing)}")
    if missing:
        print("Popravi u eturista/portal/selectors.py:")
        for check in missing:
            print(f"  - {check.locator.name}: {check.locator.description}")
    return 1 if missing else 0


def _check_system(prepare_driver: bool) -> int:
    from eturista.provera import ispisi, proveri_sistem

    return ispisi(proveri_sistem(sa_drajverom=prepare_driver))


def _run_fake_portal() -> int:
    from fake_portal.app import main as fake_main

    fake_main()
    return 0


def _prepare_signature(ulaz: str, izlaz: str) -> int:
    from alati.pripremi_potpis import main as pripremi_main

    return pripremi_main([ulaz, izlaz])


def _calibrate(pdf_path: str) -> int:
    """Pokaži gde bi potpis pao na zadatom vaučeru, bez utiskivanja slike.

    Snima kopiju sa **crvenim okvirom** na mestu potpisa, pa se ``ETURISTA_POTPIS_*``
    podešava gledanjem umesto pogađanjem.
    """
    import io
    from pathlib import Path

    from pypdf import PdfReader, PdfWriter
    from reportlab.lib.units import mm
    from reportlab.pdfgen import canvas

    from eturista.config import Config
    from eturista.potpis import Raspored, nadji_sidro, okvir_potpisa

    Config.load()  # samo da .env bude učitan pre Raspored.iz_env()
    raspored = Raspored.iz_env()
    pdf = Path(pdf_path).expanduser()
    if not pdf.is_file():
        print(f"Nema fajla: {pdf}")
        return 2

    print(f"Vaučer: {pdf}")
    print(
        f"Raspored: visina {raspored.visina} mm · pomak x {raspored.pomak_x} mm · "
        f"pomak y {raspored.pomak_y} mm · najveća širina {raspored.max_sirina} mm"
    )

    citac = PdfReader(pdf)
    pisac = PdfWriter()
    nadeno = 0

    for broj, strana in enumerate(citac.pages, start=1):
        sidro = nadji_sidro(strana)
        if sidro is not None:
            x, y = sidro
            visina = raspored.visina * mm
            sirina = min(visina * 3.0, raspored.max_sirina * mm)
            levo = x + raspored.pomak_x * mm - sirina / 2
            dole = y - raspored.pomak_y * mm

            print(f"  strana {broj}: sidro na x={x:.1f} y={y:.1f}")
            print(
                f"    potpis 3:1 bi zauzeo {sirina/mm:.1f} x {visina/mm:.1f} mm, "
                f"donji levi ugao ({levo:.1f}, {dole:.1f})"
            )

            bafer = io.BytesIO()
            sloj = canvas.Canvas(
                bafer,
                pagesize=(float(strana.mediabox.width), float(strana.mediabox.height)),
            )
            sloj.setStrokeColorRGB(0.85, 0.1, 0.1)
            sloj.setLineWidth(0.7)
            sloj.rect(levo, dole, sirina, visina)
            sloj.save()
            strana.merge_page(PdfReader(io.BytesIO(bafer.getvalue())).pages[0])
            nadeno += 1
        pisac.add_page(strana)

    if not nadeno:
        print("  natpis za potpis ugostitelja nije nađen - potpisivanje ne bi radilo")
        return 1

    izlaz = pdf.with_name(f"{pdf.stem}_kalibracija.pdf")
    with open(izlaz, "wb") as fajl:
        pisac.write(fajl)
    print(f"\nOtvori i pogledaj crveni okvir: {izlaz}")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(
        prog="eturista",
        description="Prijava gostiju na portal eTurista.",
    )
    parser.add_argument(
        "--proveri-selektore",
        action="store_true",
        help="prijavi se na portal i proveri koji selektori i dalje važe",
    )
    parser.add_argument("--nalog", help="naziv naloga iz .env (podrazumevano prvi)")
    parser.add_argument(
        "--lazni-portal",
        action="store_true",
        help="pokreni lokalni lažni portal za probu",
    )
    parser.add_argument(
        "--pripremi-potpis",
        nargs=2,
        metavar=("ULAZ", "IZLAZ"),
        help="screenshot potpisa pretvori u providni PNG za utiskivanje u vaučer",
    )
    parser.add_argument(
        "--kalibracija",
        metavar="PDF",
        help="pokaži gde bi potpis pao na ovom vaučeru, sa crvenim okvirom",
    )
    parser.add_argument(
        "--provera-sistema",
        action="store_true",
        help="proveri ima li Python, biblioteke, Chrome, git i podešene naloge",
    )
    parser.add_argument(
        "--pripremi-drajver",
        action="store_true",
        help="uz --provera-sistema: odmah skini chromedriver, da prva tura ne čeka",
    )
    args = parser.parse_args()

    if args.lazni_portal:
        return _run_fake_portal()
    if args.pripremi_potpis:
        return _prepare_signature(*args.pripremi_potpis)
    if args.kalibracija:
        return _calibrate(args.kalibracija)
    if args.provera_sistema:
        return _check_system(args.pripremi_drajver)
    if args.proveri_selektore:
        return _check_selectors(args.nalog)
    return _run_gui()


if __name__ == "__main__":
    sys.exit(main())

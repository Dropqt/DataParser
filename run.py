#!/usr/bin/env python3
"""Ulazna tačka.

    python run.py                      # aplikacija
    python run.py --proveri-selektore  # provera da li selektori i dalje važe na portalu
    python run.py --lazni-portal       # lokalni lažni portal za probu, bez pravog sajta
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
#: nekoliko stotina znakova, pa bi bez skraćivanja pojeo ceo ekran — a ono što se iz
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
        print("Nema podešenih naloga — napravi .env po uzoru na .env.example.")
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


def _run_fake_portal() -> int:
    from fake_portal.app import main as fake_main

    fake_main()
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
    args = parser.parse_args()

    if args.lazni_portal:
        return _run_fake_portal()
    if args.proveri_selektore:
        return _check_selectors(args.nalog)
    return _run_gui()


if __name__ == "__main__":
    sys.exit(main())

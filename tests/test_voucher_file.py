"""Provera preuzetog fajla pre nego što postane vaučer.

Štampa na portalu ume da pukne i tada umesto vaučera stigne fajl sa greškom - viđeno
29.07.2026, naziv ``Greska u stampi rezervacije.pdf``. Da se gleda samo nastavak, taj
fajl bi bio preimenovan u ``2026_PREZIME_IME.pdf``, potpisan i poslat gostu. Zato se
gleda i naziv i sadržaj.
"""

from __future__ import annotations

import unicodedata

import pytest
from reportlab.lib.pagesizes import letter
from reportlab.pdfgen import canvas

from eturista.portal.voucher_page import why_not_voucher


@pytest.fixture
def pravi_pdf(tmp_path):
    putanja = tmp_path / "vaucer-1.pdf"
    c = canvas.Canvas(str(putanja), pagesize=letter)
    c.drawString(72, 700, "POTVRDA O REZERVACIJI")
    c.save()
    return putanja


def test_ispravan_vaucer_prolazi(pravi_pdf):
    assert why_not_voucher(pravi_pdf) == ""


def test_greska_se_hvata_i_kad_je_ispravan_pdf(tmp_path, pravi_pdf):
    """Najopasniji slučaj: sadržaj je uredan PDF, ali je greška - vidi se samo po nazivu."""
    greska = tmp_path / "Greska u stampi rezervacije.pdf"
    greska.write_bytes(pravi_pdf.read_bytes())

    assert "greškom" in why_not_voucher(greska)


@pytest.mark.parametrize(
    "ime",
    [
        # Naziv koji portal stvarno šalje.
        "Greska u stampi rezervacije.pdf",
        # Naziv nije uvek isti - bitno je da je reč negde u njemu.
        "greska.pdf",
        "GRESKA.pdf",
        "rezervacija-greska-2026.pdf",
        "izvestaj_o_gresci.pdf",
        "print-error-10023264.pdf",
        "exception.pdf",
    ],
)
def test_greska_u_nazivu_u_bilo_kom_obliku(tmp_path, ime):
    fajl = tmp_path / ime
    fajl.write_bytes(b"%PDF-1.4 nesto")
    assert why_not_voucher(fajl) != ""


@pytest.mark.parametrize("oblik", ["NFC", "NFD"])
def test_kvacice_ne_zavise_od_zapisa(tmp_path, oblik):
    """Isto slovo stiže u dva oblika: kao jedan znak ili kao slovo + kvačica.

    Portal trenutno šalje naziv bez kvačica, ali razloženi oblik je na ovom sistemu
    već viđen (``2025 RADICA MESAREVIĆ.pdf``), pa poređenje ne sme da zavisi od
    toga kako je naziv zapisan.
    """
    ime = unicodedata.normalize(oblik, "Greška u štampi rezervacije.pdf")
    fajl = tmp_path / ime
    fajl.write_bytes(b"%PDF-1.4 nesto")

    assert "greškom" in why_not_voucher(fajl)


@pytest.mark.parametrize("ime", ["vaucer-1.pdf", "2026_PETROVIC_MARKO.pdf", "rezervacija.pdf"])
def test_obican_naziv_ne_okida_lazno(tmp_path, ime, pravi_pdf):
    fajl = tmp_path / ime
    fajl.write_bytes(pravi_pdf.read_bytes())
    assert why_not_voucher(fajl) == ""


def test_html_sa_nastavkom_pdf(tmp_path):
    """Ono što portal pošalje kad štampa pukne a naziv ne oda grešku."""
    fajl = tmp_path / "rezervacija.pdf"
    fajl.write_bytes(b"<html><body>Greska prilikom stampe.</body></html>")

    assert "sadržaj nije PDF" in why_not_voucher(fajl)


def test_nije_pdf_po_nastavku(tmp_path):
    fajl = tmp_path / "rezervacija.html"
    fajl.write_bytes(b"<html></html>")

    assert "nije PDF" in why_not_voucher(fajl)


def test_polovan_pdf(tmp_path):
    """Zaglavlje je tu, ostatak nije - preuzimanje prekinuto u pola."""
    fajl = tmp_path / "vaucer.pdf"
    fajl.write_bytes(b"%PDF-1.4\n1 0 obj\n<< /Type /Catalog")

    assert why_not_voucher(fajl) != ""


def test_prazan_fajl(tmp_path):
    fajl = tmp_path / "vaucer.pdf"
    fajl.write_bytes(b"")

    assert why_not_voucher(fajl) != ""

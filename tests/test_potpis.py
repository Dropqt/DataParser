"""Utiskivanje potpisa u vaučer.

Uzorak vaučera se pravi u samom testu, latinicom (``POTPIS UGOSTITELJA``), jer base-14
Helvetica nema ćirilicu a font sa sistema ne sme da bude uslov da testovi prođu. Ćirilica
je provereno ista - vidi ``test_cirilicno_sidro_na_pravom_vauceru`` na dnu, koji se
pušta samo kad se zada putanja do pravog vaučera.
"""

from __future__ import annotations

import os
from pathlib import Path

import pytest
from PIL import Image
from pypdf import PdfReader
from reportlab.lib.pagesizes import letter
from reportlab.lib.units import mm
from reportlab.pdfgen import canvas

from eturista.potpis import (
    MARKER,
    PotpisError,
    Raspored,
    je_potpisan,
    nadji_sidro,
    okvir_potpisa,
    potpisi_folder,
    potpisi_pdf,
)

#: Isti položaj kao na pravom vaučeru, da se i brojevi iz Rasporeda provere.
SIDRO_X = 360.1
SIDRO_Y = 304.9


def napravi_vaucer(putanja: Path, sidro: str = "POTPIS UGOSTITELJA") -> Path:
    """Uzorak vaučera sa istim rasporedom kao pravi: naslov, sidro, pa potpis gosta."""
    c = canvas.Canvas(str(putanja), pagesize=letter)
    c.setFont("Helvetica", 12)
    # Naslov sadrži reč UGOSTITELJA samu za sebe - ne sme da bude pobrkan sa sidrom.
    c.drawString(72, 548, "PODACI O PRIJAVI UGOSTITELJA ZA SEMU DODELE VAUCERA")
    c.drawString(72, 341, "Period rezervacije: 10.08.2025 - 15.08.2025")
    c.drawString(SIDRO_X, SIDRO_Y, sidro)
    c.line(361, 274, 508, 274)
    # Potpis korisnika je niže i ne sme da bude pobrkan sa sidrom.
    c.drawString(360, 100, "POTPIS KORISNIKA")
    c.line(361, 70, 508, 70)
    c.save()
    return putanja


def napravi_potpis(putanja: Path, sirina: int = 300, visina: int = 110) -> Path:
    slika = Image.new("RGBA", (sirina, visina), (0, 0, 0, 0))
    for x in range(10, sirina - 10):
        for d in range(-3, 4):
            slika.putpixel((x, visina // 2 + d), (25, 25, 32, 255))
    slika.save(putanja)
    return putanja


@pytest.fixture
def vaucer(tmp_path):
    return napravi_vaucer(tmp_path / "vaucer.pdf")


@pytest.fixture
def potpis(tmp_path):
    return napravi_potpis(tmp_path / "potpis.png")


# -- traženje sidra ---------------------------------------------------------

def test_sidro_se_nalazi_na_tacnom_mestu(vaucer):
    x, y = nadji_sidro(PdfReader(vaucer).pages[0])
    assert x == pytest.approx(SIDRO_X, abs=1.0)
    assert y == pytest.approx(SIDRO_Y, abs=1.0)


def test_potpis_korisnika_i_naslov_se_ne_hvataju(tmp_path):
    """Bez para reči sidro bi palo na potpis gosta ili u naslov iznad."""
    pdf = tmp_path / "bez.pdf"
    c = canvas.Canvas(str(pdf), pagesize=letter)
    c.setFont("Helvetica", 12)
    c.drawString(72, 548, "PODACI O PRIJAVI UGOSTITELJA ZA SEMU DODELE VAUCERA")
    c.drawString(360, 100, "POTPIS KORISNIKA")
    c.save()

    assert nadji_sidro(PdfReader(pdf).pages[0]) is None


def test_sidro_razbijeno_na_vise_komada_se_i_dalje_nalazi(tmp_path):
    """PDF sme da razbije natpis; grupisanje po redu mora da ga sklopi nazad."""
    pdf = tmp_path / "razbijeno.pdf"
    c = canvas.Canvas(str(pdf), pagesize=letter)
    c.setFont("Helvetica", 12)
    c.drawString(SIDRO_X, SIDRO_Y, "POTPIS")
    c.drawString(SIDRO_X + 55, SIDRO_Y, "UGOSTITELJA")
    c.save()

    x, y = nadji_sidro(PdfReader(pdf).pages[0])
    assert x == pytest.approx(SIDRO_X, abs=1.0)


def test_vaucer_bez_sidra_daje_gresku(tmp_path, potpis):
    pdf = tmp_path / "prazan.pdf"
    canvas.Canvas(str(pdf), pagesize=letter).save()

    with pytest.raises(PotpisError, match="natpis"):
        potpisi_pdf(pdf, potpis)


# -- raspored ---------------------------------------------------------------

def test_potpis_sedi_na_crti_i_ne_dodiruje_natpis(potpis):
    """Prostora ima svega 28 pt; podrazumevane vrednosti moraju da stanu u njega."""
    levo, dole, sirina, visina = okvir_potpisa(SIDRO_X, SIDRO_Y, potpis, Raspored())

    assert dole < 274.1, "potpis mora da prelazi preko crte, kao rukom pisan"
    assert dole + visina < 302.3, "gornja ivica ne sme u natpis iznad"
    assert levo > 361.0 and levo + sirina < 508.8, "potpis mora da stane na crtu"


def test_preveliki_potpis_se_smanjuje_bez_razvlacenja(tmp_path):
    """Neko ima dugačak potpis - mora da se smanji ceo, ne da se spljošti."""
    siroki = napravi_potpis(tmp_path / "siroki.png", sirina=2000, visina=100)
    _, _, sirina, visina = okvir_potpisa(SIDRO_X, SIDRO_Y, siroki, Raspored())

    assert sirina == pytest.approx(Raspored().max_sirina * mm, abs=0.1)
    assert sirina / visina == pytest.approx(20.0, rel=0.01)


def test_raspored_cita_env(monkeypatch):
    monkeypatch.setenv("ETURISTA_POTPIS_VISINA", "9,5")   # zarez kao u srpskom Excelu
    monkeypatch.setenv("ETURISTA_POTPIS_POMAK_X", "bezveze")

    raspored = Raspored.iz_env()
    assert raspored.visina == 9.5
    assert raspored.pomak_x == Raspored().pomak_x, "besmislena vrednost pada na podrazumevanu"


# -- utiskivanje ------------------------------------------------------------

def test_potpisan_vaucer_ostaje_ispravan_pdf(vaucer, potpis):
    assert potpisi_pdf(vaucer, potpis) is True

    assert vaucer.read_bytes().startswith(b"%PDF")
    assert je_potpisan(vaucer)
    tekst = PdfReader(vaucer).pages[0].extract_text()
    assert "POTPIS UGOSTITELJA" in tekst, "tekst vaučera mora da preživi utiskivanje"


def test_originalni_metapodaci_prezive(tmp_path, potpis):
    """Bez ovoga pypdf upiše sebe kao autora i vaučer izgleda kao tuđ dokument."""
    pdf = tmp_path / "sa_autorom.pdf"
    c = canvas.Canvas(str(pdf), pagesize=letter)
    c.setAuthor("MTTT")
    c.setFont("Helvetica", 12)
    c.drawString(SIDRO_X, SIDRO_Y, "POTPIS UGOSTITELJA")
    c.save()

    potpisi_pdf(pdf, potpis)

    metapodaci = PdfReader(pdf).metadata
    assert metapodaci["/Author"] == "MTTT"
    assert metapodaci[MARKER] == potpis.name


def test_drugi_prolaz_ne_dira_fajl(vaucer, potpis):
    potpisi_pdf(vaucer, potpis)
    posle_prvog = vaucer.read_bytes()

    assert potpisi_pdf(vaucer, potpis) is False
    assert vaucer.read_bytes() == posle_prvog, "dvostruki potpis bi se video na vaučeru"


def test_original_se_cuva(tmp_path, vaucer, potpis):
    pre = vaucer.read_bytes()
    originali = tmp_path / "_bez_potpisa"

    potpisi_pdf(vaucer, potpis, original_dir=originali)

    assert (originali / vaucer.name).read_bytes() == pre


def test_nema_slike_potpisa(vaucer, tmp_path):
    with pytest.raises(PotpisError, match="nema slike"):
        potpisi_pdf(vaucer, tmp_path / "ne-postoji.png")


def test_neuspeh_ne_ostavlja_polovan_fajl(tmp_path, potpis):
    """Vaučer bez sidra mora da ostane bajt-u-bajt isti."""
    pdf = tmp_path / "prazan.pdf"
    canvas.Canvas(str(pdf), pagesize=letter).save()
    pre = pdf.read_bytes()

    with pytest.raises(PotpisError):
        potpisi_pdf(pdf, potpis)

    assert pdf.read_bytes() == pre
    assert not list(tmp_path.glob("*.novi"))


# -- ceo folder -------------------------------------------------------------

def test_potpisivanje_celog_foldera(tmp_path, potpis):
    folder = tmp_path / "vauceri"
    (folder / "gost@primer.rs").mkdir(parents=True)
    napravi_vaucer(folder / "prvi.pdf")
    napravi_vaucer(folder / "gost@primer.rs" / "drugi.pdf")
    canvas.Canvas(str(folder / "bez_sidra.pdf"), pagesize=letter).save()

    potpisano, preskoceno, greske = potpisi_folder(folder, potpis)

    assert (potpisano, preskoceno) == (2, 0)
    assert [pdf.name for pdf, _ in greske] == ["bez_sidra.pdf"]
    assert (folder / "_bez_potpisa" / "prvi.pdf").is_file()

    # Drugi prolaz ne sme da udvostruči potpis ni da krene po originalima.
    potpisano, preskoceno, _ = potpisi_folder(folder, potpis)
    assert (potpisano, preskoceno) == (0, 2)


# -- pravi vaučer -----------------------------------------------------------

@pytest.mark.skipif(
    not os.getenv("ETURISTA_TEST_VAUCER"),
    reason="zadaj ETURISTA_TEST_VAUCER=putanja do pravog vaučera (ima lične podatke, ne ide u repo)",
)
def test_cirilicno_sidro_na_pravom_vauceru(tmp_path, potpis):
    izvor = Path(os.environ["ETURISTA_TEST_VAUCER"]).expanduser()
    kopija = tmp_path / "pravi.pdf"
    kopija.write_bytes(izvor.read_bytes())

    x, y = nadji_sidro(PdfReader(kopija).pages[0])
    assert (x, y) == pytest.approx((SIDRO_X, SIDRO_Y), abs=1.0)
    assert potpisi_pdf(kopija, potpis) is True

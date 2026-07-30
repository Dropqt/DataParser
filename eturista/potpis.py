"""Utiskivanje slike potpisa u PDF vaučer.

Vaučer ima pri dnu polje **ПОТПИС УГОСТИТЕЉА** - natpis, pa vodoravna crta ispod njega.
Potpis se ne postavlja na fiksne koordinate nego se **traži natpis u tekstu PDF-a** i
meri od njega. Fiksne koordinate bi otkazale prvog dana kad ministarstvo pomeri red u
obrascu; natpis mora da ostane jer se po njemu zna gde se potpisuje.

Izmereno na vaučeru iz 2025 (612x792 pt): natpis je na x=360.1, osnovna linija y=304.9,
crta za potpis 30.8 pt ispod nje. Odatle podrazumevane vrednosti u :class:`Raspored`.
Potpis prelazi malo preko crte - tako izgleda i kad se potpisuje rukom.

Isti dokument sadrži i ``ПОТПИС КОРИСНИКА`` (potpis gosta, ne naš) i reč ``УГОСТИТЕЉА``
u naslovu iznad. Zato sidro traži **obe reči zajedno** - inače potpis završi na tuđem
mestu.
"""

from __future__ import annotations

import io
import os
import shutil
from dataclasses import dataclass
from pathlib import Path

from pypdf import PdfReader, PdfWriter
from reportlab.lib.units import mm
from reportlab.lib.utils import ImageReader
from reportlab.pdfgen import canvas

#: Natpis po kom se traži mesto za potpis, ćirilicom i latinicom.
SIDRA = ("ПОТПИС УГОСТИТЕЉА", "POTPIS UGOSTITELJA")

#: Ključ u metapodacima PDF-a - po njemu se zna da je vaučer već potpisan.
MARKER = "/ETuristaPotpis"

#: Folder sa nepotpisanim originalima, unutar foldera sa vaučerima. Stoji iznad
#: foldera po e-mail adresama, pa ne ulazi u grupu koja se kači na mejl.
ORIGINALI = "_bez_potpisa"


class PotpisError(Exception):
    """Potpis nije mogao da se utisne. Ne prekida turu - gost ostaje prijavljen."""


@dataclass(frozen=True)
class Raspored:
    """Gde i koliki potpis ide, sve u milimetrima, mereno od natpisa.

    Podrazumevane vrednosti su izmerene na pravom vaučeru i proverene gledanjem.
    Menjaju se preko ``.env`` ako ministarstvo promeni obrazac; ``run.py --kalibracija``
    pokazuje gde bi potpis pao sa trenutnim vrednostima.
    """

    #: Visina potpisa. Od donje ivice natpisa do crte ima svega 28 pt (9.9 mm), pa
    #: viši potpis od ovoga počinje da udara u natpis.
    visina: float = 12.0
    #: Vodoravno, od početka natpisa do **sredine** potpisa.
    pomak_x: float = 26.4
    #: Naniže, od osnovne linije natpisa do **donje ivice** potpisa. Crta je na
    #: 10.9 mm, pa potpis prelazi preko nje za oko 3.5 mm.
    pomak_y: float = 14.5
    #: Gornja granica širine - crta je duga 52 mm. Širi potpis se srazmerno smanji.
    max_sirina: float = 50.0

    @classmethod
    def iz_env(cls) -> "Raspored":
        podrazumevano = cls()

        def broj(kljuc: str, podrazumevana: float) -> float:
            sirovo = os.getenv(kljuc, "").strip().replace(",", ".")
            try:
                return float(sirovo) if sirovo else podrazumevana
            except ValueError:
                return podrazumevana

        return cls(
            visina=broj("ETURISTA_POTPIS_VISINA", podrazumevano.visina),
            pomak_x=broj("ETURISTA_POTPIS_POMAK_X", podrazumevano.pomak_x),
            pomak_y=broj("ETURISTA_POTPIS_POMAK_Y", podrazumevano.pomak_y),
            max_sirina=broj("ETURISTA_POTPIS_MAX_SIRINA", podrazumevano.max_sirina),
        )


def nadji_sidro(strana) -> tuple[float, float] | None:
    """Nađi natpis za potpis ugostitelja. Vraća ``(x, y)`` u tačkama, ili ``None``.

    Komadi teksta se grupišu po osnovnoj liniji pa spajaju u jedan red. Na vaučeru iz
    2025 natpis stiže kao jedan komad, ali PDF sme da ga razbije na više delova - tada
    bi traženje po komadu promašilo, a po redu ne.
    """
    redovi: dict[float, list[tuple[float, str]]] = {}

    def posetilac(tekst, cm, tm, font, velicina) -> None:
        if tekst and tekst.strip():
            redovi.setdefault(round(tm[5], 1), []).append((tm[4], tekst))

    strana.extract_text(visitor_text=posetilac)

    for y, komadi in sorted(redovi.items()):
        komadi.sort()
        spojeno = " ".join(" ".join(tekst.split()) for _, tekst in komadi).upper()
        if any(sidro in spojeno for sidro in SIDRA):
            return komadi[0][0], y
    return None


def okvir_potpisa(
    x: float, y: float, slika: Path, raspored: Raspored
) -> tuple[float, float, float, float]:
    """Gde tačno legne slika: ``(levo, dole, širina, visina)`` u tačkama."""
    crtez = ImageReader(str(slika))
    px_sirina, px_visina = crtez.getSize()

    visina = raspored.visina * mm
    sirina = visina * px_sirina / px_visina
    if sirina > raspored.max_sirina * mm:
        # Preširok potpis se smanjuje ceo, ne razvlači - odnos stranica mora da ostane.
        sirina = raspored.max_sirina * mm
        visina = sirina * px_visina / px_sirina

    levo = x + raspored.pomak_x * mm - sirina / 2
    dole = y - raspored.pomak_y * mm
    return levo, dole, sirina, visina


def je_potpisan(pdf: Path) -> bool:
    """Da li PDF već nosi naš marker. Greška u čitanju znači 'ne znam' - probaj."""
    try:
        metapodaci = PdfReader(pdf).metadata
    except Exception:
        return False
    return bool(metapodaci and MARKER in metapodaci)


def potpisi_pdf(
    pdf: Path,
    slika: Path,
    raspored: Raspored | None = None,
    *,
    original_dir: Path | None = None,
) -> bool:
    """Utisni potpis u vaučer, na licu mesta. Vraća ``False`` ako je već potpisan.

    ``original_dir`` - ako je zadat, nepotpisana kopija se snima tamo pre izmene.

    Piše se u privremeni fajl pa se preimenuje preko originala, tako da prekid usred
    pisanja ne ostavi pola vaučera.
    """
    raspored = raspored or Raspored()
    pdf = Path(pdf)
    slika = Path(slika)

    if not slika.is_file():
        raise PotpisError(f"nema slike potpisa: {slika}")
    if je_potpisan(pdf):
        return False

    try:
        citac = PdfReader(pdf)
    except Exception as exc:
        raise PotpisError(f"PDF ne može da se pročita: {exc}") from exc

    if citac.is_encrypted:
        raise PotpisError("PDF je zaštićen, ne može da se menja")

    pisac = PdfWriter()
    utisnuto = 0

    for strana in citac.pages:
        sidro = nadji_sidro(strana)
        if sidro is not None:
            levo, dole, sirina, visina = okvir_potpisa(*sidro, slika, raspored)
            bafer = io.BytesIO()
            sloj = canvas.Canvas(
                bafer,
                pagesize=(float(strana.mediabox.width), float(strana.mediabox.height)),
            )
            # mask="auto" poštuje alfa kanal - bez toga bi providna pozadina PNG-a
            # postala bela kutija preko crte.
            sloj.drawImage(
                ImageReader(str(slika)), levo, dole, width=sirina, height=visina, mask="auto"
            )
            sloj.save()
            strana.merge_page(PdfReader(io.BytesIO(bafer.getvalue())).pages[0])
            utisnuto += 1
        pisac.add_page(strana)

    if not utisnuto:
        raise PotpisError("nije nađen natpis za potpis ugostitelja")

    # Originalni metapodaci (autor MTTT, datum izdavanja) moraju da prežive - bez ovoga
    # ih pypdf zameni svojima i vaučer izgleda kao da ga je izdao neko drugi.
    if citac.metadata:
        pisac.add_metadata(citac.metadata)
    pisac.add_metadata({MARKER: slika.name})

    if original_dir is not None:
        # Uvezeno ovde, ne na vrhu: ``driver`` povlači selenium, a ovaj modul inače
        # radi bez njega (koristi ga i alat za pripremu potpisa, i testovi).
        from .driver import unique_path

        original_dir = Path(original_dir)
        original_dir.mkdir(parents=True, exist_ok=True)
        # Originali svih gostiju idu u isti folder, a folderi po e-mail adresama mogu
        # da imaju istoimene fajlove - dva gosta sa istim imenom i prezimenom idu u
        # ``2026_PETROVIC_MARKO.pdf`` oba. Bez ovoga bi drugi tiho pregazio prvi.
        shutil.copy2(pdf, unique_path(original_dir, pdf.name))

    privremeni = pdf.with_name(pdf.name + ".novi")
    try:
        with open(privremeni, "wb") as fajl:
            pisac.write(fajl)
        os.replace(privremeni, pdf)
    except OSError:
        privremeni.unlink(missing_ok=True)
        raise

    return True


def potpisi_folder(
    folder: Path, slika: Path, raspored: Raspored | None = None
) -> tuple[int, int, list[tuple[Path, str]]]:
    """Potpiši sve vaučere u folderu. Vraća ``(potpisano, preskočeno, greške)``.

    Za naknadno potpisivanje vaučera preuzetih pre nego što je ova mogućnost postojala.
    Već potpisani se prepoznaju po markeru i preskaču, pa alat sme da se pusti dvaput.
    Folder sa originalima se preskače da se ne bi potpisali i oni.
    """
    folder = Path(folder)
    potpisano = 0
    preskoceno = 0
    greske: list[tuple[Path, str]] = []

    for pdf in sorted(folder.rglob("*.pdf")):
        if ORIGINALI in pdf.parts:
            continue
        try:
            if potpisi_pdf(pdf, slika, raspored, original_dir=folder / ORIGINALI):
                potpisano += 1
            else:
                preskoceno += 1
        except (PotpisError, OSError) as exc:
            greske.append((pdf, str(exc)))

    return potpisano, preskoceno, greske

#!/usr/bin/env python3
"""Screenshot potpisa -> providni PNG spreman za utiskivanje u vaučer.

    .venv/bin/python run.py --pripremi-potpis ~/Slike/potpis.png potpisi/danica.png

Radi lokalno, bez interneta. Online alati za skidanje pozadine ovde ne pomažu iz dva
razloga: seku po pragu pa ostave nazubljene ivice, a sliku sopstvenog potpisa ionako
ne treba slati na tuđi server.

Tri koraka, svaki rešava po jedan problem sa screenshot-om:

1. **Bele margine.** Screenshot uhvati i papir okolo. Bez odsecanja bi potpis u vaučeru
   ispao premalen i pomeren u stranu.
2. **Providnost.** Pozadina je čisto bela, pa se providnost izvodi iz svetline piksela.
   Poluprovidne ivice poteza ostaju poluprovidne - odatle mek potez umesto stepenica.
3. **Bledilo.** Skenirani potpis je srednje siv, ne crn. Skala se rasteže tako da
   najtamniji potez postane pun, inače potpis na vaučeru izgleda izbledelo.
"""

from __future__ import annotations

import sys
from pathlib import Path

from PIL import Image

#: Sve svetlije od ovoga je papir, ne trag.
BELA = 250
#: Ispod ovoliko providnosti je šum sa screenshot-a, ne trag.
PRAG_SUMA = 0.06
#: Boja mastila. Namerno ne čisto crna - potpis hemijskom nikad nije čisto crn.
MASTILO = (25, 25, 32)


def _na_belu(slika: Image.Image) -> Image.Image:
    """Spljošti na belu podlogu pa u sivu skalu - screenshot ume već da ima alfa kanal."""
    if slika.mode in ("RGBA", "LA", "P"):
        slika = slika.convert("RGBA")
        podloga = Image.new("RGBA", slika.size, (255, 255, 255, 255))
        slika = Image.alpha_composite(podloga, slika)
    return slika.convert("L")


def _crna_tacka(siva: Image.Image) -> int:
    """Koliko je taman najtamniji stvarni trag.

    Gleda se samo mastilo, ne cela slika: papir je preko 97% piksela, pa bi percentil
    preko svih piksela vratio belu i kontrast se ne bi ni pomerio. Uzima se 2. percentil
    mastila umesto apsolutnog minimuma - jedan usamljen taman piksel (prašina, ivica
    prozora) ne sme da odredi skalu za celu sliku.
    """
    # tobytes() umesto getdata(): u sivoj skali je jedan bajt po pikselu, radi na svim
    # verzijama Pillow-a i ne vuče upozorenje o zastarelosti.
    mastilo = sorted(v for v in siva.tobytes() if v < BELA - 15)
    if not mastilo:
        return BELA - 1
    return mastilo[len(mastilo) // 50]


def pripremi(ulaz: Path, izlaz: Path) -> tuple[int, int]:
    """Obradi sliku i snimi je. Vraća dimenzije rezultata."""
    siva = _na_belu(Image.open(ulaz))
    crna = _crna_tacka(siva)
    raspon = max(1, BELA - crna)

    alfa = siva.point(lambda v: min(255, max(0, int((BELA - v) * 255 / raspon))))
    # Šum sa screenshot-a je jedva vidljiv na beloj, ali bi u vaučeru posivio
    # pravougaonik oko potpisa.
    alfa = alfa.point(lambda a: 0 if a < PRAG_SUMA * 255 else a)

    okvir = alfa.getbbox()
    if okvir is None:
        raise SystemExit(f"{ulaz.name}: nema nijednog traga, samo papir")

    potpis = Image.new("RGBA", siva.size, MASTILO + (0,))
    potpis.putalpha(alfa)
    potpis = potpis.crop(okvir)

    izlaz.parent.mkdir(parents=True, exist_ok=True)
    potpis.save(izlaz)
    return potpis.size


def main(argv: list[str]) -> int:
    if len(argv) != 2:
        print(__doc__)
        return 2

    ulaz, izlaz = Path(argv[0]).expanduser(), Path(argv[1]).expanduser()
    if not ulaz.is_file():
        print(f"Nema fajla: {ulaz}")
        return 2

    sirina, visina = pripremi(ulaz, izlaz)
    odnos = sirina / visina
    # Potpis je u vaučeru visok 12 mm; odatle ispada koliko je stvarno oštar na štampi.
    dpi = sirina / (12.0 * odnos / 25.4)
    print(f"{ulaz.name} → {izlaz}")
    print(f"  {sirina}x{visina} px, odnos {odnos:.2f}")
    print(f"  u vaučeru: 12.0 x {12.0 * odnos:.1f} mm, oštrina {dpi:.0f} dpi")
    if dpi < 200:
        print("  napomena: ispod 200 dpi se na štampi vidi mekoća - vredi uslikati izbliza")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))

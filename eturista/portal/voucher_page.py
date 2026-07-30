"""Preuzimanje PDF vaučera i imenovanje fajla."""

from __future__ import annotations

import shutil
import time
import unicodedata
from pathlib import Path

from selenium.common.exceptions import WebDriverException

from ..driver import BrowserSession, unique_path
from ..errors import ErrorKind, PortalError
from ..models import Guest
from . import selectors as S
from .base_page import BasePage

#: Koliko čekamo da se PDF preuzme pre nego što odustanemo.
DOWNLOAD_TIMEOUT = 60.0

#: Koliko čekamo da se dugme za preuzimanje aktivira posle čuvanja rezervacije.
ENABLE_TIMEOUT = 20.0

#: Koliko puta ukupno pokušavamo preuzimanje. Štampa na portalu ume da pukne i tada
#: umesto vaučera stigne fajl sa greškom; sledeći klik obično prođe.
DOWNLOAD_ATTEMPTS = 5

#: Osnovna pauza između pokušaja. Raste sa svakim krugom (3, 6, 9, 12 s): kad štampa
#: pukne zato što snimanje rezervacije još traje, kratko čekanje samo potroši pokušaj.
RETRY_PAUSE = 3.0

#: Reči koje se pojavljuju **u nazivu** fajla kad štampa na portalu pukne - naziv nije
#: uvek isti, ali reč je unutra (viđeno: „greška u štampi rezervacije“). Zato se traži
#: sadržana reč, ne ceo naziv.
#:
#: Piše se **bez kvačica**, jer se naziv pre poređenja provlači kroz :func:`_bez_kvacica`.
#:
#: Provera po sadržaju hvata i ono što nije na ovom spisku, ali greška ume da stigne i
#: kao **ispravan PDF** sa porukom unutra - tada je naziv jedino po čemu se prepoznaje.
#: Naziv koji se ovde gleda je onaj koji je dao portal, pre preimenovanja u ime gosta,
#: pa nema opasnosti da se poklopi sa prezimenom.
ERROR_NAMES = ("greska", "greske", "gresci", "error", "exception")


def _bez_kvacica(tekst: str) -> str:
    """Mala slova bez kvačica, da poređenje ne zavisi od zapisa.

    Isto slovo ume da stigne u dva oblika: kao jedan znak (``š``) ili kao ``s`` plus
    kombinujuća kvačica. Na ovom sistemu je već viđeno drugo - fajl
    ``2025 RADICA MESAREVIĆ.pdf`` ima ``Ć`` zapisano razloženo. Bez normalizacije bi
    ``"greška" in naziv`` promašilo baš onaj naziv zbog kog je provera i napisana.
    """
    razlozeno = unicodedata.normalize("NFKD", tekst)
    bez = "".join(znak for znak in razlozeno if not unicodedata.combining(znak))
    # ``đ`` nema razlaganje u NFKD, pa se prevodi ručno.
    return bez.lower().replace("đ", "d")


def why_not_voucher(path: Path) -> str:
    """Zašto preuzeti fajl nije upotrebljiv vaučer. Prazan string = sve je u redu.

    Gleda se **sadržaj**, ne samo nastavak: kad štampa na portalu pukne, ume da stigne
    fajl koji se zove ``greska.pdf`` a nije PDF. Bez ove provere bi bio preimenovan u
    ``2026_PREZIME_IME.pdf``, potpisan i poslat gostu.
    """
    naziv = _bez_kvacica(path.stem.strip())
    if any(rec in naziv for rec in ERROR_NAMES):
        return f"portal je poslao fajl sa greškom ({path.name})"
    if path.suffix.lower() != ".pdf":
        return f"preuzet fajl nije PDF ({path.name})"

    try:
        with open(path, "rb") as fajl:
            if fajl.read(5) != b"%PDF-":
                return f"sadržaj nije PDF ({path.name})"
    except OSError as exc:
        return f"preuzet fajl se ne čita: {exc}"

    try:
        from pypdf import PdfReader

        if not PdfReader(path).pages:
            return f"PDF nema nijednu stranu ({path.name})"
    except Exception as exc:  # noqa: BLE001 - svaki kvar u PDF-u je isti zaključak
        return f"PDF je neispravan ({path.name}): {exc}"

    return ""


class VoucherPage(BasePage):
    """Klikne na preuzimanje i sačeka da fajl stvarno legne na disk.

    Stara skripta je posle preuzimanja tražila "najskoriji fajl u ~/Downloads" - što
    uhvati tuđi fajl ako se nešto drugo preuzelo u međuvremenu, i uhvati nedovršen
    fajl ako download još traje. Ovde se pamti stanje foldera pre klika, pa je novi
    fajl jednoznačno određen.
    """

    def __init__(self, driver, session: BrowserSession, timeout: float = 15.0) -> None:
        super().__init__(driver, timeout)
        self.session = session

    def wait_until_enabled(self) -> None:
        """Sačekaj da „Одштампај резервацију“ postane aktivno.

        Dugme je onemogućeno dok rezervacija nije sačuvana. Bez ovog čekanja klik ode u
        prazno ili - gore - portal odštampa potvrdu iz **sadržaja forme**, pa na disk
        legne uredan PDF za rezervaciju koja na portalu ne postoji. Viđeno u probnoj
        turi 29.07.2026, kad potvrda u dijalogu još nije bila kliknuta.
        """
        deadline = time.monotonic() + ENABLE_TIMEOUT
        while time.monotonic() < deadline:
            element = self.find_optional(S.VOUCHER_DOWNLOAD, timeout=1.0)
            try:
                if element is not None and element.is_enabled():
                    return
            except WebDriverException:
                pass  # strana se promenila pod nogama - sledeći krug gleda novi element
            time.sleep(0.3)

        raise PortalError(
            ErrorKind.PDF_DOWNLOAD_FAILED,
            "Dugme za preuzimanje vaučera se nije aktiviralo",
            "rezervacija verovatno nije sačuvana - potvrda u dijalogu nije prošla",
        )

    def download(self, guest: Guest, target_dir: Path, year: int) -> str:
        """Preuzmi vaučer i preimenuj ga. Vraća putanju do snimljenog fajla.

        Štampa na portalu ume da pukne i tada umesto vaučera stigne fajl sa greškom.
        Zato se preuzimanje ponavlja: neispravan fajl se **obriše** (da ne bi bio
        pokupljen u sledećem krugu) i klikne se ponovo. Tek ako ni posle
        ``DOWNLOAD_ATTEMPTS`` puta ne stigne ispravan PDF, gost pada - i tada bez
        ijednog fajla na disku, umesto sa greškom preimenovanom u ime gosta.
        """
        target_dir.mkdir(parents=True, exist_ok=True)
        problem = ""

        for pokusaj in range(1, DOWNLOAD_ATTEMPTS + 1):
            if pokusaj > 1:
                # Sve duža pauza: najčešći uzrok neuspele štampe je da snimanje
                # rezervacije još traje, a to se ne rešava bržim ponavljanjem.
                time.sleep(RETRY_PAUSE * (pokusaj - 1))

            self.wait_until_enabled()
            before = self.session.snapshot_downloads()
            self.click(S.VOUCHER_DOWNLOAD)

            try:
                downloaded = self.session.wait_for_download(before, timeout=DOWNLOAD_TIMEOUT)
            except PortalError as exc:
                problem = exc.message
                continue

            problem = why_not_voucher(downloaded)
            if not problem:
                destination = unique_path(target_dir, guest.pdf_name(year))
                try:
                    shutil.move(str(downloaded), str(destination))
                except OSError as exc:
                    raise PortalError(
                        ErrorKind.PDF_DOWNLOAD_FAILED,
                        f"Ne mogu da premestim vaučer u {target_dir}",
                        str(exc),
                    ) from exc
                return str(destination)

            downloaded.unlink(missing_ok=True)

        raise PortalError(
            ErrorKind.PDF_DOWNLOAD_FAILED,
            f"Vaučer nije preuzet ni iz {DOWNLOAD_ATTEMPTS} pokušaja",
            problem,
        )

    @property
    def is_available(self) -> bool:
        """Da li je preuzimanje vaučera uopšte podešeno (nije zaključano)."""
        return S.VOUCHER_DOWNLOAD.is_ready

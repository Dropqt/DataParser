"""Preuzimanje PDF vaučera i imenovanje fajla."""

from __future__ import annotations

import shutil
from pathlib import Path

from ..driver import BrowserSession, unique_path
from ..errors import ErrorKind, PortalError
from ..models import Guest
from . import selectors as S
from .base_page import BasePage

#: Koliko čekamo da se PDF preuzme pre nego što odustanemo.
DOWNLOAD_TIMEOUT = 60.0


class VoucherPage(BasePage):
    """Klikne na preuzimanje i sačeka da fajl stvarno legne na disk.

    Stara skripta je posle preuzimanja tražila "najskoriji fajl u ~/Downloads" — što
    uhvati tuđi fajl ako se nešto drugo preuzelo u međuvremenu, i uhvati nedovršen
    fajl ako download još traje. Ovde se pamti stanje foldera pre klika, pa je novi
    fajl jednoznačno određen.
    """

    def __init__(self, driver, session: BrowserSession, timeout: float = 15.0) -> None:
        super().__init__(driver, timeout)
        self.session = session

    def download(self, guest: Guest, target_dir: Path, year: int) -> str:
        """Preuzmi vaučer i preimenuj ga. Vraća putanju do snimljenog fajla."""
        before = self.session.snapshot_downloads()
        self.click(S.VOUCHER_DOWNLOAD)

        downloaded = self.session.wait_for_download(before, timeout=DOWNLOAD_TIMEOUT)

        if downloaded.suffix.lower() != ".pdf":
            raise PortalError(
                ErrorKind.PDF_DOWNLOAD_FAILED,
                f"Preuzet fajl nije PDF ({downloaded.name})",
            )

        target_dir.mkdir(parents=True, exist_ok=True)
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

    @property
    def is_available(self) -> bool:
        """Da li je preuzimanje vaučera uopšte podešeno (nije zaključano)."""
        return S.VOUCHER_DOWNLOAD.is_ready

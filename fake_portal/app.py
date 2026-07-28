"""Lažni eTurista portal za razvoj i testiranje.

Pravi portal je delom zaključan do otvaranja registracije za vaučere, a i kad se otvori
ne želimo da svaka izmena u kodu znači pravu prijavu pravog gosta. Ovaj server servira
formu sa **istim atributima** koje traži ``eturista/portal/selectors.py``, pa se ceo tok
- prijava, popunjavanje, odbijen JMBG, čuvanje, preuzimanje vaučera - provozava lokalno.

Ume da simulira i ono što u praksi kvari turu:

* JMBG koji portal odbija (``rejected_jmbgs``)
* spor odgovor (``delay``)
* istek sesije posle N rezervacija (``expire_after``)

Pokretanje ručno:  ``python -m fake_portal.app``
"""

from __future__ import annotations

import json
import re
import threading
import time
from dataclasses import dataclass, field
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs, urlparse

RESERVATION_PATH = "/vauceri/rezervacija-smestaja"

#: Oblik u kom pravi portal sam upisuje datum kad se izabere iz kalendara: ``15.7.2026``.
#: Namerno **ne** prima vodeću nulu - da bi test pao ako se u kodu vrati ``strftime``
#: sa ``%d.%m.%Y``, koje daje ``15.07.2026``.
_DATUM = re.compile(r"[1-9]\d?\.[1-9]\d?\.\d{4}")

_STYLE = """
body { font-family: system-ui, sans-serif; max-width: 640px; margin: 40px auto; padding: 0 16px; }
label { display: block; margin: 12px 0 4px; font-weight: 600; }
input { width: 100%; padding: 8px; font-size: 15px; box-sizing: border-box; }
button { margin-top: 16px; padding: 10px 18px; font-size: 15px; cursor: pointer; }
mat-error { display: block; color: #c62828; margin-top: 4px; font-size: 13px; }
.ok { color: #2e7d32; font-weight: 600; }
mat-toolbar { display: flex; gap: 16px; background: #b71c1c; color: #fff; padding: 8px 12px; }
mat-step-header { display: inline-block; margin-right: 12px; font-weight: 600; opacity: .5; }
mat-step-header[aria-selected="true"] { opacity: 1; }
mat-date-range-input { display: flex; gap: 8px; align-items: center; }
[hidden] { display: none; }
/* Pravi portal skriva <input> čekboksa i crta svoj kvadratić. Zato Selenium ne sme da
   klikne input nego omotač - ovde je isto, da test to zaista proveri. */
.cdk-visually-hidden { position: absolute; width: 1px; height: 1px; overflow: hidden;
                       clip: rect(0 0 0 0); white-space: nowrap; }
.mat-checkbox-inner-container { display: inline-block; width: 18px; height: 18px;
                                border: 2px solid #555; cursor: pointer; }
.mat-checkbox-checked .mat-checkbox-inner-container { background: #b71c1c; }
.mat-checkbox-disabled .mat-checkbox-inner-container { border-color: #bbb; cursor: not-allowed; }
"""

#: Zaglavlje aplikacije - postoji samo posle prijave, po njemu ``LOGGED_IN_MARKER``
#: prepoznaje da sesija nije istekla.
_ZAGLAVLJE = """
<mat-toolbar class="mat-primary">
  <span class="features"><span class="features-item">Vaučeri</span></span>
  <span class="accountAndSettings">Nalog</span>
</mat-toolbar>
"""


def minimal_pdf(text: str = "Vaucer") -> bytes:
    """Najmanji ispravan PDF - dovoljno da se fajl stvarno otvori posle preuzimanja."""
    content = f"BT /F1 24 Tf 40 120 Td ({text}) Tj ET".encode("latin-1", "replace")
    objects = [
        b"<< /Type /Catalog /Pages 2 0 R >>",
        b"<< /Type /Pages /Kids [3 0 R] /Count 1 >>",
        b"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 300 200] "
        b"/Resources << /Font << /F1 5 0 R >> >> /Contents 4 0 R >>",
        b"<< /Length " + str(len(content)).encode() + b" >>\nstream\n" + content + b"\nendstream",
        b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>",
    ]

    out = bytearray(b"%PDF-1.4\n")
    offsets = []
    for number, body in enumerate(objects, start=1):
        offsets.append(len(out))
        out += f"{number} 0 obj\n".encode() + body + b"\nendobj\n"

    xref_at = len(out)
    out += f"xref\n0 {len(objects) + 1}\n".encode()
    out += b"0000000000 65535 f \n"
    for offset in offsets:
        out += f"{offset:010d} 00000 n \n".encode()
    out += (
        f"trailer\n<< /Size {len(objects) + 1} /Root 1 0 R >>\nstartxref\n{xref_at}\n%%EOF\n"
    ).encode()
    return bytes(out)


@dataclass
class PortalState:
    """Podešavanja i brojači lažnog portala."""

    username: str = "test"
    password: str = "test123"
    #: JMBG-ovi koje portal odbija, kao da su nepostojeći u matičnoj evidenciji.
    rejected_jmbgs: set[str] = field(default_factory=set)
    #: Veštačko kašnjenje po zahtevu, u sekundama.
    delay: float = 0.0
    #: Posle ovoliko sačuvanih rezervacija sesija "istekne". None = nikad.
    expire_after: int | None = None
    #: True = registracija za vaučere još nije otvorena, pa je čekboks za izbor prijave
    #: onemogućen. Tako portal izgleda van sezone (viđeno 27.07.2026).
    reservations_locked: bool = False

    sessions: set[str] = field(default_factory=set)
    saved: list[dict] = field(default_factory=list)
    login_attempts: int = 0
    _counter: int = 0

    def new_session(self) -> str:
        self._counter += 1
        token = f"sesija-{self._counter}"
        self.sessions.add(token)
        return token

    def reset(self) -> None:
        self.sessions.clear()
        self.saved.clear()
        self.login_attempts = 0


class _Handler(BaseHTTPRequestHandler):
    state: PortalState  # postavlja FakePortal

    # -- pomoćno ----------------------------------------------------------

    def log_message(self, *_args) -> None:  # tišina u test izlazu
        pass

    def _send(self, body: bytes, status: int = 200, content_type: str = "text/html; charset=utf-8",
              extra_headers: dict[str, str] | None = None) -> None:
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(body)))
        for key, value in (extra_headers or {}).items():
            self.send_header(key, value)
        self.end_headers()
        self.wfile.write(body)

    def _html(self, title: str, body: str, status: int = 200,
              extra_headers: dict[str, str] | None = None) -> None:
        page = (
            f"<!doctype html><html lang='sr'><head><meta charset='utf-8'>"
            f"<title>{title}</title><style>{_STYLE}</style></head><body>{body}</body></html>"
        )
        self._send(page.encode("utf-8"), status, extra_headers=extra_headers)

    def _redirect(self, location: str, extra_headers: dict[str, str] | None = None) -> None:
        self.send_response(302)
        self.send_header("Location", location)
        self.send_header("Content-Length", "0")
        for key, value in (extra_headers or {}).items():
            self.send_header(key, value)
        self.end_headers()

    def _form_data(self) -> dict[str, str]:
        length = int(self.headers.get("Content-Length") or 0)
        raw = self.rfile.read(length).decode("utf-8") if length else ""
        return {key: values[0] for key, values in parse_qs(raw).items()}

    def _session_token(self) -> str | None:
        cookie = self.headers.get("Cookie") or ""
        for part in cookie.split(";"):
            name, _, value = part.strip().partition("=")
            if name == "sesija" and value in self.state.sessions:
                return value
        return None

    # -- rute -------------------------------------------------------------

    def do_GET(self) -> None:  # noqa: N802 (ime traži BaseHTTPRequestHandler)
        if self.state.delay:
            time.sleep(self.state.delay)

        parsed = urlparse(self.path)
        path = parsed.path

        if path in ("/", "/prijava"):
            self._login_page()
        elif path == RESERVATION_PATH:
            self._reservation_page()
        elif path == "/proveri-jmbg":
            self._check_jmbg(parse_qs(parsed.query).get("jmbg", [""])[0])
        elif path == "/vaucer.pdf":
            self._voucher()
        else:
            self._html("Nema stranice", "<h1>404</h1>", status=404)

    def do_POST(self) -> None:  # noqa: N802
        if self.state.delay:
            time.sleep(self.state.delay)

        path = urlparse(self.path).path
        if path == "/prijava":
            self._do_login()
        elif path == RESERVATION_PATH:
            self._do_reservation()
        else:
            self._html("Nema stranice", "<h1>404</h1>", status=404)

    # -- prijava ----------------------------------------------------------

    def _login_page(self, error: str = "") -> None:
        if self._session_token():
            self._redirect(RESERVATION_PATH)
            return
        problem = f"<mat-error>{error}</mat-error>" if error else ""
        self._html(
            "Prijava",
            f"""
            <h1>eTurista - prijava</h1>
            <form method="post" action="/prijava">
              <label for="username">Korisničko ime</label>
              <input id="username" name="username" autocomplete="off">
              <label for="passwordInput">Lozinka</label>
              <input id="passwordInput" name="password" type="password">
              {problem}
              <button type="submit">Prijavi se</button>
            </form>
            """,
        )

    def _do_login(self) -> None:
        data = self._form_data()
        self.state.login_attempts += 1
        if data.get("username") == self.state.username and data.get("password") == self.state.password:
            token = self.state.new_session()
            self._redirect(RESERVATION_PATH, {"Set-Cookie": f"sesija={token}; Path=/"})
        else:
            self._login_page("Pogrešno korisničko ime ili lozinka")

    # -- rezervacija ------------------------------------------------------

    def _reservation_page(self, error: str = "") -> None:
        """Forma u tri koraka, kao na pravom portalu (provereno 27.07.2026).

        Bitno je da se poklopi troje, jer je na tome palo dosta pretpostavki:

        * datumi su **jedan** ``mat-date-range-input`` sa dva ugnežđena polja,
          ``datumSmestajaOd`` / ``datumSmestajaDo`` - ne dva odvojena ``datumOd``;
        * kroz korake se ide dugmetom koje ima **samo ikonicu**, bez teksta;
        * „Odštampaj rezervaciju“ je onemogućeno dok se ne sačuva.
        """
        if not self._session_token():
            self._redirect("/")
            return
        problem = f"<mat-error>{error}</mat-error>" if error else ""
        zakljucano_klasa = " mat-checkbox-disabled" if self.state.reservations_locked else ""
        zakljucano_input = " disabled" if self.state.reservations_locked else ""
        self._html(
            "Rezervacija smeštaja",
            f"""
            {_ZAGLAVLJE}
            <h1>Prijava gosta</h1>
            <form method="post" action="{RESERVATION_PATH}">
              <mat-horizontal-stepper>
                <mat-step-header aria-selected="true">1 Podaci o korisniku</mat-step-header>
                <mat-step-header aria-selected="false">2 Prijava ugostitelja</mat-step-header>
                <mat-step-header aria-selected="false">3 Ostali podaci</mat-step-header>

                <div class="mat-horizontal-stepper-content" data-korak="1">
                  <label>Ime</label>
                  <input formcontrolname="ime" name="ime" autocomplete="off">
                  <label>Prezime</label>
                  <input formcontrolname="prezime" name="prezime" autocomplete="off">
                  <label>JMBG</label>
                  <input formcontrolname="jmbg" name="jmbg" autocomplete="off">
                  <div id="jmbg-greska"></div>
                  <button type="button" class="mat-stepper-next"><mat-icon>navigate_next</mat-icon></button>
                </div>

                <div class="mat-horizontal-stepper-content" data-korak="2" hidden>
                  <table class="mat-table">
                    <tr><th>Rb.</th><th>Naziv objekta na prijavi</th><th>Akcije</th></tr>
                    <tr>
                      <td>1</td><td>sobe Test</td>
                      <td>
                        <mat-checkbox class="cbIzaberi{zakljucano_klasa}">
                          <span class="mat-checkbox-inner-container">
                            <input type="checkbox" name="prijava" value="1"
                                   class="mat-checkbox-input cdk-visually-hidden"{zakljucano_input}>
                          </span>
                        </mat-checkbox>
                      </td>
                    </tr>
                  </table>
                  <button type="button" class="mat-stepper-next"><mat-icon>navigate_next</mat-icon></button>
                </div>

                <div class="mat-horizontal-stepper-content" data-korak="3" hidden>
                  <label>Period boravka</label>
                  <mat-date-range-input>
                    <input formcontrolname="datumSmestajaOd" name="datumSmestajaOd"
                           placeholder="Datum od" autocomplete="off">
                    <span class="mat-date-range-input-separator">–</span>
                    <input formcontrolname="datumSmestajaDo" name="datumSmestajaDo"
                           placeholder="Datum do" autocomplete="off">
                  </mat-date-range-input>
                </div>
              </mat-horizontal-stepper>

              {problem}
              <div class="radnje">
                <button type="submit" class="btn">Sačuvaj</button>
                <button type="button" class="btn" disabled>
                  <mat-icon>cloud_download</mat-icon>Odštampaj rezervaciju
                </button>
              </div>
            </form>
            <script>
              // Kroz korake se ide klikom, a neaktivni koraci su sakriveni - isto kao
              // mat-stepper. Zato se u kodu i mora kliknuti "dalje" pre nego što se
              // dođe do datuma: sakriveno polje Selenium ne prima.
              const koraci = [...document.querySelectorAll('.mat-horizontal-stepper-content')];
              const zaglavlja = [...document.querySelectorAll('mat-step-header')];
              document.querySelectorAll('.mat-stepper-next').forEach(dugme => {{
                dugme.addEventListener('click', () => {{
                  const trenutni = koraci.findIndex(k => !k.hidden);
                  if (trenutni < 0 || trenutni + 1 >= koraci.length) return;
                  koraci[trenutni].hidden = true;
                  koraci[trenutni + 1].hidden = false;
                  zaglavlja.forEach((z, i) => z.setAttribute('aria-selected', String(i === trenutni + 1)));
                }});
              }});

              // mat-checkbox reaguje na klik po omotaču, ne po skrivenom input-u.
              document.querySelectorAll('mat-checkbox').forEach(cb => {{
                const polje = cb.querySelector('input');
                cb.querySelector('.mat-checkbox-inner-container').addEventListener('click', () => {{
                  if (polje.disabled) return;
                  polje.checked = !polje.checked;
                  cb.classList.toggle('mat-checkbox-checked', polje.checked);
                }});
              }});

              // Angular validira JMBG na izlazak iz polja; ovde radimo isto,
              // da bi se greška videla pre slanja forme - kao na pravom portalu.
              const polje = document.querySelector('[formcontrolname="jmbg"]');
              polje.addEventListener('blur', async () => {{
                const mesto = document.getElementById('jmbg-greska');
                mesto.innerHTML = '';
                if (!polje.value) return;
                const odgovor = await fetch('/proveri-jmbg?jmbg=' + encodeURIComponent(polje.value));
                const podaci = await odgovor.json();
                if (!podaci.ok) {{
                  mesto.innerHTML = '<mat-error>' + podaci.poruka + '</mat-error>';
                }}
              }});
            </script>
            """,
        )

    def _check_jmbg(self, jmbg: str) -> None:
        rejected = jmbg in self.state.rejected_jmbgs
        payload = {
            "ok": not rejected,
            "poruka": "JMBG nije pronađen u evidenciji" if rejected else "",
        }
        self._send(json.dumps(payload).encode("utf-8"), content_type="application/json")

    def _do_reservation(self) -> None:
        if not self._session_token():
            self._redirect("/")
            return

        data = self._form_data()
        jmbg = (data.get("jmbg") or "").strip()

        if jmbg in self.state.rejected_jmbgs:
            self._reservation_page("JMBG nije pronađen u evidenciji")
            return

        obavezna = ("ime", "prezime", "jmbg", "datumSmestajaOd", "datumSmestajaDo")
        if not all(data.get(k, "").strip() for k in obavezna):
            self._reservation_page("Sva polja su obavezna")
            return

        if not data.get("prijava"):
            self._reservation_page("Nije izabrana prijava ugostitelja")
            return

        for polje in ("datumSmestajaOd", "datumSmestajaDo"):
            if not _DATUM.fullmatch(data[polje].strip()):
                self._reservation_page(f"Datum nije u očekivanom obliku: {data[polje]}")
                return

        self.state.saved.append(data)

        if self.state.expire_after is not None and len(self.state.saved) >= self.state.expire_after:
            self.state.sessions.clear()

        self._html(
            "Sačuvano",
            f"""
            {_ZAGLAVLJE}
            <h1>Rezervacija</h1>
            <p class="ok">Gost je uspešno prijavljen.</p>
            <p>{data.get('prezime', '')} {data.get('ime', '')} -
               {data.get('datumSmestajaOd', '')} do {data.get('datumSmestajaDo', '')}</p>
            <form method="get" action="/vaucer.pdf">
              <button type="submit" class="btn"><mat-icon>cloud_download</mat-icon>Odštampaj rezervaciju</button>
            </form>
            <p><a href="{RESERVATION_PATH}">Novi gost</a></p>
            """,
        )

    def _voucher(self) -> None:
        index = len(self.state.saved)
        self._send(
            minimal_pdf(f"Vaucer {index}"),
            content_type="application/pdf",
            extra_headers={"Content-Disposition": f'attachment; filename="vaucer-{index}.pdf"'},
        )


class FakePortal:
    """Lažni portal koji se pokreće u niti. Koristi se kao kontekst menadžer."""

    def __init__(self, state: PortalState | None = None, port: int = 0) -> None:
        self.state = state or PortalState()
        handler = type("_BoundHandler", (_Handler,), {"state": self.state})
        self._server = ThreadingHTTPServer(("127.0.0.1", port), handler)
        self._thread: threading.Thread | None = None

    @property
    def base_url(self) -> str:
        host, port = self._server.server_address[:2]
        return f"http://{host}:{port}"

    def start(self) -> str:
        self._thread = threading.Thread(target=self._server.serve_forever, daemon=True)
        self._thread.start()
        return self.base_url

    def stop(self) -> None:
        self._server.shutdown()
        self._server.server_close()
        if self._thread is not None:
            self._thread.join(timeout=5)
            self._thread = None

    def __enter__(self) -> "FakePortal":
        self.start()
        return self

    def __exit__(self, *_exc: object) -> None:
        self.stop()


def main() -> None:
    state = PortalState()
    portal = FakePortal(state, port=8765)
    url = portal.start()
    print(f"Lažni portal radi na {url}")
    print(f"  prijava:     {state.username} / {state.password}")
    print(f"  forma:       {url}{RESERVATION_PATH}")
    print("Ctrl+C za prekid.")
    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        portal.stop()
        print("\nZaustavljeno.")


if __name__ == "__main__":
    main()

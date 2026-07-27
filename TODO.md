# TODO — eTurista prijava gostiju

Glavni pregled stanja. Ažurira se kako se stvari završavaju.

**Stanje:** faze 0–4 gotove · 148 testova prolazi · čeka se inspekcija portala

---

## ✅ Gotovo

### Faza 0 — skelet
- [x] venv, `requirements.txt`, `pytest.ini`
- [x] `.gitignore` (`.env`, `*.xlsx`, `pdf/`, `*.db`, screenshot-ovi)
- [x] `.env.example` sa 3 naloga
- [x] stari `data_loop.py` premešten u `legacy/`

### Faza 1 — sloj podataka
- [x] **JMBG: kontrolna cifra** po zvaničnoj formuli — tipfeler se hvata pre browsera
- [x] JMBG: tačno 13 cifara, provera datuma rođenja, izvedeni pol i oblast
- [x] JMBG: popravka kad Excel pojede vodeću nulu (samo ako kontrolna cifra tad ispadne tačna)
- [x] JMBG: naučna notacija iz Excela se odbija sa uputstvom
- [x] Datumi: **datum dolaska + broj dana** (prazno = 5 noćenja), prelazak u novu godinu
- [x] Stari zapis sa opsegom (`05.10-10.10`) i dalje se prepoznaje, pa stare liste rade
- [x] Ctrl+V iz Excela: TSV, prepoznavanje kolona iz zaglavlja ili po sadržaju
- [x] Ctrl+C nazad: `STATUS` / `RAZLOG` / `PDF` kolone
- [x] Redosled kolona `Ime · Prezime · JMBG · Dolazak · Dana · …` — isti u aplikaciji i u primeru,
      da se lepljenje nazad poklopi. Stari zapis `PREZIME Ime` se i dalje prepoznaje
      (prva kolona verzalom = prezime).
- [x] SQLite: ture, gosti, greške, događaji, nastavak posle prekida

### Faza 2 — GUI (PySide6)
- [x] Tabela sa bojenjem po statusu (zeleno / crveno / žuto / sivo)
- [x] Dropdown sa 3 naloga iz `.env`
- [x] Izmena ćelije odmah ponovo validira — red menja boju istog trena
- [x] Sve greške u redu se prijavljuju odjednom, ne jedna po jedna
- [x] Kolona `Boravak` računa raspon iz dolaska i broja dana
- [x] Log panel, progress, statusna traka
- [x] *Otvori raniju turu*, *Vrati greške u red*, kontekstni meni
- [x] Selenium u zasebnoj niti — prozor se ne zamrzava, Zaustavi radi
- [x] Provera nove verzije na GitHub-u pri pokretanju (tiho, u zasebnoj niti;
      poredi lokalni commit sa `main`, javlja se samo kad stvarno ima novije)

### Faza 3 — automatizacija
- [x] Lažni portal (`fake_portal/`) — simulira odbijen JMBG, spor odgovor, istek sesije
- [x] Svi selektori na jednom mestu, sa rezervnim varijantama i opisima na srpskom
- [x] Izbačen dinamički `cdk-describedby-message-4` iz prve ture
- [x] `WebDriverWait` svuda umesto `time.sleep()`
- [x] Greška ne prekida turu — screenshot, hard refresh, sledeći gost
- [x] Istekla sesija → ponovna prijava → gost se ponavlja
- [x] `run.py --proveri-selektore`

### Faza 4 — PDF vaučeri
- [x] Chrome snima PDF na disk umesto da ga otvori u vieweru
- [x] Čeka se da nestane `.crdownload` — nema više "najskorijeg fajla u ~/Downloads"
- [x] Preimenovanje u `2026_PETROVIC_MARKO.pdf` (ASCII, radi i na Windows-u)

### Alati
- [x] `primer/primer_gosti.xlsx` — Excel sa gotovom JMBG proverom (kolona H),
      kolone A-G istim redom kao izlaz iz aplikacije
- [x] `alati/napravi_primer_excel.py` — regeneriše taj fajl
- [x] Test koji čuva da se Excel provera i provera u aplikaciji ne raziđu

---

## ⏳ Sledeće

### Faza 5 — pravi selektori  ← **ovde smo**
- [ ] Instalirati Claude ekstenziju za Chrome i dati dozvolu za `portal.eturista.gov.rs`
- [ ] Ulogovati se na jedan nalog (forma je iza prijave)
- [ ] Uhvatiti selektore za ono što je sad otvoreno (~80%)
- [ ] Odgovoriti na otvorena pitanja (dole)
- [ ] Prebaciti stanja u `selectors.py` sa `pretpostavka` na `potvrđen`
- [ ] Smoke test: 1 gost, vidljiv browser

**Trenutno zaključano (6):** datum dolaska, datum odlaska, dugme za čuvanje, potvrda o
čuvanju, dugme za vaučer, znak da je nalog prijavljen.

### Faza 6 — dan otvaranja registracije
- [ ] `run.py --proveri-selektore` kao prva stvar
- [ ] Popuniti zaključane selektore
- [ ] Proba: 2–3 gosta pod nadzorom
- [ ] Prva prava tura

### Faza 7 — pakovanje i paralelni režim
- [ ] PyInstaller: Linux binary
- [ ] PyInstaller: Windows `.exe` (build mora na Windows mašini)
- [ ] Pri pakovanju upisati `revision.txt` pored .exe — bez toga spakovana aplikacija ne
      zna na kom je commit-u, pa provera nove verzije ćuti
- [ ] Dugme "Paralelno: 2 / 3" — `runner.py` je već pisan tako da to ne traži prepravku
- [ ] Proveriti da li portal uopšte trpi 3 istovremene sesije

---

## 💬 Za kasniju diskusiju

### Potpis izdavaoca na PDF vaučerima
Svaki vaučer treba da nosi **sliku potpisa izdavaoca**, i **potpis je različit po nalogu**
(3 naloga → 3 potpisa).

Prvo pitanje koje treba razrešiti pri inspekciji portala:

> **Da li portal ima polje za otpremanje potpisa u podešavanjima naloga?**

Od toga zavisi sve ostalo:

**A) Portal prima potpis** — najbolje. Potpis se otpremi jednom po nalogu, portal ga sam
ugrađuje u generisani PDF. Mi ne diramo PDF uopšte, dokument ostaje onakav kakav ga je
portal izdao. Ako postoji, ovde se priča završava.

**B) Portal ne prima potpis** — moramo da ga stavimo sami, posle preuzimanja:
- U `.env` po nalogu dodati putanju do PNG-a sa potpisom (`ETURISTA_NALOG1_POTPIS=...`)
- Biblioteka: `pypdf` + `reportlab` (napravi se prozirni sloj sa slikom pa se spoji sa
  stranicom) — obe rade cross-platform i idu u PyInstaller bez muke
- Treba odrediti **poziciju i veličinu** potpisa na stranici. Najlakše: jednom otvorimo
  pravi vaučer, izmerimo koordinate, pa ih upišemo u podešavanja
- Otvoreno: da li potpis ide na svaku stranu ili samo na poslednju
- Potpis se dodaje **posle** preuzimanja i **pre** preimenovanja, da se u koloni PDF vidi
  samo gotov fajl

**Treba mi od tebe kad krenemo:** 3 slike potpisa (PNG sa prozirnom pozadinom je najbolje)
i jedan primer gotovog vaučera da se vidi gde ima mesta.

> Napomena: ovo je tehnički lak deo. Sve zavisi od odgovora na pitanje A/B, pa ga ne
> diramo dok ne vidimo portal.

---

## ❓ Otvorena pitanja za inspekciju portala (faza 5)

Ovo ne mogu da odgovorim iz koda — vidi se tek na živom portalu:

1. **Koliko koraka ima forma rezervacije?** Jedna strana ili wizard sa "Dalje"?
   (Stara skripta je klikala neko "next" dugme, pa verovatno ima više koraka.)
2. **Kako se unosi datum?** Obično polje u koje se kuca, ili datepicker koji mora da se
   otvori i klikne? Koji format očekuje — `05.10.2026` ili nešto drugo?
3. **Gde nastaje PDF vaučer?** Dugme odmah posle čuvanja rezervacije, ili posebna lista
   izdatih vaučera?
4. **Ima li polje za potpis izdavaoca?** (vidi gore)
5. **Šta je tačno zaključano** do otvaranja registracije?
6. **Trpi li portal 3 istovremene sesije?** Bitno za fazu 7.

---

## 🐞 Poznata ograničenja

- `LOGGED_IN_MARKER` još nije potvrđen; do tada se prijavljenost prepoznaje po tome što se
  forma za prijavu nije vratila na ekran — radi, ali je grublje
- Provera "ima li greške ispod polja" čeka 1.5s po gostu i kad greške nema. Za 30 gostiju
  je to ~45s viška; može se skratiti kad se vidi kako portal stvarno prikazuje greške
- Prvo pokretanje ikad zna da potraje ~30s dok Selenium skine chromedriver
- Ako program pukne baš usred jednog gosta, taj gost dobija napomenu da se ručno proveri —
  ne možemo znati da li je prijava prošla na portalu pre pada

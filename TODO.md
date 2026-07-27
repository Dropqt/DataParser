# TODO — eTurista prijava gostiju

Glavni pregled stanja. Ažurira se kako se stvari završavaju.

**Stanje:** faze 0–5 gotove · portal pregledan 27.07.2026 · čeka se dan otvaranja registracije

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

### Faza 5 — pravi selektori
- [x] Claude ekstenzija za Chrome, dozvola za `portal.eturista.gov.rs`
- [x] Prijava na nalog i obilazak forme rezervacije
- [x] Uhvaćeni selektori — `run.py --proveri-selektore` javlja **14 od 15**
- [x] Odgovorena otvorena pitanja (dole), sem potpisa i paralelnih sesija
- [x] Stanja u `selectors.py` prebačena na `potvrđen`
- [x] Lažni portal prepravljen da glumi pravu formu (3 koraka, izbor prijave, opseg datuma)

**Šta se ispostavilo drugačije nego što je kod pretpostavljao:**

| Pretpostavka | Kako zaista jeste |
|---|---|
| dva polja `datumOd` / `datumDo` | jedan `mat-date-range-input`, `datumSmestajaOd` / `datumSmestajaDo` |
| datum `15.07.2026` | `15.7.2026` — **bez vodeće nule** |
| dugme „Dalje“ sa tekstom | okrugla ikonica bez ijednog slova (`button.mat-stepper-next`) |
| forma je jedna strana | stepper sa 3 koraka, srednji je izbor prijave ugostitelja |
| dugme „Preuzmi vaučer“ | „Odštampaj rezervaciju“, i onemogućeno dok se ne sačuva |
| tekst na portalu je latinica | javna strana je **ćirilica**, aplikacija iza prijave latinica |

---

## ⏳ Sledeće

### Faza 6 — dan otvaranja registracije  ← **ovde smo**
- [ ] `run.py --proveri-selektore` kao prva stvar
- [ ] Potvrditi `CONFIRMATION` — jedini selektor koji se ne vidi bez sačuvane rezervacije
- [ ] Proba: 1 gost pod nadzorom, vidljiv browser
- [ ] Proba: 2–3 gosta
- [ ] Prva prava tura

**Zaključano je samo jedno, i to na portalu a ne u kodu:** čekboks za izbor prijave
ugostitelja na 2. koraku. Onemogućen je i na prelazak mišem javi *„Rezervacija smeštaja
je zaključana.“* Aplikacija to sad prepoznaje i prekine turu sa porukom **„Portal još
nije otvorio rezervacije“** umesto da meli istu grešku kroz sve goste.

### Imenovanje preuzetih vaučera
- [ ] Promeniti naziv PDF-a u **godina · ime · prezime**: `2026_MARKO_PETROVIC.pdf`
      (sad je obrnuto — `2026_PETROVIC_MARKO.pdf`). Menja se `Guest.pdf_name`
      u `eturista/models.py`, plus test koji proverava nazive.
      Ostaje kako jeste: čist ASCII i verzal, zbog Windows-a.

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

## ✅ Odgovori sa portala (27.07.2026)

1. **Koliko koraka ima forma rezervacije?** Tri, `mat-horizontal-stepper`:
   1. *Podaci o potencijalnom korisniku vaučera* — ime, prezime, JMBG
   2. *Podaci o prijavi ugostitelja za šemu* — tabela objekata, bira se čekboksom
   3. *Ostali podaci o rezervaciji* — datumi
   Kroz korake se ide okruglim dugmetom sa ikonicom; **nema nikakav tekst**, pa se traži
   po klasi `mat-stepper-next`.
2. **Kako se unosi datum?** `mat-date-range-input` sa dva polja koja **primaju kucanje**
   (nisu `readonly`), pa kalendar ne mora da se otvara. Format je `d.M.yyyy` —
   `15.7.2026`, bez vodeće nule. Utvrđeno tako što je datum izabran iz portalovog
   kalendara pa pročitano šta je portal sam upisao.
3. **Gde nastaje PDF vaučer?** Dugme *„Odštampaj rezervaciju“* (ikonica `cloud_download`)
   stoji odmah pored *Sačuvaj*, ispod stepper-a. **Onemogućeno je dok se rezervacija ne
   sačuva** — to je ujedno i najpouzdaniji znak da je čuvanje prošlo.
4. **Ima li polje za potpis izdavaoca?** — *još neprovereno*, nije se stiglo do
   podešavanja naloga. Ostaje otvoreno, vidi diskusiju gore.
5. **Šta je tačno zaključano?** Samo čekboks za izbor prijave na 2. koraku
   (*„Rezervacija smeštaja je zaključana.“*). Sva polja, datumi i dugme *Sačuvaj* su
   otvoreni i sad.
6. **Trpi li portal 3 istovremene sesije?** — *još neprovereno*, ne može bez prave ture.

> Sitnica koja bi umela da izgriza sate: portal drži i **prazne** `<mat-error>` čvorove
> ispod polja bez greške. Provera greške zato traži samo `mat-error` sa tekstom, inače bi
> pročitala prazan string i zaključila da greške nema.

> **Pismo nije isto svuda.** U običnom Chrome-u aplikacija portala se prikazala
> latinicom, a u Chrome-u koji vozi Selenium (čist profil) — ćirilicom. Zato nijedan
> selektor ne sme da traži tekst u jednom pismu: radilo bi ručno, a padalo u turi.
> Ovo je provereno 28.07.2026. probnim pogonom, screenshot u `screenshots/`.

---

## 🐞 Poznata ograničenja

- `LOGGED_IN_MARKER` još nije potvrđen; do tada se prijavljenost prepoznaje po tome što se
  forma za prijavu nije vratila na ekran — radi, ali je grublje
- Provera "ima li greške ispod polja" čeka 1.5s po gostu i kad greške nema. Za 30 gostiju
  je to ~45s viška; može se skratiti kad se vidi kako portal stvarno prikazuje greške
- Prvo pokretanje ikad zna da potraje ~30s dok Selenium skine chromedriver
- Ako program pukne baš usred jednog gosta, taj gost dobija napomenu da se ručno proveri —
  ne možemo znati da li je prijava prošla na portalu pre pada

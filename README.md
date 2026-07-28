# eTurista - prijava gostiju

Desktop aplikacija za prijavu gostiju na `portal.eturista.gov.rs`. Gosti se kopiraju iz
glavnog Excela u tabelu aplikacije, prijave se preko izabranog naloga, i vrate se nazad
u Excel sa `STATUS` kolonom.

Zamenjuje `legacy/data_loop.py` iz prve ture.

---

## Postavljanje

```bash
python3 -m venv .venv
.venv/bin/python -m pip install -r requirements.txt
cp .env.example .env      # pa popuni korisnička imena i lozinke
```

Treba i **Chrome ili Chromium** na sistemu. Chromedriver se skida automatski pri prvom
pokretanju (Selenium Manager) - prvi put ume da potraje tridesetak sekundi.

> `.env` drži lozinke i nalazi se u `.gitignore`. Repo je javan, pa aplikacija pri
> pokretanju proveri da `.env` nije slučajno ušao u git i upozori ako jeste.

## Pokretanje

```bash
.venv/bin/python run.py                      # aplikacija
.venv/bin/python run.py --proveri-selektore  # provera da li selektori važe na portalu
.venv/bin/python run.py --lazni-portal       # lokalni lažni portal za probu
```

---

## Kako se radi tura

1. U glavnom Excelu označi grupu gostiju (**ime, prezime, JMBG, dolazak, dana, e-mail**)
   i `Ctrl+C`.
2. U aplikaciji `Ctrl+V`. Redovi se pojave u tabeli; kolone se prepoznaju same - iz
   zaglavlja ako ga ima, inače po sadržaju.
   Bez Excela: **＋ Dodaj red** (ili taster `Ins`) daje prazan red u koji se kuca direktno.
   Tab prelazi na sledeću ćeliju, `Del` briše označene redove.
3. **Crveni redovi imaju neispravan podatak** i vide se odmah, pre nego što browser
   uopšte krene. Dvoklik na ćeliju ispravlja; boja se menja istog trena.
4. Izaberi nalog iz padajućeg menija i klikni **Pokreni turu**.
5. Zeleno = prijavljen, crveno = pao, žuto = u toku. Prelaz mišem preko reda pokazuje razlog.
6. Kad se završi, `Ctrl+C` i zalepi nazad u glavni Excel.

### Datum boravka

Umesto opsega `05.10-10.10` unosi se **datum dolaska** i **broj dana**. Prazna kolona `Dana`
znači 5 noćenja - koliko traje minimalni vaučer. `5 dana` znači 5 noćenja, dakle dolazak
05.10 → odlazak 10.10, isto kao stari zapis.

Stari opseg i dalje radi: ako u koloni sa datumom nađe `05.10-10.10`, aplikacija ga pročita
kao i pre, a kolonu `Dana` tad ignoriše. Stare liste iz prve ture ne treba prepravljati.

### Listovi u `primer_gosti.xlsx`

Po jedan radni list za svaki nalog - **Danica · Mileta · Zorica** - pa svako popunjava
svoje goste bez mešanja. Nazivi listova su isti kao nalozi u padajućem meniju aplikacije.

Radni listovi su prazni i spremni za unos; izmišljeni gosti stoje zasebno na listu
**Primeri**, gde se vidi kako radi provera JMBG-a (poslednja dva su namerno pokvarena).

Zaglavlje je isto na svakom listu, pa je svejedno sa kog se kopira i na koji se lepi nazad.

### Vaučeri po folderima

Vaučeri se razvrstavaju u foldere po adresi na koju se šalju, pa se cela grupa kasnije
zakači iz jednog mesta:

```
vauceri/
  vauceri@primer.rs/   2026_MARKO_PETROVIC.pdf
                       2026_JOVAN_ILIC.pdf
  ana@drugi.rs/        2026_ANA_ANIC.pdf
```

Adresa se upisuje **jednom**, u polje *Vaučeri na:* iznad tabele (pamti se u `.env` kao
`ETURISTA_EMAIL`). Kolona `E-mail` se popunjava samo za goste čiji vaučeri idu negde
drugde - prazna ćelija znači adresu iz tog polja.

Ako se polje ostavi prazno, vaučeri ostaju u korenu `vauceri/`, kao i pre.

Pre nego što tura krene, u log se ispiše koliko vaučera ide u koji folder - bolje da se
pogrešna adresa vidi odmah nego da se posle traži gde je 30 PDF-ova završilo.

### Bojenje u glavnom Excelu

Redosled kolona (`Ime · Prezime · JMBG · Dolazak · Dana · E-mail · STATUS · RAZLOG · PDF`)
je isti kao u `primer/primer_gosti.xlsx`, pa se rezultat lepi preko istih gostiju bez
pomeranja ičega.

Kopirani redovi nose kolone `STATUS`, `RAZLOG` i `PDF`. Clipboard ne prenosi boje, pa se
bojenje u glavnom Excelu podešava jednom preko *conditional formatting* nad `STATUS` kolonom:

| Uslov | Boja |
|---|---|
| `STATUS = "OK"` | zelena |
| `STATUS = "GREŠKA"` | crvena |
| `STATUS = "PRESKOČEN"` | siva |

---

## Šta se dešava kad nešto pukne

Greška **nikad ne prekida turu** - gost pocrveni, snimi se screenshot, forma se osveži i
ide se na sledećeg gosta.

| Razlog u tabeli | Šta znači | Šta uraditi |
|---|---|---|
| `Pogrešna kontrolna cifra…` | tipfeler u JMBG-u, uhvaćen lokalno | ispravi ćeliju |
| `Portal je odbio JMBG` | JMBG je matematički ispravan ali ga portal ne nalazi | proveri podatak kod gosta |
| `Portal još nije otvorio rezervacije` | registracija za vaučere nije počela | sačekaj dan otvaranja; tura se prekida odmah |
| `Ne mogu da pročitam datum dolaska…` | datum se ne može pročitati | ispravi ćeliju |
| `Broj dana mora biti bar 1` | besmislen broj noćenja | ispravi ćeliju |
| `E-mail ne izgleda ispravno…` | u koloni E-mail nije adresa | ispravi ćeliju ili je isprazni |
| `Element nije nađen - portal je verovatno promenjen` | portal je izmenjen | `run.py --proveri-selektore`, pa popravi `selectors.py` |
| `Portal nije odgovorio na vreme` | prolazna smetnja | *Uređivanje → Vrati greške u red*, pa ponovo |
| `Sesija je istekla` | portal je izbacio nalog | rešava se sam (ponovna prijava) |

### Provera nove verzije

Pri pokretanju aplikacija tiho pita GitHub ima li novijih izmena na `main` grani i javi se
samo ako ih ima. Repo je javan, pa nije potreban token; šalje se običan zahtev i ništa o
tebi ni o gostima se ne prenosi. Ako nema mreže, ćuti i nastavlja normalno.

Poredi se tvoj lokalni commit sa `main`, pa dobijaš i tačan broj commit-a zaostatka - i
nema lažne uzbune kad si lokalno ispred. Ručno: *Pomoć → Proveri ima li nove verzije*.
Isključivanje: `ETURISTA_PROVERA_AZURIRANJA=false` u `.env`.

Ovo **samo javlja** - ne instalira ništa. Ažuriranje je `git pull` pa ponovo pokreni.

---

Napredak se snima u bazu posle **svakog** gosta. Ako program pukne nasred ture od 30
gostiju, *Datoteka → Otvori raniju turu* nastavlja od prvog neobrađenog - bez duplikata.
Gost koji je bio u obradi kad je program pukao dobija napomenu da se ručno proveri.

---

## Struktura

```
run.py                      ulazna tačka (GUI / provera selektora / lažni portal)
eturista/
  validation.py             JMBG (kontrolna cifra) i datumi boravka
  clipboard.py              Ctrl+V iz Excela, Ctrl+C nazad
  models.py                 Guest, Batch, Status
  store.py                  SQLite: ture, gosti, greške, nastavak posle prekida
  driver.py                 Chrome + preuzimanje fajlova
  runner.py                 orkestracija ture
  portal/
    selectors.py            ★ SVI selektori portala su ovde i nigde drugde
    base_page.py            WebDriverWait helperi (nema time.sleep)
    login_page.py
    reservation_page.py
    voucher_page.py
  gui/                      PySide6 prozor, tabela sa bojama, radne niti
fake_portal/app.py          lokalni lažni portal za razvoj i testove
tests/                      172 testa
legacy/data_loop.py         prototip iz prve ture, čuva se za referencu
```

### Kako izgleda forma na portalu

Rezervacija je wizard sa tri koraka (provereno 27.07.2026):

1. **Podaci o korisniku vaučera** - ime, prezime, JMBG
2. **Prijava ugostitelja za šemu** - tabela objekata; bira se čekboks u redu.
   Van sezone je taj čekboks zaključan i to je jedino što nas deli od prve ture
3. **Ostali podaci** - datum dolaska i odlaska, pa *Sačuvaj* i *Odštampaj rezervaciju*

Dve stvari koje deluju kao sitnica a lome tok: dugme za sledeći korak nema **nikakav
tekst** (samo ikonicu), a datum se piše **bez vodeće nule** - `5.10.2026`, ne `05.10.2026`.

### Kad portal izmeni sajt

Menja se **samo `eturista/portal/selectors.py`**. Nigde drugde u kodu nema CSS ni XPath
stringa. Svaki selektor ima opis na srpskom, listu rezervnih selektora i stanje:

- `potvrđen` - provereno na živom portalu
- `pretpostavka` - radilo u prvoj turi ili je logična pretpostavka
- `zaključan` - deo portala koji još nije otvoren

Tekst se traži preko `tekst_sadrzi()`, koje ne gleda ni pismo ni kvačice ni veličinu
slova - javna strana portala je ćirilična, a aplikacija iza prijave latinična.

`run.py --proveri-selektore` se prijavi na portal i ispiše koji selektori razrešavaju
element a koji ne.

---

## Testovi

```bash
.venv/bin/python -m pytest              # sve (pokreće pravi Chrome, ~2 min)
.venv/bin/python -m pytest -m "not browser"   # samo brzi, bez browsera
```

End-to-end testovi voze pravi Chrome kroz lažni portal iz `fake_portal/`, koji ume da
simulira odbijen JMBG, spor odgovor i istek sesije.

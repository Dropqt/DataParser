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
cp .env.example .env      # naloge unesi u aplikaciji: Alatke → Podešavanja
```

Treba i **Chrome ili Chromium** na sistemu. Chromedriver se skida automatski pri prvom
pokretanju (Selenium Manager) - prvi put ume da potraje tridesetak sekundi.

Na Windows-u ista tri koraka radi **`postavi.bat`** (dupli klik): nađe Python, napravi
`.venv`, instalira biblioteke, napravi `.env` iz `.env.example` i na kraju proveri da
sve zaista radi (Chrome, git, folderi, nalozi). Može da se pokrene i više puta:
postojeći `.venv` se koristi, a `.env` se nikad ne prepisuje.

Posle toga se aplikacija pokreće duplim klikom na **`pokreni.bat`** - on uzima Python iz
`.venv` foldera i otvara prozor aplikacije, bez komandne linije iza njega (`pythonw`).
Ako `.venv` ili biblioteke fale, uputi na `postavi.bat` umesto da tiho ne uradi ništa.

Na noviju verziju se prelazi duplim klikom na **`azuriraj.bat`**: povuče izmene sa
GitHub-a, doinstalira šta je dodato i proveri da sve i dalje radi. `.env` ne dira.

Tri `.bat` fajla, po jedan za svaku priliku:

| Fajl | Kada |
|---|---|
| `postavi.bat` | jednom, na novom računaru |
| `pokreni.bat` | svaki put kad se radi |
| `azuriraj.bat` | kad stigne poruka da ima novija verzija |

### Provera da li sve radi

```bash
.venv/bin/python run.py --provera-sistema
```

Ispiše da li ima Python 3.10+, sve biblioteke, Chrome, git, upisive foldere i bar jedan
podešen nalog. Isti izveštaj zove i `postavi.bat` na kraju postavljanja, pa je provera
na jednom mestu i može da se testira - `.bat` logika ne može.

Redovi označeni sa `[GRESKA]` znače da aplikacija još ne može da radi; `[pazi]` znači
da radi, ali nešto nedostaje (npr. git treba samo za `azuriraj.bat`).

Uz `--pripremi-drajver` odmah skine i chromedriver, dok računar sigurno ima internet -
inače to čeka prvu turu i izgleda kao da se program zaglavio.

> `.env` drži lozinke i nalazi se u `.gitignore`. Repo je javan, pa aplikacija pri
> pokretanju proveri da `.env` nije slučajno ušao u git i upozori ako jeste.

### Podešavanja

`.env` ne mora da se uređuje rukom. Sve što je u njemu stoji i u aplikaciji, u
**Alatke → Podešavanja** (`Ctrl+,`), u četiri jezička:

| Jezičak | Šta je unutra |
|---|---|
| **Nalozi** | tri naloga: naziv, korisnik, lozinka (maskirana, sa dugmetom *Prikaži*), slika potpisa |
| **Folderi** | gde idu vaučeri, screenshot-ovi i baza |
| **Vaučeri** | adresa za razvrstavanje, godina u nazivu PDF-a, položaj potpisa u milimetrima |
| **Ostalo** | adresa portala, rad bez prozora, provera nove verzije |

Dugme **Proveri prijavu** se stvarno prijavi na portal izabranim nalogom, pre nego što
se išta snimi - lozinka se tako proveri odmah, a ne tek kad tura krene.

Snimanje **čuva komentare** iz `.env.example`, menja samo vrednosti na njihovim
mestima, i piše preko privremenog fajla, pa prekid usred upisa ne ostavlja polupisan
`.env`. Sve sem promene baze važi **odmah, bez restarta** - novi nalog se pojavi u
padajućem meniju istog trena.

Kad naloga uopšte nema, aplikacija sama ponudi da otvori ovaj prozor.

## Pokretanje

```bash
.venv/bin/python run.py                      # aplikacija
.venv/bin/python run.py --proveri-selektore  # provera da li selektori važe na portalu
.venv/bin/python run.py --lazni-portal       # lokalni lažni portal za probu
.venv/bin/python run.py --pripremi-potpis U I  # screenshot potpisa -> providni PNG
.venv/bin/python run.py --kalibracija PDF    # gde bi potpis pao na ovom vaučeru
.venv/bin/python run.py --provera-sistema    # ima li Python, biblioteke, Chrome, nalozi
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

### Lepljenje iz Worda

`Ctrl+V` prima i tekst iz Worda, ne samo iz Excela. Wordova tabela stiže kao isti TSV kao
iz Excela, ali spisak gostiju često nije tabela - i to prolazi:

```
1. Marko Petrović 0101990710121 05.10.2026
- Jovan Ilić, 1503988710011, 06.10.2026, 7 dana
Ana Anić - JMBG 0101017505005 - dolazak 07.10.2026
```

Kad kolone ne mogu da se prepoznaju, svaki red se čita kao rečenica: JMBG po broju cifara,
datum po tački, e-mail po `@`, broj noćenja po tome što stoji posle datuma, a ono što je
ostalo od slova je ime i prezime (`clipboard._read_free_text_row`). Numeracija (`1.`, `-`)
i reči tipa `JMBG:` ili `dolazak` se izbacuju, a redovi koji ne liče na gosta (naslov,
pozdrav) se preskaču i prijave u logu. Ako nijedan red nema JMBG, aplikacija kaže da ne
prepoznaje - bolje nego praviti goste od proizvoljnih reči.

Usput se čiste i Wordovi nevidljivi znaci (tvrdi razmak, razmak nulte širine) i meki
prelom reda (`Shift+Enter`), koji je u pasusu novi gost a u tabeli prelom unutar ćelije.

### Datum boravka

Umesto opsega `05.10-10.10` unosi se **datum dolaska** i **broj dana**. Prazna kolona `Dana`
znači 5 noćenja - koliko traje minimalni vaučer. `5 dana` znači 5 noćenja, dakle dolazak
05.10 → odlazak 10.10, isto kao stari zapis.

Stari opseg i dalje radi: ako u koloni sa datumom nađe `05.10-10.10`, aplikacija ga pročita
kao i pre, a kolonu `Dana` tad ignoriše. Stare liste iz prve ture ne treba prepravljati.

#### Mesec ispisan rečju

Datum sme da ima i naziv meseca umesto broja, pa se tuđe liste ne prekucavaju:

```
29.sep.2026        29. septembar 2026      29. septembra 2026
29-sep-2026        29. септембар 2026      29 September 2026
29.sep.26          29.sep                  5.okt-10.okt.2026
```

Prihvata se skraćenica i pun naziv, **latinica i ćirilica**, srpski i engleski, kao i
genitiv (`septembra`) - tako se datum i izgovara. Dvocifrena godina (`26`) znači 2026, a
ako godine nema uzima se `ETURISTA_GODINA`. Nepoznata reč i dalje daje istu grešku kao
pre, pa se tipfeler vidi u tabeli.

> Reč se čita kao mesec **samo kad joj neposredno prethodi dan**. Bez tog pravila bi
> gost po imenu **Maja** postao 1. maj, jer je `maja` i žensko ime i genitiv od *maj*.

### Listovi u `primer_gosti.xlsx`

Po jedan radni list za svaki nalog - **Danica · Mileta · Zorica** - pa svako popunjava
svoje goste bez mešanja. Nazivi listova su isti kao nalozi u padajućem meniju aplikacije.

Radni listovi su prazni i spremni za unos; izmišljeni gosti stoje zasebno na listu
**Primeri**, gde se vidi kako radi provera JMBG-a (poslednja dva su namerno pokvarena).

Zaglavlje je isto na svakom listu, pa je svejedno sa kog se kopira i na koji se lepi nazad.

### JMBG sa vodećom nulom i lepljenje iz Worda

Cela `JMBG` kolona je formatirana kao **Tekst**, ne samo redovi u kojima ima formula -
inače gost upisan ispod poslednjeg formuliranog reda ostane bez vodeće nule.

Ako lepljenje ipak pregazi format i ćelija postane broj, **sama ćelija u koloni `JMBG`
požuti** - uslovno formatiranje po `ISNUMBER`. Poruka desno to isto kaže, ali u nju se ne
gleda dok se ne posumnja, a žuto usred kolone se primeti odmah. Bojenje reda po statusu
to ne prekriva.

Ako se nula izgubi, kolona `PROVERA JMBG` požuti i napiše šta treba da stoji:
`⚠ Fali vodeća nula - upiši 0…`.
Unos i tada prolazi, jer aplikacija tu nulu vraća sama (`validation.clean_jmbg`), ali se
u tabeli odmah vidi šta popraviti. Provera pre računanja izbaci i ono što lepljenje iz
Worda donese - tvrde razmake, en/em crte, tačke - pa `010199-071012-1` prolazi kao ✓.

Iz Worda se lepi **bez formata** (`Ctrl+Shift+V`; LibreOffice: *Neformatirani tekst*),
inače dolaze Wordov font i okviri i format kolone. Najkraće je preskočiti Excel i lepiti
iz Worda pravo u aplikaciju - videti *Lepljenje iz Worda* niže.

### Prebacivanje gosta na drugi list

Gost upisan kod pogrešnog naloga se seli **kopiranjem kolona A-F** (`Ctrl+C`), pa se
original obriše. Kolone `G`-`P` se ne prenose - one su formule i na svakom listu su iste.

Isecanje (`Ctrl+X`) je ranije razbijalo proveru: Excel bi formulama sa starog lista
prepisao reference na novi list, pa bi provera prvo počela da čita tuđe goste, a čim se
ti redovi obrišu - `#REF!`. Zato u generisanim formulama više nema nijedne adrese ćelije;
sve ide preko `INDEX($C:$C;ROW())`, što znači "moja kolona, moj red" i preživljava i
seljenje i brisanje redova (`alati/napravi_primer_excel.py`, funkcija `ref`). Test
`test_formulas_never_point_at_a_single_cell` čuva to svojstvo.

### Vaučeri po folderima

Vaučeri se razvrstavaju u foldere po adresi na koju se šalju, pa se cela grupa kasnije
zakači iz jednog mesta:

```
vauceri/
  vauceri@primer.rs/   2026_MARKO_PETROVIC.pdf
                       2026_JOVAN_ILIC.pdf
  ana@drugi.rs/        2026_ANA_ANIC.pdf
```

Adresa se upisuje **jednom**, u polje *Vaučeri na:* iznad tabele. Pri zatvaranju
programa se pamti u `.env` kao `ETURISTA_EMAIL`, pa sledeći put stoji ista - može i
ručno, u *Alatke → Podešavanja*. Kolona `E-mail` se popunjava samo za goste čiji
vaučeri idu negde drugde - prazna ćelija znači adresu iz tog polja.

Ako se polje ostavi prazno, vaučeri ostaju u korenu `vauceri/`, kao i pre.

Pre nego što tura krene, u log se ispiše koliko vaučera ide u koji folder - bolje da se
pogrešna adresa vidi odmah nego da se posle traži gde je 30 PDF-ova završilo.

### Potpisivanje vaučera

Vaučer ima pri dnu polje **ПОТПИС УГОСТИТЕЉА** - natpis pa vodoravna crta ispod njega.
Aplikacija tu utisne sliku potpisa **odmah po preuzimanju**, pa PDF stiže na disk već
potpisan.

Koji potpis ide određuje **nalog** kojim je gost prijavljen - nalog je uvek ista osoba,
pa se potpisnik ne bira posebno.

**1. Napravi sliku potpisa.** Potpiši se na belom papiru, uslikaj ili skeniraj, pa:

```bash
.venv/bin/python run.py --pripremi-potpis ~/Slike/potpis.png potpisi/danica.png
```

Alat odseče bele margine, pretvori svetlinu u providnost i pojača kontrast. Radi
lokalno - **slika sopstvenog potpisa ne treba da ode ni na kakav online alat.** Ispiše i
koliko je potpis oštar; ispod 200 dpi se na štampi vidi mekoća, pa vredi uslikati izbliza.

**2. Upiši je uz nalog u `.env`:**

```ini
ETURISTA_NALOG1_NAZIV=danica
ETURISTA_NALOG1_POTPIS=potpisi/danica.png
```

Folder `potpisi/` je u `.gitignore`, isto kao `.env`. Nalog bez podešenog potpisa i dalje
radi - samo pre pokretanja ture pita da li si siguran.

**Nepotpisani original** se čuva u `vauceri/_bez_potpisa/`. Stoji iznad foldera po e-mail
adresama, pa ne ulazi u grupu koja se kači na mejl.

**Vaučeri preuzeti ranije** se potpisuju naknadno: *Alatke → Potpiši vaučere u folderu…*
Uzima potpis izabranog naloga i prolazi kroz sve PDF-ove u folderu. Već potpisani se
prepoznaju po markeru u metapodacima i preskaču, pa alat sme da se pusti i dvaput.

**Ako potpis ne legne** - obrazac promenjen, slika obrisana - gost svejedno ostaje
**zeleno prijavljen**, uz upozorenje u logu. Prijava na portalu je gotova i ne poništava
se zbog slike; vaučer se posle sredi alatkom iz prethodnog pasusa.

#### Kad ministarstvo promeni obrazac

Potpis se ne postavlja na fiksne koordinate nego se **traži natpis u tekstu PDF-a** i
meri od njega, pa pomeranje reda u obrascu ništa ne kvari. Traže se obe reči zajedno -
sama reč *УГОСТИТЕЉА* stoji i u naslovu iznad, a *ПОТПИС* i u polju za potpis gosta ispod.

Ako se ipak pomeri sam odnos natpisa i crte, prvo pogledaj gde bi potpis pao:

```bash
.venv/bin/python run.py --kalibracija "vauceri/2026_PETROVIC_MARKO.pdf"
```

Snima kopiju sa crvenim okvirom na mestu potpisa. Brojevi se onda podese u `.env`
(`ETURISTA_POTPIS_VISINA`, `_POMAK_X`, `_POMAK_Y`, `_MAX_SIRINA`), sve u milimetrima.
Podrazumevane vrednosti su izmerene na vaučeru iz 2025: od donje ivice natpisa do crte
ima svega 28 pt, pa potpis visok 12 mm sedi na crti i prelazi malo preko nje.

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

Ovo **samo javlja** - ne instalira ništa. Ažuriranje je `git pull` pa ponovo pokreni,
a na Windows-u dupli klik na `azuriraj.bat`.

---

Napredak se snima u bazu posle **svakog** gosta. Ako program pukne nasred ture od 30
gostiju, *Datoteka → Otvori raniju turu* nastavlja od prvog neobrađenog - bez duplikata.
Gost koji je bio u obradi kad je program pukao dobija napomenu da se ručno proveri.

---

## Struktura

```
run.py                      ulazna tačka (GUI / selektori / lažni portal / potpisi)
eturista/
  validation.py             JMBG (kontrolna cifra) i datumi boravka
  clipboard.py              Ctrl+V iz Excela, Ctrl+C nazad
  models.py                 Guest, Batch, Status
  store.py                  SQLite: ture, gosti, greške, nastavak posle prekida
  driver.py                 Chrome + preuzimanje fajlova
  runner.py                 orkestracija ture
  potpis.py                 utiskivanje potpisa u PDF vaučer
  env_file.py               upis u .env uz čuvanje komentara
  provera.py                --provera-sistema: zavisnosti, Chrome, nalozi
  portal/
    selectors.py            ★ SVI selektori portala su ovde i nigde drugde
    base_page.py            WebDriverWait helperi (nema time.sleep)
    login_page.py
    reservation_page.py
    voucher_page.py
  gui/                      PySide6 prozor, tabela sa bojama, radne niti
    settings_dialog.py      Alatke → Podešavanja
alati/pripremi_potpis.py    screenshot potpisa -> providni PNG
fake_portal/app.py          lokalni lažni portal za razvoj i testove
tests/                      201 test
legacy/data_loop.py         prototip iz prve ture, čuva se za referencu
```

### Kako izgleda forma na portalu

Rezervacija je wizard sa tri koraka (provereno probnom turom 29.07.2026):

1. **Podaci o korisniku vaučera** - ime, prezime, JMBG
2. **Prijava ugostitelja za šemu** - tabela objekata; bira se čekboks u redu.
   Van sezone je taj čekboks zaključan; od 29.07.2026. je otvoren.
3. **Ostali podaci** - datum dolaska i odlaska, pa *Sačuvaj* i *Odštampaj rezervaciju*

Dve stvari koje deluju kao sitnica a lome tok: dugme za sledeći korak nema **nikakav
tekst** (samo ikonicu), a datum se piše **bez vodeće nule** - `5.10.2026`, ne `05.10.2026`.

Tabela prijava na drugom koraku stiže **zasebnim zahtevom**, oko sekundu posle otvaranja
forme. Zato `--proveri-selektore` ume da javi da `SCHEME_ROW` ne radi iako radi - ta
provera gleda DOM bez čekanja.

#### Čuvanje ima dva koraka, a portal ne javlja uspeh

Klik na *Сачувај* ne sačuva ništa odmah - otvori se dijalog:

> **Сачувај резервацију смештаја**
> Да ли сте сигурни да желите да сачувате резервацију смештаја?
> \[Не] \[Да]

Tek *Да* sačuva. Posle toga **nema nikakve poruke o uspehu** - ni snackbar-a, ni
`role="alert"`, ostane samo prazan `mat-dialog-container`. Zato se ne čeka poruka nego
posledica: dugme *Одштампај резервацију* je onemogućeno dok rezervacija nije sačuvana,
pa je njegovo aktiviranje jedini pouzdan znak (`ReservationPage.wait_until_saved`).

Ovo se ne sme preskočiti. Portal na klik **odštampa potvrdu iz sadržaja forme čak i kad
rezervacija nije sačuvana** - bez ove provere bi na disk legao uredan, potpisan vaučer
za rezervaciju koja na portalu ne postoji. Viđeno u probnoj turi.

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

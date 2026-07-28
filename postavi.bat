@echo off
rem ======================================================================
rem  eTurista - postavljanje na novom racunaru (Windows)
rem
rem  Klikni dva puta na ovaj fajl. Radi jednom sve sto treba:
rem    1. proveri da li ima Python
rem    2. proveri da li ima Chrome
rem    3. napravi .venv
rem    4. instalira biblioteke iz requirements.txt
rem  i na kraju napravi .env iz .env.example, pa ga otvori za popunjavanje.
rem
rem  Moze da se pokrene i vise puta: postojeci .venv se koristi, a .env se
rem  nikad ne prepisuje - u njemu su lozinke.
rem
rem  Poruke su namerno bez kvacica. CMD prozor koristi staru kodnu stranu,
rem  pa bi se "s" i "c" sa kvacicom prikazali kao smece.
rem ======================================================================

cd /d "%~dp0"
title eTurista - postavljanje

echo.
echo ======================================================
echo   eTurista - postavljanje na ovom racunaru
echo ======================================================
echo.

if not exist "requirements.txt" goto :nema_projekta

rem --- 1/4  Python ------------------------------------------------------
set "PY="
py -3 --version >nul 2>&1
if not errorlevel 1 set "PY=py -3"
if not defined PY (
    python --version >nul 2>&1
    if not errorlevel 1 set "PY=python"
)
if not defined PY goto :nema_pythona

%PY% -c "import sys; raise SystemExit(0 if sys.version_info >= (3, 10) else 1)"
if errorlevel 1 goto :stari_python

for /f "tokens=2" %%v in ('%PY% --version 2^>^&1') do set "PYVER=%%v"
echo [1/4] Python %PYVER% ... u redu

rem --- 2/4  Chrome ------------------------------------------------------
rem  Chrome mora da postoji na sistemu; drajver za njega se ne instalira
rem  rucno nego ga Selenium skine sam pri prvom pokretanju.
set "CHROME="
if exist "%ProgramFiles%\Google\Chrome\Application\chrome.exe" set "CHROME=1"
if exist "%ProgramFiles(x86)%\Google\Chrome\Application\chrome.exe" set "CHROME=1"
if exist "%LocalAppData%\Google\Chrome\Application\chrome.exe" set "CHROME=1"
if not defined CHROME (
    reg query "HKLM\SOFTWARE\Microsoft\Windows\CurrentVersion\App Paths\chrome.exe" >nul 2>&1
    if not errorlevel 1 set "CHROME=1"
)
if defined CHROME echo [2/4] Chrome ... u redu
if not defined CHROME call :bez_chroma

rem --- 3/4  virtuelno okruzenje -----------------------------------------
if exist ".venv\Scripts\python.exe" goto :venv_postoji
echo [3/4] pravim .venv ...
%PY% -m venv .venv
if errorlevel 1 goto :venv_pukao
goto :venv_gotov

:venv_postoji
echo [3/4] .venv vec postoji, koristim njega

:venv_gotov

rem --- 4/4  biblioteke --------------------------------------------------
echo [4/4] instaliram biblioteke ...
echo       PySide6 je krupan, prvi put ume da potraje par minuta.
echo.
".venv\Scripts\python.exe" -m pip install --upgrade pip
".venv\Scripts\python.exe" -m pip install -r requirements.txt
if errorlevel 1 goto :paketi_pukli

rem Provera da biblioteke zaista mogu da se ucitaju. Nije suvisno: .venv ostane
rem naizgled ispravan i kad se Python nadogradi na noviju verziju, a paketi iz
rem njega se vise ne vide - greska se onda vidi tek pri pokretanju aplikacije.
".venv\Scripts\python.exe" -c "import PySide6, selenium, dotenv"
if errorlevel 1 goto :venv_pokvaren

rem --- lozinke ----------------------------------------------------------
if exist ".env" goto :env_postoji
copy ".env.example" ".env" >nul
echo.
echo Napravljen je .env - u njemu stoje korisnicka imena i lozinke naloga.
echo Otvara se u Notepad-u: popuni ETURISTA_NALOG1_USER i ETURISTA_NALOG1_PASS,
echo pa sacuvaj i zatvori.
start "" notepad ".env"
goto :env_gotov

:env_postoji
echo.
echo .env vec postoji, ne diram ga - u njemu su lozinke.

:env_gotov

echo.
echo ======================================================
echo   Gotovo.
echo.
echo   Aplikacija se pokrece sa:
echo       .venv\Scripts\python run.py
echo.
echo   Prvo pokretanje ume da potraje tridesetak sekundi,
echo   dok Selenium skine drajver za Chrome.
echo ======================================================
goto :kraj

rem --- poruke o gresci --------------------------------------------------

:nema_projekta
echo GRESKA: u ovom folderu nema requirements.txt.
echo.
echo Ovaj fajl mora da stoji u istom folderu kao run.py, tj. u folderu
echo cele aplikacije. Prebaci ga tamo pa pokreni ponovo.
goto :kraj

:nema_pythona
echo GRESKA: Python nije nadjen.
echo.
echo Skini ga sa https://www.python.org/downloads/
echo VAZNO: pri instalaciji cekiraj "Add python.exe to PATH",
echo inace ga ovaj fajl nece naci.
echo Kad zavrsis instalaciju, pokreni ovaj fajl ponovo.
goto :kraj

:stari_python
echo GRESKA: Python %PYVER% je prestar, treba 3.10 ili noviji.
echo.
echo Skini noviji sa https://www.python.org/downloads/
echo i pokreni ovaj fajl ponovo.
goto :kraj

:venv_pukao
echo.
echo GRESKA: pravljenje .venv nije uspelo.
echo.
echo Najcesce je razlog to sto je Python instaliran samo za drugog korisnika
echo ili je folder zasticen. Probaj desni klik na ovaj fajl pa
echo "Pokreni kao administrator".
goto :kraj

:paketi_pukli
echo.
echo GRESKA: instaliranje biblioteka nije uspelo.
echo.
echo Proveri da li racunar ima internet, pa pokreni ovaj fajl ponovo.
echo Vec skinuto se ne skida ponovo, tako da drugi pokusaj ide brze.
goto :kraj

:venv_pokvaren
echo.
echo GRESKA: biblioteke su instalirane ali se ne ucitavaju.
echo.
echo To se desava kad je .venv napravljen jednom verzijom Pythona, a Python
echo je u medjuvremenu nadogradjen - stari .venv onda vise ne vidi svoje pakete.
echo Popravka: obrisi folder .venv i pokreni ovaj fajl ponovo.
goto :kraj

:bez_chroma
echo [2/4] UPOZORENJE: Chrome nije nadjen.
echo.
echo       Aplikacija prijavljuje goste kroz Chrome i bez njega ne radi.
echo       Skini ga sa https://www.google.com/chrome/ - postavljanje se
echo       nastavlja, Chrome moze i posle da se instalira.
echo.
goto :eof

:kraj
echo.
pause

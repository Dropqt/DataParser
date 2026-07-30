@echo off
rem ======================================================================
rem  eTurista - postavljanje na novom racunaru (Windows)
rem
rem  Klikni dva puta na ovaj fajl. Radi jednom sve sto treba:
rem    1. proveri da li ima Python
rem    2. napravi .venv
rem    3. instalira biblioteke iz requirements.txt
rem    4. proveri da sve radi (Chrome, git, folderi) i skine chromedriver
rem  i na kraju napravi .env iz .env.example.
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

rem --- 2/4  virtuelno okruzenje -----------------------------------------
if exist ".venv\Scripts\python.exe" goto :venv_postoji
echo [2/4] pravim .venv ...
%PY% -m venv .venv
if errorlevel 1 goto :venv_pukao
goto :venv_gotov

:venv_postoji
echo [2/4] .venv vec postoji, koristim njega

:venv_gotov

rem --- 3/4  biblioteke --------------------------------------------------
echo [3/4] instaliram biblioteke ...
echo       PySide6 je krupan, prvi put ume da potraje par minuta.
echo.
".venv\Scripts\python.exe" -m pip install --upgrade pip
".venv\Scripts\python.exe" -m pip install -r requirements.txt
if errorlevel 1 goto :paketi_pukli

rem --- lozinke ----------------------------------------------------------
if exist ".env" goto :env_postoji
copy ".env.example" ".env" >nul
echo.
echo Napravljen je .env - u njemu stoje korisnicka imena i lozinke naloga.
echo Ne mora da se otvara rucno: naloge unesi u samoj aplikaciji, u meniju
echo    Alatke -^> Podesavanja
echo Aplikacija ce ih sama ponuditi pri prvom pokretanju.
goto :env_gotov

:env_postoji
echo.
echo .env vec postoji, ne diram ga - u njemu su lozinke.

:env_gotov

rem --- 4/4  provera ----------------------------------------------------
rem  Ista provera radi i na Linux-u i moze da se testira, za razliku od .bat
rem  logike. Usput natera Selenium da odmah skine chromedriver, dok korisnik
rem  sigurno ima internet - inace to ceka prvu turu.
echo.
echo [4/4] proveravam da sve radi ...
echo       Prvi put ovde ume da stoji tridesetak sekundi, dok se skine
echo       drajver za Chrome.
echo.
".venv\Scripts\python.exe" run.py --provera-sistema --pripremi-drajver
if errorlevel 1 goto :provera_pukla

echo.
echo ======================================================
echo   Gotovo.
echo.
echo   Aplikacija se pokrece duplim klikom na pokreni.bat
echo.
echo   Naloge unesi u aplikaciji: Alatke -^> Podesavanja
echo.
echo   Kasnije azuriranje na noviju verziju: azuriraj.bat
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

:provera_pukla
echo.
echo Postavljanje je proslo, ali provera javlja da nesto nedostaje.
echo Pogledaj redove oznacene sa [GRESKA] iznad - u njima pise sta i odakle
echo se skida.
echo.
echo Ako pise da se biblioteke ne ucitavaju, .venv je najverovatnije napravljen
echo starijom verzijom Pythona pa vise ne vidi svoje pakete. Popravka: obrisi
echo folder .venv i pokreni ovaj fajl ponovo.
goto :kraj

:kraj
echo.
pause

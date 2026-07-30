@echo off
rem ======================================================================
rem  eTurista - azuriranje na noviju verziju (Windows)
rem
rem  Klikni dva puta na ovaj fajl. Povuce novu verziju sa GitHub-a,
rem  doinstalira sto je u medjuvremenu dodato, pa proveri da sve radi.
rem
rem  .env se NE dira - u njemu su lozinke i podesavanja.
rem
rem  Poruke su bez kvacica - CMD prozor koristi staru kodnu stranu, pa bi
rem  se "s" i "c" sa kvacicom prikazali kao smece.
rem ======================================================================

cd /d "%~dp0"
title eTurista - azuriranje

echo.
echo ======================================================
echo   eTurista - azuriranje
echo ======================================================
echo.

if not exist "run.py" goto :nema_projekta
if not exist ".git" goto :nije_git
if not exist ".venv\Scripts\python.exe" goto :nema_venv

rem --- 1/3  nova verzija ------------------------------------------------
git --version >nul 2>&1
if errorlevel 1 goto :nema_gita

echo [1/3] povlacim novu verziju sa GitHub-a ...
git pull --ff-only
if errorlevel 1 goto :pull_pukao

rem --- 2/3  biblioteke --------------------------------------------------
echo.
echo [2/3] doinstaliram biblioteke ...
".venv\Scripts\python.exe" -m pip install -r requirements.txt
if errorlevel 1 goto :paketi_pukli

rem --- 3/3  provera -----------------------------------------------------
echo.
echo [3/3] proveravam da sve radi ...
echo.
".venv\Scripts\python.exe" run.py --provera-sistema
if errorlevel 1 goto :provera_pukla

echo.
echo ======================================================
echo   Gotovo. Aplikacija se pokrece sa pokreni.bat
echo ======================================================
goto :kraj

rem --- poruke o gresci --------------------------------------------------

:nema_projekta
echo GRESKA: u ovom folderu nema run.py.
echo.
echo Ovaj fajl mora da stoji u folderu cele aplikacije, zajedno sa run.py
echo i postavi.bat.
goto :kraj

:nije_git
echo Ova kopija nije preuzeta gitom, pa ne moze ovako da se azurira.
echo.
echo Skini novu verziju sa GitHub-a kao ZIP i raspakuj je preko ovog
echo foldera. Fajl .env sa lozinkama ostaje kakav jeste - ZIP ga nema.
goto :kraj

:nema_gita
echo GRESKA: git nije nadjen.
echo.
echo Skini ga sa https://git-scm.com/download/win pa pokreni ovaj fajl
echo ponovo. Ili skini novu verziju rucno, kao ZIP sa GitHub-a.
goto :kraj

:nema_venv
echo Aplikacija jos nije postavljena na ovom racunaru.
echo.
echo Pokreni prvo postavi.bat u istom folderu.
goto :kraj

:pull_pukao
echo.
echo GRESKA: povlacenje nove verzije nije uspelo. Nista nije promenjeno.
echo.
echo Najcesce je razlog to sto su neki fajlovi lokalno menjani, pa bi ih
echo novo stanje pregazilo. Posalji ovaj ispis onome ko odrzava program.
goto :kraj

:paketi_pukli
echo.
echo GRESKA: instaliranje biblioteka nije uspelo.
echo.
echo Proveri da racunar ima internet, pa pokreni ovaj fajl ponovo.
echo Vec skinuto se ne skida ponovo, pa drugi pokusaj ide brze.
goto :kraj

:provera_pukla
echo.
echo Azuriranje je proslo, ali provera javlja da nesto nedostaje.
echo Pogledaj redove oznacene sa [GRESKA] iznad.
goto :kraj

:kraj
echo.
pause

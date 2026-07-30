@echo off
rem ======================================================================
rem  eTurista - pokretanje aplikacije (Windows)
rem
rem  Klikni dva puta na ovaj fajl. Nema komandne linije, nema kucanja:
rem  sam uzima Python iz .venv foldera i otvara aplikaciju.
rem
rem  Pre prvog pokretanja mora jednom da se pokrene postavi.bat.
rem
rem  Poruke su bez kvacica - CMD prozor koristi staru kodnu stranu, pa bi
rem  se "s" i "c" sa kvacicom prikazali kao smece.
rem ======================================================================

cd /d "%~dp0"
title eTurista

if not exist "run.py" goto :nema_projekta
if not exist ".venv\Scripts\pythonw.exe" goto :nema_venv
if not exist ".venv\Lib\site-packages\PySide6" goto :nema_biblioteka
if not exist ".env" call :bez_env

rem  pythonw umesto python: aplikacija se otvara bez crnog prozora iza sebe.
rem  start bez cekanja, pa se i ovaj prozor odmah zatvara.
start "" ".venv\Scripts\pythonw.exe" "run.py"
exit /b 0

rem --- poruke o gresci --------------------------------------------------

:nema_projekta
echo.
echo GRESKA: u ovom folderu nema run.py.
echo.
echo Ovaj fajl mora da stoji u folderu cele aplikacije, zajedno sa run.py
echo i postavi.bat.
goto :kraj

:nema_venv
echo.
echo Aplikacija jos nije postavljena na ovom racunaru.
echo.
echo Pokreni prvo postavi.bat u istom folderu - on instalira sve sto treba.
echo Posle toga ovaj fajl radi.
goto :kraj

:nema_biblioteka
echo.
echo GRESKA: .venv postoji, ali biblioteke nisu instalirane u njemu.
echo.
echo Pokreni postavi.bat ponovo - dovrsice instalaciju.
goto :kraj

:bez_env
echo.
echo Nema .env fajla, pa jos nema nijednog naloga za prijavu.
echo.
echo Aplikacija ce se svejedno otvoriti i sama ponuditi da ih unesete -
echo meni Alatke -^> Podesavanja. Nista se ne mora uredjivati rucno.
echo.
goto :eof

:kraj
echo.
pause

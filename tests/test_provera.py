"""Provera sistema i nalazenje Chrome-a na Windows-u."""

from __future__ import annotations

import sys

import pytest

from eturista import driver, provera


# --- pojedinacni nalazi -----------------------------------------------------

def test_python_verzija_prolazi():
    nalaz = provera.proveri_python()
    assert nalaz.ok and nalaz.obavezno


def test_biblioteke_su_na_broju():
    """Testovi se i pokrecu iz .venv-a, pa sve mora da postoji."""
    assert provera.proveri_biblioteke().ok


def test_biblioteka_koja_fali_se_prijavi(monkeypatch):
    monkeypatch.setattr(provera, "_REQUIRED", (("nepostojeci_paket", "nista"),))
    nalaz = provera.proveri_biblioteke()

    assert not nalaz.ok
    assert "nepostojeci_paket" in nalaz.poruka
    assert "postavi.bat" in nalaz.poruka


def test_oznaka_razlikuje_gresku_od_upozorenja():
    assert provera.Nalaz("a", True, "").oznaka.strip() == "[u redu]"
    assert provera.Nalaz("a", False, "").oznaka.strip() == "[GRESKA]"
    assert provera.Nalaz("a", False, "", obavezno=False).oznaka.strip() == "[pazi]"


def test_ispis_je_ceo_ascii(capsys):
    """Izvestaj ide u CMD prozor sa starom kodnom stranom - kvacice bi bile smece."""
    provera.ispisi(provera.proveri_sistem())
    assert capsys.readouterr().out.isascii()


# --- izlazni kod ------------------------------------------------------------

def test_izlazni_kod_je_nula_kad_je_sve_u_redu(capsys):
    nalazi = [provera.Nalaz("a", True, "")]
    assert provera.ispisi(nalazi) == 0


def test_upozorenje_ne_obara_izlazni_kod(capsys):
    nalazi = [provera.Nalaz("a", True, ""), provera.Nalaz("b", False, "", obavezno=False)]
    assert provera.ispisi(nalazi) == 0


def test_obavezan_nalaz_obara_izlazni_kod(capsys):
    nalazi = [provera.Nalaz("a", False, "")]
    assert provera.ispisi(nalazi) == 1


def test_bez_biblioteka_se_ne_ide_dalje(monkeypatch):
    """Bez selenium-a bi ostale provere pukle sa trejsbekom umesto da kazu sta fali."""
    monkeypatch.setattr(provera, "_REQUIRED", (("nepostojeci_paket", "nista"),))
    nalazi = provera.proveri_sistem()

    assert [n.naziv for n in nalazi] == ["Python", "Biblioteke", "Ostalo"]


# --- Chrome na Windows-u ----------------------------------------------------

@pytest.fixture
def windows(monkeypatch):
    """Glumi Windows na Linux-u.

    ``os.path.expandvars`` siri ``%IME%`` samo na Windows-u - na Linux-u zna samo za
    ``$IME``, pa bi grana koju testiramo ostala nedodirnuta. Zato se ovde podmece
    sirenje koje radi svuda; sve ostalo (preskakanje nerazresenog, provera da fajl
    postoji) je nas kod i testira se onakav kakav jeste.
    """
    import os as _os

    monkeypatch.setattr(sys, "platform", "win32")
    monkeypatch.setattr(driver.shutil, "which", lambda name: None)

    def expandvars(text: str) -> str:
        for kljuc, vrednost in _os.environ.items():
            text = text.replace(f"%{kljuc}%", vrednost)
        return text

    monkeypatch.setattr(driver.os.path, "expandvars", expandvars)


def test_windows_chrome_se_nadje_u_program_files(tmp_path, monkeypatch, windows):
    chrome = tmp_path / "chrome.exe"
    chrome.write_text("", encoding="utf-8")

    monkeypatch.setenv("ProgramFiles", str(tmp_path))
    monkeypatch.setattr(driver, "_WINDOWS_CHROME_PATHS", ("%ProgramFiles%/chrome.exe",))

    assert driver.find_chrome_binary() == str(chrome)


def test_windows_putanja_koja_ne_postoji_se_preskace(tmp_path, monkeypatch, windows):
    """Zastarela putanja je gora od nikakve - binary_location na nju obara Chrome."""
    monkeypatch.setenv("ProgramFiles", str(tmp_path))
    monkeypatch.setattr(driver, "_WINDOWS_CHROME_PATHS", ("%ProgramFiles%/chrome.exe",))

    # winreg na Linux-u ne postoji, pa se pada na None - isto sto i prazan registar.
    assert driver.find_chrome_binary() is None


def test_prva_putanja_koja_postoji_pobedjuje(tmp_path, monkeypatch, windows):
    drugi = tmp_path / "drugi.exe"
    drugi.write_text("", encoding="utf-8")

    monkeypatch.setenv("ProgramFiles", str(tmp_path))
    monkeypatch.setattr(driver, "_WINDOWS_CHROME_PATHS", (
        "%ProgramFiles%/nema.exe",
        "%ProgramFiles%/drugi.exe",
    ))

    assert driver.find_chrome_binary() == str(drugi)


def test_nerazresena_promenljiva_okruzenja_se_preskace(monkeypatch, windows):
    """expandvars ostavi %IME% kad promenljive nema - to nije putanja."""
    monkeypatch.delenv("ProgramFiles", raising=False)
    monkeypatch.setattr(driver, "_WINDOWS_CHROME_PATHS", ("%ProgramFiles%/chrome.exe",))

    assert driver.find_chrome_binary() is None


def test_na_linuxu_se_windows_grana_ne_pali(monkeypatch):
    monkeypatch.setattr(sys, "platform", "linux")
    monkeypatch.setattr(driver.shutil, "which", lambda name: None)

    def ne_zovi_me():
        raise AssertionError("Windows grana ne sme da se pozove na Linux-u")

    monkeypatch.setattr(driver, "_windows_chrome", ne_zovi_me)
    assert driver.find_chrome_binary() is None


def test_chrome_iz_path_a_ima_prednost(monkeypatch):
    monkeypatch.setattr(driver.shutil, "which", lambda name: "/usr/bin/chromium" if name == "chromium" else None)
    assert driver.find_chrome_binary() == "/usr/bin/chromium"

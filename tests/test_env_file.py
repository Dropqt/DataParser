import os

import pytest

from eturista import env_file

PRIMER = """\
# Kopiraj u .env i popuni pravim podacima.

# ---- Nalog 1 ----
ETURISTA_NALOG1_NAZIV=majka
ETURISTA_NALOG1_USER=
ETURISTA_NALOG1_PASS=

# ---- Podesavanja ----
# Osnovni URL portala
ETURISTA_URL=https://www.portal.eturista.gov.rs
"""


@pytest.fixture
def app_folder(tmp_path, monkeypatch):
    """Folder aplikacije premešten u tmp, sa .env.example u njemu."""
    (tmp_path / ".env.example").write_text(PRIMER, encoding="utf-8")
    monkeypatch.setattr(env_file, "app_dir", lambda: tmp_path)
    return tmp_path


def test_env_is_created_from_the_example(app_folder):
    env_file.create_if_missing()

    assert (app_folder / ".env").is_file()
    assert env_file.read_env()["ETURISTA_NALOG1_NAZIV"] == "majka"


def test_comments_survive_a_write(app_folder):
    env_file.write_env({"ETURISTA_NALOG1_USER": "danica@primer.rs"})

    lines = (app_folder / ".env").read_text(encoding="utf-8").splitlines()
    comments = [line for line in lines if line.startswith("#")]
    assert comments == [line for line in PRIMER.splitlines() if line.startswith("#")]


def test_value_is_replaced_in_place(app_folder):
    env_file.write_env({"ETURISTA_NALOG1_USER": "danica@primer.rs"})
    lines = (app_folder / ".env").read_text(encoding="utf-8").splitlines()

    # Isti broj redova i ključ na svom starom mestu - fajl se ne prepisuje ispočetka.
    assert len(lines) == len(PRIMER.splitlines())
    assert lines[4] == "ETURISTA_NALOG1_USER=danica@primer.rs"


def test_unknown_key_is_appended(app_folder):
    env_file.write_env({"ETURISTA_NOVO": "1"})

    text = (app_folder / ".env").read_text(encoding="utf-8")
    assert text.rstrip().endswith("ETURISTA_NOVO=1")
    assert "Dodato iz aplikacije" in text


@pytest.mark.parametrize("password", [
    "obicna",
    'sa # tarabom',
    'sa " navodnikom',
    "sa 'apostrofom'",
    "sa \\ kosom crtom",
    "  sa razmacima  ",
    "sa  dva  razmaka",
    "=znak=jednakosti=",
])
def test_password_survives_the_round_trip(app_folder, password):
    """Lozinka se vraća znak po znak - tiho 'sređivanje' bi oborilo prijavu."""
    env_file.write_env({"ETURISTA_NALOG1_PASS": password})
    assert env_file.read_env()["ETURISTA_NALOG1_PASS"] == password


def test_writing_does_not_touch_other_keys(app_folder):
    env_file.write_env({"ETURISTA_NALOG1_PASS": "tajna", "ETURISTA_URL": "http://lokalno"})
    env_file.write_env({"ETURISTA_NALOG1_USER": "danica@primer.rs"})

    values = env_file.read_env()
    assert values["ETURISTA_NALOG1_PASS"] == "tajna"
    assert values["ETURISTA_URL"] == "http://lokalno"


def test_no_temp_file_is_left_behind(app_folder):
    env_file.write_env({"ETURISTA_URL": "http://lokalno"})
    assert not (app_folder / ".env.tmp").exists()


def test_original_survives_a_failed_write(app_folder, monkeypatch):
    env_file.write_env({"ETURISTA_URL": "http://prvo"})
    before = (app_folder / ".env").read_text(encoding="utf-8")

    def boom(*args, **kwargs):
        raise OSError("disk pun")

    monkeypatch.setattr(env_file.os, "replace", boom)
    with pytest.raises(OSError):
        env_file.write_env({"ETURISTA_URL": "http://drugo"})

    assert (app_folder / ".env").read_text(encoding="utf-8") == before
    assert not (app_folder / ".env.tmp").exists()


def test_reload_overrides_the_environment(app_folder, monkeypatch):
    """Bez override=True bi stara lozinka ostala u okruženju posle snimanja."""
    monkeypatch.setenv("ETURISTA_NALOG1_PASS", "stara")
    env_file.write_env({"ETURISTA_NALOG1_PASS": "nova"})

    env_file.reload()
    assert os.environ["ETURISTA_NALOG1_PASS"] == "nova"


def test_managed_keys_cover_every_account_and_setting():
    assert "ETURISTA_NALOG3_POTPIS" in env_file.MANAGED_KEYS
    assert "ETURISTA_PROVERA_AZURIRANJA" in env_file.MANAGED_KEYS
    # Bez duplikata - inače bi merge_lines dvaput upisao isti ključ.
    assert len(env_file.MANAGED_KEYS) == len(set(env_file.MANAGED_KEYS))


def test_duplicated_key_is_replaced_everywhere(app_folder):
    """dotenv čita poslednju pojavu - menjati samo prvu bi ostavilo staru vrednost."""
    (app_folder / ".env").write_text(
        "ETURISTA_URL=http://staro\n# komentar\nETURISTA_URL=http://takodje-staro\n",
        encoding="utf-8",
    )
    env_file.write_env({"ETURISTA_URL": "http://novo"})

    assert env_file.read_env()["ETURISTA_URL"] == "http://novo"
    text = (app_folder / ".env").read_text(encoding="utf-8")
    assert "staro" not in text
    assert "# komentar" in text

"""Nalozi za portal - čitaju se iz .env, biraju se iz dropdown-a u aplikaciji."""

from __future__ import annotations

import os
from dataclasses import dataclass

#: Koliko naloga tražimo u .env (ETURISTA_NALOG1_… do ETURISTA_NALOG3_…).
MAX_ACCOUNTS = 3


@dataclass(frozen=True)
class Account:
    label: str
    username: str
    password: str

    def __str__(self) -> str:
        return self.label

    def masked(self) -> str:
        """Za log - nikad ne ispisujemo lozinku."""
        return f"{self.label} ({self.username})"


def load_accounts() -> list[Account]:
    """Učitaj popunjene naloge iz okruženja, redom kojim su definisani.

    Nalog bez korisničkog imena ili lozinke se preskače - tako .env može da ima
    pripremljena sva tri slota, a da radi i kad su popunjena samo dva.
    ``Config.load()`` mora biti pozvan pre ovoga da bi .env bio učitan.
    """
    accounts: list[Account] = []
    for i in range(1, MAX_ACCOUNTS + 1):
        username = os.getenv(f"ETURISTA_NALOG{i}_USER", "").strip()
        password = os.getenv(f"ETURISTA_NALOG{i}_PASS", "").strip()
        if not username or not password:
            continue
        label = os.getenv(f"ETURISTA_NALOG{i}_NAZIV", "").strip() or f"nalog {i}"
        accounts.append(Account(label=label, username=username, password=password))
    return accounts


def find_account(accounts: list[Account], label: str) -> Account | None:
    return next((a for a in accounts if a.label == label), None)

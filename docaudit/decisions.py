"""Jurnalul deciziilor utilizatorului (SQLite local, lângă datele extrase).

Fiecare decizie are: cine, când, ce pagină, ce acțiune, de ce. O decizie se poate
anula oricând înainte de „Aplică” (Etapa 7); anularea nu șterge rândul, îl
marchează ca anulat, ca istoricul să rămână complet.

Acțiuni pe pagină (una curentă pe pagină, ultima câștigă):
    reference   pagina e versiunea bună
    mark_stale  de marcat ca învechită (în OneNote doar după „Aplică”)
    archive     de mutat în secțiunea „Arhivă” (doar după „Aplică”)
    keep        rămâne cum e
Alte acțiuni (se adună, nu se înlocuiesc):
    ignore      constatarea nu e o problemă (cu cheia constatării)
    not_in_group pagina nu face parte din grup (se scrie și în group_overrides.json)
    note        notă pentru mine
"""

from __future__ import annotations

import getpass
import sqlite3
from contextlib import closing
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path

DB_FILE = "decisions.db"
PAGE_ACTIONS = ("reference", "mark_stale", "archive", "keep")
OTHER_ACTIONS = ("ignore", "not_in_group", "note")
ACTIONS = PAGE_ACTIONS + OTHER_ACTIONS
PENDING_ACTIONS = ("mark_stale", "archive")  # cele care vor scrie în OneNote în Etapa 7

_SCHEMA = """
CREATE TABLE IF NOT EXISTS decisions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    created_at TEXT NOT NULL,
    user TEXT NOT NULL,
    page_id TEXT NOT NULL,
    group_id TEXT NOT NULL DEFAULT '',
    action TEXT NOT NULL,
    finding TEXT NOT NULL DEFAULT '',
    note TEXT NOT NULL DEFAULT '',
    undone_at TEXT,
    applied_at TEXT
);
CREATE INDEX IF NOT EXISTS idx_decisions_page ON decisions(page_id);
CREATE TABLE IF NOT EXISTS applied (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    decision_id INTEGER NOT NULL REFERENCES decisions(id),
    applied_at TEXT NOT NULL,
    user TEXT NOT NULL,
    action TEXT NOT NULL,
    page_id TEXT NOT NULL,
    title TEXT NOT NULL,
    notebook_id TEXT NOT NULL DEFAULT '',
    section_id TEXT NOT NULL DEFAULT '',
    section TEXT NOT NULL DEFAULT '',
    new_page_id TEXT NOT NULL DEFAULT '',
    old_title_html TEXT NOT NULL DEFAULT '',
    backup TEXT NOT NULL DEFAULT '',
    restored_at TEXT
);
"""


@dataclass
class Decision:
    id: int
    created_at: str
    user: str
    page_id: str
    group_id: str
    action: str
    finding: str
    note: str
    undone_at: str | None
    applied_at: str | None

    def to_dict(self) -> dict:
        return asdict(self)


def _now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _user() -> str:
    try:
        return getpass.getuser()
    except Exception:  # pragma: no cover - fără utilizator în mediu
        return "?"


class Journal:
    def __init__(self, folder: Path) -> None:
        self.path = folder / DB_FILE
        with closing(self._connect()) as db, db:
            db.executescript(_SCHEMA)

    def _connect(self) -> sqlite3.Connection:
        db = sqlite3.connect(self.path)
        db.row_factory = sqlite3.Row
        return db

    def add(self, page_id: str, action: str, group_id: str = "", finding: str = "", note: str = "",
            user: str | None = None) -> Decision:
        if action not in ACTIONS:
            raise ValueError(f"acțiune necunoscută: {action}")
        if action == "ignore" and not finding:
            raise ValueError("„ignore” are nevoie de cheia constatării")
        with closing(self._connect()) as db, db:
            cur = db.execute(
                "INSERT INTO decisions (created_at, user, page_id, group_id, action, finding, note)"
                " VALUES (?, ?, ?, ?, ?, ?, ?)",
                (_now(), user or _user(), page_id, group_id, action, finding, note))
            row = db.execute("SELECT * FROM decisions WHERE id = ?", (cur.lastrowid,)).fetchone()
        return Decision(**dict(row))

    def undo(self, decision_id: int) -> bool:
        """Anulează o decizie neaplicată. Întoarce False dacă nu există, e deja anulată sau aplicată."""
        with closing(self._connect()) as db, db:
            cur = db.execute("UPDATE decisions SET undone_at = ? WHERE id = ? AND undone_at IS NULL"
                             " AND applied_at IS NULL", (_now(), decision_id))
        return cur.rowcount == 1

    def history(self) -> list[Decision]:
        with closing(self._connect()) as db:
            rows = db.execute("SELECT * FROM decisions ORDER BY id DESC").fetchall()
        return [Decision(**dict(r)) for r in rows]

    def active(self) -> list[Decision]:
        return [d for d in self.history() if d.undone_at is None]

    def current(self) -> dict[str, Decision]:
        """Decizia curentă pentru fiecare pagină (doar acțiunile pe pagină; ultima câștigă)."""
        out: dict[str, Decision] = {}
        for d in self.active():  # cele mai noi întâi
            if d.action in PAGE_ACTIONS and d.page_id not in out:
                out[d.page_id] = d
        return out

    def ignored_findings(self) -> set[str]:
        return {d.finding for d in self.active() if d.action == "ignore"}

    def notes(self) -> dict[str, list[Decision]]:
        out: dict[str, list[Decision]] = {}
        for d in self.active():
            if d.action == "note":
                out.setdefault(d.page_id, []).append(d)
        return out

    # --- Etapa 7: ce s-a aplicat în OneNote ---
    def record_applied(self, decision_id: int, action: str, page_id: str, title: str, *, notebook_id: str = "",
                       section_id: str = "", section: str = "", new_page_id: str = "", old_title_html: str = "",
                       backup: str = "", user: str | None = None) -> int:
        now = _now()
        with closing(self._connect()) as db, db:
            cur = db.execute(
                "INSERT INTO applied (decision_id, applied_at, user, action, page_id, title, notebook_id, section_id,"
                " section, new_page_id, old_title_html, backup) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (decision_id, now, user or _user(), action, page_id, title, notebook_id, section_id, section,
                 new_page_id, old_title_html, backup))
            db.execute("UPDATE decisions SET applied_at = ? WHERE id = ?", (now, decision_id))
        return int(cur.lastrowid)

    def applied(self) -> list[dict]:
        with closing(self._connect()) as db:
            return [dict(r) for r in db.execute("SELECT * FROM applied ORDER BY id DESC").fetchall()]

    def get_applied(self, applied_id: int) -> dict | None:
        with closing(self._connect()) as db:
            row = db.execute("SELECT * FROM applied WHERE id = ?", (applied_id,)).fetchone()
        return dict(row) if row else None

    def mark_restored(self, applied_id: int, decision_id: int) -> None:
        """După restaurare, decizia se consideră anulată (pagina e din nou ca înainte)."""
        now = _now()
        with closing(self._connect()) as db, db:
            db.execute("UPDATE applied SET restored_at = ? WHERE id = ?", (now, applied_id))
            db.execute("UPDATE decisions SET undone_at = ? WHERE id = ?", (now, decision_id))

    def pending(self) -> list[Decision]:
        """Deciziile care, în Etapa 7, vor scrie în OneNote (arhivare, marcare), încă neaplicate."""
        return [d for d in self.current().values() if d.action in PENDING_ACTIONS and d.applied_at is None]


def finding_key(finding: dict) -> str:
    """Cheie stabilă pentru o constatare, ca „ignoră” să se păstreze între rulări."""
    d = finding.get("details", {})
    extra = d.get("step", "") if finding["kind"] != "stale" else ""
    return f"{finding['kind']}:{','.join(finding['pages'])}:{extra}"

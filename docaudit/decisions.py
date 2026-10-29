"""Jurnalul deciziilor utilizatorului (SQLite local, lângă datele extrase).

Fiecare decizie are: cine, când, ce pagină, ce acțiune, de ce. O decizie se poate
anula oricând înainte de „Aplică” (Etapa 7); anularea nu șterge rândul, îl
marchează ca anulat, ca istoricul să rămână complet.

Acțiuni pe pagină (una curentă pe pagină, ultima câștigă):
    reference   pagina e versiunea bună
    mark_stale  de marcat ca învechită (în OneNote doar după „Aplică”)
    archive     de mutat în secțiunea „Arhivă” (doar după „Aplică”)
    move        de mutat în altă secțiune, aleasă de utilizator (`target` = „notebook<TAB>secțiune”)
    keep        rămâne cum e
Modificări în pagină (pe lângă decizia de mai sus; scriu în OneNote doar după „Aplică”):
    rename      titlu nou (`target` = noul titlu; ultima câștigă)
    add_text    text adăugat în pagină (`target` = „top<TAB>text” sau „end<TAB>text”; se adună)
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
PAGE_ACTIONS = ("reference", "mark_stale", "archive", "move", "keep")
EDIT_ACTIONS = ("rename", "add_text")
OTHER_ACTIONS = ("ignore", "not_in_group", "note")
ACTIONS = PAGE_ACTIONS + EDIT_ACTIONS + OTHER_ACTIONS
PENDING_ACTIONS = ("mark_stale", "archive", "move")  # cele care scriu în OneNote la „Aplică”
TEXT_POSITIONS = ("top", "end")

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
    restored_at TEXT,
    added_ids TEXT NOT NULL DEFAULT '',
    after_modified TEXT NOT NULL DEFAULT ''
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
    target: str = ""  # „move”: „notebook<TAB>secțiune”; „rename”: titlul nou; „add_text”: „top|end<TAB>text”

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
            cols = {r["name"] for r in db.execute("PRAGMA table_info(decisions)")}
            if "target" not in cols:  # jurnale create înainte de 0.1.8
                db.execute("ALTER TABLE decisions ADD COLUMN target TEXT NOT NULL DEFAULT ''")
            cols = {r["name"] for r in db.execute("PRAGMA table_info(applied)")}
            for col in ("added_ids", "after_modified"):  # jurnale create înainte de 0.1.13
                if col not in cols:
                    db.execute(f"ALTER TABLE applied ADD COLUMN {col} TEXT NOT NULL DEFAULT ''")

    def _connect(self) -> sqlite3.Connection:
        db = sqlite3.connect(self.path)
        db.row_factory = sqlite3.Row
        return db

    def add(self, page_id: str, action: str, group_id: str = "", finding: str = "", note: str = "",
            user: str | None = None, target: str = "") -> Decision:
        if action not in ACTIONS:
            raise ValueError(f"acțiune necunoscută: {action}")
        if action == "ignore" and not finding:
            raise ValueError("„ignore” are nevoie de cheia constatării")
        if action == "move" and not split_target(target)[1]:
            raise ValueError("„move” are nevoie de secțiunea în care se mută pagina")
        if action == "rename":
            target = " ".join((target or "").split())
            if not target:
                raise ValueError("„rename” are nevoie de titlul nou")
        if action == "add_text":
            at, text = split_text_target(target)
            if not text:
                raise ValueError("„add_text” are nevoie de text și de poziție (top / end)")
            target = make_text_target(at, text)
        with closing(self._connect()) as db, db:
            cur = db.execute(
                "INSERT INTO decisions (created_at, user, page_id, group_id, action, finding, note, target)"
                " VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                (_now(), user or _user(), page_id, group_id, action, finding, note,
                 target if action in ("move",) + EDIT_ACTIONS else ""))
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

    def edits(self) -> dict[str, dict]:
        """Pe pagină: titlul nou (ultimul activ) și textele de adăugat, aplicate sau nu."""
        out: dict[str, dict] = {}
        for d in reversed(self.active()):  # cele mai vechi întâi
            e = out.setdefault(d.page_id, {"rename": None, "add_text": []})
            if d.action == "rename":
                e["rename"] = d
            elif d.action == "add_text":
                e["add_text"].append(d)
        return {pid: e for pid, e in out.items() if e["rename"] or e["add_text"]}

    def notes(self) -> dict[str, list[Decision]]:
        out: dict[str, list[Decision]] = {}
        for d in self.active():
            if d.action == "note":
                out.setdefault(d.page_id, []).append(d)
        return out

    # --- Etapa 7: ce s-a aplicat în OneNote ---
    def record_applied(self, decision_id: int, action: str, page_id: str, title: str, *, notebook_id: str = "",
                       section_id: str = "", section: str = "", new_page_id: str = "", old_title_html: str = "",
                       backup: str = "", added_ids: str = "", after_modified: str = "",
                       user: str | None = None) -> int:
        now = _now()
        with closing(self._connect()) as db, db:
            cur = db.execute(
                "INSERT INTO applied (decision_id, applied_at, user, action, page_id, title, notebook_id, section_id,"
                " section, new_page_id, old_title_html, backup, added_ids, after_modified)"
                " VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (decision_id, now, user or _user(), action, page_id, title, notebook_id, section_id, section,
                 new_page_id, old_title_html, backup, added_ids, after_modified))
            db.execute("UPDATE decisions SET applied_at = ? WHERE id = ?", (now, decision_id))
        return int(cur.lastrowid)

    def applied(self) -> list[dict]:
        with closing(self._connect()) as db:
            return [dict(r) for r in db.execute("SELECT * FROM applied ORDER BY id DESC").fetchall()]

    def get_applied(self, applied_id: int) -> dict | None:
        with closing(self._connect()) as db:
            row = db.execute("SELECT * FROM applied WHERE id = ?", (applied_id,)).fetchone()
        return dict(row) if row else None

    def mark_restored(self, applied_id: int, decision_id: int, after_modified: str = "") -> None:
        """După restaurare, decizia se consideră anulată (pagina e din nou ca înainte)."""
        now = _now()
        with closing(self._connect()) as db, db:
            db.execute("UPDATE applied SET restored_at = ?, after_modified = ? WHERE id = ?",
                       (now, after_modified, applied_id))
            db.execute("UPDATE decisions SET undone_at = ? WHERE id = ?", (now, decision_id))

    def own_modified(self) -> dict[str, str]:
        """page_id -> data modificării lăsată de ultima noastră scriere în pagină (aplicare sau restaurare)."""
        out: dict[str, str] = {}
        for r in sorted(self.applied(), key=lambda r: r["restored_at"] or r["applied_at"]):  # ultima câștigă
            if r["after_modified"]:
                out[r["page_id"]] = r["after_modified"]
        return out

    def pending(self) -> list[Decision]:
        """Deciziile care vor scrie în OneNote la „Aplică”, încă neaplicate."""
        out = [d for d in self.current().values() if d.action in PENDING_ACTIONS and d.applied_at is None]
        for e in self.edits().values():
            if e["rename"] and e["rename"].applied_at is None:
                out.append(e["rename"])
            out.extend(d for d in e["add_text"] if d.applied_at is None)
        return out


def make_target(notebook: str, section: str) -> str:
    return f"{notebook}\t{section}"


def split_target(target: str) -> tuple[str, str]:
    """„notebook<TAB>secțiune” → (notebook, secțiune); fără TAB: ("", "")."""
    notebook, sep, section = (target or "").partition("\t")
    return (notebook, section) if sep and section else ("", "")


def make_text_target(at: str, text: str) -> str:
    return f"{at}\t{text}"


def split_text_target(target: str) -> tuple[str, str]:
    """„top<TAB>text” → ("top", "text"); poziția lipsă sau greșită → "top"."""
    at, sep, text = (target or "").partition("\t")
    if not sep or at not in TEXT_POSITIONS:
        at, text = "top", target or ""
    return at, text.strip()


def finding_key(finding: dict) -> str:
    """Cheie stabilă pentru o constatare, ca „ignoră” să se păstreze între rulări."""
    d = finding.get("details", {})
    extra = d.get("step", "") if finding["kind"] != "stale" else ""
    return f"{finding['kind']}:{','.join(finding['pages'])}:{extra}"

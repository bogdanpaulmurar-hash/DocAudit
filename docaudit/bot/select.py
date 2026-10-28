"""Ce pagini intră în documentele pentru bot și în ce document.

Nu se pierde nimic pe tăcute: fiecare pagină lăsată deoparte are un motiv, iar
utilizatorul o poate include totuși (sau poate scoate o pagină) din ecran; alegerile
lui stau în `<extragere>/bot/overrides.json` și au prioritate.

Motive:
- `empty`     — pagina nu are text, imagini sau fișiere atașate;
- `duplicate` — același conținut ca altă pagină (rămâne una: referința, altfel cea mai nouă);
- `stale`     — compararea a găsit-o învechită (și nu ai ales „păstrează” / „referință”);
- `archived`  — ai decis „arhivează” sau „marchează învechit”;
- `excluded`  — ai scos-o tu din export.
Paginile fără titlu („Untitled page”, „Fără titlu”, „Unbenannt”) intră dacă au conținut,
dar sunt semnalate și nu se compară ca duplicate (OneNote le pune peste tot).
"""

from __future__ import annotations

import hashlib
import json
import re
from dataclasses import asdict, dataclass, field
from pathlib import Path

from ..decisions import Journal, finding_key, split_target
from ..group.text import normalize
from ..lang import is_untitled
from ..model import Page, read_pages

BOT_DIR = "bot"
OVERRIDES_FILE = "overrides.json"
LEVELS = ("notebook", "top", "section")
REASONS = ("empty", "duplicate", "stale", "archived", "excluded")
_BAD_CHARS = re.compile(r'[\\/:*?"<>|\x00-\x1f]+')


@dataclass
class BotPage:
    id: str
    title: str
    section: str
    doc: str
    included: bool = True
    reason: str = ""
    duplicate_of: str = ""
    untitled: bool = False
    override: str = ""  # "include" | "exclude" | ""
    modified: str = ""


@dataclass
class BotPlan:
    documents: list[dict] = field(default_factory=list)  # [{"name", "pages": [id, ...]}] doar paginile incluse
    pages: list[BotPage] = field(default_factory=list)

    def counts(self) -> dict[str, int]:
        out = {"included": sum(p.included for p in self.pages), "untitled": sum(p.untitled and p.included
                                                                               for p in self.pages)}
        for r in REASONS:
            out[r] = sum((not p.included) and p.reason == r for p in self.pages)
        return out

    def to_dict(self) -> dict:
        return {"documents": self.documents, "pages": [asdict(p) for p in self.pages], "counts": self.counts()}


def bot_dir(folder: Path) -> Path:
    return folder / BOT_DIR


def safe_name(text: str, limit: int = 80) -> str:
    """Nume de fișier valid pe Windows (diacriticele rămân)."""
    name = _BAD_CHARS.sub("_", text).strip().strip(".").strip()
    name = re.sub(r"\s+", " ", name)[:limit].rstrip(" .")
    return name or "Document"


def content_key(page: Page) -> str:
    """Amprenta conținutului: textul normalizat + imaginile + fișierele atașate."""
    parts = [normalize(page.text), *sorted(i.sha256 for i in page.images),
             *sorted(a.sha256 for a in page.attachments)]
    return hashlib.sha256("\n".join(parts).encode("utf-8")).hexdigest()


def is_empty(page: Page) -> bool:
    return not normalize(page.text) and not page.images and not page.attachments


def load_overrides(folder: Path) -> dict[str, str]:
    try:
        raw = json.loads((bot_dir(folder) / OVERRIDES_FILE).read_text("utf-8"))
    except (OSError, ValueError):
        return {}
    return {k: v for k, v in raw.items() if v in ("include", "exclude")} if isinstance(raw, dict) else {}


def set_override(folder: Path, page_id: str, value: str | None) -> dict[str, str]:
    """value: "include" / "exclude" / None (înapoi la regula automată)."""
    if value not in ("include", "exclude", None):
        raise ValueError(value)
    data = load_overrides(folder)
    if value is None:
        data.pop(page_id, None)
    else:
        data[page_id] = value
    path = bot_dir(folder) / OVERRIDES_FILE
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False, indent=1), encoding="utf-8")
    return data


def _doc_parts(notebook: str, section_path: list[str], level: str) -> tuple[str, ...]:
    if level == "notebook" or not section_path:
        return (notebook,)
    if level == "top":
        return (notebook, section_path[0])
    return (notebook, *section_path)


def _stale_pages(folder: Path, journal: Journal) -> set[str]:
    path = folder / "findings.json"
    if not path.is_file():
        return set()
    ignored = journal.ignored_findings()
    out: set[str] = set()
    for g in json.loads(path.read_text("utf-8")).get("groups", []):
        for f in g.get("findings", []):
            if f.get("kind") == "stale" and finding_key(f) not in ignored:
                out.update(f["pages"])
    return out


def build_plan(folder: Path, level: str = "top", skip_stale: bool = True, skip_duplicates: bool = True,
               pages: list[Page] | None = None) -> BotPlan:
    if level not in LEVELS:
        raise ValueError(level)
    pages = pages if pages is not None else read_pages(folder)
    journal = Journal(folder)
    current = journal.current()
    stale = _stale_pages(folder, journal) if skip_stale else set()
    overrides = load_overrides(folder)

    # unde ajunge fiecare pagină (o mutare decisă, încă neaplicată, contează deja)
    where: dict[str, tuple[str, list[str]]] = {}
    for p in pages:
        d = current.get(p.id)
        nb, sec = split_target(d.target) if d and d.action == "move" else ("", "")
        where[p.id] = (nb, [x for x in sec.split("/") if x]) if nb else (p.notebook, p.section_path)
    single_notebook = len({nb for nb, _ in where.values()}) == 1

    # duplicate exacte: rămâne referința, altfel pagina cea mai nouă, altfel prima
    keep_for: dict[str, str] = {}
    if skip_duplicates:
        by_key: dict[str, list[Page]] = {}
        for p in pages:
            if not is_empty(p) and not is_untitled(p.title):
                by_key.setdefault(content_key(p), []).append(p)
        for same in by_key.values():
            if len(same) < 2:
                continue
            order = {p.id: i for i, p in enumerate(same)}
            keep = min(same, key=lambda p: (current.get(p.id) is None or current[p.id].action != "reference",
                                            [-ord(c) for c in p.modified], order[p.id]))
            for p in same:
                if p.id != keep.id:
                    keep_for[p.id] = keep.id

    plan = BotPlan()
    docs: dict[tuple[str, ...], list[str]] = {}
    names: dict[tuple[str, ...], str] = {}
    for p in pages:
        nb, path = where[p.id]
        key = _doc_parts(nb, path, level)
        if key not in names:
            shown = key[1:] if single_notebook and len(key) > 1 else key
            names[key] = safe_name(" - ".join(shown))
        d = current.get(p.id)
        reason, dup = "", ""
        if is_empty(p):
            reason = "empty"
        elif d and d.action in ("archive", "mark_stale"):
            reason = "archived"
        elif p.id in keep_for:
            reason, dup = "duplicate", keep_for[p.id]
        elif p.id in stale and not (d and d.action in ("keep", "reference")):
            reason = "stale"
        ov = overrides.get(p.id, "")
        if ov == "exclude":
            reason = reason or "excluded"
        included = ov == "include" or (not reason)
        if ov == "exclude":
            included = False
        bp = BotPage(id=p.id, title=p.title, section=" › ".join([nb, *path]), doc=names[key], included=included,
                     reason=reason, duplicate_of=dup, untitled=is_untitled(p.title), override=ov, modified=p.modified)
        plan.pages.append(bp)
        if included:
            docs.setdefault(key, []).append(p.id)

    # două chei diferite cu același nume de fișier: al doilea primește un număr
    used: dict[str, int] = {}
    for key, ids in docs.items():
        name = names[key]
        n = used.get(name.casefold(), 0) + 1
        used[name.casefold()] = n
        if n > 1:
            name = f"{name} ({n})"
            for bp in plan.pages:
                if bp.doc == names[key] and bp.id in ids:
                    bp.doc = name
        plan.documents.append({"name": name, "pages": ids})
    return plan

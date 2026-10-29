"""Raportul: constatările + deciziile, ca HTML (de citit sau printat), CSV (Excel) sau Markdown.

`build_state()` adună tot ce arată interfața și raportul: grupurile, paginile cu
decizia lor curentă, constatările (cu cele ignorate marcate). Doar citește.
"""

from __future__ import annotations

import csv
import html
import io
import json
from pathlib import Path

from .compare.run import FINDINGS_FILE
from .decisions import Journal, finding_key, split_target, split_text_target
from .group.run import GROUPS_FILE
from .i18n import t
from .model import MANIFEST_FILE, read_pages

FORMATS = ("html", "csv", "md")
_SEVERITY_ORDER = {"high": 0, "medium": 1, "low": 2}


def _json(path: Path) -> dict | None:
    return json.loads(path.read_text("utf-8")) if path.is_file() else None


def build_state(folder: Path, lang: str | None = None) -> dict:
    manifest = _json(folder / MANIFEST_FILE) or {}
    groups = _json(folder / GROUPS_FILE)
    findings = _json(folder / FINDINGS_FILE)
    pages = {p.id: p for p in read_pages(folder)}
    journal = Journal(folder)
    current = journal.current()
    ignored = journal.ignored_findings()
    notes = journal.notes()
    edits = journal.edits()

    def page_info(pid: str) -> dict:
        p = pages.get(pid)
        d = current.get(pid)
        return {
            "id": pid,
            "title": p.title if p else pid,
            "notebook": p.notebook if p else "",
            "section": "/".join(p.section_path) if p else "",
            "modified": p.modified if p else "",
            "decision": d.action if d else None,
            "decision_id": d.id if d else None,
            "decision_target": " › ".join(x for x in split_target(d.target) if x) if d and d.action == "move" else "",
            "notes": [n.note for n in notes.get(pid, [])],
            **_edits_info(edits.get(pid)),
        }

    titles = {pid: p.title for pid, p in pages.items()}
    reports = {g["group"]: g for g in (findings or {}).get("groups", [])}
    out_groups = []
    for g in (groups or {}).get("groups", []):
        rep = reports.get(g["id"], {})
        items = []
        for f in rep.get("findings", []):
            key = finding_key(f)
            items.append({**f, "key": key, "ignored": key in ignored, "text": describe(f, titles, lang)})
        open_items = [f for f in items if not f["ignored"]]
        severity = min((_SEVERITY_ORDER[f["severity"]] for f in open_items), default=3)
        decided = all(pid in current for pid in g["pages"])
        out_groups.append({
            "id": g["id"], "label": g["label"], "score": g.get("avg_score"),
            "pages": [page_info(pid) for pid in g["pages"]],
            "reference": rep.get("reference"),
            "other_language": rep.get("other_language", []),
            "findings": items,
            "severity": ("high", "medium", "low", "none")[severity],
            "resolved": decided or not open_items,
        })
    out_groups.sort(key=lambda g: (g["resolved"], ("high", "medium", "low", "none").index(g["severity"]),
                                   g["label"].casefold()))
    return {
        "folder": str(folder),
        "name": folder.name,
        "page_count": len(pages),
        "extracted_at": manifest.get("extracted_at", ""),
        "source": (manifest.get("source") or {}).get("ref", ""),
        "grouped": groups is not None,
        "compared": findings is not None,
        "threshold": (groups or {}).get("threshold"),
        "semantic": (groups or {}).get("semantic", False),
        "groups": out_groups,
        "ungrouped": len((groups or {}).get("ungrouped", [])),
        "shared_images": (findings or {}).get("shared_images", []),
        "pending": [d.to_dict() | {"title": page_info(d.page_id)["title"],
                                   "section": page_info(d.page_id)["section"]} for d in journal.pending()],
        "history": [d.to_dict() for d in journal.history()],
    }


def _edits_info(e: dict | None) -> dict:
    """Titlul nou și textele de adăugat ale unei pagini, pentru interfață."""
    r = e["rename"] if e else None
    texts = []
    for d in (e["add_text"] if e else []):
        at, text = split_text_target(d.target)
        texts.append({"id": d.id, "at": at, "text": text, "applied": d.applied_at is not None})
    return {"rename": {"id": r.id, "title": r.target, "applied": r.applied_at is not None} if r else None,
            "added_texts": texts}


def describe(f: dict, titles: dict[str, str], lang: str | None = None) -> str:
    """Constatarea într-o frază, pentru raport (aceleași texte ca în CLI)."""
    d = f["details"]

    def names(ids: list[str]) -> str:
        return ", ".join(titles.get(i, i) for i in ids)

    if f["kind"] == "value_conflict":
        vals = " · ".join(f"{v or '—'} ({titles.get(p, p)})" for p, v in d["values"].items())
        return t("cli.compare.value_conflict", lang, values=vals).strip()
    if f["kind"] in ("missing_step", "extra_step"):
        return t(f"cli.compare.{f['kind']}", lang, pages=names(f["pages"]), text=d["text"]).strip()
    if f["kind"] == "reordered":
        return t("cli.compare.reordered", lang, page=names([d["page"]]), text=" / ".join(d["texts"])).strip()
    if f["kind"] == "duplicate":
        return t("cli.compare.duplicate", lang, similarity=d["similarity"], pages=names(f["pages"])).strip()
    if f["kind"] == "stale":
        reasons = []
        for r in d["reasons"]:
            if r["reason"] == "marker":
                reasons.append(t("cli.compare.reason.marker", lang, value=", ".join(r["markers"])))
            elif r["reason"] == "old":
                reasons.append(t("cli.compare.reason.old", lang, days=r["days_older"]))
            else:
                reasons.append(t(f"cli.compare.reason.{r['reason']}", lang, value=r["value"], other=r.get("other", "")))
        return t("cli.compare.stale", lang, page=names(f["pages"]), reasons="; ".join(reasons)).strip()
    return t("cli.compare.shared_image", lang, pages=names(f["pages"])).strip()


def _rows(state: dict, lang: str | None) -> list[dict]:
    titles = {p["id"]: p["title"] for g in state["groups"] for p in g["pages"]}
    rows = []
    for g in state["groups"]:
        for f in g["findings"]:
            rows.append({
                "group": g["label"], "severity": t(f"ui.severity.{f['severity']}", lang),
                "kind": t(f"ui.kind.{f['kind']}", lang), "pages": "; ".join(titles.get(p, p) for p in f["pages"]),
                "text": describe(f, titles, lang),
                "status": t("ui.ignored", lang) if f["ignored"] else "",
                "decisions": "; ".join(f"{p['title']}: {t('ui.action.' + p['decision'], lang)}"
                                       for p in g["pages"] if p["decision"] and p["id"] in f["pages"]),
            })
    return rows


_COLUMNS = ("group", "severity", "kind", "pages", "text", "status", "decisions")


def render(state: dict, fmt: str, lang: str | None = None) -> str:
    if fmt not in FORMATS:
        raise ValueError(fmt)
    rows = _rows(state, lang)
    head = [t(f"ui.report.col.{c}", lang) for c in _COLUMNS]
    if fmt == "csv":
        buf = io.StringIO()
        w = csv.writer(buf, delimiter=";")  # Excel în setările românești/germane folosește „;”
        w.writerow(head)
        for r in rows:
            w.writerow([r[c] for c in _COLUMNS])
        return "\ufeff" + buf.getvalue()  # BOM: Excel recunoaște UTF-8 (diacritice)
    title = t("ui.report.title", lang, name=state["name"])
    summary = t("ui.report.summary", lang, pages=state["page_count"], groups=len(state["groups"]),
                findings=len(rows), pending=len(state["pending"]))
    if fmt == "md":
        def cell(s: str) -> str:
            return s.replace("|", "\\|").replace("\n", " ")
        lines = [f"# {title}", "", summary, "", "| " + " | ".join(head) + " |", "|" + "---|" * len(head)]
        lines += ["| " + " | ".join(cell(r[c]) for c in _COLUMNS) + " |" for r in rows]
        return "\n".join(lines) + "\n"
    e = html.escape
    body = "".join("<tr>" + "".join(f"<td>{e(r[c])}</td>" for c in _COLUMNS) + "</tr>" for r in rows)
    return (f"<!doctype html><html lang=\"{lang or 'ro'}\"><head><meta charset=\"utf-8\"><title>{e(title)}</title>"
            "<style>body{font:14px system-ui,sans-serif;margin:24px;color:#1f2328}"
            "table{border-collapse:collapse;width:100%}td,th{border:1px solid #d0d7de;padding:6px 8px;"
            "text-align:left;vertical-align:top}th{background:#f6f8fa}h1{font-size:20px}</style></head>"
            f"<body><h1>{e(title)}</h1><p>{e(summary)}</p><table><thead><tr>"
            + "".join(f"<th>{e(h)}</th>" for h in head) + f"</tr></thead><tbody>{body}</tbody></table></body></html>\n")

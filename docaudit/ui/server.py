"""Interfața web locală: un server mic din biblioteca standard, doar pe 127.0.0.1.

Protecții:
- ascultă doar pe o adresă locală (refuză altceva la pornire);
- acceptă doar cereri cu Host 127.0.0.1 / localhost (împotriva „DNS rebinding”);
- orice /api/ cere un jeton aleator, generat la pornire și pus doar în pagina servită
  de acest server (alt site deschis în browser nu îl poate afla);
- fără CORS, fără resurse externe, fără telemetrie.
"""

from __future__ import annotations

import contextlib

import json
import mimetypes
import secrets
import sys
import threading
import webbrowser
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from importlib import resources
from pathlib import Path
from urllib.parse import parse_qs, urlparse

from .. import __version__, log
from ..i18n import LANGUAGES, _load
from ..model import PAGES_FILE, image_path, read_manifest, read_pages
from ..paths import data_dir, datasets
from ..safety import is_loopback
from ..settings import load_settings, update_settings

_write_lock = threading.Lock()  # o singură analiză / extragere / aplicare odată
_lg = log.get("ui")


class ApiError(Exception):
    def __init__(self, status: int, key: str, **params: object) -> None:
        super().__init__(key)
        self.status, self.key, self.params = status, key, params


def _static(name: str) -> bytes:
    return resources.files("docaudit.ui").joinpath(f"static/{name}").read_bytes()


def _dataset(name: str | None) -> Path:
    if not name or "/" in name or "\\" in name or name.startswith("."):
        raise ApiError(400, "ui.error.dataset")
    folder = data_dir() / name
    if not (folder / PAGES_FILE).is_file():
        raise ApiError(404, "ui.error.dataset")
    return folder


def _ui_texts(lang: str) -> dict[str, str]:
    base = {k: v for k, v in _load("ro").items() if k.startswith(("ui.", "cli.compare.", "apply.", "diag."))}
    base.update({k: v for k, v in _load(lang).items() if k.startswith(("ui.", "cli.compare.", "apply.", "diag."))})
    return base


# ---------- acțiunile API ----------

def api_info(q: dict) -> dict:
    from ..extract.selection import list_profiles

    items = []
    for folder in datasets():
        try:
            m = read_manifest(folder)
            items.append({"name": folder.name, "pages": m.page_count, "extracted_at": m.extracted_at,
                          "source": m.source.kind, "grouped": (folder / "groups.json").is_file(),
                          "compared": (folder / "findings.json").is_file()})
        except Exception:
            continue
    import importlib.util

    return {"version": __version__, "languages": list(LANGUAGES), "settings": load_settings().to_dict(),
            "semantic_available": importlib.util.find_spec("sentence_transformers") is not None,
            "log": log.info(), "datasets": items, "profiles": list_profiles(data_dir() / "profiles"), "data_dir": str(data_dir())}


def api_texts(q: dict) -> dict:
    lang = q.get("lang") or load_settings().lang
    return _ui_texts(lang if lang in LANGUAGES else "ro")


def api_state(q: dict) -> dict:
    from ..report import build_state

    lang = q.get("lang") if q.get("lang") in LANGUAGES else load_settings().lang
    return build_state(_dataset(q.get("ds")), lang)


def api_page(q: dict) -> dict:
    folder = _dataset(q.get("ds"))
    page = next((p for p in read_pages(folder) if p.id == q.get("id")), None)
    if page is None:
        raise ApiError(404, "ui.error.page")
    return page.to_dict()


def _hierarchy(demo: bool):
    from ..extract.com import OneNoteError
    from ..extract.onenote_xml import parse_hierarchy

    try:
        if demo:
            from ..extract.demo import DemoOneNote

            source = DemoOneNote()
        else:  # pragma: no cover - Windows
            from ..extract.com import ReadOnlyOneNote

            source = ReadOnlyOneNote()
        return parse_hierarchy(source.get_hierarchy_xml())
    except OneNoteError as e:
        raise ApiError(503, "ui.error.onenote", error=str(e))


def api_tree(q: dict) -> dict:
    h = _hierarchy(q.get("demo") == "1")
    return {"notebooks": [{"name": nb.name, "location": nb.location, "sections": [
        {"path": "/".join(s.path), "pages": [{"id": p.id, "title": p.title, "modified": p.modified} for p in s.pages]}
        for s in nb.sections]} for nb in h.notebooks]}


def api_diagnose(q: dict) -> dict:
    """Verifică pe rând legătura cu OneNote (doar citire)."""
    from ..extract.diagnose import diagnose

    if q.get("demo") == "1":
        from ..extract.demo import DemoOneNote

        checks = diagnose(DemoOneNote, windows_checks=False)
    else:
        checks = diagnose()
    return {"checks": [c.to_dict() for c in checks]}


def api_link(body: dict) -> dict:
    """Link-ul din browser → notebook-ul (și secțiunea) din OneNote desktop. Fără rețea."""
    from ..extract.links import LinkError, match_link, parse_link

    try:
        info = parse_link(str(body.get("link") or ""))
    except LinkError:
        raise ApiError(400, "ui.error.link")
    m = match_link(_hierarchy(bool(body.get("demo"))), info)
    return {"found": m is not None, "notebook": m and m.notebook, "section": m and m.section,
            "page": info.page, "open_url": info.open_url}


class Job:
    """O extragere care rulează în fundal: notebook-urile mari (sute de pagini) durează minute."""

    def __init__(self, kind: str) -> None:
        self.id = secrets.token_hex(6)
        self.kind = kind
        self.state = "running"  # running | done | error
        self.done = 0
        self.total = 0
        self.result: dict | None = None
        self.error: dict | None = None
        self.cancel = threading.Event()
        self.child_log: list[str] = []  # rândurile de log ale procesului de extragere

    def to_dict(self) -> dict:
        return {"id": self.id, "kind": self.kind, "state": self.state, "done": self.done, "total": self.total,
                "result": self.result, "error": self.error,
                "log": (self.child_log or log.tail(12))[-12:]}


_jobs: dict[str, Job] = {}


def _start_job(kind: str, work) -> Job:
    """Pornește `work(job)` într-un fir separat, dacă nu rulează deja altă scriere."""
    if not _write_lock.acquire(blocking=False):
        raise ApiError(409, "ui.error.busy")
    job = Job(kind)
    _jobs[job.id] = job

    def run() -> None:
        try:
            job.result = work(job)
            job.state = "done"
        except ApiError as e:
            job.error = {"error": e.key, "params": {k: str(v) for k, v in e.params.items()}}
            job.state = "error"
            _lg.error("%s: %s %s", kind, e.key, log.describe_error(e) if e.params else "")
        except Exception as e:  # o eroare neprevăzută: în log cu locul din cod
            job.error = {"error": "ui.error.internal", "params": {"error": f"{type(e).__name__}: {e}"}}
            job.state = "error"
            _lg.exception("%s a picat: %s", kind, log.describe_error(e))
        finally:
            _write_lock.release()

    threading.Thread(target=run, daemon=True, name=f"docaudit-{kind}").start()
    return job


def api_job(q: dict) -> dict:
    job = _jobs.get(q.get("id") or "")
    if job is None:
        raise ApiError(404, "ui.error.notfound")
    return job.to_dict()


def api_job_cancel(body: dict) -> dict:
    job = _jobs.get(str(body.get("id") or ""))
    if job is None:
        raise ApiError(404, "ui.error.notfound")
    job.cancel.set()
    return job.to_dict()


def api_log(q: dict) -> dict:
    return {**log.info(), "lines": log.tail(300)}


def _supervise(job: Job, spec: dict, cancelled_result) -> dict:
    """Pornește procesul copil (`extract-worker`) și îl urmărește: progres, „Oprește”, blocare."""
    import time

    from ..extract import worker

    proc, spec_path = worker.spawn(spec, job.id)
    status_path = spec_path.with_suffix(".status.json")
    cancel_path = spec_path.with_suffix(".cancel")
    started = last_beat = time.time()
    cancel_at = None
    status: dict | None = None
    try:
        while True:
            status = worker.read_status(status_path) or status
            if status:
                job.done, job.total = status.get("done", job.done), status.get("total", job.total)
                job.child_log = status.get("log") or job.child_log
                last_beat = max(last_beat, float(status.get("beat", 0)))
            if proc.poll() is not None:
                status = worker.read_status(status_path) or status
                break
            now = time.time()
            if job.cancel.is_set() and cancel_at is None:
                cancel_path.touch()
                cancel_at = now
            if cancel_at is not None and now - cancel_at > worker.CANCEL_GRACE:
                _lg.warning("%s nu s-a oprit în %ss: procesul e oprit forțat", job.kind, worker.CANCEL_GRACE)
                worker.kill_tree(proc)
                status = {"state": "done", "result": cancelled_result(job.done, round(now - started))}
                break
            if now - last_beat > worker.STALL_SECONDS:
                _lg.error("%s nu mai avansează de %ss (pagina %s din %s): procesul e oprit",
                          job.kind, worker.STALL_SECONDS, max(job.done, 1), job.total)
                worker.kill_tree(proc)
                raise ApiError(504, "ui.error.extract.stalled", page=max(job.done, 1), total=job.total,
                               seconds=worker.STALL_SECONDS)
            time.sleep(0.3)
    finally:
        worker.kill_tree(proc)
        worker.cleanup(spec_path)
    if not status or status.get("state") == "running":
        raise ApiError(502, "ui.error.extract.crashed", page=max(job.done, 1), total=job.total,
                       code=proc.returncode)
    if status["state"] == "error":
        code = 503 if status["error"] == "ui.error.onenote" else 502
        raise ApiError(code, status["error"], **status.get("params", {}))
    return status["result"]


def api_extract(body: dict) -> dict:
    """Pornește extragerea în fundal; progresul se citește din /api/job."""
    from ..extract.selection import Selection, save_profile

    name = (body.get("out") or ("demo" if body.get("demo") else "onenote")).strip()
    if not name or any(c in name for c in '\\/:*?"<>|') or name.startswith("."):
        raise ApiError(400, "ui.error.name")
    settings = load_settings()
    sel = Selection(notebooks=body.get("notebooks") or [], sections=body.get("sections") or [],
                    pages=body.get("pages") or [], exclude_sections=body.get("exclude", settings.exclude_sections))
    if body.get("profile"):
        save_profile(data_dir() / "profiles", body["profile"], sel)

    def work(job: Job) -> dict:
        # Într-un proces separat: dacă OneNote se blochează într-un apel COM, procesul se
        # poate opri, iar interfața rămâne liberă (înainte rămânea „rulează deja o extragere”).
        spec = {"name": name, "demo": bool(body.get("demo")), "full": bool(body.get("full")),
                "selection": sel.to_dict(), "out": str(data_dir() / name)}
        if body.get("hang_after") is not None:  # doar testele: OneNote „înghețat”
            spec["hang_after"] = int(body["hang_after"])
        return _supervise(job, spec, lambda done, seconds: {
            "name": name, "cancelled": True, "total": done, "fetched": 0, "reused": 0, "skipped": 0, "removed": 0,
            "errors": [], "error_count": 0, "seconds": seconds})

    job = _start_job("extract", work)
    if body.get("wait"):  # linia de comandă și testele: așteaptă rezultatul
        while job.state == "running":
            threading.Event().wait(0.05)
        if job.error:
            raise ApiError(400 if job.error["error"] == "ui.error.name" else 503, job.error["error"],
                           **job.error["params"])
        return job.result or {}
    return {"job": job.id}


def api_analyze(body: dict) -> dict:
    from ..compare.run import run_compare
    from ..group.run import run_grouping
    from ..group.semantic import SemanticUnavailable

    import time

    folder = _dataset(body.get("ds"))
    settings = load_settings()
    threshold = float(body.get("threshold", settings.threshold))
    if not 0 < threshold < 1:
        raise ApiError(400, "ui.error.threshold")
    if read_manifest(folder).page_count == 0:
        raise ApiError(400, "ui.error.nopages")
    semantic = bool(body.get("semantic", settings.semantic))
    t0 = time.monotonic()
    try:
        groups = run_grouping(folder, threshold, use_semantic=semantic)
    except SemanticUnavailable as e:
        raise ApiError(503, "ui.error.semantic", error=str(e))
    t1 = time.monotonic()
    result = run_compare(folder)
    _lg.info("Analiză: %d grupuri, %d pagini negrupate, %d constatări (prag %.2f, sens %s; grupare %.1f s, "
             "comparare %.1f s)", len(groups.groups), len(groups.ungrouped), len(result.findings()), threshold,
             "da" if semantic else "nu", t1 - t0, time.monotonic() - t1)
    return {"groups": len(groups.groups), "ungrouped": len(groups.ungrouped), "findings": len(result.findings())}


def api_scan(q: dict) -> dict:
    from ..group.run import scan_thresholds

    folder = _dataset(q.get("ds"))
    rows = scan_thresholds(folder, [round(0.3 + 0.05 * i, 2) for i in range(14)])
    return {"rows": [{"threshold": th, "groups": g, "pages": p} for th, g, p in rows]}


def api_decision(body: dict) -> dict:
    from ..decisions import ACTIONS, Journal
    from ..group.overrides import GroupOverrides
    from ..group.run import load_groups

    folder = _dataset(body.get("ds"))
    action = body.get("action")
    if action not in ACTIONS or not body.get("page"):
        raise ApiError(400, "ui.error.action")
    try:
        d = Journal(folder).add(body["page"], action, group_id=body.get("group", ""),
                                finding=body.get("finding", ""), note=(body.get("note") or "")[:2000],
                                target=str(body.get("target") or "")[:1000])
    except ValueError:
        raise ApiError(400, "ui.error.action")
    if action == "not_in_group":
        group = next((g for g in load_groups(folder)["groups"] if body["page"] in g["pages"]), None)
        if group:
            ov = GroupOverrides.load(folder)
            ov.detach(body["page"], group["pages"])
            ov.save(folder)
    return d.to_dict()


def api_sections(q: dict) -> dict:
    """Secțiunile în care se poate muta o pagină: din OneNote acum (doar citire), altfel din extragere."""
    from ..apply.run import WriteDisabled, writer_for
    from ..extract.com import OneNoteError
    from ..extract.onenote_xml import parse_hierarchy

    folder = _dataset(q.get("ds"))
    try:
        with _writer(writer_for(folder, load_settings().lang)) as w:
            h = parse_hierarchy(w.get_hierarchy_xml())
        items = [{"notebook": nb.name, "section": "/".join(sec.path)} for nb in h.notebooks for sec in nb.sections]
        live = True
    except (OneNoteError, WriteDisabled, RuntimeError) as e:
        _lg.warning("api_sections: %s; folosesc secțiunile din extragere", log.describe_error(e))
        seen = {(p.notebook, "/".join(p.section_path)) for p in read_pages(folder)}
        items = [{"notebook": nb, "section": sec} for nb, sec in sorted(seen)]
        live = False
    return {"sections": items, "live": live}


def _bot_options(body: dict) -> dict:
    s = load_settings()
    return {"level": body.get("level", s.bot_level), "skip_stale": bool(body.get("skip_stale", s.bot_skip_stale)),
            "skip_duplicates": bool(body.get("skip_duplicates", s.bot_skip_duplicates))}


def api_bot_plan(q: dict) -> dict:
    """Ce pagini intră în documentele pentru bot (și de ce lipsesc celelalte)."""
    from ..bot.export import default_out_dir, foreign_files, is_offline, last_run
    from ..bot.select import build_plan

    folder = _dataset(q.get("ds"))
    s = load_settings()
    opts = _bot_options({k: (v == "1") if k.startswith("skip_") else v for k, v in q.items()})
    try:
        plan = build_plan(folder, **opts)
    except ValueError:
        raise ApiError(400, "ui.error.settings", error="level")
    out_dir = Path(s.bot_out_dir) if s.bot_out_dir else default_out_dir(folder)
    return {**plan.to_dict(), "options": opts, "max_mb": s.bot_max_mb,
            "out_dir": str(out_dir), "custom_out_dir": bool(s.bot_out_dir),
            "foreign": foreign_files(folder, out_dir),
            "offline": is_offline(folder), "compared": (folder / "findings.json").is_file(),
            "last": last_run(folder)}


def api_bot_override(body: dict) -> dict:
    from ..bot.select import set_override

    folder = _dataset(body.get("ds"))
    value = body.get("value")
    try:
        set_override(folder, str(body.get("page") or ""), value if value in ("include", "exclude") else None)
    except ValueError:
        raise ApiError(400, "ui.error.action")
    return {"ok": True}


def api_bot_export(body: dict) -> dict:
    """Pornește exportul pentru bot în procesul separat; progresul se citește din /api/job."""
    folder = _dataset(body.get("ds"))
    s = load_settings()
    spec = {"kind": "bot", "name": folder.name, "folder": str(folder), "out_dir": s.bot_out_dir,
            "max_mb": s.bot_max_mb, "full": bool(body.get("full")), **_bot_options(body)}

    def work(job: Job) -> dict:
        return _supervise(job, spec, lambda done, seconds: {"cancelled": True, "pages": [], "files": [],
                                                             "reupload": [], "manual": [], "counts": {},
                                                             "seconds": seconds, "out_dir": spec["out_dir"]})

    job = _start_job("bot", work)
    if body.get("wait"):  # testele: așteaptă rezultatul
        while job.state == "running":
            threading.Event().wait(0.05)
        if job.error:
            raise ApiError(503, job.error["error"], **job.error["params"])
        return job.result or {}
    return {"job": job.id}


def api_bot_move_foreign(body: dict) -> dict:
    """Mută fișierele care nu sunt ale DocAudit (de la scriptul vechi) într-un subfolder `_vechi_…`."""
    from ..bot.export import default_out_dir, move_foreign

    folder = _dataset(body.get("ds"))
    s = load_settings()
    out_dir = Path(s.bot_out_dir) if s.bot_out_dir else default_out_dir(folder)
    names = [str(n) for n in body.get("names") or []]
    target = move_foreign(folder, out_dir, names)
    return {"moved": len(names) if target else 0, "to": str(target) if target else ""}


PICK_FOLDER_SCRIPT = r"""
Add-Type -AssemblyName System.Windows.Forms
$owner = New-Object System.Windows.Forms.Form -Property @{TopMost = $true; ShowInTaskbar = $false}
$d = New-Object System.Windows.Forms.FolderBrowserDialog
$d.Description = 'DocAudit'
$d.ShowNewFolderButton = $true
if ($d.ShowDialog($owner) -eq [System.Windows.Forms.DialogResult]::OK) {
  [Console]::Out.Write([Convert]::ToBase64String([Text.Encoding]::UTF8.GetBytes($d.SelectedPath)))
}
"""


def api_bot_pick_folder(body: dict) -> dict:
    """Fereastra Windows „Alege folderul” (local, pe calculatorul utilizatorului); întoarce calea aleasă."""
    if sys.platform != "win32":
        raise ApiError(501, "ui.bot.pick.unsupported")
    import base64  # pragma: no cover - Windows
    import shutil
    import subprocess

    exe = shutil.which("powershell.exe") or shutil.which("powershell")
    if not exe:
        raise ApiError(501, "ui.bot.pick.unsupported")
    encoded = base64.b64encode(PICK_FOLDER_SCRIPT.encode("utf-16-le")).decode("ascii")
    try:
        r = subprocess.run([exe, "-NoProfile", "-NonInteractive", "-STA", "-EncodedCommand", encoded],
                           capture_output=True, timeout=600, creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
    except (OSError, subprocess.SubprocessError) as e:
        raise ApiError(500, "ui.error.internal", error=type(e).__name__)
    out = r.stdout.decode("ascii", "ignore").strip()
    return {"path": base64.b64decode(out).decode("utf-8") if out else ""}


def api_bot_open(body: dict) -> dict:
    """Deschide folderul cu documentele pentru bot în Explorer (doar pe Windows)."""
    from ..bot.export import default_out_dir

    folder = _dataset(body.get("ds"))
    target = Path(load_settings().bot_out_dir or default_out_dir(folder))
    target.mkdir(parents=True, exist_ok=True)
    if sys.platform == "win32":  # pragma: no cover - Windows
        import os

        os.startfile(str(target))  # noqa: S606 - folderul local ales de utilizator
        return {"opened": True, "path": str(target)}
    return {"opened": False, "path": str(target)}


def api_undo(body: dict) -> dict:
    from ..decisions import Journal

    if not Journal(_dataset(body.get("ds"))).undo(int(body.get("id", 0))):
        raise ApiError(409, "ui.error.undo")
    return {"ok": True}


@contextlib.contextmanager
def _writer(w):
    """Legătura de scriere se închide după fiecare cerere (procesul PowerShell nu rămâne pornit)."""
    try:
        yield w
    finally:
        close = getattr(w, "close", None)
        if close:
            close()


def api_plan(q: dict) -> dict:
    from ..apply.run import WriteDisabled, plan, writer_for
    from ..extract.com import OneNoteError

    folder = _dataset(q.get("ds"))
    settings = load_settings()
    try:
        with _writer(writer_for(folder, settings.lang)) as w:
            items = plan(folder, w, settings)
    except (OneNoteError, WriteDisabled) as e:
        raise ApiError(503, "ui.error.onenote", error=str(e))
    return {"items": [i.to_dict() for i in items], "write_enabled": settings.write_enabled}


def api_apply(body: dict) -> dict:
    from ..apply.run import WriteDisabled, apply, writer_for
    from ..extract.com import OneNoteError

    folder = _dataset(body.get("ds"))
    settings = load_settings()
    if not settings.write_enabled:
        raise ApiError(403, "apply.disabled")
    ids = [int(i) for i in body.get("ids", [])]
    if not ids or body.get("confirm") is not True:
        raise ApiError(400, "ui.error.confirm")
    try:
        with _writer(writer_for(folder, settings.lang)) as w:
            return apply(folder, w, settings, ids, settings.lang).to_dict()
    except (OneNoteError, WriteDisabled) as e:
        raise ApiError(503, "ui.error.onenote", error=str(e))


def api_applied(q: dict) -> dict:
    from ..decisions import Journal

    return {"items": Journal(_dataset(q.get("ds"))).applied()}


def api_restore(body: dict) -> dict:
    from ..apply.run import WriteDisabled, restore, writer_for
    from ..extract.com import OneNoteError

    folder = _dataset(body.get("ds"))
    settings = load_settings()
    if not settings.write_enabled:
        raise ApiError(403, "apply.disabled")
    try:
        with _writer(writer_for(folder, settings.lang)) as w:
            return restore(folder, w, settings, int(body.get("id", 0)), settings.lang)
    except (OneNoteError, WriteDisabled, ValueError) as e:
        raise ApiError(409, "ui.error.restore", error=str(e))


def api_delete_dataset(body: dict) -> dict:
    """Șterge o extragere din folderul de date (doar local; OneNote nu e atins)."""
    import shutil

    if body.get("confirm") is not True:
        raise ApiError(400, "ui.error.confirm")
    folder = _dataset(body.get("ds"))
    if folder.resolve().parent != data_dir().resolve():
        raise ApiError(400, "ui.error.dataset")
    shutil.rmtree(folder)
    return {"deleted": folder.name}


def api_reset_settings(body: dict) -> dict:
    """Setările implicite (scrierea în OneNote oprită). Extragerile rămân."""
    from ..settings import Settings, save_settings

    save_settings(Settings())
    return Settings().to_dict()


def api_settings(body: dict) -> dict:
    try:
        result = update_settings(body).to_dict()
    except (TypeError, ValueError) as e:
        raise ApiError(400, "ui.error.settings", error=str(e))
    if {"share_log", "log_dir"} & set(body):
        log.setup(force=True)
    return result


GET_ROUTES = {"/api/info": api_info, "/api/texts": api_texts, "/api/state": api_state, "/api/page": api_page,
              "/api/tree": api_tree, "/api/sections": api_sections, "/api/scan": api_scan, "/api/plan": api_plan,
              "/api/applied": api_applied, "/api/bot/plan": api_bot_plan,
              "/api/diagnose": api_diagnose, "/api/job": api_job, "/api/log": api_log}
POST_ROUTES = {"/api/extract": api_extract, "/api/analyze": api_analyze, "/api/decision": api_decision,
               "/api/undo": api_undo, "/api/apply": api_apply, "/api/restore": api_restore,
               "/api/settings": api_settings, "/api/link": api_link,
               "/api/dataset/delete": api_delete_dataset, "/api/settings/reset": api_reset_settings,
               "/api/job/cancel": api_job_cancel, "/api/bot/override": api_bot_override,
               "/api/bot/export": api_bot_export, "/api/bot/open": api_bot_open,
               "/api/bot/move-foreign": api_bot_move_foreign, "/api/bot/pick-folder": api_bot_pick_folder}
WRITE_ROUTES = {"/api/analyze", "/api/apply", "/api/restore", "/api/dataset/delete"}


# ---------- serverul ----------

class Handler(BaseHTTPRequestHandler):
    server: "DocAuditServer"
    server_version = f"DocAudit/{__version__}"
    sys_version = ""

    def log_message(self, fmt: str, *args: object) -> None:  # fără jurnal în consolă (pythonw)
        pass

    def _send(self, status: int, body: bytes, ctype: str, extra: dict[str, str] | None = None) -> None:
        self.send_response(status)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("X-Frame-Options", "DENY")
        self.send_header("Referrer-Policy", "no-referrer")
        self.send_header("Content-Security-Policy",
                         "default-src 'self'; img-src 'self' data:; style-src 'self'; script-src 'self'; "
                         "connect-src 'self'; frame-ancestors 'none'")
        for k, v in (extra or {}).items():
            self.send_header(k, v)
        self.end_headers()
        if self.command != "HEAD":
            self.wfile.write(body)

    def _json(self, status: int, data: object) -> None:
        self._send(status, json.dumps(data, ensure_ascii=False).encode("utf-8"), "application/json; charset=utf-8")

    def _host_ok(self) -> bool:
        host = (self.headers.get("Host") or "").rsplit(":", 1)[0].strip("[]")
        return host in ("127.0.0.1", "localhost", "::1")

    def _token_ok(self, query: dict) -> bool:
        given = self.headers.get("X-DocAudit-Token") or query.get("t", "")
        return secrets.compare_digest(given, self.server.token)

    def _query(self) -> tuple[str, dict]:
        url = urlparse(self.path)
        return url.path, {k: v[-1] for k, v in parse_qs(url.query).items()}

    def do_GET(self) -> None:
        if not self._host_ok():
            return self._send(403, b"forbidden", "text/plain")
        path, q = self._query()
        if path in ("/", "/index.html"):
            html = _static("index.html").decode("utf-8").replace("__TOKEN__", self.server.token)
            return self._send(200, html.encode("utf-8"), "text/html; charset=utf-8")
        if path in ("/app.js", "/app.css", "/icon.svg"):
            ctype = mimetypes.guess_type(path)[0] or "application/octet-stream"
            if path.endswith(".svg"):
                ctype = "image/svg+xml"
            return self._send(200, _static(path[1:]), f"{ctype}; charset=utf-8" if "svg" not in ctype else ctype)
        if not path.startswith("/api/"):
            return self._send(404, b"not found", "text/plain")
        if not self._token_ok(q):
            return self._json(403, {"error": "ui.error.token"})
        if path == "/api/image":
            return self._image(q)
        if path == "/api/report":
            return self._report(q)
        fn = GET_ROUTES.get(path)
        if fn is None:
            return self._json(404, {"error": "ui.error.notfound"})
        self._run(fn, q)

    def do_POST(self) -> None:
        if not self._host_ok():
            return self._send(403, b"forbidden", "text/plain")
        path, q = self._query()
        origin = self.headers.get("Origin")
        if origin and urlparse(origin).hostname not in ("127.0.0.1", "localhost", "::1"):
            return self._json(403, {"error": "ui.error.token"})
        if not self._token_ok({}):  # la POST jetonul vine doar în antet
            return self._json(403, {"error": "ui.error.token"})
        if path == "/api/quit":  # o pornire nouă (altă versiune) îi cere celei vechi să se închidă
            self._json(200, {"ok": True})
            threading.Thread(target=self.server.quit, daemon=True).start()
            return
        fn = POST_ROUTES.get(path)
        if fn is None:
            return self._json(404, {"error": "ui.error.notfound"})
        length = int(self.headers.get("Content-Length") or 0)
        if length > 1_000_000:
            return self._json(413, {"error": "ui.error.toolarge"})
        try:
            body = json.loads(self.rfile.read(length) or b"{}")
        except ValueError:
            return self._json(400, {"error": "ui.error.json"})
        if not isinstance(body, dict):
            return self._json(400, {"error": "ui.error.json"})
        if path in WRITE_ROUTES:
            with _write_lock:
                return self._run(fn, body)
        self._run(fn, body)

    def _run(self, fn, arg: dict) -> None:
        try:
            self._json(200, fn(arg))
        except ApiError as e:
            if e.status >= 500 or e.key == "ui.error.onenote":
                _lg.warning("%s: %s %s", getattr(fn, "__name__", "api"), e.key,
                            "; ".join(f"{k}={v}" for k, v in e.params.items())[:800])
            self._json(e.status, {"error": e.key, "params": {k: str(v) for k, v in e.params.items()}})
        except Exception as e:  # o eroare neprevăzută nu oprește serverul
            _lg.exception("%s a picat: %s", getattr(fn, "__name__", "api"), log.describe_error(e))
            self._json(500, {"error": "ui.error.internal", "params": {"error": f"{type(e).__name__}: {e}"}})

    def _image(self, q: dict) -> None:
        try:
            folder = _dataset(q.get("ds"))
        except ApiError as e:
            return self._json(e.status, {"error": e.key})
        sha = q.get("sha", "")
        path = image_path(folder, sha) if len(sha) == 64 and all(c in "0123456789abcdef" for c in sha) else None
        if path is None:
            return self._send(404, b"", "text/plain")
        ctype = mimetypes.guess_type(path.name)[0] or "application/octet-stream"
        if not ctype.startswith("image/") or ctype == "image/svg+xml":
            ctype = "application/octet-stream"
        self._send(200, path.read_bytes(), ctype)

    def _report(self, q: dict) -> None:
        from ..report import FORMATS, build_state, render

        try:
            folder = _dataset(q.get("ds"))
        except ApiError as e:
            return self._json(e.status, {"error": e.key})
        fmt = q.get("format", "html")
        if fmt not in FORMATS:
            return self._json(400, {"error": "ui.error.format"})
        lang = q.get("lang") if q.get("lang") in LANGUAGES else load_settings().lang
        text = render(build_state(folder, lang), fmt, lang)
        ctype = {"html": "text/html", "csv": "text/csv", "md": "text/markdown"}[fmt]
        self._send(200, text.encode("utf-8"), f"{ctype}; charset=utf-8",
                   {"Content-Disposition": f'attachment; filename="DocAudit-{folder.name}.{fmt}"'})


class DocAuditServer(ThreadingHTTPServer):
    daemon_threads = True
    # Pe Windows SO_REUSEADDR lasă două servere pe același port: a doua pornire n-ar mai vedea prima.
    allow_reuse_address = sys.platform != "win32"

    def __init__(self, host: str, port: int) -> None:
        if not is_loopback(host):
            raise ValueError(f"DocAudit ascultă doar local, nu pe {host}")
        self.token = secrets.token_urlsafe(24)
        super().__init__((host, port), Handler)

        self.on_quit = None  # tray: oprește și iconița

    def quit(self) -> None:
        if self.on_quit is not None:
            try:
                self.on_quit()
            except Exception:
                pass
        self.shutdown()
        self.server_close()  # eliberează portul pentru pornirea nouă

    @property
    def url(self) -> str:
        host, port = self.server_address[:2]
        return f"http://{host}:{port}/"


def make_server(port: int = 8765, host: str = "127.0.0.1") -> DocAuditServer:
    log.setup()
    try:
        return DocAuditServer(host, port)
    except OSError:
        return DocAuditServer(host, 0)  # portul e ocupat: alege altul liber


def serve(port: int = 8765, open_browser: bool = True) -> None:  # pragma: no cover - pornire interactivă
    server = make_server(port)
    if open_browser:
        threading.Timer(0.5, lambda: webbrowser.open(server.url)).start()
    try:
        server.serve_forever()
    finally:
        server.server_close()

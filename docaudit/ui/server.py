"""Interfața web locală: un server mic din biblioteca standard, doar pe 127.0.0.1.

Protecții:
- ascultă doar pe o adresă locală (refuză altceva la pornire);
- acceptă doar cereri cu Host 127.0.0.1 / localhost (împotriva „DNS rebinding”);
- orice /api/ cere un jeton aleator, generat la pornire și pus doar în pagina servită
  de acest server (alt site deschis în browser nu îl poate afla);
- fără CORS, fără resurse externe, fără telemetrie.
"""

from __future__ import annotations

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

from .. import __version__
from ..i18n import LANGUAGES, _load
from ..model import PAGES_FILE, image_path, read_manifest, read_pages
from ..paths import data_dir, datasets
from ..safety import is_loopback
from ..settings import load_settings, update_settings

_write_lock = threading.Lock()  # o singură analiză / extragere / aplicare odată


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
    return {"version": __version__, "languages": list(LANGUAGES), "settings": load_settings().to_dict(),
            "datasets": items, "profiles": list_profiles(data_dir() / "profiles"), "data_dir": str(data_dir())}


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


def api_extract(body: dict) -> dict:
    from ..extract.com import OneNoteError
    from ..extract.run import extract_to_dataset
    from ..extract.selection import Selection, save_profile

    name = (body.get("out") or ("demo" if body.get("demo") else "onenote")).strip()
    if not name or any(c in name for c in '\\/:*?"<>|') or name.startswith("."):
        raise ApiError(400, "ui.error.name")
    settings = load_settings()
    sel = Selection(notebooks=body.get("notebooks") or [], sections=body.get("sections") or [],
                    pages=body.get("pages") or [], exclude_sections=body.get("exclude", settings.exclude_sections))
    if body.get("profile"):
        save_profile(data_dir() / "profiles", body["profile"], sel)
    try:
        if body.get("demo"):
            from ..extract.demo import DemoOneNote

            source, label = DemoOneNote(), "demo (eșantion fictiv)"
        else:  # pragma: no cover - Windows
            from ..extract.com import ReadOnlyOneNote

            source, label = ReadOnlyOneNote(), "OneNote desktop (COM)"
        report = extract_to_dataset(source, sel, data_dir() / name, incremental=not body.get("full"),
                                    source_label=label)
    except OneNoteError as e:
        raise ApiError(503, "ui.error.onenote", error=str(e))
    return {"name": name, "total": report.total, "fetched": report.fetched, "reused": report.reused,
            "skipped": report.skipped, "removed": report.removed, "errors": report.errors}


def api_analyze(body: dict) -> dict:
    from ..compare.run import run_compare
    from ..group.run import run_grouping
    from ..group.semantic import SemanticUnavailable

    folder = _dataset(body.get("ds"))
    settings = load_settings()
    threshold = float(body.get("threshold", settings.threshold))
    if not 0 < threshold < 1:
        raise ApiError(400, "ui.error.threshold")
    try:
        groups = run_grouping(folder, threshold, use_semantic=bool(body.get("semantic", settings.semantic)))
    except SemanticUnavailable as e:
        raise ApiError(503, "ui.error.semantic", error=str(e))
    result = run_compare(folder)
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
    d = Journal(folder).add(body["page"], action, group_id=body.get("group", ""),
                            finding=body.get("finding", ""), note=(body.get("note") or "")[:2000])
    if action == "not_in_group":
        group = next((g for g in load_groups(folder)["groups"] if body["page"] in g["pages"]), None)
        if group:
            ov = GroupOverrides.load(folder)
            ov.detach(body["page"], group["pages"])
            ov.save(folder)
    return d.to_dict()


def api_undo(body: dict) -> dict:
    from ..decisions import Journal

    if not Journal(_dataset(body.get("ds"))).undo(int(body.get("id", 0))):
        raise ApiError(409, "ui.error.undo")
    return {"ok": True}


def api_plan(q: dict) -> dict:
    from ..apply.run import WriteDisabled, plan, writer_for
    from ..extract.com import OneNoteError

    folder = _dataset(q.get("ds"))
    settings = load_settings()
    try:
        items = plan(folder, writer_for(folder, settings.lang), settings)
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
        return apply(folder, writer_for(folder, settings.lang), settings, ids, settings.lang).to_dict()
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
        return restore(folder, writer_for(folder, settings.lang), settings, int(body.get("id", 0)), settings.lang)
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
        return update_settings(body).to_dict()
    except (TypeError, ValueError) as e:
        raise ApiError(400, "ui.error.settings", error=str(e))


GET_ROUTES = {"/api/info": api_info, "/api/texts": api_texts, "/api/state": api_state, "/api/page": api_page,
              "/api/tree": api_tree, "/api/scan": api_scan, "/api/plan": api_plan, "/api/applied": api_applied,
              "/api/diagnose": api_diagnose}
POST_ROUTES = {"/api/extract": api_extract, "/api/analyze": api_analyze, "/api/decision": api_decision,
               "/api/undo": api_undo, "/api/apply": api_apply, "/api/restore": api_restore,
               "/api/settings": api_settings, "/api/link": api_link,
               "/api/dataset/delete": api_delete_dataset, "/api/settings/reset": api_reset_settings}
WRITE_ROUTES = {"/api/extract", "/api/analyze", "/api/apply", "/api/restore", "/api/dataset/delete"}


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
            self._json(e.status, {"error": e.key, "params": {k: str(v) for k, v in e.params.items()}})
        except Exception as e:  # o eroare neprevăzută nu oprește serverul
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

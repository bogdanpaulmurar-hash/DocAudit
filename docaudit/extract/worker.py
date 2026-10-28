"""Extragerea într-un proces separat, pornit și supravegheat de interfață.

De ce: când OneNote cade în timpul unei cereri (sau rămâne la fereastra „How do you
want to start OneNote?”), apelul COM nu se mai întoarce. Într-un fir al serverului asta
bloca toată aplicația („rulează deja o extragere”). Un proces separat poate fi oprit:
la „Oprește” sau când nu mai dă semn de viață un timp (`STALL_SECONDS`).

Comunicarea e prin fișiere în `data_dir()/_jobs/`:
- `<id>.json` — ce se extrage (scris de server);
- `<id>.status.json` — progresul și rezultatul (scris de proces, înlocuit atomic);
- `<id>.cancel` — cererea de oprire (scrisă de server; procesul salvează și iese).
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
import time
from pathlib import Path

from .. import log
from ..paths import data_dir

STALL_SECONDS = 180  # fără niciun progres atât timp = OneNote blocat; procesul se oprește
CANCEL_GRACE = 20  # după „Oprește”: cât așteptăm să salveze singur înainte să-l oprim


def jobs_dir() -> Path:
    return data_dir() / "_jobs"


def _write_status(path: Path, data: dict) -> None:
    data["beat"] = time.time()
    data["log"] = log.tail(12)
    tmp = path.with_suffix(".tmp")
    tmp.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
    for _ in range(20):  # pe Windows înlocuirea poate pica cât timp serverul citește fișierul
        try:
            os.replace(tmp, path)
            return
        except PermissionError:
            time.sleep(0.05)


def read_status(path: Path) -> dict | None:
    try:
        return json.loads(path.read_text("utf-8"))
    except (OSError, ValueError):
        return None


class _HangingDemo:
    """Doar pentru teste: eșantionul care „îngheață” după N pagini, ca OneNote blocat."""

    def __init__(self, after: int) -> None:
        from .demo import DemoOneNote

        self.inner, self.after, self.n = DemoOneNote(), after, 0

    def get_hierarchy_xml(self) -> str:
        return self.inner.get_hierarchy_xml()

    def get_page_xml(self, page_id: str) -> str:
        self.n += 1
        if self.n > self.after:
            time.sleep(3600)
        return self.inner.get_page_xml(page_id)


def run_worker(spec_path: Path) -> int:
    """Rulează în procesul copil (`python -m docaudit extract-worker SPEC`)."""
    from .com import OneNoteError
    from .run import extract_to_dataset
    from .selection import Selection

    spec = json.loads(spec_path.read_text("utf-8"))
    status_path = spec_path.with_suffix(".status.json")
    cancel_path = spec_path.with_suffix(".cancel")
    state = {"state": "running", "done": 0, "total": 0}
    _write_status(status_path, state)

    def progress(n: int, total: int, _title: str) -> None:
        state.update(done=n, total=total)
        _write_status(status_path, state)

    try:
        if spec.get("demo"):
            from .demo import DemoOneNote

            hang = spec.get("hang_after")
            source = _HangingDemo(int(hang)) if hang is not None else DemoOneNote()
            label = "demo (eșantion fictiv)"
        else:  # pragma: no cover - Windows
            from .com import ReadOnlyOneNote

            source, label = ReadOnlyOneNote(), "OneNote desktop (COM)"
        _write_status(status_path, state)  # legătura e făcută: semn de viață înainte de ierarhie
        report = extract_to_dataset(source, Selection.from_dict(spec["selection"]), Path(spec["out"]),
                                    incremental=not spec.get("full"), source_label=label, progress=progress,
                                    cancel=cancel_path.exists)
    except OneNoteError as e:
        _write_status(status_path, {"state": "error", "error": "ui.error.onenote", "params": {"error": str(e)}})
        return 2
    except Exception as e:
        log.get("extract").exception("Extragerea a picat: %s", log.describe_error(e))
        _write_status(status_path, {"state": "error", "error": "ui.error.internal",
                                    "params": {"error": f"{type(e).__name__}: {e}"}})
        return 3
    if report.aborted:
        _write_status(status_path, {"state": "error", "error": "ui.error.extract.aborted",
                                    "params": {"error": report.aborted}})
        return 2
    _write_status(status_path, {"state": "done", "done": state["done"], "total": state["total"], "result": {
        "name": spec["name"], "total": report.total, "fetched": report.fetched, "reused": report.reused,
        "skipped": report.skipped, "removed": report.removed, "errors": report.errors[:50],
        "error_count": len(report.errors), "cancelled": report.cancelled, "seconds": round(report.seconds)}})
    return 0


def spawn(spec: dict, job_id: str) -> tuple[subprocess.Popen, Path]:
    """Pornește procesul copil; întoarce procesul și calea fișierului de stare."""
    folder = jobs_dir()
    folder.mkdir(parents=True, exist_ok=True)
    spec_path = folder / f"{job_id}.json"
    spec_path.write_text(json.dumps(spec, ensure_ascii=False), encoding="utf-8")
    for suffix in (".status.json", ".cancel"):
        spec_path.with_suffix(suffix).unlink(missing_ok=True)
    flags = getattr(subprocess, "CREATE_NO_WINDOW", 0) if sys.platform == "win32" else 0
    proc = subprocess.Popen([sys.executable, "-m", "docaudit", "extract-worker", str(spec_path)],
                            stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                            creationflags=flags)
    return proc, spec_path


def kill_tree(proc: subprocess.Popen) -> None:
    """Oprește procesul de extragere împreună cu ce a pornit el (PowerShell pentru citirea paginilor)."""
    if proc.poll() is not None:
        return
    if sys.platform == "win32":  # pragma: no cover - Windows
        flags = getattr(subprocess, "CREATE_NO_WINDOW", 0)
        try:
            subprocess.run(["taskkill", "/F", "/T", "/PID", str(proc.pid)], stdout=subprocess.DEVNULL,
                           stderr=subprocess.DEVNULL, timeout=15, creationflags=flags)
        except (OSError, subprocess.SubprocessError):
            pass
    if proc.poll() is None:
        proc.kill()
    try:
        proc.wait(10)
    except subprocess.TimeoutExpired:
        pass


def cleanup(spec_path: Path) -> None:
    for suffix in (".json", ".status.json", ".status.tmp", ".cancel"):
        try:
            spec_path.with_suffix(suffix).unlink(missing_ok=True)
        except OSError:
            pass

"""„Verifică legătura cu OneNote”: pașii pe rând, cu ce e de făcut la cel care pică.

Doar citește: Windows, pywin32, OneNote înregistrat pentru COM, pornirea COM,
lista de notebook-uri. Nu scrie nimic și nu face apeluri de rețea.
"""

from __future__ import annotations

import platform
import sys
from collections.abc import Callable
from dataclasses import asdict, dataclass

from .com import OneNoteError, OneNoteSource
from .onenote_xml import parse_hierarchy


@dataclass
class Check:
    key: str  # „system”, „pywin32”, „registry”, „com”, „notebooks”
    ok: bool | None  # None = nu s-a mai verificat (a picat un pas înainte)
    detail: str = ""

    def to_dict(self) -> dict:
        return asdict(self)


def _real_source() -> OneNoteSource:  # pragma: no cover - doar pe Windows
    from .com import ReadOnlyOneNote

    return ReadOnlyOneNote()


def _registered() -> tuple[bool, str]:  # pragma: no cover - doar pe Windows
    import winreg  # type: ignore[import-not-found]

    found = []
    for progid in ("OneNote.Application", "OneNote.Application.12"):
        try:
            with winreg.OpenKey(winreg.HKEY_CLASSES_ROOT, progid + "\\CLSID") as k:
                found.append(f"{progid} = {winreg.QueryValue(k, None)}")
        except OSError:
            pass
    return bool(found), "; ".join(found)


def diagnose(make_source: Callable[[], OneNoteSource] | None = None,
             windows_checks: bool = True) -> list[Check]:
    """Pașii în ordine. `make_source` și `windows_checks=False` sunt pentru teste și eșantion."""
    checks: list[Check] = []

    def failed() -> bool:
        return any(c.ok is False for c in checks)

    if windows_checks:
        is_win = sys.platform == "win32"
        checks.append(Check("system", is_win, f"{platform.platform()} · Python {platform.python_version()}"))
        if failed():
            checks.append(Check("pywin32", None))
        else:  # pragma: no cover - doar pe Windows
            try:
                import pythoncom  # type: ignore[import-not-found]  # noqa: F401
                import win32com.client  # type: ignore[import-not-found]  # noqa: F401

                checks.append(Check("pywin32", True))
            except ImportError as e:
                checks.append(Check("pywin32", False, str(e)))
        if failed():
            checks.append(Check("registry", None))
        else:  # pragma: no cover - doar pe Windows
            ok, detail = _registered()
            checks.append(Check("registry", ok, detail))

    if failed():
        checks += [Check("com", None), Check("notebooks", None)]
        return checks
    try:
        source = (make_source or _real_source)()
        how = getattr(source, "_how", "")
        tried = getattr(source, "_problems", None) or []
        checks.append(Check("com", True, how + (f" (înainte: {'; '.join(tried)})" if tried else "")))
    except OneNoteError as e:
        checks += [Check("com", False, str(e)), Check("notebooks", None)]
        return checks
    try:
        names = [nb.name for nb in parse_hierarchy(source.get_hierarchy_xml()).notebooks]
    except OneNoteError as e:
        checks.append(Check("notebooks", False, str(e)))
        return checks
    except Exception as e:  # XML neașteptat: îl arătăm, nu ascundem
        checks.append(Check("notebooks", False, f"{type(e).__name__}: {e}"))
        return checks
    checks.append(Check("notebooks", bool(names), f"{len(names)}: " + ", ".join(names) if names else "0"))
    return checks

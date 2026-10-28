"""Legătura COM cu OneNote desktop, cu mai multe încercări (doar Windows).

De ce mai multe: pe unele instalări Microsoft 365 biblioteca de tipuri a OneNote
nu e înregistrată corect. Atunci pywin32 ajunge la legarea dinamică, iar OneNote
răspunde la orice metodă cu `AttributeError: OneNote.Application.GetHierarchy`.
Încercăm pe rând, și fiecare variantă e verificată cu o citire mică a listei de
notebook-uri:
1. pywin32 cu biblioteca înregistrată („OneNote.Application”, apoi „.12”);
2. pywin32 cu biblioteca de tipuri citită direct din ONENOTE.EXE (sau din .tlb);
3. comtypes (opțional), tot cu biblioteca din ONENOTE.EXE;
4. legarea dinamică (ultima șansă).

Modulul doar se conectează. Ce metode se apelează decid `com.ReadOnlyOneNote`
(doar citire) și `apply/writer.py` (scrierile, după decizia utilizatorului).
"""

from __future__ import annotations

import glob
import os
from typing import Any

HS_NOTEBOOKS = 2  # HierarchyScope.hsNotebooks: cea mai mică citire, pentru verificare
XS_2013 = 2
PROGIDS = ("OneNote.Application", "OneNote.Application.12")
TYPELIB_GUID = "{0EA692EE-BB50-4E3C-AEF0-356D91732725}"  # Microsoft OneNote Type Library


class ConnectError(RuntimeError):
    def __init__(self, problems: list[str]) -> None:
        super().__init__("; ".join(problems))
        self.problems = problems


class _StripMissing:  # pragma: no cover - doar pe Windows
    """comtypes primește doar parametrii de intrare: scoate locurile pentru [out] (pythoncom.Missing)."""

    def __init__(self, inner: Any, missing: Any) -> None:
        self._inner, self._missing = inner, missing

    def __getattr__(self, name: str):
        fn = getattr(self._inner, name)
        return lambda *a: fn(*[x for x in a if x is not self._missing])


def _reg_value(root: Any, path: str) -> str | None:  # pragma: no cover - doar pe Windows
    import winreg  # type: ignore[import-not-found]

    try:
        with winreg.OpenKey(root, path) as k:
            return winreg.QueryValue(k, None) or None
    except OSError:
        return None


def _exe_of(command: str | None) -> str | None:
    """„"C:\\…\\ONENOTE.EXE" /x” → „C:\\…\\ONENOTE.EXE”."""
    if not command:
        return None
    command = command.strip()
    if command.startswith('"'):
        return command[1:].split('"', 1)[0]
    low = command.lower()
    i = low.find(".exe")
    return command[: i + 4] if i >= 0 else command


def typelib_candidates() -> list[str]:  # pragma: no cover - doar pe Windows
    """Fișierele din care se poate citi biblioteca de tipuri OneNote, cele mai sigure întâi."""
    import winreg  # type: ignore[import-not-found]

    hkcr, hklm = winreg.HKEY_CLASSES_ROOT, winreg.HKEY_LOCAL_MACHINE
    found: list[str] = []
    for version in ("1.1", "1.0", "1.2"):
        for plat in ("win64", "win32"):
            found.append(_reg_value(hkcr, rf"TypeLib\{TYPELIB_GUID}\{version}\0\{plat}") or "")
    for progid in PROGIDS:
        clsid = _reg_value(hkcr, rf"{progid}\CLSID")
        if clsid:
            found.append(_exe_of(_reg_value(hkcr, rf"CLSID\{clsid}\LocalServer32")) or "")
            c2r = rf"SOFTWARE\Microsoft\Office\ClickToRun\REGISTRY\MACHINE\Software\Classes\CLSID\{clsid}\LocalServer32"
            found.append(_exe_of(_reg_value(hklm, c2r)) or "")
    for base in (os.environ.get("ProgramFiles"), os.environ.get("ProgramFiles(x86)")):
        if base:
            found += sorted(glob.glob(os.path.join(base, "Microsoft Office", "root", "Office1*", "ONENOTE.EXE")),
                            reverse=True)
            found += sorted(glob.glob(os.path.join(base, "Microsoft Office", "Office1*", "ONENOTE.EXE")),
                            reverse=True)
    out: list[str] = []
    for f in found:
        f = os.path.expandvars(f.strip().strip('"'))
        if f and os.path.isfile(f) and f.lower() not in {o.lower() for o in out}:
            out.append(f)
    return out


def _verify(app: Any, missing: Any) -> None:  # pragma: no cover - doar pe Windows
    """O citire mică: dacă trece, varianta e bună."""
    last: Exception | None = None
    for args in (("", HS_NOTEBOOKS, missing, XS_2013), ("", HS_NOTEBOOKS)):
        try:
            result = getattr(app, "GetHierarchy")(*args)
        except Exception as e:  # semnătura diferă între versiuni
            last = e
            continue
        if isinstance(result, tuple):
            result = next((r for r in result if isinstance(r, str)), None)
        if isinstance(result, str) and result.lstrip().startswith("<"):
            return
        last = RuntimeError(f"răspuns neașteptat: {type(result).__name__}")
    raise last or RuntimeError("GetHierarchy nu a răspuns")


def _pywin32_from_file(path: str) -> Any:  # pragma: no cover - doar pe Windows
    import pythoncom  # type: ignore[import-not-found]
    from win32com.client import gencache  # type: ignore[import-not-found]

    tlb = pythoncom.LoadTypeLib(path)
    guid, lcid, _syskind, major, minor = tlb.GetLibAttr()[:5]
    try:
        mod = gencache.GetModuleForTypelib(str(guid), lcid, major, minor)
    except ImportError:
        gencache.MakeModuleForTypelibInterface(tlb, bForDemand=False)
        mod = gencache.GetModuleForTypelib(str(guid), lcid, major, minor)
    coclass = getattr(mod, "Application", None)
    if coclass is None:
        raise RuntimeError("biblioteca nu are clasa Application")
    return coclass()


def _comtypes_from_file(path: str, missing: Any) -> Any:  # pragma: no cover - doar pe Windows
    import comtypes  # type: ignore[import-not-found]
    import comtypes.client  # type: ignore[import-not-found]

    comtypes.CoInitialize()
    mod = comtypes.client.GetModule(path)
    iface = getattr(mod, "IApplication", None)
    app = comtypes.client.CreateObject("OneNote.Application", interface=iface) if iface else \
        comtypes.client.CreateObject("OneNote.Application")
    return _StripMissing(app, missing)


def connect() -> tuple[Any, str, list[str]]:  # pragma: no cover - doar pe Windows
    """(obiectul OneNote, cum s-a conectat, ce n-a mers înainte). ConnectError dacă nimic nu merge."""
    import pythoncom  # type: ignore[import-not-found]
    import win32com.client  # type: ignore[import-not-found]
    from win32com.client import gencache  # type: ignore[import-not-found]

    pythoncom.CoInitialize()
    missing = pythoncom.Missing
    problems: list[str] = []

    def attempt(label: str, make) -> Any | None:
        try:
            app = make()
            _verify(app, missing)
            return app
        except Exception as e:
            text = f"{type(e).__name__}: {e}"
            if "CLSIDToClassMap" in text:  # cache gen_py stricat: se reface din registru
                try:
                    gencache.Rebuild()
                except Exception:
                    pass
            problems.append(f"{label}: {text}")
            return None

    for progid in PROGIDS:
        app = attempt(f"pywin32 {progid}", lambda p=progid: gencache.EnsureDispatch(p))
        if app is not None:
            return app, f"pywin32 ({progid})", problems
    files = []
    try:
        files = typelib_candidates()
    except Exception as e:
        problems.append(f"căutarea ONENOTE.EXE: {e}")
    if not files:
        problems.append("biblioteca de tipuri OneNote (ONENOTE.EXE) nu a fost găsită")
    for path in files:
        app = attempt(f"pywin32 din {path}", lambda p=path: _pywin32_from_file(p))
        if app is not None:
            return app, f"pywin32, biblioteca din {path}", problems
    try:
        import comtypes  # type: ignore[import-not-found]  # noqa: F401

        for path in files:
            app = attempt(f"comtypes din {path}", lambda p=path: _comtypes_from_file(p, missing))
            if app is not None:
                return app, f"comtypes, biblioteca din {path}", problems
    except ImportError:
        problems.append("comtypes nu e instalat (Install.bat îl instalează)")
    app = attempt("pywin32 dinamic", lambda: win32com.client.Dispatch("OneNote.Application"))
    if app is not None:
        return app, "pywin32 (dinamic)", problems
    raise ConnectError(problems)

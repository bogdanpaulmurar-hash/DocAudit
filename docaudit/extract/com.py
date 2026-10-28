"""Accesul la OneNote desktop prin COM, strict doar citire.

Clasa expune numai GetHierarchy și GetPageContent. Metodele care scriu
(UpdatePageContent, DeleteHierarchy etc.) nu sunt accesibile de aici; scrierea
în OneNote va avea un modul separat (Etapa 7), apelat doar după decizia
utilizatorului.

Necesită Windows, OneNote desktop (Microsoft 365 / 2016) și pywin32.
"""

from __future__ import annotations

from typing import Protocol

HS_PAGES = 4  # HierarchyScope.hsPages
XS_2013 = 2  # XMLSchema.xs2013
PI_BINARY_DATA = 1  # PageInfo.piBinaryData: imaginile vin în XML, ca base64


class OneNoteError(RuntimeError):
    """OneNote nu e disponibil sau a refuzat cererea."""


class OneNoteSource(Protocol):
    def get_hierarchy_xml(self) -> str: ...

    def get_page_xml(self, page_id: str) -> str: ...


class ReadOnlyOneNote:
    """Clientul COM real. Se creează doar pe Windows."""

    def __init__(self) -> None:
        try:
            import pythoncom  # type: ignore[import-not-found]
            import win32com.client  # type: ignore[import-not-found]
        except ImportError as e:  # pragma: no cover - doar pe Windows
            raise OneNoteError("pywin32 lipsește (pip install pywin32) sau sistemul nu e Windows") from e
        pythoncom.CoInitialize()
        self._missing = pythoncom.Missing
        self._app = None
        problems: list[str] = []
        # gencache știe parametrii de ieșire ([out]) și îi întoarce ca rezultat. Unele instalări
        # Microsoft 365 au înregistrată biblioteca de tipuri doar sub „OneNote.Application.12”.
        for make, progid in ((win32com.client.gencache.EnsureDispatch, "OneNote.Application"),
                             (win32com.client.gencache.EnsureDispatch, "OneNote.Application.12"),
                             (win32com.client.Dispatch, "OneNote.Application")):
            try:  # pragma: no cover - doar pe Windows
                self._app = make(progid)
                break
            except AttributeError as e:  # pragma: no cover - cache gen_py stricat
                problems.append(f"{progid}: {e} (șterge folderul %LOCALAPPDATA%\\Temp\\gen_py)")
            except Exception as e:  # pragma: no cover - doar pe Windows
                problems.append(f"{progid}: {e}")
        if self._app is None:  # pragma: no cover - doar pe Windows
            raise OneNoteError("OneNote desktop nu răspunde prin COM (e instalat OneNote din Microsoft 365 / "
                               "2016, nu doar „OneNote for Windows 10”?): " + "; ".join(problems))

    def get_hierarchy_xml(self) -> str:  # pragma: no cover - doar pe Windows
        return self._call("GetHierarchy", ("", HS_PAGES, self._missing, XS_2013), ("", HS_PAGES))

    def get_page_xml(self, page_id: str) -> str:  # pragma: no cover - doar pe Windows
        return self._call("GetPageContent", (page_id, self._missing, PI_BINARY_DATA, XS_2013),
                          (page_id, self._missing, PI_BINARY_DATA))

    def _call(self, method: str, args: tuple, fallback: tuple) -> str:  # pragma: no cover
        fn = getattr(self._app, method)
        last: Exception | None = None
        for a in (args, fallback):
            try:
                result = fn(*a)
            except Exception as e:  # semnătura diferă între versiuni de pywin32/OneNote
                last = e
                continue
            if isinstance(result, tuple):  # unele versiuni întorc (rezultat, ieșiri...)
                result = next((r for r in result if isinstance(r, str) and r.startswith("<")), None)
            if isinstance(result, str) and result.lstrip().startswith("<"):
                return result
        raise OneNoteError(f"{method} a eșuat: {last}")

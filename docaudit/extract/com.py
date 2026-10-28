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
            import win32com.client  # type: ignore[import-not-found]  # noqa: F401
        except ImportError as e:  # pragma: no cover - doar pe Windows
            raise OneNoteError("pywin32 lipsește (pip install pywin32) sau sistemul nu e Windows") from e
        from .connect import ComCaller, ConnectError, connect

        try:  # pragma: no cover - doar pe Windows
            app, self._how, self._problems = connect()
        except ConnectError as e:  # pragma: no cover - doar pe Windows
            raise OneNoteError("OneNote desktop nu răspunde prin COM (e instalat OneNote din Microsoft 365 / "
                               "2016, nu doar „OneNote for Windows 10”?): " + str(e)) from e
        self._call = ComCaller(app, pythoncom.Missing)  # pragma: no cover - doar pe Windows

    def get_hierarchy_xml(self) -> str:  # pragma: no cover - doar pe Windows
        return self._read("GetHierarchy", ("", HS_PAGES), (XS_2013,))

    def get_page_xml(self, page_id: str) -> str:  # pragma: no cover - doar pe Windows
        return self._read("GetPageContent", (page_id,), (PI_BINARY_DATA, XS_2013))

    def _read(self, method: str, before: tuple, after: tuple) -> str:  # pragma: no cover - doar pe Windows
        try:
            return self._call(method, before, after, xml=True)
        except RuntimeError as e:
            raise OneNoteError(str(e)) from e

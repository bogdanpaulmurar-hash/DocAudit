"""Accesul la OneNote desktop prin COM, strict doar citire.

Clasa expune numai GetHierarchy și GetPageContent. Metodele care scriu
(UpdatePageContent, DeleteHierarchy etc.) nu sunt accesibile de aici; scrierea
în OneNote va avea un modul separat (Etapa 7), apelat doar după decizia
utilizatorului.

Necesită Windows, OneNote desktop (Microsoft 365 / 2016) și pywin32.
"""

from __future__ import annotations

import time
from typing import Protocol

from .. import log

HS_PAGES = 4  # HierarchyScope.hsPages
XS_2013 = 2  # XMLSchema.xs2013
PI_BASIC = 0  # PageInfo.piBasic: fără imagini (rezerva pentru paginile la care OneNote cade)
PI_BINARY_DATA = 1  # PageInfo.piBinaryData: imaginile vin în XML, ca base64
PAUSE = 0.05  # pauză mică între pagini, ca OneNote să nu fie bombardat (scriptul vechi: 150 ms)


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
        self._missing = pythoncom.Missing
        self.without_images = 0  # pagini citite fără imagini (OneNote cădea cu imaginile)
        self._connect()  # pragma: no cover - doar pe Windows

    def _connect(self) -> None:  # pragma: no cover - doar pe Windows
        from .connect import ComCaller, ConnectError, connect

        try:
            app, self._how, self._problems = connect()
        except ConnectError as e:
            raise OneNoteError("OneNote desktop nu răspunde prin COM (e instalat OneNote din Microsoft 365 / "
                               "2016, nu doar „OneNote for Windows 10”?): " + str(e)) from e
        chosen = getattr(getattr(self, "_call", None), "_chosen", {})
        self._call = ComCaller(app, self._missing)
        self._call._chosen.update(chosen)  # varianta de parametri rămâne aceeași după reconectare
        log.get("com").info("Legătura cu OneNote: %s", self._how)

    def get_hierarchy_xml(self) -> str:  # pragma: no cover - doar pe Windows
        return self._read("GetHierarchy", ("", HS_PAGES), (XS_2013,))

    def get_page_xml(self, page_id: str) -> str:  # pragma: no cover - doar pe Windows
        try:
            return self._read("GetPageContent", (page_id,), (PI_BINARY_DATA, XS_2013))
        except OneNoteError as e:
            if not getattr(e, "gone", False):
                raise
        # OneNote a căzut de două ori la pagina asta cu imagini: o cerem fără imagini
        xml = self._read("GetPageContent", (page_id,), (PI_BASIC, XS_2013))
        self.without_images += 1
        log.get("com").warning("Pagină citită fără imagini după ce OneNote a căzut (în total: %d)",
                               self.without_images)
        return xml

    def _read(self, method: str, before: tuple, after: tuple) -> str:  # pragma: no cover - doar pe Windows
        from .connect import OneNoteGone

        lg = log.get("com")
        for attempt in range(4):
            try:
                result = self._call(method, before, after, xml=True)
                if method == "GetPageContent":
                    time.sleep(PAUSE)
                return result
            except OneNoteGone as e:
                if e.busy and attempt < 3:  # OneNote ocupat (sincronizare): așteptăm puțin
                    lg.warning("%s; aștept %d s", e, 2 * (attempt + 1))
                    time.sleep(2 * (attempt + 1))
                    continue
                if not e.busy and attempt == 0:  # OneNote s-a închis / blocat: reconectare o dată
                    lg.warning("%s; mă reconectez și încerc din nou", e)
                    time.sleep(3)
                    self._connect()
                    continue
                err = OneNoteError(str(e))
                err.gone = True  # type: ignore[attr-defined]
                raise err from e
            except RuntimeError as e:
                raise OneNoteError(str(e)) from e
        raise OneNoteError(f"{method}: OneNote nu răspunde")

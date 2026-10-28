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
from .connect import OneNoteGone

HS_PAGES = 4  # HierarchyScope.hsPages
XS_2013 = 2  # XMLSchema.xs2013
PI_BASIC = 0  # PageInfo.piBasic: fără imagini (rezerva pentru paginile la care OneNote cade)
PI_BINARY_DATA = 1  # PageInfo.piBinaryData: imaginile vin în XML, ca base64
PAUSE = 0.05  # pauză mică între pagini, ca OneNote să nu fie bombardat (scriptul vechi: 150 ms)
RECOVER = 5  # după ce OneNote a căzut: cât îl lăsăm să se închidă de tot înainte de cererea următoare
WAYS = ("pywin32", "powershell", "comtypes", "dinamic")  # căile de citire a paginilor, în ordinea încercării
READ_MEMORY = "onenote_read.json"  # ce cale a mers / ce cale face OneNote să cadă pe laptopul acesta


class OneNoteError(RuntimeError):
    """OneNote nu e disponibil sau a refuzat cererea."""


class _Unusable(RuntimeError):
    """O cale de citire nu se poate folosi pe calculatorul acesta (fără ca OneNote să fi căzut)."""


def load_read_memory() -> dict:
    import json

    from ..paths import data_dir

    try:
        data = json.loads((data_dir() / READ_MEMORY).read_text("utf-8"))
        return data if isinstance(data, dict) else {}
    except (OSError, ValueError):
        return {}


def save_read_memory(data: dict) -> None:
    import json

    from ..paths import data_dir

    try:
        path = data_dir() / READ_MEMORY
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
    except OSError:
        pass


def _comtypes_app(missing):  # pragma: no cover - doar pe Windows
    from .connect import _comtypes_from_file, _verify, typelib_candidates

    try:
        import comtypes  # type: ignore[import-not-found]  # noqa: F401
    except ImportError as e:
        raise _Unusable("comtypes nu e instalat") from e
    problems = []
    for path in typelib_candidates():
        try:
            app = _comtypes_from_file(path, missing)
            _verify(app, missing)
            return app
        except Exception as e:
            problems.append(f"{type(e).__name__}: {e}")
    raise _Unusable("; ".join(problems) or "biblioteca de tipuri OneNote nu a fost găsită")


def _dynamic_app(missing):  # pragma: no cover - doar pe Windows
    import win32com.client.dynamic  # type: ignore[import-not-found]

    from .connect import PROGIDS, _verify

    problems = []
    for progid in PROGIDS:
        try:
            app = win32com.client.dynamic.Dispatch(progid)
            _verify(app, missing)
            return app
        except Exception as e:
            problems.append(f"{progid}: {type(e).__name__}: {e}")
    raise _Unusable("; ".join(problems))


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
        self._init_ways()
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
        if self._problems:  # de ce n-au mers variantele dinainte (doar tipuri de erori, fără conținut)
            log.get("com").info("Variante de legătură care n-au mers: %s", " | ".join(self._problems)[:800])

    def get_hierarchy_xml(self) -> str:  # pragma: no cover - doar pe Windows
        return self._read("GetHierarchy", ("", HS_PAGES), (XS_2013,))

    # ---------- paginile: mai multe căi, cea care merge e ținută minte ----------

    def get_page_xml(self, page_id: str) -> str:
        """XML-ul paginii, prin prima cale care nu face OneNote să cadă.

        Pe laptopul de lucru OneNote cădea la fiecare GetPageContent cerut prin legătura
        pywin32, iar DocAudit îl repornea la fiecare pagină („Start Normally” mereu).
        Acum: dacă o cale face OneNote să cadă înainte să fi citit vreo pagină, se trece
        la următoarea (PowerShell, comtypes, legarea dinamică) și se ține minte în
        `data_dir()/onenote_read.json`. Dacă o cale a mers deja și o anumită pagină face
        OneNote să cadă, pagina se cere o dată fără imagini, apoi se sare.
        """
        lg = log.get("com")
        while True:
            way = self._current_way()
            try:
                xml = self._page_call(way, page_id, PI_BINARY_DATA)
            except (_Unusable, AttributeError, TypeError) as e:
                self._give_up(way, crashed=False, why=e)
                continue
            except OneNoteGone as e:
                if not self._way_ok:
                    self._give_up(way, crashed=True, why=e)
                    time.sleep(RECOVER)
                    continue
                lg.warning("%s la o pagină; o cer din nou fără imagini", e)
                time.sleep(RECOVER)
                try:
                    xml = self._page_call(way, page_id, PI_BASIC)
                except OneNoteGone as e2:
                    time.sleep(RECOVER)
                    raise OneNoteError(f"{e2}: pagina face OneNote să cadă, o sar") from e2
                except RuntimeError as e2:
                    raise OneNoteError(str(e2)) from e2
                self.without_images += 1
                lg.warning("Pagină citită fără imagini după ce OneNote a căzut (în total: %d)",
                           self.without_images)
            except RuntimeError as e:
                if not self._way_ok and way != WAYS[0]:  # o cale de rezervă care nu merge deloc aici
                    self._give_up(way, crashed=False, why=e)
                    continue
                raise OneNoteError(str(e)) from e
            if not self._way_ok:
                self._way_ok = True
                lg.info("Paginile se citesc prin: %s", way)
                if self._memory.get("ok") != way:
                    self._memory["ok"] = way
                    save_read_memory(self._memory)
            return xml

    def _init_ways(self) -> None:
        self._memory = load_read_memory()
        self._readers: dict[str, object] = {}
        self._skipped: set[str] = set()
        self._way: str | None = None
        self._way_ok = False

    def _current_way(self) -> str:
        if self._way:
            return self._way
        ok = self._memory.get("ok")
        crashed = set(self._memory.get("crashed", []))
        order = ([ok] if ok in WAYS else []) + [w for w in WAYS if w != ok]
        left = [w for w in order if w not in self._skipped and w not in crashed] or \
               [w for w in order if w not in self._skipped]  # toate au căzut cândva: mai încercăm o dată
        if not left:
            err = OneNoteError("OneNote cade la citirea paginilor pe toate căile încercate ("
                               + ", ".join(WAYS) + "). Lista de notebook-uri se citește, paginile nu: "
                               "vezi docs/INSTALARE.md, „OneNote cade la fiecare pagină”.")
            err.gone = True  # type: ignore[attr-defined]
            err.fatal = True  # type: ignore[attr-defined]
            raise err
        self._way = left[0]
        if self._skipped or self._way != WAYS[0]:
            log.get("com").info("Încerc citirea paginilor prin: %s", self._way)
        return self._way

    def _give_up(self, way: str, crashed: bool, why: BaseException) -> None:
        lg = log.get("com")
        self._skipped.add(way)
        self._drop_reader(way)
        self._way = None
        if crashed:
            lg.warning("Citirea paginilor prin %s face OneNote să cadă (%s); trec la altă cale. Dacă apare "
                       "fereastra OneNote „How do you want to start OneNote?”, alege Start Normally.",
                       way, log.describe_error(why))
            mem_crashed = set(self._memory.get("crashed", [])) | {way}
            self._memory["crashed"] = sorted(mem_crashed)
            if self._memory.get("ok") == way:
                self._memory.pop("ok")
            save_read_memory(self._memory)
        else:
            lg.info("Calea %s nu se poate folosi aici: %s", way, log.describe_error(why))

    def _page_call(self, way: str, page_id: str, info: int) -> str:
        lg = log.get("com")
        for attempt in range(4):
            reader = self._reader(way)
            try:
                xml = reader(page_id, info)
                time.sleep(PAUSE)
                return xml
            except OneNoteGone as e:
                if e.busy and attempt < 3:  # OneNote ocupat (sincronizare): așteptăm puțin
                    lg.warning("%s; aștept %d s", e, 2 * (attempt + 1))
                    time.sleep(2 * (attempt + 1))
                    continue
                self._drop_reader(way)
                raise
        raise OneNoteError("GetPageContent: OneNote nu răspunde")

    def _reader(self, way: str):
        if way in self._readers:
            return self._readers[way]
        try:
            return self._make_reader(way)
        except (_Unusable, OneNoteGone):
            raise
        except Exception as e:  # pornirea căii a picat (lipsește ceva): nu e o cădere OneNote
            raise _Unusable(log.describe_error(e)) from e

    def _make_reader(self, way: str):
        from .connect import ComCaller

        if way == "pywin32":
            if getattr(self, "_stale", False):
                self._connect()
                self._stale = False
            call = self._call
        elif way == "powershell":
            from .psbridge import BridgeUnavailable, PowerShellReader

            try:
                bridge = PowerShellReader()
            except BridgeUnavailable as e:
                raise _Unusable(str(e)) from e
            self._readers[way] = bridge.page
            self._bridge = bridge
            return bridge.page
        elif way == "comtypes":
            call = ComCaller(_comtypes_app(self._missing), self._missing)
        elif way == "dinamic":
            call = ComCaller(_dynamic_app(self._missing), self._missing)
        else:
            raise _Unusable(way)

        def read(page_id: str, info: int) -> str:
            return call("GetPageContent", (page_id,), (info, XS_2013), xml=True)

        self._readers[way] = read
        return read

    def _drop_reader(self, way: str) -> None:
        self._readers.pop(way, None)
        if way == "pywin32":
            self._stale = True  # obiectul COM e mort: legătura se reface la nevoie
        if way == "powershell" and getattr(self, "_bridge", None) is not None:
            try:
                self._bridge.close()
            except Exception:
                pass
            self._bridge = None

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

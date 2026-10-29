"""Scrierea în OneNote, folosită DOAR de „Aplică” (după decizia și confirmarea utilizatorului).

Separat de extragere: `extract.com.ReadOnlyOneNote` rămâne doar citire.

Operațiile permise sunt puține și reversibile:
- create_section: secțiunea „Arhivă” într-un notebook, dacă lipsește;
- create_page + update_page: copia paginii în Arhivă (sau înapoi, la restaurare);
- update_page cu XML parțial: doar titlul (prefixul „[ÎNVECHIT]” sau titlul nou ales)
  ori un singur bloc de text, cu paragrafele adăugate de utilizator;
- delete_content: scoate la restaurare doar paragrafele adăugate de DocAudit (după objectID);
- delete_page: trimite pagina în Coșul OneNote (recuperabilă din OneNote), nu definitiv.

`FakeOneNote` imită aceleași operații într-un fișier JSON: îl folosesc testele
și modul demo, ca tot fluxul să se poată încerca fără OneNote.
"""

from __future__ import annotations

import json
import uuid
import xml.etree.ElementTree as ET
from datetime import datetime, timezone
from pathlib import Path
from typing import Protocol

from ..extract.com import HS_PAGES, PI_BINARY_DATA, XS_2013, OneNoteError
from ..extract.onenote_xml import ONE, render_page_xml
from .xmlops import title_of

CFT_SECTION = 3  # CreateFileType.cftSection
NPS_DEFAULT = 0


class WritableOneNote(Protocol):
    def get_hierarchy_xml(self) -> str: ...

    def get_page_xml(self, page_id: str) -> str: ...

    def create_section(self, notebook_id: str, name: str) -> str: ...

    def create_page(self, section_id: str) -> str: ...

    def update_page(self, xml: str) -> None: ...

    def delete_page(self, page_id: str) -> None: ...

    def delete_content(self, page_id: str, object_id: str) -> None: ...


class ComOneNote:  # pragma: no cover - doar pe Windows, cu OneNote desktop
    """OneNote desktop prin COM, cu operațiile de scriere de mai sus și nimic altceva."""

    def __init__(self) -> None:
        try:
            import pythoncom  # type: ignore[import-not-found]
            import win32com.client  # type: ignore[import-not-found]  # noqa: F401
        except ImportError as e:
            raise OneNoteError("pywin32 lipsește sau sistemul nu e Windows") from e
        from ..extract.connect import ComCaller, ConnectError, connect

        try:
            app, self._how, _ = connect()
        except ConnectError as e:
            raise OneNoteError(f"OneNote desktop nu răspunde prin COM: {e}") from e
        # Aceeași legătură ca la citire: locul pentru [out] se dă doar dacă legarea îl cere.
        self._call = ComCaller(app, pythoncom.Missing)

    def _do(self, method: str, before: tuple, after: tuple = (), xml: bool = False, write: bool = True):
        try:
            return self._call(method, before, after, xml=xml, write=write)
        except RuntimeError as e:
            raise OneNoteError(str(e)) from e

    def get_hierarchy_xml(self) -> str:
        return self._do("GetHierarchy", ("", HS_PAGES), (XS_2013,), xml=True, write=False)

    def get_page_xml(self, page_id: str) -> str:
        return self._do("GetPageContent", (page_id,), (PI_BINARY_DATA, XS_2013), xml=True, write=False)

    def create_section(self, notebook_id: str, name: str) -> str:
        return self._do("OpenHierarchy", (f"{name}.one", notebook_id), (CFT_SECTION,))

    def create_page(self, section_id: str) -> str:
        return self._do("CreateNewPage", (section_id,), (NPS_DEFAULT,))

    def update_page(self, xml: str) -> None:
        self._call.app.UpdatePageContent(xml, 0, XS_2013)  # fără parametru [out]

    def delete_page(self, page_id: str) -> None:
        self._call.app.DeleteHierarchy(page_id, 0, False)  # False = în Coș, nu definitiv

    def delete_content(self, page_id: str, object_id: str) -> None:
        self._call.app.DeletePageContent(page_id, object_id, 0)


def _now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


class FakeOneNote:
    """OneNote fals, ținut într-un fișier JSON (notebook-uri, secțiuni, pagini cu XML-ul lor)."""

    def __init__(self, path: Path) -> None:
        self.path = path
        self.state = json.loads(path.read_text("utf-8")) if path.is_file() else {"notebooks": []}
        self.calls: list[str] = []

    @classmethod
    def from_sample(cls, path: Path) -> "FakeOneNote":
        from ..extract.onenote_xml import ImageData
        from ..sample import build_sample

        _, pages, images, _ = build_sample()
        imgs = {sha: ImageData("png", data) for sha, data in images.items()}
        fake = cls(path)
        fake.state = {"notebooks": []}
        for p in pages:
            nb = fake._notebook(p.notebook, create=True)
            sec = fake._section(nb, "/".join(p.section_path), create=True)
            sec["pages"].append({"id": p.id, "name": p.title, "dateTime": p.created,
                                 "lastModifiedTime": p.modified, "xml": _with_object_ids(render_page_xml(p, imgs)),
                                 "recycled": False})
        fake.save()
        return fake

    def save(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.path.write_text(json.dumps(self.state, ensure_ascii=False), encoding="utf-8", newline="\n")

    def _notebook(self, name: str, create: bool = False) -> dict:
        for nb in self.state["notebooks"]:
            if nb["name"] == name or nb["id"] == name:
                return nb
        if not create:
            raise OneNoteError(f"notebook inexistent: {name}")
        nb = {"id": f"nb:{name}", "name": name, "sections": []}
        self.state["notebooks"].append(nb)
        return nb

    @staticmethod
    def _section(nb: dict, path: str, create: bool = False) -> dict:
        for s in nb["sections"]:
            if s["path"] == path:
                return s
        if not create:
            raise OneNoteError(f"secțiune inexistentă: {path}")
        s = {"id": f"sec:{nb['name']}/{path}", "path": path, "pages": []}
        nb["sections"].append(s)
        return s

    def _find(self, page_id: str) -> tuple[dict, dict, dict]:
        for nb in self.state["notebooks"]:
            for s in nb["sections"]:
                for p in s["pages"]:
                    if p["id"] == page_id:
                        return nb, s, p
        raise OneNoteError(f"pagină inexistentă: {page_id}")

    # --- citire, ca OneNote ---
    def get_hierarchy_xml(self) -> str:
        root = ET.Element(f"{ONE}Notebooks")
        for nb in self.state["notebooks"]:
            nb_el = ET.SubElement(root, f"{ONE}Notebook", {"ID": nb["id"], "name": nb["name"], "nickname": nb["name"]})
            containers: dict[tuple[str, ...], ET.Element] = {(): nb_el}
            for s in nb["sections"]:
                parts = s["path"].split("/")
                parent = nb_el
                for depth in range(len(parts) - 1):
                    key = tuple(parts[: depth + 1])
                    if key not in containers:
                        containers[key] = ET.SubElement(parent, f"{ONE}SectionGroup", {"name": parts[depth],
                                                                                        "ID": f"sg:{'/'.join(key)}"})
                    parent = containers[key]
                sec_el = ET.SubElement(parent, f"{ONE}Section", {"ID": s["id"], "name": parts[-1]})
                for p in s["pages"]:
                    attrs = {"ID": p["id"], "name": p["name"], "dateTime": p["dateTime"],
                             "lastModifiedTime": p["lastModifiedTime"], "pageLevel": "1"}
                    if p["recycled"]:
                        attrs["isInRecycleBin"] = "true"
                    ET.SubElement(sec_el, f"{ONE}Page", attrs)
        return ET.tostring(root, encoding="unicode")

    def get_page_xml(self, page_id: str) -> str:
        return self._find(page_id)[2]["xml"]

    # --- scriere ---
    def create_section(self, notebook_id: str, name: str) -> str:
        self.calls.append(f"create_section {name}")
        nb = self._notebook(notebook_id)
        sec = self._section(nb, name, create=True)
        self.save()
        return sec["id"]

    def create_page(self, section_id: str) -> str:
        self.calls.append("create_page")
        for nb in self.state["notebooks"]:
            for s in nb["sections"]:
                if s["id"] == section_id:
                    pid = "{" + str(uuid.uuid4()).upper() + "}"
                    now = _now()
                    s["pages"].append({"id": pid, "name": "", "dateTime": now, "lastModifiedTime": now,
                                       "xml": f'<one:Page xmlns:one="{ONE[1:-1]}" ID="{pid}" />',
                                       "recycled": False})
                    self.save()
                    return pid
        raise OneNoteError(f"secțiune inexistentă: {section_id}")

    def update_page(self, xml: str) -> None:
        self.calls.append("update_page")
        new = ET.fromstring(xml)
        _, _, page = self._find(new.get("ID", ""))
        old = ET.fromstring(page["xml"])
        children = [c for c in new if c.tag != f"{ONE}Title"]
        known = {el.get("objectID") for el in old if el.get("objectID")}
        if children and all(c.get("objectID") in known for c in children):  # blocuri existente, ca OneNote
            for c in children:
                i, prev = next((i, el) for i, el in enumerate(old) if el.get("objectID") == c.get("objectID"))
                old.remove(prev)
                old.insert(i, c)
            page["xml"] = ET.tostring(old, encoding="unicode")
        elif children or old.find(f"{ONE}Title") is None:
            page["xml"] = xml  # conținut complet
        else:  # doar titlul
            old.remove(old.find(f"{ONE}Title"))
            old.insert(0, new.find(f"{ONE}Title"))
            page["xml"] = ET.tostring(old, encoding="unicode")
        page["xml"] = _with_object_ids(page["xml"])
        page["name"] = title_of(page["xml"])
        page["lastModifiedTime"] = _now()
        self.save()

    def delete_page(self, page_id: str) -> None:
        self.calls.append("delete_page")
        _, _, page = self._find(page_id)
        page["recycled"] = True
        self.save()

    def delete_content(self, page_id: str, object_id: str) -> None:
        self.calls.append("delete_content")
        _, _, page = self._find(page_id)
        root = ET.fromstring(page["xml"])
        for parent in root.iter():
            for child in list(parent):
                if child.get("objectID") == object_id:
                    parent.remove(child)
                    page["xml"] = ET.tostring(root, encoding="unicode")
                    page["lastModifiedTime"] = _now()
                    self.save()
                    return
        raise OneNoteError(f"obiect inexistent: {object_id}")


_OBJECT_TAGS = {f"{ONE}{t}" for t in ("Outline", "OE", "Image", "Table", "InsertedFile")}


def _with_object_ids(xml: str) -> str:
    """Ca OneNote: fiecare bloc, paragraf sau imagine primește un objectID dacă nu are."""
    root = ET.fromstring(xml)
    for el in root.iter():
        if el.tag in _OBJECT_TAGS and not el.get("objectID"):
            el.set("objectID", "{" + str(uuid.uuid4()).upper() + "}")
    return ET.tostring(root, encoding="unicode")


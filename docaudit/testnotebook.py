"""Creează în OneNote un notebook NOU de test, cu paginile eșantionului fictiv.

Singurul loc din DocAudit care scrie în OneNote înainte de Etapa 7, și doar
într-un notebook nou, într-un folder ales de utilizator. Refuză dacă folderul
există deja, ca să nu atingă un notebook real.

Structura: notebook „DocAudit Test” → grup de secțiuni pentru fiecare notebook
din eșantion → secțiunile lui. Plus o secțiune „Arhivă” cu 2 pagini, care
trebuie să lipsească din extragerea implicită.
"""

from __future__ import annotations

from pathlib import Path

from .extract.onenote_xml import ImageData, render_page_xml
from .model import Block, Page, Source
from .sample import build_sample

CFT_NOTEBOOK, CFT_FOLDER, CFT_SECTION = 1, 2, 3  # CreateFileType
XS_2013 = 2


def archive_pages() -> list[Page]:
    return [
        Page(id="", notebook="", section_path=["Arhivă"], title=f"Pagină arhivată {i}",
             created="2020-01-01T00:00:00Z", modified="2020-01-01T00:00:00Z",
             text=f"Această pagină e în Arhivă ({i}).", blocks=[Block("para", f"Această pagină e în Arhivă ({i}).")],
             source=Source(kind="sample"))
        for i in (1, 2)
    ]


def create_test_notebook(folder: Path, name: str = "DocAudit Test") -> int:  # pragma: no cover - Windows
    import pythoncom  # type: ignore[import-not-found]
    import win32com.client  # type: ignore[import-not-found]

    if folder.exists():
        raise FileExistsError(f"{folder} există deja; alege un folder nou pentru notebook-ul de test")
    folder.parent.mkdir(parents=True, exist_ok=True)
    pythoncom.CoInitialize()
    app = win32com.client.gencache.EnsureDispatch("OneNote.Application")
    missing = pythoncom.Missing

    def open_h(path: str, relative_to: str, kind: int) -> str:
        result = app.OpenHierarchy(path, relative_to, missing, kind)
        return result if isinstance(result, str) else result[0]

    nb_id = open_h(str(folder), "", CFT_NOTEBOOK)
    _, pages, images, _ = build_sample()
    imgs = {sha: ImageData("png", data) for sha, data in images.items()}
    groups: dict[str, str] = {}
    sections: dict[tuple[str, str], str] = {}
    count = 0
    for page in pages + archive_pages():
        if page.section_path == ["Arhivă"]:
            parent, sec_name = nb_id, "Arhivă"
        else:
            if page.notebook not in groups:
                groups[page.notebook] = open_h(page.notebook, nb_id, CFT_FOLDER)
            parent, sec_name = groups[page.notebook], page.section_path[-1]
        key = (parent, sec_name)
        if key not in sections:
            sections[key] = open_h(f"{sec_name}.one", parent, CFT_SECTION)
        result = app.CreateNewPage(sections[key], missing, 0)
        page_id = result if isinstance(result, str) else result[0]
        app.UpdatePageContent(render_page_xml(page, imgs, page_id=page_id, for_update=True), 0, XS_2013)
        count += 1
    return count

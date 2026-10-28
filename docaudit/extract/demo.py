"""Un OneNote „de jucărie” care servește eșantionul fictiv prin aceeași interfață ca COM.

Permite rularea întregului flux (extragere, analiză, UI) fără Windows și fără
OneNote, și e folosit de teste.
"""

from __future__ import annotations

from ..model import Page
from ..sample import build_sample
from .onenote_xml import ImageData, render_hierarchy_xml, render_page_xml


# Un site SharePoint fictiv, ca link-urile din browser să poată fi încercate pe eșantion.
DEMO_LOCATION = "https://exemplu.sharepoint.com/sites/Echipa/Shared Documents"


class DemoOneNote:
    def __init__(self, pages: list[Page] | None = None, images: dict[str, bytes] | None = None) -> None:
        if pages is None:
            _, pages, images, _ = build_sample()
        self.pages = {p.id: p for p in pages}
        self.images = {sha: ImageData("png", data) for sha, data in (images or {}).items()}
        self.page_requests: list[str] = []

    def get_hierarchy_xml(self) -> str:
        return render_hierarchy_xml(list(self.pages.values()), DEMO_LOCATION)

    def get_page_xml(self, page_id: str) -> str:
        self.page_requests.append(page_id)
        return render_page_xml(self.pages[page_id], self.images)

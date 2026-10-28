"""PDF-uri: o pagină simplă din text (rezerva fără OneNote) și unirea pe documente sub o limită.

Unirea folosește `pypdf` (instalat cu DocAudit). Fiecare pagină OneNote primește un semn de
carte cu titlul ei, ca botul (și un om) să știe de unde vine textul. Un document peste limită
se împarte în `<nume>_Part1.pdf`, `<nume>_Part2.pdf`, …, fără să se rupă o pagină OneNote în
două; o singură pagină mai mare decât limita rămâne singură (și e semnalată).
"""

from __future__ import annotations

import io
import textwrap
import unicodedata
from dataclasses import dataclass, field
from pathlib import Path


def _latin1(c: str) -> str:
    try:
        c.encode("latin-1")
        return c
    except UnicodeEncodeError:  # ă ș ț → a s t (fontul de bază nu le are)
        base = "".join(x for x in unicodedata.normalize("NFKD", c) if not unicodedata.combining(x))
        return base if base and all(ord(x) < 256 for x in base) else "?"


def _pdf_text(s: str) -> str:
    s = "".join(_latin1(c) for c in s)
    return s.replace("\\", "\\\\").replace("(", "\\(").replace(")", "\\)")


def text_pdf(title: str, lines: list[str]) -> bytes:
    """Un PDF minimal (A4, Helvetica) cu titlul și rândurile date; pagini noi când nu mai încap."""
    wrapped: list[tuple[int, str]] = [(14, title)]
    for line in lines:
        for part in textwrap.wrap(line, 95) or [""]:
            wrapped.append((10, part))
    per_page = 60
    chunks = [wrapped[i:i + per_page] for i in range(0, len(wrapped), per_page)] or [[]]
    objs: list[bytes] = []
    n_pages = len(chunks)
    # 1 catalog, 2 pages, 3 font, apoi câte (pagină, conținut) pentru fiecare pagină
    kids = " ".join(f"{4 + 2 * i} 0 R" for i in range(n_pages))
    objs.append(b"<< /Type /Catalog /Pages 2 0 R >>")
    objs.append(f"<< /Type /Pages /Kids [{kids}] /Count {n_pages} >>".encode())
    objs.append(b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica /Encoding /WinAnsiEncoding >>")
    for i, chunk in enumerate(chunks):
        y, ops = 800, ["BT"]
        for size, text in chunk:
            ops.append(f"/F1 {size} Tf 1 0 0 1 50 {y} Tm ({_pdf_text(text)}) Tj")
            y -= size + 3
        ops.append("ET")
        stream = "\n".join(ops).encode("latin-1")
        objs.append(f"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 595 842] /Resources << /Font << /F1 3 0 R >> >>"
                    f" /Contents {5 + 2 * i} 0 R >>".encode())
        objs.append(b"<< /Length " + str(len(stream)).encode() + b" >>\nstream\n" + stream + b"\nendstream")
    out = io.BytesIO()
    out.write(b"%PDF-1.4\n%\xe2\xe3\xcf\xd3\n")
    offsets = []
    for n, body in enumerate(objs, 1):
        offsets.append(out.tell())
        out.write(f"{n} 0 obj\n".encode() + body + b"\nendobj\n")
    xref = out.tell()
    out.write(f"xref\n0 {len(objs) + 1}\n0000000000 65535 f \n".encode())
    for off in offsets:
        out.write(f"{off:010d} 00000 n \n".encode())
    out.write(f"trailer\n<< /Size {len(objs) + 1} /Root 1 0 R >>\nstartxref\n{xref}\n%%EOF\n".encode())
    return out.getvalue()


@dataclass
class Item:
    path: Path
    title: str


@dataclass
class Part:
    path: Path
    items: int
    pages: int
    size: int
    oversize: bool = False


@dataclass
class MergeResult:
    parts: list[Part] = field(default_factory=list)
    skipped: list[tuple[str, str]] = field(default_factory=list)  # (titlu, motiv)


def _render(items: list[Item], skipped: list[tuple[str, str]]) -> tuple[bytes, int]:
    from pypdf import PdfReader, PdfWriter

    writer = PdfWriter()
    for it in items:
        try:
            reader = PdfReader(str(it.path))
            if reader.is_encrypted:
                reader.decrypt("")
            if not reader.pages:
                skipped.append((it.title, "0 pages"))
                continue
            start = len(writer.pages)
            for page in reader.pages:
                writer.add_page(page)
            writer.add_outline_item(it.title or "-", start)
        except Exception as e:  # un PDF stricat nu oprește documentul
            skipped.append((it.title, type(e).__name__))
    buf = io.BytesIO()
    writer.write(buf)
    return buf.getvalue(), len(writer.pages)


def merge(items: list[Item], out_dir: Path, name: str, max_bytes: int) -> MergeResult:
    """Unește `items` în `out_dir/<name>.pdf` sau în părți sub `max_bytes`."""
    result = MergeResult()
    # grupuri după mărimea fișierelor (o estimare bună: unirea adaugă puțin), apoi verificare reală
    groups: list[list[Item]] = []
    cur: list[Item] = []
    size = 0
    for it in items:
        s = it.path.stat().st_size if it.path.is_file() else 0
        if cur and size + s > max_bytes * 0.97:
            groups.append(cur)
            cur, size = [], 0
        cur.append(it)
        size += s
    if cur:
        groups.append(cur)

    rendered: list[tuple[bytes, int, int]] = []
    queue = list(groups)
    while queue:
        g = queue.pop(0)
        data, n = _render(g, result.skipped)
        if len(data) > max_bytes and len(g) > 1:
            half = len(g) // 2
            queue[:0] = [g[:half], g[half:]]
            continue
        rendered.append((data, n, len(g)))

    out_dir.mkdir(parents=True, exist_ok=True)
    multi = len(rendered) > 1
    for i, (data, n, count) in enumerate(rendered, 1):
        path = out_dir / (f"{name}_Part{i}.pdf" if multi else f"{name}.pdf")
        tmp = path.with_suffix(".tmp")
        tmp.write_bytes(data)
        tmp.replace(path)
        result.parts.append(Part(path=path, items=count, pages=n, size=len(data), oversize=len(data) > max_bytes))
    result.skipped = list(dict.fromkeys(result.skipped))  # o grupă refăcută după înjumătățire nu se numără de două ori
    return result

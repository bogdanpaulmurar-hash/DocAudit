"""Pagina OneNote → fișier (PDF, Word, pagină web) prin Windows PowerShell; Word → PDF.

Folosește doar `Publish` din OneNote, care scrie un fișier pe disc și nu schimbă nimic în
OneNote, și Word (dacă există) ca să transforme .docx / .mht / .html în PDF, fără fereastră.
Aceeași cale ca la citirea paginilor (`extract/psbridge.py`): pe laptopul de lucru OneNote
cade la cererile prin pywin32, iar prin PowerShell merge.

Fișierele se scriu întâi într-un folder temporar cu nume scurt: Publish și Word nu merg cu
căi mai lungi de ~255 de caractere (lecție din vechiul script de export).
"""

from __future__ import annotations

from pathlib import Path

from ..extract.psbridge import PowerShellProcess, b64

FORMATS = {"mht": 2, "pdf": 3, "word": 5}  # PublishFormat: pfMHTML, pfPDF, pfWord
WORD_PDF = 17  # wdFormatPDF

SCRIPT = r"""
$ErrorActionPreference = 'Stop'
$utf8 = New-Object System.Text.UTF8Encoding $false
function Arg($s) { return $utf8.GetString([Convert]::FromBase64String($s)) }
try {
  $on = New-Object -ComObject OneNote.Application
} catch {
  [Console]::Out.WriteLine('ERR ' + $_.Exception.HResult + ' ' + ($_.Exception.Message -replace "[`r`n]", ' '))
  [Console]::Out.Flush()
  exit 1
}
$word = $null
[Console]::Out.WriteLine('READY')
[Console]::Out.Flush()
try {
  while ($true) {
    $line = [Console]::In.ReadLine()
    if ($line -eq $null -or $line -eq '') { break }
    $p = $line.Split("`t")
    try {
      switch ($p[0]) {
        'PUB' {
          $on.Publish((Arg $p[1]), (Arg $p[2]), [int]$p[3], '')
          [Console]::Out.WriteLine('OK ')
        }
        'WORD' {
          if ($word -eq $null) {
            $word = New-Object -ComObject Word.Application
            $word.Visible = $false
            $word.DisplayAlerts = 0
          }
          $doc = $word.Documents.Open((Arg $p[1]), $false, $true)
          try {
            $dst = (Arg $p[2])
            try { $doc.SaveAs([ref]$dst, [ref]17) } catch { $doc.SaveAs2($dst, 17) }
          } finally { $doc.Close($false) }
          [Console]::Out.WriteLine('OK ')
        }
        default { [Console]::Out.WriteLine('ERR 0 comanda necunoscuta') }
      }
    } catch {
      $ex = $_.Exception
      while ($ex.InnerException -ne $null) { $ex = $ex.InnerException }
      [Console]::Out.WriteLine('ERR ' + $ex.HResult + ' ' + ($ex.Message -replace "[`r`n]", ' '))
    }
    [Console]::Out.Flush()
  }
} finally {
  if ($word -ne $null) { try { $word.Quit() } catch {} }
}
"""


class Unsupported(RuntimeError):
    """Calea aceasta nu există pentru sursa datelor (ex. extragere din fișiere, eșantion)."""


class PowerShellPublisher(PowerShellProcess):
    """Publish din OneNote și conversia Word → PDF, într-un proces PowerShell."""

    def __init__(self, exe: str | None = None) -> None:
        super().__init__(SCRIPT, exe)

    def publish(self, page_id: str, path: Path, fmt: str) -> None:
        self.request(f"PUB\t{b64(page_id)}\t{b64(str(path))}\t{FORMATS[fmt]}", "Publish")

    def word_to_pdf(self, src: Path, dst: Path) -> None:
        self.request(f"WORD\t{b64(str(src))}\t{b64(str(dst))}", "Word")


class OfflinePublisher:
    """Pentru extrageri fără OneNote în spate (eșantion, demo, fișiere importate): doar textul."""

    def publish(self, page_id: str, path: Path, fmt: str) -> None:
        raise Unsupported("fără OneNote")

    def word_to_pdf(self, src: Path, dst: Path) -> None:
        raise Unsupported("fără Word")

    def close(self) -> None:
        pass

"""Operațiile lui „Aplică” prin Windows PowerShell (aceeași cale care citește paginile).

De ce: pe laptopul de lucru OneNote cade la cererile făcute prin pywin32, iar prin
PowerShell merge. Scriptul face exact operațiile din `writer.ComOneNote`, nimic
altceva: citirea ierarhiei și a paginii (pentru copia de siguranță), crearea unei
secțiuni, a unei pagini, actualizarea unei pagini și trimiterea unei pagini în Coș
(`DeleteHierarchy` cu deletePermanently = $false). Se folosește doar din `apply/`.

Toți parametrii și rezultatele trec ca base64 (ASCII), un rând pe cerere.
"""

from __future__ import annotations

from ..extract.com import OneNoteError
from ..extract.psbridge import PowerShellProcess, b64

SCRIPT = r"""
$ErrorActionPreference = 'Stop'
$utf8 = New-Object System.Text.UTF8Encoding $false
function Arg($s) { return $utf8.GetString([Convert]::FromBase64String($s)) }
function Ok($s) { [Console]::Out.WriteLine('OK ' + [Convert]::ToBase64String($utf8.GetBytes([string]$s))) }
try {
  $on = New-Object -ComObject OneNote.Application
} catch {
  [Console]::Out.WriteLine('ERR ' + $_.Exception.HResult + ' ' + ($_.Exception.Message -replace "[`r`n]", ' '))
  [Console]::Out.Flush()
  exit 1
}
[Console]::Out.WriteLine('READY')
[Console]::Out.Flush()
while ($true) {
  $line = [Console]::In.ReadLine()
  if ($line -eq $null -or $line -eq '') { break }
  $p = $line.Split("`t")
  try {
    $x = ''
    switch ($p[0]) {
      'HIER'    { $on.GetHierarchy('', 4, [ref]$x, 2); Ok $x }
      'PAGE'    { $on.GetPageContent((Arg $p[1]), [ref]$x, 1, 2); Ok $x }
      'SECTION' { $on.OpenHierarchy((Arg $p[2]) + '.one', (Arg $p[1]), [ref]$x, 3); Ok $x }
      'NEWPAGE' { $on.CreateNewPage((Arg $p[1]), [ref]$x, 0); Ok $x }
      'UPDATE'  { $on.UpdatePageContent((Arg $p[1]), [DateTime]::MinValue, 2); Ok '' }
      'RECYCLE' { $on.DeleteHierarchy((Arg $p[1]), [DateTime]::MinValue, $false); Ok '' }
      default   { [Console]::Out.WriteLine('ERR 0 comanda necunoscuta') }
    }
  } catch {
    $ex = $_.Exception
    while ($ex.InnerException -ne $null) { $ex = $ex.InnerException }
    [Console]::Out.WriteLine('ERR ' + $ex.HResult + ' ' + ($ex.Message -replace "[`r`n]", ' '))
  }
  [Console]::Out.Flush()
}
"""


class PowerShellWriter(PowerShellProcess):
    """Aceleași metode ca `writer.ComOneNote`, prin PowerShell."""

    def __init__(self, exe: str | None = None) -> None:
        super().__init__(SCRIPT, exe)

    def request(self, line: str, method: str) -> str:
        try:
            return super().request(line, method)
        except RuntimeError as e:  # inclusiv OneNote căzut: „Aplică” o arată pe pagina respectivă
            raise OneNoteError(str(e)) from e

    def get_hierarchy_xml(self) -> str:
        return self.request("HIER", "GetHierarchy")

    def get_page_xml(self, page_id: str) -> str:
        return self.request(f"PAGE\t{b64(page_id)}", "GetPageContent")

    def create_section(self, notebook_id: str, name: str) -> str:
        return self.request(f"SECTION\t{b64(notebook_id)}\t{b64(name)}", "OpenHierarchy")

    def create_page(self, section_id: str) -> str:
        return self.request(f"NEWPAGE\t{b64(section_id)}", "CreateNewPage")

    def update_page(self, xml: str) -> None:
        self.request(f"UPDATE\t{b64(xml)}", "UpdatePageContent")

    def delete_page(self, page_id: str) -> None:
        self.request(f"RECYCLE\t{b64(page_id)}", "DeleteHierarchy")

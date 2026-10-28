"""Citirea paginilor OneNote prin Windows PowerShell (doar GetPageContent).

De ce: pe unele laptopuri OneNote cade la fiecare GetPageContent cerut prin pywin32,
deși lista de notebook-uri se citește bine. Scriptul vechi de export („1. Updating
Script”) citea paginile din PowerShell pe același laptop, deci aceasta e o cale de
rezervă. Un singur proces PowerShell rămâne pornit: primește id-ul paginii pe stdin
și întoarce XML-ul (base64) pe stdout; pe ambele trec doar caractere ASCII (id-urile
sunt GUID-uri), deci codarea consolei nu contează. Scriptul doar citește.

Scriptul se dă prin `-EncodedCommand`, nu ca fișier .ps1, ca să nu fie oprit de
politica de execuție a scripturilor de pe laptopurile de firmă.
"""

from __future__ import annotations

import base64
import shutil
import subprocess
import sys

from .connect import RPC_BUSY, RPC_GONE, OneNoteGone

SCRIPT = r"""
$ErrorActionPreference = 'Stop'
$utf8 = New-Object System.Text.UTF8Encoding $false
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
  $parts = $line.Split("`t")
  try {
    $x = ''
    $on.GetPageContent($parts[0], [ref]$x, [int]$parts[1], 2)
    [Console]::Out.WriteLine('OK ' + [Convert]::ToBase64String($utf8.GetBytes($x)))
  } catch {
    $ex = $_.Exception
    while ($ex.InnerException -ne $null) { $ex = $ex.InnerException }
    [Console]::Out.WriteLine('ERR ' + $ex.HResult + ' ' + ($ex.Message -replace "[`r`n]", ' '))
  }
  [Console]::Out.Flush()
}
"""


class BridgeUnavailable(RuntimeError):
    """PowerShell lipsește sau nu poate porni OneNote: calea nu se poate folosi (OneNote nu a căzut)."""


def parse_reply(line: str) -> str:
    """Un rând de la PowerShell → XML-ul paginii, sau eroarea potrivită."""
    line = line.strip()
    if line.startswith("OK "):
        return base64.b64decode(line[3:]).decode("utf-8")
    if line.startswith("ERR "):
        head, _, message = line[4:].partition(" ")
        try:
            code = int(head)
        except ValueError:
            code = 0
        if code in RPC_GONE or code in RPC_BUSY:
            raise OneNoteGone("GetPageContent", code, code in RPC_BUSY)
        raise RuntimeError(f"GetPageContent (PowerShell): {hex(code & 0xFFFFFFFF)} {message[:300]}")
    # procesul s-a oprit fără răspuns: OneNote (sau PowerShell) a căzut în timpul cererii
    raise OneNoteGone("GetPageContent", -2147023170, False)


class PowerShellReader:
    def __init__(self, exe: str | None = None) -> None:
        exe = exe or shutil.which("powershell.exe") or shutil.which("powershell") or shutil.which("pwsh")
        if not exe:
            raise BridgeUnavailable("PowerShell nu a fost găsit")
        encoded = base64.b64encode(SCRIPT.encode("utf-16-le")).decode("ascii")
        flags = getattr(subprocess, "CREATE_NO_WINDOW", 0) if sys.platform == "win32" else 0
        try:
            self.proc = subprocess.Popen(
                [exe, "-NoLogo", "-NoProfile", "-NonInteractive", "-EncodedCommand", encoded],
                stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, creationflags=flags)
        except OSError as e:
            raise BridgeUnavailable(f"PowerShell nu pornește: {e}") from e
        first = self._readline()
        if first.strip() != "READY":
            self.close()
            raise BridgeUnavailable("PowerShell nu a putut porni OneNote: " + (first.strip()[:300] or "fără răspuns"))

    def _readline(self) -> str:
        assert self.proc.stdout is not None
        return self.proc.stdout.readline().decode("utf-8", "replace")

    def page(self, page_id: str, info: int) -> str:
        assert self.proc.stdin is not None
        try:
            self.proc.stdin.write(f"{page_id}\t{int(info)}\n".encode("utf-8"))
            self.proc.stdin.flush()
        except OSError as e:
            raise OneNoteGone("GetPageContent", -2147023170, False) from e
        return parse_reply(self._readline())

    def close(self) -> None:
        try:
            if self.proc.stdin:
                self.proc.stdin.close()
            self.proc.wait(5)
        except Exception:
            self.proc.kill()

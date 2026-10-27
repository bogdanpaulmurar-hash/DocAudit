@echo off
rem DocAudit - ruleaza o comanda, de exemplu: DocAudit.bat tree   sau   DocAudit.bat extract --demo
chcp 65001 >nul
setlocal
set "PYEXE=%LOCALAPPDATA%\DocAudit\venv\Scripts\python.exe"
if not exist "%PYEXE%" (
  echo DocAudit nu e instalat. Ruleaza intai Install.bat.
  exit /b 1
)
set "PYTHONIOENCODING=utf-8"
"%PYEXE%" -m docaudit %*

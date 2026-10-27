@echo off
rem DocAudit - instalare fara admin. Mediul Python sta in %LOCALAPPDATA%\DocAudit\venv.
rem Folosire: Install.bat            (instalare de baza)
rem           Install.bat semantic   (plus asemanarea dupa sens; descarca modelul o singura data)
chcp 65001 >nul
setlocal
set "ROOT=%~dp0"
set "APP=%LOCALAPPDATA%\DocAudit"
set "VENV=%APP%\venv"
set "EXTRAS=windows,tray"
if /I "%~1"=="semantic" set "EXTRAS=windows,tray,semantic"

where py >nul 2>nul
if %errorlevel%==0 (set "PY=py -3") else (set "PY=python")
%PY% -c "import sys; sys.exit(0 if sys.version_info >= (3, 11) else 1)" >nul 2>nul
if errorlevel 1 (
  echo Python 3.11 sau mai nou lipseste. Instaleaza-l din Microsoft Store sau de pe python.org.
  goto :fail
)

if not exist "%VENV%\Scripts\python.exe" (
  echo Creez mediul Python in %VENV% ...
  %PY% -m venv "%VENV%" || goto :fail
)
echo Instalez DocAudit ...
"%VENV%\Scripts\python.exe" -m pip install --upgrade pip --quiet || goto :fail
pushd "%ROOT%"
"%VENV%\Scripts\python.exe" -m pip install -e ".[%EXTRAS%]" --quiet
set "RC=%errorlevel%"
popd
if not "%RC%"=="0" goto :fail

if /I "%~1"=="semantic" (
  echo Descarc modelul pentru asemanarea dupa sens - singura data cand DocAudit foloseste internetul ...
  "%VENV%\Scripts\python.exe" -m docaudit download-model || goto :fail
)
echo Creez iconita si scurtaturile DocAudit (Desktop si meniul Start) ...
"%VENV%\Scripts\python.exe" -m docaudit make-icon "%APP%" >nul || goto :fail
powershell -NoProfile -ExecutionPolicy Bypass -Command "$s=New-Object -ComObject WScript.Shell; foreach($d in @([Environment]::GetFolderPath('Desktop'), [Environment]::GetFolderPath('Programs'))){ $l=$s.CreateShortcut((Join-Path $d 'DocAudit.lnk')); $l.TargetPath='%VENV%\Scripts\pythonw.exe'; $l.Arguments='-m docaudit'; $l.WorkingDirectory='%APP%'; $l.IconLocation='%APP%\docaudit.ico'; $l.Description='DocAudit'; $l.Save() }"
if errorlevel 1 echo Scurtaturile nu au putut fi create; DocAudit porneste si cu: DocAudit.bat ui
"%VENV%\Scripts\python.exe" -m docaudit --version
echo.
echo Gata. Porneste DocAudit din iconita de pe Desktop sau din meniul Start.
echo Comenzile se ruleaza si cu DocAudit.bat din acest folder, de exemplu: DocAudit.bat tree
echo Datele extrase stau in %APP%\data (local, nu in Google Drive).
pause
exit /b 0

:fail
echo.
echo Instalarea nu a reusit. Trimite-mi mesajul de mai sus.
pause
exit /b 1

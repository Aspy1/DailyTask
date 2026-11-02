@echo off
rem Windows cmd treats ".venv/Scripts/python.exe" as command ".venv" plus the
rem argument "/Scripts/python.exe" (forward slash is a switch delimiter).
rem The Restart gate uses exactly that form, so this shim forwards to the real
rem venv interpreter. It is a no-op for ".venv\Scripts\python.exe" (backslash),
rem which cmd executes directly.
setlocal
set "PY=%~dp0.venv\Scripts\python.exe"
if not exist "%PY%" (
  echo .venv.cmd: missing "%PY%" 1>&2
  exit /b 9009
)
set "ARGS=%*"
if /I "%ARGS:~0,19%"=="/Scripts/python.exe" set "ARGS=%ARGS:~20%"
if /I "%ARGS:~0,19%"=="/scripts/python.exe" set "ARGS=%ARGS:~20%"
"%PY%" %ARGS%

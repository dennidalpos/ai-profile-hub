@echo off
setlocal
chcp 65001 >nul
set PYTHONUTF8=1
if exist "%~dp0.venv\Scripts\python.exe" (
  "%~dp0.venv\Scripts\python.exe" "%~dp0scripts\main.py" %*
  exit /b
)
where py.exe >nul 2>&1
if errorlevel 1 goto python
py.exe -3 "%~dp0scripts\main.py" %*
exit /b %errorlevel%
:python
python.exe "%~dp0scripts\main.py" %*
exit /b %errorlevel%

@echo off
setlocal
chcp 65001 >nul
set PYTHONUTF8=1
if not exist "%~dp0.venv\Scripts\python.exe" goto launcher
"%~dp0.venv\Scripts\python.exe" "%~dp0scripts\build.py" %*
exit /b %errorlevel%
:launcher
where py.exe >nul 2>&1
if errorlevel 1 goto python
py.exe -3 "%~dp0scripts\build.py" %*
exit /b %errorlevel%
:python
python.exe "%~dp0scripts\build.py" %*
exit /b %errorlevel%

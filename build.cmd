@echo off
setlocal
chcp 65001 >nul
set PYTHONUTF8=1
where py.exe >nul 2>&1
if errorlevel 1 goto python
py.exe -3 "%~dp0build.py" %*
exit /b %errorlevel%
:python
python.exe "%~dp0build.py" %*
exit /b %errorlevel%

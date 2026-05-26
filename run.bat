@echo off
cd /d %~dp0
set PYTHONIOENCODING=utf-8
set PYTHONUTF8=1

:: Utiliser le venv s'il a été créé par install.bat
if exist "venv\Scripts\activate.bat" (
    call venv\Scripts\activate.bat
)

python -X utf8 main.py
pause

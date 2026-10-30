@echo off
chcp 65001 >nul
title PRISME
cd /d "%~dp0"
where python >nul 2>nul
if %errorlevel% neq 0 (
  where py >nul 2>nul
  if %errorlevel% neq 0 (
    echo [ERREUR] Python 3 est introuvable. Installez-le depuis https://www.python.org/downloads/
    echo          en cochant "Add Python to PATH", puis relancez ce fichier.
    pause
    exit /b 1
  )
  py -3 server.py
) else (
  python server.py
)
pause

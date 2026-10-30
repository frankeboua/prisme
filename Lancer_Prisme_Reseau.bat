@echo off
chcp 65001 >nul
title PRISME - Partage sur le reseau local (ESATIC TWIN3 - Groupe 7)
cd /d "%~dp0"
echo Les appareils connectes au MEME Wi-Fi pourront ouvrir l'application
echo avec l'adresse affichee ci-dessous (telephones, PC des camarades, jury).
echo Si Windows demande l'autorisation du pare-feu, cliquez sur "Autoriser".
echo.
where python >nul 2>nul
if %errorlevel% neq 0 (
  py -3 server.py --reseau
) else (
  python server.py --reseau
)
pause

@echo off
chcp 65001 >nul
cd /d "%~dp0"
echo Cette operation supprime la base de donnees (comptes crees, favoris, signalements...)
echo et la recree avec les donnees de demonstration au prochain lancement.
set /p ok="Confirmer ? (O/N) : "
if /i "%ok%"=="O" (
  del /q "database\prisme.db" "database\prisme.db-wal" "database\prisme.db-shm" 2>nul
  echo Base supprimee. Lancez maintenant Lancer_Prisme.bat
)
pause

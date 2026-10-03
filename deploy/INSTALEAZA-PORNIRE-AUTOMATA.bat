@echo off
title PostsYT - Pornire automata la fiecare boot
cd /d "%~dp0\.."
echo.
echo  Instalez pornirea AUTOMATA a agentului la fiecare logare Windows.
echo  (curent: %CD%)
echo.

REM --- stergem taskul vechi daca exista
schtasks /delete /tn "PostsYT-Daemon" /f >nul 2>&1
schtasks /delete /tn "PostsYT-Dashboard" /f >nul 2>&1

REM --- daemon: la logare, porneste minimizat
schtasks /create /tn "PostsYT-Daemon" /sc ONLOGON /rl HIGHEST /f ^
  /tr "cmd /c start /min python -m postsyt daemon"

REM --- dashboard: la logare
schtasks /create /tn "PostsYT-Dashboard" /sc ONLOGON /f ^
  /tr "cmd /c start /min python -m postsyt dashboard --port 8787"

echo.
echo  [OK] Gata! De acum, la fiecare logare Windows:
echo   - agentul porneste singur (si posteaza)
echo   - dashboardul e pe  http://localhost:8787
echo.
echo  Ca sa pornesti ACUM fara restart, dublu-click pe PORNESTE-POSTSYT.bat
echo  Ca sa dezinstalezi: schtasks /delete /tn "PostsYT-Daemon" /f
echo.
pause

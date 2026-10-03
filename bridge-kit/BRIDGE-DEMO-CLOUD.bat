@echo off
title PC Bridge -> DEMO cloud (Arena)
set "DEST=%USERPROFILE%\PostsYT-Bridge"

powershell -NoProfile -Command "(Get-Content '%DEST%\postsyt-bridge.ini') -replace 'server = .*','server = https://8787-i959etlo29pm9myd7oy3v.e2b.app' | Set-Content '%DEST%\postsyt-bridge.ini'"

wmic process where "name='pythonw.exe' and CommandLine like '%%pc_bridge%%'" delete >nul 2>nul
wmic process where "name='python.exe' and CommandLine like '%%pc_bridge%%'" delete >nul 2>nul
timeout /t 2 >nul

set "PYW=pythonw"
where pythonw >nul 2>nul || set "PYW=python"
start "" "%PYW%" "%DEST%\pc_bridge.py"

echo [OK] Bridge-ul vorbeste acum cu dashboard-ul de DEMO din CLOUD.
echo Deschide link-ul de preview din chat: sus trebuie sa scrie
echo PC Bridge ONLINE - cu hub-ul in cloud si executia pe PC-ul TAU.
echo.
pause

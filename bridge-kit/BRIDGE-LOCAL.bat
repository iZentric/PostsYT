@echo off
title PC Bridge -> agentul local (127.0.0.1)
set "DEST=%USERPROFILE%\PostsYT-Bridge"

powershell -NoProfile -Command "(Get-Content '%DEST%\postsyt-bridge.ini') -replace 'server = .*','server = http://127.0.0.1:8787' | Set-Content '%DEST%\postsyt-bridge.ini'"

wmic process where "name='pythonw.exe' and CommandLine like '%%pc_bridge%%'" delete >nul 2>nul
wmic process where "name='python.exe' and CommandLine like '%%pc_bridge%%'" delete >nul 2>nul
timeout /t 2 >nul

set "PYW=pythonw"
where pythonw >nul 2>nul || set "PYW=python"
start "" "%PYW%" "%DEST%\pc_bridge.py"

echo [OK] Bridge-ul vorbeste acum cu agentul DE PE PC-UL TAU.
echo Porneste agentul cu PORNESTE-POSTSYT.bat si deschide
echo http://localhost:8787 - sus trebuie sa scrie PC Bridge ONLINE.
echo.
pause

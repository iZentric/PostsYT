@echo off
title PC Bridge -> SERVERUL TAU VPS (permanent)
set "DEST=%USERPROFILE%\PostsYT-Bridge"

echo.
echo  Comuta bridge-ul pe serverul tau final (Oracle).
echo  Valorile le vezi la finalul instalarii pe server.
echo.
set /p SERVER="Adresa serverului, ex http://80.240.24.15:8787 : "
set /p SECRET="bridge_secret de pe server (hex): "
set "PCNAME=%COMPUTERNAME%"

> "%DEST%\postsyt-bridge.ini" echo [bridge]
>>"%DEST%\postsyt-bridge.ini" echo server = %SERVER%
>>"%DEST%\postsyt-bridge.ini" echo secret = %SECRET%
>>"%DEST%\postsyt-bridge.ini" echo name = %PCNAME%
>>"%DEST%\postsyt-bridge.ini" echo agent = postsyt
>>"%DEST%\postsyt-bridge.ini" echo allow = *

wmic process where "name='pythonw.exe' and CommandLine like '%%pc_bridge%%'" delete >nul 2>nul
wmic process where "name='python.exe' and CommandLine like '%%pc_bridge%%'" delete >nul 2>nul
timeout /t 2 >nul

set "PYW=pythonw"
where pythonw >nul 2>nul || set "PYW=python"
start "" "%PYW%" "%DEST%\pc_bridge.py"

echo.
echo [OK] Bridge-ul vorbeste acum cu SERVERUL TAU: %SERVER%
echo Deschide %SERVER% in browser - sus scrie: PC Bridge ONLINE.
echo (Ca sa revii pe testul local: BRIDGE-LOCAL.bat)
echo.
pause

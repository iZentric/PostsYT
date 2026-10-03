@echo off
chcp 65001 >nul
title PostsYT PC Bridge - Instalare (releu universal)

echo ════════════════════════════════════════════════════════════
echo   🌉 PostsYT PC Bridge — instalare
echo.
echo   Ce va face PC-ul tău? Un mic releu, nimic greu:
echo   (~15-20 MB RAM, 0%% CPU, niciun fișier mare)
echo   Agentul de pe server cere, PC-ul execută cererea cu
echo   IP-ul tău de acasă și întoarce răspunsul. Atât.
echo ════════════════════════════════════════════════════════════
echo.

where python >nul 2>nul
if %errorlevel% neq 0 (
  echo ❌ Python nu e instalat. Instalează Python 3.10+ de pe python.org
  echo    (bifează "Add Python to PATH") apoi rulează din nou acest fișier.
  pause
  exit /b 1
)

set "DEST=%USERPROFILE%\PostsYT-Bridge"
if not exist "%DEST%" mkdir "%DEST%"

REM iau pc_bridge.py din repo (deploy\..\bridge\) sau de lângă acest .bat
if exist "%~dp0..\bridge\pc_bridge.py" (
  copy /y "%~dp0..\bridge\pc_bridge.py" "%DEST%\pc_bridge.py" >nul
) else if exist "%~dp0pc_bridge.py" (
  copy /y "%~dp0pc_bridge.py" "%DEST%\pc_bridge.py" >nul
)

REM daca exista postsyt-bridge.ini gata completat langa bat -> ZERO intrebari
if exist "%~dp0postsyt-bridge.ini" (
  copy /y "%~dp0postsyt-bridge.ini" "%DEST%\postsyt-bridge.ini" >nul
  echo ✔ Folosesc configuratia gata facuta din postsyt-bridge.ini — fara intrebari.
  goto DUPA_INI
)

set /p SERVER="Adresa serverului (ex: http://80.240.24.15:8787): "
set /p SECRET="Secret (bridge_secret din config.json de pe server): "
set /p PCNAME="Numele acestui PC [apasă Enter = %COMPUTERNAME%]: "
if "%PCNAME%"=="" set "PCNAME=%COMPUTERNAME%"

> "%DEST%\postsyt-bridge.ini" echo [bridge]
>>"%DEST%\postsyt-bridge.ini" echo server = %SERVER%
>>"%DEST%\postsyt-bridge.ini" echo secret = %SECRET%
>>"%DEST%\postsyt-bridge.ini" echo name = %PCNAME%
>>"%DEST%\postsyt-bridge.ini" echo agent = postsyt
:DUPA_INI

REM prefer pythonw (fără fereastră); altfel python
set "PYW=pythonw"
where pythonw >nul 2>nul || set "PYW=python"

schtasks /Delete /TN "PostsYT PC Bridge" /F >nul 2>nul
schtasks /Create /TN "PostsYT PC Bridge" /SC ONLOGON /RL LIMITED /F ^
  /TR "\"%PYW%\" \"%DEST%\pc_bridge.py\"" >nul
if %errorlevel% neq 0 (
  echo ❌ Nu am putut crea sarcina de pornire automată.
  pause
  exit /b 1
)

REM îl pornesc și acum, ca să nu aștepți următorul login
start "" "%PYW%" "%DEST%\pc_bridge.py"

echo.
echo ✅ Gata! Bridge-ul pornește automat la fiecare pornire a PC-ului
echo    și CHIAR ACUM rulează în fundal.
echo.
echo    Verifică în dashboard (sus apare „🌉 PC Bridge ONLINE").
echo    Dacă vrei vreodată să-l oprești: Task Scheduler → „PostsYT PC Bridge".
echo.
pause

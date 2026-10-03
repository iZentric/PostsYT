@echo off
title PostsYT PC Bridge - Instalare

echo ============================================================
echo   PostsYT PC Bridge - instalare
echo.
echo   Nu consuma aproape nimic: sub 25 MB RAM, 0%% CPU.
echo   Agentul cere, PC-ul executa cererea si intoarce raspunsul.
echo ============================================================
echo.

where python >nul 2>nul
if %errorlevel% neq 0 (
  echo [X] Python nu e instalat.
  echo     Instaleaza Python 3.10+ de pe python.org
  echo     si bifeaza Add Python to PATH, apoi ruleaza din nou.
  pause
  exit /b 1
)

set "DEST=%USERPROFILE%\PostsYT-Bridge"
if not exist "%DEST%" mkdir "%DEST%"

if exist "%~dp0pc_bridge.py" copy /y "%~dp0pc_bridge.py" "%DEST%\pc_bridge.py" >nul
if exist "%~dp0..\bridge\pc_bridge.py" copy /y "%~dp0..\bridge\pc_bridge.py" "%DEST%\pc_bridge.py" >nul

if exist "%~dp0postsyt-bridge.ini" (
  copy /y "%~dp0postsyt-bridge.ini" "%DEST%\postsyt-bridge.ini" >nul
  echo [OK] Configuratia gata facuta gasita - ZERO intrebari.
  goto DUPA_INI
)

set /p SERVER="Adresa serverului, ex http://80.240.24.15:8787 : "
set /p SECRET="Secret, din config.json de pe server: "
set /p PCNAME="Numele acestui PC, Enter = %COMPUTERNAME% : "
if "%PCNAME%"=="" set "PCNAME=%COMPUTERNAME%"

> "%DEST%\postsyt-bridge.ini" echo [bridge]
>>"%DEST%\postsyt-bridge.ini" echo server = %SERVER%
>>"%DEST%\postsyt-bridge.ini" echo secret = %SECRET%
>>"%DEST%\postsyt-bridge.ini" echo name = %PCNAME%
>>"%DEST%\postsyt-bridge.ini" echo agent = postsyt
>>"%DEST%\postsyt-bridge.ini" echo allow = *
:DUPA_INI

set "PYW=pythonw"
where pythonw >nul 2>nul || set "PYW=python"

schtasks /Delete /TN "PostsYT PC Bridge" /F >nul 2>nul
schtasks /Create /TN "PostsYT PC Bridge" /SC ONLOGON /RL LIMITED /F /TR "\"%PYW%\" \"%DEST%\pc_bridge.py\"" >nul
if %errorlevel% neq 0 (
  echo [X] Nu am putut crea sarcina de pornire automata.
  pause
  exit /b 1
)

start "" "%PYW%" "%DEST%\pc_bridge.py"

echo.
echo ============================================================
echo  [OK] GATA! Bridge-ul porneste automat la fiecare reset
echo       si ruleaza CHIAR ACUM in fundal, invizibil.
echo.
echo  Verificare: deschide dashboard-ul si sus trebuie sa
echo  scrie PC Bridge ONLINE.
echo  Oprire oricand: Task Scheduler - PostsYT PC Bridge.
echo ============================================================
echo.
pause

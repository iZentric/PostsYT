@echo off
title PostsYT - Agentul lui iSentric
cd /d "%~dp0"
echo.
echo  ====================================================
echo   POSTSYT - agentul de postari YouTube al lui iSentric
echo  ====================================================
echo.

REM --- verifica Python
python --version >nul 2>&1
if errorlevel 1 (
    echo  [X] Python NU este instalat!
    echo      Descarca-l de aici: https://www.python.org/downloads/
    echo      IMPORTANT: la instalare bifeaza "Add Python to PATH"
    echo.
    pause
    exit /b 1
)
echo  [OK] Python gasit.

REM --- varianta minimala: ZERO dependinte, doar stdlib
REM     (oprtional, pentru per total imagini PNG + sondaje native:
REM      debifeaza randul urmator stergand "REM " din fata)
REM python -m pip install --quiet pillow cairosvg playwright && python -m playwright install chromium

REM --- daca nu ai facut login inca, te intreaba (poti sari peste)
if not exist "data\cookies.json" if not exist "data\cookies.txt" (
    echo.
    echo  [!] Ca sa POSTEZI pe canal e nevoie o data de cookie-urile YouTube.
    echo      Dar dashboard-ul si bridge-ul merg si fara - poti sari peste.
    echo.
    choice /c YN /n /m "  Te loghezi acum cu cookie-urile? [Y=da, N=sar peste]: "
    if errorlevel 2 goto NOLOGIN
    echo.
    python -m postsyt login
    :NOLOGIN
)

echo.
echo  [OK] Pornesc agentul + dashboard-ul.
echo.
echo   Dashboard (aprobare/editare postari):
echo      http://localhost:8787
echo.
echo   Nu inchide fereastra asta cat vrei sa posteze automat!
echo.

REM --- daemon pe fundal + dashboard in prim-plan + browserul se deschide singur
start "PostsYT Daemon" /min python -m postsyt daemon
start "" cmd /c "timeout /t 4 >nul && start http://localhost:8787"
python -m postsyt dashboard --port 8787
pause

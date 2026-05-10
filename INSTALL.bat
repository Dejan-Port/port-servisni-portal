@echo off
title Port Servisni Portal - Instalacija
color 0A

REM ── ADMIN PROVJERA ────────────────────────────────────────────────────────
net session >nul 2>&1
if %errorlevel% neq 0 (
    echo  Potrebna su administratorska prava!
    echo  Desni klik na INSTALL.bat i izaberi "Pokreni kao administrator"
    pause
    exit /b 1
)

REM ── PUTANJE ───────────────────────────────────────────────────────────────
set SRC=%~dp0resources
set APP_DIR=C:\PortServis
set TASK=PortServisniPortal

echo.
echo  ============================================================
echo   Port Servisni Portal - Instalacija v1.0.0
echo  ============================================================
echo.
echo  Izvor:       %SRC%
echo  Instalacija: %APP_DIR%
echo.

REM ── PROVJERA RESURSA ──────────────────────────────────────────────────────
if not exist "%SRC%\server.py" (
    echo  [!] GRESKA: resources\server.py nije pronađen!
    pause
    exit /b 1
)
if not exist "%SRC%\fbclient.dll" (
    echo  [!] GRESKA: resources\fbclient.dll nije pronađen!
    pause
    exit /b 1
)
if not exist "%SRC%\db\servis.gdb" (
    echo  [!] GRESKA: resources\db\servis.gdb nije pronađen!
    pause
    exit /b 1
)

REM ── ZAUSTAVI STARI TASK/SERVIS ────────────────────────────────────────────
echo  Zaustavljam stari servis ako postoji...
schtasks /end /tn "%TASK%" 2>nul
schtasks /delete /tn "%TASK%" /f 2>nul
sc stop "%TASK%" 2>nul
timeout /t 3 /nobreak >nul
sc delete "%TASK%" 2>nul
taskkill /F /IM python.exe /T 2>nul
timeout /t 3 /nobreak >nul

REM ── KREIRANJE DIREKTORIJUMA ───────────────────────────────────────────────
echo  [1/4] Kreiram direktorijume...
mkdir "%APP_DIR%" 2>nul
mkdir "%APP_DIR%\html" 2>nul
mkdir "%APP_DIR%\db" 2>nul
mkdir "%APP_DIR%\db\backup" 2>nul
mkdir "%APP_DIR%\logs" 2>nul
mkdir "%APP_DIR%\plugins" 2>nul
echo  [OK] Direktorijumi kreirani

REM ── KOPIRANJE FAJLOVA ─────────────────────────────────────────────────────
echo  [2/4] Kopiram fajlove...

copy "%SRC%\server.py"      "%APP_DIR%\server.py"    >nul
xcopy "%SRC%\html\*"        "%APP_DIR%\html\"   /E /I /Q /Y >nul
echo  [OK] Aplikacija kopirana

if not exist "%APP_DIR%\db\servis.gdb" (
    copy "%SRC%\db\servis.gdb" "%APP_DIR%\db\servis.gdb" >nul
    echo  [OK] Baza kopirana
) else (
    echo  [OK] Baza vec postoji - preskacam
)

copy "%SRC%\fbclient.dll"   "%APP_DIR%\fbclient.dll"  >nul
copy "%SRC%\firebird.msg"   "%APP_DIR%\firebird.msg"  >nul 2>&1
copy "%SRC%\ib_util.dll"    "%APP_DIR%\ib_util.dll"   >nul 2>&1
copy "%SRC%\icudt52.dll"    "%APP_DIR%\icudt52.dll"   >nul 2>&1
copy "%SRC%\icuin52.dll"    "%APP_DIR%\icuin52.dll"   >nul 2>&1
copy "%SRC%\icuuc52.dll"    "%APP_DIR%\icuuc52.dll"   >nul 2>&1
copy "%SRC%\icudt52l.dat"   "%APP_DIR%\icudt52l.dat"  >nul 2>&1
copy "%SRC%\msvcp100.dll"   "%APP_DIR%\msvcp100.dll"  >nul 2>&1
copy "%SRC%\msvcr100.dll"   "%APP_DIR%\msvcr100.dll"  >nul 2>&1
copy "%SRC%\zlib1.dll"      "%APP_DIR%\zlib1.dll"     >nul 2>&1
echo  [OK] Firebird DLL kopirani

xcopy "%SRC%\plugins\*" "%APP_DIR%\plugins\" /E /I /Q /Y >nul 2>&1
echo  [OK] Plugins kopirani

xcopy "%SRC%\python\*" "%APP_DIR%\python\" /E /I /Q /Y >nul
echo  [OK] Python kopiran

REM ── KREIRANJE start_server.bat ────────────────────────────────────────────
echo  [3/4] Kreiram start_server.bat...
(
echo @echo off
echo cd /d C:\PortServis
echo set FIREBIRD=C:\PortServis
echo set FIREBIRD_CLIENT=C:\PortServis\fbclient.dll
echo set PATH=C:\PortServis;C:\PortServis\plugins;%%PATH%%
echo python\python.exe -m uvicorn server:app --host 0.0.0.0 --port 8080 --workers 1
) > "%APP_DIR%\start_server.bat"
echo  [OK] start_server.bat kreiran

REM ── TASK SCHEDULER ────────────────────────────────────────────────────────
echo  [4/4] Instaliram Task Scheduler zadatak...
schtasks /create /tn "%TASK%" /tr "cmd /c %APP_DIR%\start_server.bat" /sc onstart /ru SYSTEM /rl HIGHEST /f /delay 0000:30
if %errorlevel% neq 0 (
    echo  [!] Greska pri kreiranju zadatka!
    pause
    exit /b 1
)
echo  [OK] Task Scheduler zadatak kreiran

REM ── POKRETANJE ────────────────────────────────────────────────────────────
echo  Pokrecem server...
schtasks /run /tn "%TASK%"
timeout /t 5 /nobreak >nul

REM Provjeri
curl -s http://localhost:8080/health >nul 2>&1
if %errorlevel% equ 0 (
    echo  [OK] Server pokrenut!
) else (
    echo  [!] Server se jos pokrace, sacekajte trenutak...
)

REM Precica na desktopu
powershell -ExecutionPolicy Bypass -Command "$ws=New-Object -ComObject WScript.Shell; $s=$ws.CreateShortcut([Environment]::GetFolderPath('Desktop')+'\Port Servisni Portal.lnk'); $s.TargetPath='http://localhost:8080'; $s.Save()" 2>nul

start "" "http://localhost:8080"

echo.
echo  ============================================================
echo   Instalacija zavrsena!
echo   URL:  http://localhost:8080
echo   Servis se automatski pokrace sa Windowsom.
echo  ============================================================
echo.
pause

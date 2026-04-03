@echo off
setlocal EnableDelayedExpansion
chcp 65001 >nul 2>&1

echo.
echo ╔══════════════════════════════════════════════════════╗
echo ║          Live Pro Player  —  Windows Build           ║
echo ╚══════════════════════════════════════════════════════╝
echo.

REM ── Change to the project root from this script folder ──────────────────
pushd "%~dp0\..\.."

REM ═══════════════════════════════════════════════════════════════════════
REM  1. Verificar Python
REM ═══════════════════════════════════════════════════════════════════════
echo [1/5]  A verificar Python...
where python >nul 2>&1
if errorlevel 1 (
    echo.
    echo  [ERRO] Python nao encontrado no PATH.
    echo  Instala Python 3.11 ou 3.12 em https://python.org
    echo  ^(marca a opcao "Add Python to PATH" durante a instalacao^)
    echo.
    goto :fail
)

for /f "tokens=2 delims= " %%v in ('python --version 2^>^&1') do set PY_VER=%%v
echo        OK  ^(Python %PY_VER%^)

REM Aviso se versao for muito antiga
for /f "tokens=1,2 delims=." %%a in ("%PY_VER%") do (
    set PY_MAJOR=%%a
    set PY_MINOR=%%b
)
if %PY_MAJOR% LSS 3 (
    echo  [ERRO] Python 3.11+ e necessario.
    goto :fail
)
if %PY_MAJOR% EQU 3 if %PY_MINOR% LSS 11 (
    echo  [AVISO] Recomendado Python 3.11+. Versao actual: %PY_VER%
    echo          Continuar pode funcionar mas nao e garantido.
    echo.
)

REM ═══════════════════════════════════════════════════════════════════════
REM  2. Instalar dependencias
REM ═══════════════════════════════════════════════════════════════════════
echo [2/5]  A instalar dependencias...
python -m pip install --upgrade pip --quiet --no-warn-script-location
if errorlevel 1 (
    echo  [AVISO] Nao foi possivel actualizar pip — a continuar...
)

python -m pip install ^
    "pyinstaller>=6.0" ^
    "pyqt5>=5.15" ^
    "numpy>=1.26" ^
    "soundfile>=0.12" ^
    "sounddevice>=0.4" ^
    --quiet --no-warn-script-location

if errorlevel 1 (
    echo.
    echo  [ERRO] Falha ao instalar dependencias.
    echo  Tenta correr este script como Administrador, ou instala manualmente:
    echo    python -m pip install pyinstaller pyqt5 numpy soundfile sounddevice
    echo.
    goto :fail
)
echo        OK

REM ═══════════════════════════════════════════════════════════════════════
REM  3. Limpar builds anteriores
REM ═══════════════════════════════════════════════════════════════════════
echo [3/5]  A limpar builds anteriores...
if exist "build" rmdir /s /q "build"
if exist "dist"  rmdir /s /q "dist"
echo        OK

REM ═══════════════════════════════════════════════════════════════════════
REM  4. Compilar com PyInstaller
REM ═══════════════════════════════════════════════════════════════════════
echo [4/5]  A compilar com PyInstaller...
echo        ^(pode demorar 1-3 minutos na primeira vez^)
echo.

python -m PyInstaller --noconfirm --clean LiveProPlayer.spec

if errorlevel 1 (
    echo.
    echo  [ERRO] PyInstaller falhou. Ver mensagens acima para detalhes.
    goto :fail
)

REM Verificar que o exe existe
if not exist "dist\LiveProPlayer\LiveProPlayer.exe" (
    echo  [ERRO] Exe nao encontrado apos build. Algo correu mal.
    goto :fail
)

echo        OK  —  dist\LiveProPlayer\LiveProPlayer.exe gerado

REM ═══════════════════════════════════════════════════════════════════════
REM  5. Gerar installer com Inno Setup (opcional)
REM ═══════════════════════════════════════════════════════════════════════
echo [5/5]  A procurar Inno Setup...

set INNO=
where iscc >nul 2>&1 && set INNO=iscc
if not defined INNO (
    if exist "C:\Program Files (x86)\Inno Setup 6\ISCC.exe" (
        set INNO="C:\Program Files (x86)\Inno Setup 6\ISCC.exe"
    ) else if exist "C:\Program Files\Inno Setup 6\ISCC.exe" (
        set INNO="C:\Program Files\Inno Setup 6\ISCC.exe"
    )
)

if not defined INNO (
    echo        Inno Setup nao encontrado — a saltar geracao de installer.
    echo        Para gerar um installer .exe:
    echo          1. Instala Inno Setup 6 em https://jrsoftware.org/isinfo.php
    echo          2. Corre este script novamente.
    echo.
    goto :success_no_installer
)

echo        Inno Setup encontrado. A gerar installer...
%INNO% "/DMyAppVersion=0.4.3" "build_scripts\windows\liveproplayer.iss"
if errorlevel 1 (
    echo  [AVISO] Inno Setup retornou erro. O exe foi gerado mesmo assim.
    goto :success_no_installer
)

echo        OK  —  dist\installer\LiveProPlayer-setup-v0.4.3.exe gerado

REM ═══════════════════════════════════════════════════════════════════════
REM  Sucesso com installer
REM ═══════════════════════════════════════════════════════════════════════
echo.
echo ╔══════════════════════════════════════════════════════╗
echo ║  Build concluido com sucesso!                        ║
echo ║                                                      ║
echo ║  Executavel:  dist\LiveProPlayer\LiveProPlayer.exe   ║
echo ║  Installer:   dist\installer\                        ║
echo ╚══════════════════════════════════════════════════════╝
echo.
popd
pause
exit /b 0

:success_no_installer
echo.
echo ╔══════════════════════════════════════════════════════╗
echo ║  Build concluido com sucesso!                        ║
echo ║                                                      ║
echo ║  Executavel:  dist\LiveProPlayer\LiveProPlayer.exe   ║
echo ╚══════════════════════════════════════════════════════╝
echo.
popd
pause
exit /b 0

:fail
echo.
echo ╔══════════════════════════════════════════════════════╗
echo ║  Build FALHOU. Ver mensagens de erro acima.          ║
echo ╚══════════════════════════════════════════════════════╝
echo.
popd
pause
exit /b 1

rem py -m pip freeze >requirements.txt
@echo off
setlocal

set "BASE_DIR=%~dp0"
set "BUILD_SCRIPT=%BASE_DIR%build_exe.py"

echo ==========================================================
echo === Compilando asiscfg.exe (Entorno 32-bit) ===
echo ==========================================================

:: 1. Priorizar el intérprete del entorno virtual .venv si existe
if exist "%BASE_DIR%.venv\Scripts\python.exe" (
    set "PYTHON_EXE=%BASE_DIR%.venv\Scripts\python.exe"
) else (
    set "PYTHON_EXE=python"
)

:: 2. Ejecutar script de compilación reenviando parámetros (%*)
"%PYTHON_EXE%" "%BUILD_SCRIPT%" %*
if %ERRORLEVEL% NEQ 0 (
    echo.
    echo [ERROR] La compilacion ha fallado con codigo %ERRORLEVEL%.
    pause
    endlocal
    exit /b %ERRORLEVEL%
)

echo.
echo [OK] Compilacion completada con exito.
pause
endlocal

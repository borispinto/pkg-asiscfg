# -*- coding: utf-8 -*-
# SPDX-FileCopyrightText: 2026 ASISNET Computación, CA <proyectos@asisnet.net>
# SPDX-FileCopyrightText: 2026 Boris Pinto <borispinto@gmail.com>
# SPDX-License-Identifier: MIT
# Autor: Boris Pinto <borispinto@gmail.com>
# Contacto Institucional: ASISNET Computación, CA <proyectos@asisnet.net>
# File: demo/DEMO.ps1

param(
    [Parameter(Position = 0)]
    [string]$Opcion = ""
)

$demoDir = $PSScriptRoot
$projectRoot = Split-Path $demoDir -Parent
$demoScript = Join-Path $demoDir "demo.py"

# Asegurar que el contexto de ejecución esté situado en demo/
Set-Location $demoDir

# 1. Localizar el mejor intérprete de Python disponible
$pythonExe = $null
$venvPython = Join-Path $projectRoot ".venv\Scripts\python.exe"

if (Test-Path $venvPython) {
    $pythonExe = $venvPython
} elseif (Get-Command "py" -ErrorAction SilentlyContinue) {
    $pythonExe = "py"
} elseif (Get-Command "python" -ErrorAction SilentlyContinue) {
    $pythonExe = "python"
}

if (-not $pythonExe) {
    Write-Host "Error: No se encontró ningún intérprete de Python (.venv, py o python en PATH)." -ForegroundColor Red
    exit 1
}

# 2. Si no se especificó opción por parámetro, desplegar menú interactivo
if (-not $Opcion) {
    Write-Host ""
    Write-Host "======================================================================" -ForegroundColor Cyan
    Write-Host "  DEMO PORTABLE PKG-ASISCFG: SQLITE MULTI-PERFIL Y HERENCIA EN CASCADA" -ForegroundColor Cyan
    Write-Host "======================================================================" -ForegroundColor Cyan
    Write-Host "  Clave de administración preconfigurada para la demo: demo" -ForegroundColor Yellow
    Write-Host ""
    Write-Host "  [1] Iniciar Interfaz Gráfica (GUI con perfiles y prueba de conexión)" -ForegroundColor White
    Write-Host "  [2] Ejecutar demo en consola (Lectura y herencia jerárquica en Python)" -ForegroundColor White
    Write-Host "  [3] Resetear clave de administración (--reset-admin-pass)" -ForegroundColor White
    Write-Host "  [0] Salir" -ForegroundColor Gray
    Write-Host ""
    $Opcion = Read-Host "Seleccione una opción [1-3, 0]"
}

# Normalizar opción recibida
$opcionNorm = if ($Opcion) { $Opcion.Trim().ToLower() } else { "0" }
if ($opcionNorm -in @("ui", "gui", "interfaz")) { $opcionNorm = "1" }
elseif ($opcionNorm -in @("console", "consola", "demo")) { $opcionNorm = "2" }
elseif ($opcionNorm -in @("reset", "reset-pass", "clave")) { $opcionNorm = "3" }

# 3. Despachar acción según la opción seleccionada
switch ($opcionNorm) {
    "1" {
        $cmdArgs = @($demoScript, "--ui", "--dev", "--edit", "--theme", "dark")
        $cmdDisplay = "$pythonExe `"$demoScript`" --ui --dev --edit --theme dark"
        Write-Host "`nClave de administración para acceder a la GUI: demo" -ForegroundColor Yellow
        Write-Host "Comando a ejecutar:" -ForegroundColor Green
        Write-Host "  $cmdDisplay`n" -ForegroundColor Cyan
        & $pythonExe @cmdArgs
    }
    "2" {
        $cmdArgs = @($demoScript)
        $cmdDisplay = "$pythonExe `"$demoScript`""
        Write-Host "`nComando a ejecutar:" -ForegroundColor Green
        Write-Host "  $cmdDisplay`n" -ForegroundColor Cyan
        & $pythonExe @cmdArgs
    }
    "3" {
        $cmdArgs = @($demoScript, "--ui", "--dev", "--reset-admin-pass")
        $cmdDisplay = "$pythonExe `"$demoScript`" --ui --dev --reset-admin-pass"
        Write-Host "`nComando a ejecutar:" -ForegroundColor Green
        Write-Host "  $cmdDisplay`n" -ForegroundColor Cyan
        & $pythonExe @cmdArgs
    }
    "0" {
        Write-Host "Operación cancelada por el usuario." -ForegroundColor Gray
        exit 0
    }
    default {
        Write-Host "Opción inválida: '$Opcion'. Por favor seleccione 1, 2, 3 o 0." -ForegroundColor Red
        exit 1
    }
}

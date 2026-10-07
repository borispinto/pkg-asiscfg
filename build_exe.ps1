# Script ejecutable de PowerShell para compilar asiscfg
param(
    [ValidateSet("onedir", "onefile")]
    [string]$Mode = "onedir",
    [switch]$Console,
    [switch]$NoClean
)

$PythonExe = if (Test-Path ".\.venv\Scripts\python.exe") { ".\.venv\Scripts\python.exe" } else { "python" }
$Params = @(".\build_exe.py", "--mode", $Mode)

if ($Console) {
    $Params += "--console"
}
if ($NoClean) {
    $Params += "--no-clean"
}

& $PythonExe @Params

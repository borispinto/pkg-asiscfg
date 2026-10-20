Write-Host "[1/4] Creando entorno virtual .venv..." -ForegroundColor Cyan
py -m venv .venv

Write-Host "[2/4] Activando entorno virtual..." -ForegroundColor Cyan
& .venv\Scripts\Activate.ps1

Write-Host "[3/4] Actualizando pip..." -ForegroundColor Cyan
python -m pip install --upgrade pip

Write-Host "[4/4] Instalando dependencias desde requirements.txt..." -ForegroundColor Cyan
pip install -r requirements.txt

Write-Host "`nEntorno configurado con éxito." -ForegroundColor Green
Read-Host -Prompt "Presiona Enter para salir"

@echo off
echo [1/4] Creando entorno virtual .venv...
py -m venv .venv

echo [2/4] Activando entorno virtual...
call .venv\Scripts\activate.bat

echo [3/4] Actualizando pip...
python -m pip install --upgrade pip

echo [4/4] Instalando dependencias desde requirements.txt...
pip install -r requirements.txt

echo Entorno configurado con exito.
pause

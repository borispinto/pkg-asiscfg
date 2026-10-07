# -*- coding: utf-8 -*-
# SPDX-FileCopyrightText: 2026 Asisnet Computacion, CA <proyectos@asisnet.net>
# SPDX-License-Identifier: MIT
# Autor: Boris Pinto <borispinto@asisnet.net>
# File: build_exe.py

"""
Script de compilación Standalone para asiscfg usando PyInstaller.
Genera el paquete ejecutable asiscfg en dist/.
"""

import sys
import os
import subprocess
import argparse
import importlib.util

ASISCFG_DIR = os.path.dirname(os.path.abspath(__file__))


def is_module_available(module_name: str, extra_paths: list = None) -> bool:
    """Verifica si un módulo o paquete está disponible en el entorno o rutas especificadas."""
    if importlib.util.find_spec(module_name) is not None:
        return True
    if extra_paths:
        for p in extra_paths:
            candidate = os.path.join(p, module_name)
            if os.path.isdir(candidate) or os.path.isfile(f"{candidate}.py"):
                return True
    return False


def generate_version_file(output_path: str) -> None:
    """Genera la estructura de metadatos de versión de Windows para el ejecutable."""
    content = """# UTF-8
VSVersionInfo(
  ffi=FixedFileInfo(
    filevers=(1, 0, 0, 0),
    prodvers=(1, 0, 0, 0),
    mask=0x3f,
    flags=0x0,
    OS=0x40004,
    fileType=0x1,
    subtype=0x0,
    date=(0, 0)
  ),
  kids=[
    StringFileInfo(
      [
      StringTable(
        '040904B0',
        [StringStruct('CompanyName', 'Asisnet Computacion, CA'),
        StringStruct('FileDescription', 'Libreria modular y GUI de configuracion cifrada'),
        StringStruct('FileVersion', '1.0.0'),
        StringStruct('InternalName', 'asiscfg'),
        StringStruct('LegalCopyright', 'Copyright (C) 2026 Asisnet Computacion, CA'),
        StringStruct('OriginalFilename', 'asiscfg.exe'),
        StringStruct('ProductName', 'asiscfg'),
        StringStruct('ProductVersion', '1.0.0')])
      ]), 
    VarFileInfo([VarStruct('Translation', [1033, 1200])])
  ]
)
"""
    with open(output_path, "w", encoding="utf-8") as f:
        f.write(content)


def build(mode: str = "onedir", console: bool = False, clean: bool = True):
    arch = "64-bit" if sys.maxsize > 2**32 else "32-bit"
    py_ver = sys.version.split()[0]
    display_mode = f"{mode} ({'consola' if console else 'ventana/gui'})"
    print(f"[BUILD] Iniciando compilación de asiscfg (modo: {display_mode})...")
    print(f"[BUILD] Intérprete: Python {py_ver} ({arch})")
    print(f"[BUILD] Ruta: {sys.executable}")

    try:
        import PyInstaller  # noqa: F401
    except ImportError:
        print("[BUILD] PyInstaller no está instalado. Intentando instalación vía pip...")
        try:
            subprocess.check_call([sys.executable, "-m", "pip", "install", "pyinstaller"])
        except subprocess.CalledProcessError as err:
            print(f"\n❌ [BUILD ERROR] No se pudo instalar PyInstaller automáticamente: {err}")
            print("[BUILD] Por favor, instálelo manualmente ejecutando: pip install pyinstaller")
            sys.exit(1)

    # Separador de rutas de PyInstaller según SO (Windows usa ;)
    sep = ";" if sys.platform.startswith("win") else ":"

    # 1. Resolver rutas de paquetes hermanos si existen
    pathex_dirs = [ASISCFG_DIR]
    for sibling in ["pkg-i18n", "pkg-asisdb"]:
        sib_path = os.path.abspath(os.path.join(ASISCFG_DIR, "..", sibling))
        if os.path.isdir(sib_path) and sib_path not in pathex_dirs:
            pathex_dirs.append(sib_path)

    pathex_args = []
    for p in pathex_dirs:
        pathex_args.extend(["--paths", p])

    # 2. Incluir directorio de recursos
    add_data_args = []
    resources_dir = os.path.join(ASISCFG_DIR, "asiscfg", "resources")
    if not os.path.exists(resources_dir):
        resources_dir = os.path.join(ASISCFG_DIR, "resources")
    if os.path.exists(resources_dir):
        add_data_args.extend(["--add-data", f"{resources_dir}{sep}resources"])

    # 3. Icono si existe
    icon_path = os.path.join(resources_dir, "logo.ico")
    icon_arg = ["--icon", icon_path] if os.path.exists(icon_path) else []

    # 4. Archivo de versión de Windows (metadatos PE)
    version_arg = []
    if sys.platform.startswith("win"):
        version_file = os.path.join(ASISCFG_DIR, "version_info.txt")
        try:
            generate_version_file(version_file)
            version_arg = ["--version-file", version_file]
        except Exception as e:
            print(f"[BUILD] Advertencia: No se pudo generar version_info.txt: {e}")

    # 5. Modo de empaquetado y consola
    mode_arg = f"--{mode}"
    window_arg = "--console" if console else "--windowed"

    # 6. Colección de paquetes y dependencias opcionales
    collect_pkgs = ["customtkinter", "asiscfg"]
    for opt_pkg in ["i18n", "asisdb"]:
        if is_module_available(opt_pkg, pathex_dirs):
            collect_pkgs.append(opt_pkg)

    collect_args = []
    for pkg in collect_pkgs:
        collect_args.extend(["--collect-all", pkg])

    # 7. Hidden imports selectivos para drivers/conectores
    hidden_imports = [
        "cryptography",
        "sqlalchemy",
        "pymssql",
        "psycopg2",
        "pymysql",
        "pyodbc",
        "sqlite3",
        "dbfread"
    ]
    hidden_args = []
    for h in hidden_imports:
        hidden_args.extend(["--hidden-import", h])

    cmd = [
        sys.executable, "-m", "PyInstaller",
        "--noconfirm",
    ]
    if clean:
        cmd.append("--clean")
        
    cmd.extend([
        mode_arg,
        window_arg,
        "--name", "asiscfg"
    ])
    cmd.extend(pathex_args)
    cmd.extend(icon_arg)
    cmd.extend(version_arg)
    cmd.extend(add_data_args)
    cmd.extend(collect_args)
    cmd.extend(hidden_args)
    cmd.append(os.path.join(ASISCFG_DIR, "asiscfg.py"))

    print("\n[BUILD] Comando PyInstaller:")
    print(" ".join(cmd))
    print("-" * 70)

    res = subprocess.run(cmd, cwd=ASISCFG_DIR)
    if res.returncode == 0:
        print("\n" + "=" * 70)
        print("✅ [BUILD SUCCESS] Compilación completada con éxito.")
        out_path = (
            os.path.join(ASISCFG_DIR, "dist", "asiscfg.exe")
            if mode == "onefile"
            else os.path.join(ASISCFG_DIR, "dist", "asiscfg")
        )
        print(f"📁 Salida generada en: {out_path}")
        print("=" * 70)
    else:
        print("\n❌ [BUILD ERROR] La compilación falló.")
        sys.exit(res.returncode)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="Script de compilación Standalone para asiscfg usando PyInstaller."
    )
    parser.add_argument(
        "--mode",
        choices=["onedir", "onefile"],
        default="onedir",
        help="Modo de empaquetado: 'onedir' (carpeta con archivos) o 'onefile' (ejecutable único). Por defecto: onedir."
    )
    parser.add_argument(
        "--console",
        action="store_true",
        default=False,
        help="Compila mostrando ventana de consola (útil para depuración o uso CLI con --help/--generate-key). Por defecto es modo ventana sin consola."
    )
    parser.add_argument(
        "--no-clean",
        action="store_true",
        default=False,
        help="Omite la limpieza previa de la caché de PyInstaller para una compilación más rápida."
    )
    args = parser.parse_args()
    build(mode=args.mode, console=args.console, clean=not args.no_clean)

# -*- coding: utf-8 -*-
# SPDX-FileCopyrightText: 2026 Asisnet Computacion, CA <proyectos@asisnet.net>
# SPDX-License-Identifier: MIT
# Autor: Boris Pinto <borispinto@asisnet.net>
# File: asiscfg.py

"""
Punto de entrada CLI/GUI y capa de ejecución para asiscfg.
Wrapper ejecutable que delega en el paquete modular `asiscfg`.
"""

import sys
import os
import argparse

ASISCFG_DIR = os.path.dirname(os.path.abspath(__file__))
if ASISCFG_DIR not in sys.path:
    sys.path.insert(0, ASISCFG_DIR)

from i18n import t18n
from asiscfg.constants import (
    DEFAULT_CONFIG_FILENAME,
    DEFAULT_KEY_FILENAME,
    DEFAULT_SCHEMA_FILENAME,
    FORMAT_MODES
)
from asiscfg.models import create_app_context
from asiscfg.core import execute_app_action

CLI_ARGS = None

def main():
    global CLI_ARGS

    parser = argparse.ArgumentParser(description=t18n("asiscfg.cli_description", "Herramienta Standalone de Configuración Cifrada"))
    parser.add_argument("--schema-file", default=None, help=f"Ruta al archivo .py con el esquema (por defecto: {DEFAULT_SCHEMA_FILENAME})")
    parser.add_argument("--config-file", default=None, help=f"Ruta al archivo cifrado (por defecto: {DEFAULT_CONFIG_FILENAME})")
    parser.add_argument("--key-file", default=None, help=f"Ruta a la clave maestra (por defecto: {DEFAULT_KEY_FILENAME})")
    parser.add_argument("--i18n-path", default=None, help="Ruta al módulo o carpeta contenedora de i18n")
    parser.add_argument("--dev", action="store_true", help="Modo desarrollo (omite validación UAC)")
    parser.add_argument("--app", action="store_true", help="Permite la edición de los valores de la sección 'app'")
    format_choices = list(FORMAT_MODES.keys())
    format_desc = ", ".join(f"'{k}' ({v.name})" for k, v in FORMAT_MODES.items())
    parser.add_argument("--format-mode", choices=format_choices, default="plain", help=f"Modo de almacenamiento del archivo: {format_desc}.")
    parser.add_argument("--theme", choices=["dark", "light", "system"], default="dark", help="Modo de apariencia visual: 'dark' (por defecto), 'light' o 'system'")
    parser.add_argument("--reset-admin-pass", action="store_true", help="Restablece la clave de administración al valor por defecto")
    parser.add_argument("--export-schema", action="store_true", help="Exporta el archivo de esquema config_schema.py en la ruta destino")
    parser.add_argument("--generate-key", action="store_true", help="Genera explícitamente un nuevo archivo de clave Fernet")
    parser.add_argument("--overwrite-key", action="store_true", help="Permite sobreescribir el archivo de clave existente con --generate-key")

    CLI_ARGS = parser.parse_args()

    action = "ui"
    if CLI_ARGS.generate_key:
        action = "generate_key"
    elif CLI_ARGS.export_schema:
        action = "export_schema"
    
    ctx = create_app_context(
        action=action,
        config_file=CLI_ARGS.config_file,
        key_file=CLI_ARGS.key_file,
        schema_file=CLI_ARGS.schema_file,
        format_mode=CLI_ARGS.format_mode,
        is_standalone=True,
        dev_mode=CLI_ARGS.dev
    )
    
    code = execute_app_action(
        context=ctx,
        overwrite_key=CLI_ARGS.overwrite_key,
        i18n_path=CLI_ARGS.i18n_path,
        allow_app_edit=CLI_ARGS.app,
        reset_admin_pass=CLI_ARGS.reset_admin_pass,
        theme=CLI_ARGS.theme,
        exit_on_finish=True
    )
    if code is not None:
        sys.exit(code)


if __name__ == "__main__":
    main()



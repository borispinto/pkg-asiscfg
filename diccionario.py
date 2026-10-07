# -*- coding: utf-8 -*-
# SPDX-FileCopyrightText: 2026 Asisnet Computacion, CA <proyectos@asisnet.net>
# SPDX-License-Identifier: MIT
# Autor: Boris Pinto <borispinto@asisnet.net>
# File: diccionario.py

from i18n import extract_base_language

resultado = extract_base_language(
    origin_dir="asiscfg",                      # Carpeta fuente del proyecto a escanear
    output_dir="PRUEBA",      # Carpeta donde guardar es.json
    file_extensions=[".py", ".html"],      # Extensiones a escanear
    recursive=True,                        # Escanear subdirectorios
    function_names=["t18n"],               # Nombres de funciones a detectar
    language_name="Español",
    target_filename="asiscfg_es.json",
    show_source=True
)

print(resultado)
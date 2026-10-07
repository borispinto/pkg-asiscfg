# -*- coding: utf-8 -*-
# SPDX-FileCopyrightText: 2026 Asisnet Computacion, CA <proyectos@asisnet.net>
# SPDX-License-Identifier: MIT
# Autor: Boris Pinto <borispinto@asisnet.net>
# File: asiscfg/constants.py

"""
Constantes centralizadas del sistema para el paquete asiscfg.
Define los nombres de archivo por defecto, prefijos, centinelas y registro canónico de formatos.
"""

import os
import sys

# Directorio base de la librería y del proyecto / entorno de ejecución
PACKAGE_DIR = os.path.dirname(os.path.abspath(__file__))

if getattr(sys, "frozen", False):
    BASE_DIR = os.path.dirname(os.path.abspath(sys.executable))
else:
    BASE_DIR = os.path.abspath(os.getcwd())

# Nombres por defecto para archivos del sistema
DEFAULT_CONFIG_FILENAME = "config.enc"
DEFAULT_KEY_FILENAME = "config.key"
DEFAULT_SCHEMA_FILENAME = "config_schema.py"

# Prefijos de seguridad y centinela de campos protegidos
ENC_PREFIX = "ENC:"
NULL_SENTINEL = "<%null$>"

# Prefijos canónicos de clasificación
PREFIX_SCHEMA_DIRECTIVE = "_"  # Directivas de esquema (volátiles, no persistentes)
PREFIX_SPECIAL_SECTION = "@"   # Secciones especiales de sistema (persistentes)

# Nombres canónicos de secciones especiales
SECTION_PROFILES = "@profiles"
SECTION_ASISCFG = "@asiscfg"

SECURITY_SECTIONS = ['app']

# Modos / Acciones canónicas de inicialización de contexto
VALID_ACTIONS = ("consume", "ui", "generate_key", "export_schema")


def is_security_section(key: str) -> bool:
    """Indica si una clave corresponde a una sección protegida de seguridad."""
    return bool(key and isinstance(key, str) and key in SECURITY_SECTIONS)


def is_schema_directive(key: str) -> bool:
    """Indica si una clave corresponde a una directiva/metadato de esquema (inicia con '_')."""
    return bool(key and isinstance(key, str) and key.startswith(PREFIX_SCHEMA_DIRECTIVE))


def is_special_section(key: str) -> bool:
    """Indica si una clave corresponde a una sección especial de sistema (inicia con '@')."""
    return bool(key and isinstance(key, str) and key.startswith(PREFIX_SPECIAL_SECTION))


def is_business_section(key: str) -> bool:
    """Indica si una clave corresponde a una sección estándar de negocio (ni directiva ni especial)."""
    return bool(key and isinstance(key, str) and not is_schema_directive(key) and not is_special_section(key))


# Registro canónico de modos de formato y motores criptográficos (Strategy/Registry)
from asiscfg.crypto import (
    BaseFormatEngine,
    PlainFormatEngine,
    FernetFormatEngine,
    Aes256GcmFormatEngine,
    ChaCha20FormatEngine,
    FORMAT_MODES,
    get_format_engine,
    detect_format_engine,
)

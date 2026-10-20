# -*- coding: utf-8 -*-
# SPDX-FileCopyrightText: 2026 ASISNET Computación, CA <proyectos@asisnet.net>
# SPDX-FileCopyrightText: 2026 Boris Pinto <borispinto@gmail.com>
# SPDX-License-Identifier: MIT
# Autor: Boris Pinto <borispinto@gmail.com>
# Contacto Institucional: ASISNET Computación, CA <proyectos@asisnet.net>
# File: asiscfg/constants.py

"""
Constantes centralizadas del sistema para el paquete asiscfg.
Define los nombres de archivo por defecto, prefijos canónicos, centinelas y clasificación de secciones.
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
DEFAULT_KEY_FILENAME = "secret.key"
DEFAULT_SCHEMA_FILENAME = "config_schema.py"

# Prefijos de seguridad y centinela de campos protegidos
ENC_PREFIX = "ENC:"
NULL_SENTINEL = "<%null$>"

# Prefijo de comentario informativo público en cabecera
PUBLIC_PREFIX = "# "

# Clave de sellado forense para modo PLAIN con security_level = 1
NO_MODIFY_KEY = "@NO_MODIFICAR_NO_MODIFY"

# Prefijos canónicos de clasificación
PREFIX_SCHEMA_DIRECTIVE = "_"  # Directivas de esquema (volátiles, no persistentes)
PREFIX_SPECIAL_SECTION = "@"   # Secciones especiales de sistema (persistentes)

# Nombres canónicos de secciones especiales
SECTION_PROFILES = "@profiles"
SECTION_ASISCFG = "@asiscfg"

SECURITY_SECTIONS = ["app"]

# Modos / Acciones canónicas de inicialización de contexto
VALID_ACTIONS = ("consume", "ui", "generate_key", "export_schema", "install")


def is_security_section(key: str) -> bool:
    """Indica si una clave corresponde a una sección protegida de seguridad."""
    return key in SECURITY_SECTIONS


def is_schema_directive(key: str) -> bool:
    """Indica si una clave corresponde a una directiva/metadato de esquema (inicia con '_')."""
    return key.startswith(PREFIX_SCHEMA_DIRECTIVE)


def is_special_section(key: str) -> bool:
    """Indica si una clave corresponde a una sección especial de sistema (inicia con '@')."""
    return key.startswith(PREFIX_SPECIAL_SECTION)


def is_business_section(key: str) -> bool:
    """Indica si una clave corresponde a una sección estándar de negocio (ni directiva ni especial)."""
    return not key.startswith(PREFIX_SCHEMA_DIRECTIVE) and not key.startswith(PREFIX_SPECIAL_SECTION)


# Re-exportación canónica de motores y registros criptográficos
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

__all__ = [
    "PACKAGE_DIR",
    "BASE_DIR",
    "DEFAULT_CONFIG_FILENAME",
    "DEFAULT_KEY_FILENAME",
    "DEFAULT_SCHEMA_FILENAME",
    "ENC_PREFIX",
    "NULL_SENTINEL",
    "PUBLIC_PREFIX",
    "NO_MODIFY_KEY",
    "PREFIX_SCHEMA_DIRECTIVE",
    "PREFIX_SPECIAL_SECTION",
    "SECTION_PROFILES",
    "SECTION_ASISCFG",
    "SECURITY_SECTIONS",
    "VALID_ACTIONS",
    "is_security_section",
    "is_schema_directive",
    "is_special_section",
    "is_business_section",
    "BaseFormatEngine",
    "PlainFormatEngine",
    "FernetFormatEngine",
    "Aes256GcmFormatEngine",
    "ChaCha20FormatEngine",
    "FORMAT_MODES",
    "get_format_engine",
    "detect_format_engine",
]

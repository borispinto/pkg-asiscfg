# -*- coding: utf-8 -*-
# SPDX-FileCopyrightText: 2026 Asisnet Computacion, CA <proyectos@asisnet.net>
# SPDX-License-Identifier: MIT
# Autor: Boris Pinto <borispinto@asisnet.net>
# File: asiscfg/security.py

"""
Módulo de seguridad, hashing de contraseñas y auditoría para asiscfg (Versión 1).
"""

import hashlib
import logging
from datetime import datetime
from typing import Any, Union
from asiscfg.models import ConfigDict
from asiscfg.constants import SECTION_ASISCFG


def hash_password(password: str) -> str:
    """Genera hash SHA-256 para contraseñas de administración."""
    return hashlib.sha256(password.encode("utf-8")).hexdigest()


def check_admin_password(input_password: str, config_or_hash: Union[ConfigDict, dict, str, None]) -> bool:
    """
    Verifica si la contraseña ingresada coincide con la almacenada en la configuración
    (sección @asiscfg.admin_pass_hash) o con un hash string directo.
    """
    stored_hash = None

    if isinstance(config_or_hash, str):
        stored_hash = config_or_hash
    elif isinstance(config_or_hash, (dict, ConfigDict)):
        cfg_tool = config_or_hash.get(SECTION_ASISCFG, {})
        if isinstance(cfg_tool, dict):
            stored_hash = cfg_tool.get("admin_pass_hash")

    if not stored_hash:
        # Clave por defecto en V1: 'admin'
        stored_hash = hash_password("admin")

    return hash_password(input_password) == stored_hash


def set_admin_password(config: Any, new_password: str) -> None:
    """Actualiza el hash de la contraseña admin en el diccionario de configuración o en la app."""
    if isinstance(new_password, (dict, ConfigDict)) and isinstance(config, str):
        config, new_password = new_password, config

    # Soporte si se pasa la instancia de la aplicación directamente
    if hasattr(config, "working_config") and isinstance(config.working_config, dict):
        set_admin_password(config.working_config, new_password)
    if hasattr(config, "current_config") and isinstance(config.current_config, (dict, ConfigDict)):
        set_admin_password(config.current_config, new_password)

    if not isinstance(config, (dict, ConfigDict)):
        return

    if SECTION_ASISCFG not in config or not isinstance(config[SECTION_ASISCFG], dict):
        config[SECTION_ASISCFG] = {}
    config[SECTION_ASISCFG]["admin_pass_hash"] = hash_password(new_password)



def is_admin() -> bool:
    """Verifica si el proceso actual posee privilegios elevados de Administrador del sistema operativo (UAC en Windows o root)."""
    try:
        import ctypes
        return ctypes.windll.shell32.IsUserAnAdmin() != 0
    except Exception:
        try:
            import os
            geteuid = getattr(os, "geteuid", None)
            if callable(geteuid):
                return geteuid() == 0
            return False
        except Exception:
            return False


def log_audit_event(action: str, details: str = "") -> None:
    """Registra eventos de seguridad o modificación en el archivo audit.log."""
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    msg = f"[{timestamp}] AUDIT: {action} | Details: {details}"
    logging.info(msg)

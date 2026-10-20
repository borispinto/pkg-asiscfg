# -*- coding: utf-8 -*-
# SPDX-FileCopyrightText: 2026 ASISNET Computación, CA <proyectos@asisnet.net>
# SPDX-FileCopyrightText: 2026 Boris Pinto <borispinto@gmail.com>
# SPDX-License-Identifier: MIT
# Autor: Boris Pinto <borispinto@gmail.com>
# Contacto Institucional: ASISNET Computación, CA <proyectos@asisnet.net>
# File: asiscfg/context.py

"""
Contexto canónico unificado de ejecución para asiscfg (Nivel 2).
Centraliza rutas absolutas de archivos, estado criptográfico y parámetros de runtime.
"""

import os
import sys
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

from asiscfg.constants import (
    BASE_DIR,
    DEFAULT_CONFIG_FILENAME,
    DEFAULT_KEY_FILENAME,
    DEFAULT_SCHEMA_FILENAME,
    SECTION_ASISCFG,
    VALID_ACTIONS,
)
from asiscfg.crypto import get_format_engine
from asiscfg.schema import load_schema_definition


@dataclass
class AppConfigContext:
    """
    Contexto canónico de ejecución para asiscfg.
    Garantiza rutas absolutas y contratos íntegros para las capas subsiguientes.
    """

    config_file_path: str = ""
    config_file_name: str = ""
    key_file_path: str = ""
    key_file_name: str = ""
    schema_file_path: str = ""
    schema_file_name: str = ""
    base_dir: str = ""
    action: str = "consume"
    app_title: str = "ASISCFG"
    is_standalone: bool = False
    dev_mode: bool = False
    key_status: str = "ok"
    key_detail: str = ""
    default_config: Dict[str, Any] = field(default_factory=dict)
    validation_rules: Dict[str, Any] = field(default_factory=dict)
    profile_template: Dict[str, Any] = field(default_factory=dict)
    password_fields: List[str] = field(default_factory=list)
    public_fields: List[str] = field(default_factory=list)
    security_level: int = 0
    backup_settings: Dict[str, Any] = field(default_factory=dict)
    admin_pass_hash: Optional[str] = None
    key_bytes: Optional[bytes] = None
    format_mode: str = "plain"
    active_profile: Optional[str] = None
    metadata: Dict[str, Any] = field(default_factory=dict)

    def __post_init__(self):
        engine = get_format_engine(self.format_mode)
        self.format_mode = engine.mode_id
        norm_action = str(self.action).strip().lower() if self.action else "consume"
        if norm_action not in VALID_ACTIONS:
            raise ValueError(
                f"Acción '{self.action}' inválida en AppConfigContext. Debe ser una de: {', '.join(VALID_ACTIONS)}"
            )
        self.action = norm_action


def resolve_file_path(path_full: Optional[str], default_name: str, base_dir: str) -> str:
    """
    Resuelve la ruta completa de un archivo persistente en disco (config.enc, secret.key).
    - Si path_full está vacío o None -> base_dir/default_name
    - Si path_full es un nombre de archivo -> base_dir/nombre.ext
    - Si path_full es un directorio -> base_dir/directorio/default_name
    - Si path_full es absoluto -> se respeta tal cual
    """
    if path_full and str(path_full).strip():
        path_str = str(path_full).strip()
        resolved = path_str if os.path.isabs(path_str) else os.path.join(base_dir, path_str)
        resolved = os.path.abspath(resolved)
        if os.path.isdir(resolved):
            resolved = os.path.join(resolved, default_name)
    else:
        resolved = os.path.abspath(os.path.join(base_dir, default_name))
    return resolved


def resolve_dir_path(
    path_dir: Optional[str],
    base_dir: str,
    default_dir: Optional[str] = "",
) -> str:
    """
    Resuelve y normaliza la ruta completa de un directorio en disco.
    - Soporta interpolación del comodín '{ROOT}' reemplazándolo por base_dir.
    - Si path_dir está vacío o None, utiliza default_dir (o base_dir si default_dir está vacío o None).
    - Si la ruta resultante es relativa, la ancla a base_dir.
    - Retorna siempre una ruta absoluta normalizada.
    """
    resolved_base = os.path.abspath(base_dir)
    raw = str(path_dir).strip() if (path_dir and str(path_dir).strip()) else ""
    if not raw:
        raw = str(default_dir).strip() if (default_dir and str(default_dir).strip()) else ""

    if not raw:
        return resolved_base

    raw = raw.replace("{ROOT}", resolved_base)
    resolved = raw if os.path.isabs(raw) else os.path.join(resolved_base, raw)
    return os.path.abspath(resolved)



def resolve_schema_path(
    schema_param: Optional[str],
    default_name: str,
    base_dir: str,
    is_standalone: bool = False,
) -> str:
    """
    Detecta de forma canónica y determinista la ruta del archivo de esquema:
    1. Siempre primeramente busca físicamente en el camino indicado por el anfitrión.
    2. Si no existe:
       a. Si está ejecutando compilado (sys.frozen y sys._MEIPASS):
          - Buscar en el compilado primero en el camino indicado por el anfitrión (_MEIPASS / <camino_relativo>).
          - Luego en la raíz del compilado (_MEIPASS / <nombre_archivo>).
          - Si no existe en el compilado -> Lanza FileNotFoundError.
       b. Sino está ejecutando compilado -> Lanza FileNotFoundError.
    """
    param_str = str(schema_param).strip() if (schema_param and str(schema_param).strip()) else ""

    if not param_str:
        if is_standalone:
            param_str = default_name
        else:
            raise FileNotFoundError("No se especificó la ruta del archivo de esquema requerido por el anfitrión.")

    # 1. Determinar el camino físico indicado por el anfitrión
    if os.path.isabs(param_str):
        physical_path = os.path.abspath(param_str)
    else:
        physical_path = os.path.abspath(os.path.join(base_dir, param_str))

    if os.path.isdir(physical_path):
        physical_path = os.path.abspath(os.path.join(physical_path, default_name))

    # Paso 1: Si existe físicamente en el camino indicado por el anfitrión, retornar
    if os.path.isfile(physical_path):
        return physical_path

    # Paso 2: Si no existe físicamente
    is_frozen = bool(getattr(sys, "frozen", False) and hasattr(sys, "_MEIPASS"))

    if is_frozen:
        meipass_dir = getattr(sys, "_MEIPASS", "")
        # Determinar el camino relativo indicado por el anfitrión
        if not os.path.isabs(param_str):
            rel_path = param_str
        else:
            try:
                rel_path = os.path.relpath(physical_path, base_dir)
                if rel_path.startswith(".."):
                    rel_path = os.path.basename(physical_path)
            except ValueError:
                rel_path = os.path.basename(physical_path)

        # 1º En el camino indicado por el anfitrión dentro del compilado
        cand_host = os.path.abspath(os.path.join(meipass_dir, rel_path))
        if os.path.isfile(cand_host):
            return cand_host

        # 2º En la raíz del compilado
        cand_root = os.path.abspath(os.path.join(meipass_dir, os.path.basename(physical_path)))
        if os.path.isfile(cand_root):
            return cand_root

        raise FileNotFoundError(
            f"Archivo de esquema no encontrado en el compilado: no existe en '{cand_host}' ni en la raíz '{cand_root}'."
        )

    # Modo interpretado: si no existe físicamente, falla de inmediato (cero asunciones)
    raise FileNotFoundError(
        f"Archivo de esquema no existe físicamente en el camino indicado por el anfitrión: '{physical_path}'."
    )


def create_app_context(
    action: str = "consume",
    config_file: Optional[str] = None,
    key_file: Optional[str] = None,
    schema_file: Optional[str] = None,
    base_dir: Optional[str] = None,
    app_title: str = "ASISCFG",
    admin_pass_hash: Optional[str] = None,
    key_bytes: Optional[bytes] = None,
    format_mode: str = "plain",
    active_profile: Optional[str] = None,
    is_standalone: bool = False,
    dev_mode: bool = False,
    metadata: Optional[Dict[str, Any]] = None,
    default_config: Optional[Dict[str, Any]] = None,
    validation_rules: Optional[Dict[str, Any]] = None,
) -> AppConfigContext:
    """
    Resuelve y normaliza el contexto de ejecución canónico según la acción solicitada.
    """
    norm_action = str(action).strip().lower() if action else "consume"
    if norm_action not in VALID_ACTIONS:
        raise ValueError(f"Acción '{action}' inválida. Debe ser una de: {', '.join(VALID_ACTIONS)}")

    engine = get_format_engine(format_mode)
    resolved_base = os.path.abspath(base_dir) if (base_dir and base_dir.strip()) else BASE_DIR
    resolved_config = resolve_file_path(config_file, DEFAULT_CONFIG_FILENAME, resolved_base)
    resolved_key = resolve_file_path(key_file, DEFAULT_KEY_FILENAME, resolved_base)
    if norm_action in ("generate_key", "export_schema"):
        resolved_schema = resolve_file_path(schema_file, DEFAULT_SCHEMA_FILENAME, resolved_base) if schema_file else ""
    else:
        resolved_schema = resolve_schema_path(
            schema_file, DEFAULT_SCHEMA_FILENAME, resolved_base, is_standalone=is_standalone
        )
    ctx = AppConfigContext(
        config_file_path=resolved_config,
        config_file_name=os.path.basename(resolved_config),
        key_file_path=resolved_key,
        key_file_name=os.path.basename(resolved_key),
        schema_file_path=resolved_schema,
        schema_file_name=os.path.basename(resolved_schema),
        base_dir=resolved_base,
        action=norm_action,
        app_title=app_title,
        is_standalone=is_standalone,
        dev_mode=dev_mode,
        key_bytes=key_bytes,
        format_mode=engine.mode_id,
        active_profile=active_profile,
        metadata=dict(metadata) if metadata else {},
    )
    if norm_action in ["generate_key", "export_schema"]:
        return ctx

    # Verificación y resolución de clave criptográfica
    key_status = "ok"
    key_detail = ""
    if ctx.key_bytes is None:
        if not os.path.exists(resolved_key):
            key_status = "missing"
            key_detail = f"El archivo Llave no existe en la ruta: {resolved_key}"
        elif os.path.getsize(resolved_key) == 0:
            key_status = "empty"
            key_detail = f"El archivo Llave está vacío (0 bytes): {resolved_key}"
        else:
            try:
                with open(resolved_key, "rb") as f:
                    ctx.key_bytes = f.read().strip()
            except Exception as e:
                key_status = "corrupted"
                key_detail = f"Error al leer el archivo Llave: {e}"

    ctx.key_status = key_status
    ctx.key_detail = key_detail

    # Carga de metadatos de esquema (obligatorio, fail-fast definitivo)
    if not resolved_schema or not os.path.exists(resolved_schema):
        raise FileNotFoundError(
            f"El archivo de esquema es obligatorio y no fue encontrado en: '{resolved_schema or schema_file or DEFAULT_SCHEMA_FILENAME}'"
        )

    schema_info = load_schema_definition(resolved_schema)
    ctx.default_config = schema_info["default_config"]
    ctx.validation_rules = schema_info["validation_rules"]
    ctx.profile_template = schema_info["profile_template"]
    ctx.password_fields = schema_info["password_fields"]
    ctx.public_fields = schema_info["public_fields"]
    ctx.security_level = schema_info["security_level"]
    ctx.backup_settings = schema_info["backup_settings"]

    if default_config is not None:
        ctx.default_config = default_config
    if validation_rules is not None:
        ctx.validation_rules = validation_rules

    # Asignación de admin_pass_hash
    resolved_admin_hash = admin_pass_hash
    if not resolved_admin_hash:
        resolved_admin_hash = ctx.default_config.get(SECTION_ASISCFG, {}).get("admin_pass_hash")

    ctx.admin_pass_hash = resolved_admin_hash
    return ctx

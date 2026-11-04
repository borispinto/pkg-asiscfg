# -*- coding: utf-8 -*-
# SPDX-FileCopyrightText: 2026 ASISNET Computación, CA <proyectos@asisnet.net>
# SPDX-FileCopyrightText: 2026 Boris Pinto <borispinto@gmail.com>
# SPDX-License-Identifier: MIT
# Autor: Boris Pinto <borispinto@gmail.com>
# Contacto Institucional: ASISNET Computación, CA <proyectos@asisnet.net>
# File: asiscfg/storage.py

"""
Módulo de almacenamiento, persistencia en disco y seguridad criptográfica (Nivel 3).
Implementa ciclo único de carga con validación acumulativa de errores,
punto único de comodines (_handle_wildcard), sellado forense y sistema de respaldos.
"""

import copy
import hmac
import json
import logging
import os
import shutil
import sys
from datetime import datetime
from typing import Any, Dict, List, Optional, Set, Tuple

from asiscfg.constants import (
    ENC_PREFIX,
    NO_MODIFY_KEY,
    NULL_SENTINEL,
    PUBLIC_PREFIX,
    SECTION_ASISCFG,
    SECTION_PROFILES,
    is_business_section,
    is_schema_directive,
    is_security_section,
    is_special_section,
    has_wildcard,
    resolve_wildcards,
)
from asiscfg.context import AppConfigContext, resolve_dir_path
from asiscfg.crypto import (
    BaseFormatEngine,
    FORMAT_MODES,
    detect_format_engine,
    get_format_engine,
)
from asiscfg.models import ConfigDict
from asiscfg.schema import (
    DEFAULT_BACKUP_SETTINGS,
    build_schema_index,
    load_schema_definition,
    validate_and_correct_config,
    _apply_field_rule,
)
from asiscfg.security import is_admin, log_audit_event, set_admin_password


# ==============================================================================
# GESTIÓN DE CLAVES CRIPTOGRÁFICAS (NIVEL 2)
# ==============================================================================


def get_key(context: AppConfigContext, forzar: bool = False) -> bytes:
    """
    Obtiene la clave criptográfica en bytes desde el contexto en memoria o leyendo de disco.
    Lanza FileNotFoundError si el archivo no existe físicamente.
    """
    target_path = context.key_file_path if context else ""

    if not forzar and context and context.key_bytes:
        return context.key_bytes

    if not target_path or not os.path.exists(target_path):
        raise FileNotFoundError(f"Error al leer el archivo de clave: ruta inexistente '{target_path}'")

    try:
        with open(target_path, "rb") as f:
            key_bytes = f.read().strip()
    except Exception as e:
        raise FileNotFoundError(f"Error al leer el archivo de clave {target_path}: {e}") from e

    if context:
        context.key_bytes = key_bytes
    return key_bytes


def verify_key_integrity(context: AppConfigContext) -> Tuple[str, str]:
    """
    Verifica de forma estricta la existencia y validez del archivo de clave (.key).
    Retorna tupla (status, detail):
      - status: "ok", "missing", o "corrupted"
      - detail: mensaje descriptivo.
    """
    abs_config = context.config_file_path
    abs_key = context.key_file_path

    if not os.path.exists(abs_key):
        return "missing", f"El archivo de clave no existe en la ruta: {abs_key}"

    try:
        with open(abs_key, "rb") as f:
            key_bytes = f.read().strip()
    except Exception as e:
        return "corrupted", f"No se pudo leer el archivo de clave: {e}"

    if not key_bytes:
        return "corrupted", "El archivo de clave está vacío (0 bytes)."

    if os.path.exists(abs_config):
        try:
            with open(abs_config, "rb") as f:
                raw_config = f.read().strip()
        except Exception as e:
            return "corrupted", f"No se pudo leer el archivo de configuración: {e}"

        try:
            detected_format, engine = detect_format_engine(raw_config)
        except Exception as e:
            return "corrupted", f"El archivo de configuración no contiene una cabecera de formato válida: {e}"

        if not engine.validate_key(key_bytes):
            return "corrupted", f"La clave no posee un formato válido para el motor '{engine.name}'."

        lines = raw_config.splitlines()
        data_lines = []
        header_found = False
        for l in lines:
            line_str = l.decode("utf-8", errors="ignore").strip()
            if not header_found:
                if line_str == engine.header:
                    header_found = True
                continue
            if line_str.startswith("#"):
                continue
            data_lines.append(l)

        payload_bytes = b"\n".join(data_lines).strip()

        if engine.is_full_encrypted:
            try:
                decrypted = engine.decrypt_payload(payload_bytes, key_bytes)
                json.loads(decrypted.decode("utf-8"))
            except Exception:
                return (
                    "corrupted",
                    "La clave está alterada o no coincide con los datos cifrados del archivo de configuración.",
                )
        else:
            try:
                data = json.loads(payload_bytes.decode("utf-8"))
                enc_tokens = []

                def _collect(node):
                    if isinstance(node, dict):
                        for v in node.values():
                            _collect(v)
                    elif isinstance(node, list):
                        for item in node:
                            _collect(item)
                    elif isinstance(node, str) and node.startswith(ENC_PREFIX):
                        enc_tokens.append(node)

                _collect(data)
                for token in enc_tokens:
                    try:
                        dec_val = engine.decrypt_field(token, key_bytes)
                        if dec_val.startswith(ENC_PREFIX):
                            return (
                                "corrupted",
                                "La clave está alterada o no coincide con los campos protegidos cifrados.",
                            )
                    except Exception:
                        return (
                            "corrupted",
                            "La clave está alterada o no coincide con los campos protegidos cifrados.",
                        )
            except Exception:
                return "corrupted", "El archivo de configuración contiene un JSON inválido."
    else:
        target_mode = getattr(context, "format_mode", "plain") or "plain"
        engine = FORMAT_MODES.get(target_mode) or get_format_engine(target_mode)
        if not engine.validate_key(key_bytes):
            return "corrupted", f"El formato de clave no es válido para el modo '{target_mode}'."

    return "ok", ""


def generate_key_file(context: AppConfigContext, overwrite: bool = False) -> bytes:
    """
    Genera de forma explícita un nuevo archivo de clave delegando en el motor de formato.
    Lanza FileExistsError si el archivo ya existe y overwrite es False.
    """
    key_path = context.key_file_path

    if os.path.exists(key_path) and not overwrite:
        raise FileExistsError(f"El archivo de clave ya existe: {key_path}")

    mode = getattr(context, "format_mode", None) or "plain"
    engine = FORMAT_MODES.get(mode) or get_format_engine(mode)
    key = engine.generate_key()

    parent_dir = os.path.dirname(os.path.abspath(key_path))
    if parent_dir:
        os.makedirs(parent_dir, exist_ok=True)

    with open(key_path, "wb") as f:
        f.write(key)

    if context:
        context.key_bytes = key
    return key


# ==============================================================================
# LECTURA FÍSICA Y VERIFICACIÓN FORENSE (NIVEL 3)
# ==============================================================================


def _get_nested_dict_value(data: Any, key_path: str) -> Any:
    """Navega una estructura de diccionarios anidados según una ruta por puntos ('seccion.campo')."""
    if not isinstance(data, dict) or not key_path:
        return None
    val = data
    for part in key_path.split("."):
        if isinstance(val, dict) and part in val:
            val = val[part]
        else:
            return None
    return val


def _collect_public_comments(data: Dict[str, Any], public_fields: List[str]) -> List[str]:
    """Recolecta comentarios informativos `# <key_path>: <valor>` para campos marcados como públicos."""
    comments: List[str] = []
    if not isinstance(data, dict) or not public_fields:
        return comments

    for field_path in public_fields:
        if field_path.startswith(f"{SECTION_PROFILES}."):
            sub_path = field_path[len(f"{SECTION_PROFILES}.") :]
            profiles = data.get(SECTION_PROFILES, {})
            if isinstance(profiles, dict):
                for p_code in sorted(profiles.keys()):
                    if is_schema_directive(p_code):
                        continue
                    val = _get_nested_dict_value(profiles[p_code], sub_path)
                    if val is not None and not str(val).startswith(ENC_PREFIX):
                        comments.append(f"{PUBLIC_PREFIX}{SECTION_PROFILES}.{p_code}.{sub_path}: {val}")
        else:
            val = _get_nested_dict_value(data, field_path)
            if val is not None and not str(val).startswith(ENC_PREFIX):
                comments.append(f"{PUBLIC_PREFIX}{field_path}: {val}")

    return comments


def _compare_plain_snapshots(
    original: Dict[str, Any],
    current: Dict[str, Any],
    pwd_set: set,
    engine: Any,
    key: Any,
    prefix: str = "",
) -> List[Dict[str, Any]]:
    """Compara recursivamente el snapshot forense contra los datos actuales normalizando campos protegidos."""
    diffs = []
    all_keys = set(original.keys()) | set(current.keys())

    for k in sorted(all_keys):
        if k == NO_MODIFY_KEY:
            continue
        key_path = f"{prefix}.{k}" if prefix else k

        parts = key_path.split(".")
        if len(parts) >= 3 and parts[0] == SECTION_PROFILES:
            rule_path = f"{SECTION_PROFILES}.{'.'.join(parts[2:])}"
        else:
            rule_path = key_path

        is_pwd = (rule_path in pwd_set) or (key_path in pwd_set) or (k == "password")

        v_orig = original.get(k)
        v_curr = current.get(k)

        if isinstance(v_orig, dict) and isinstance(v_curr, dict):
            diffs.extend(_compare_plain_snapshots(v_orig, v_curr, pwd_set, engine, key, prefix=key_path))
            continue

        if is_pwd:
            def _normalize_pwd(v):
                if v is None or v == "" or v == NULL_SENTINEL:
                    return ""
                if isinstance(v, str) and v.startswith(ENC_PREFIX):
                    try:
                        dec = engine.decrypt_field(v, key) if (engine and key) else v
                        return "" if (dec == NULL_SENTINEL or dec is None) else str(dec)
                    except Exception:
                        return v
                return str(v)

            norm_orig = _normalize_pwd(v_orig)
            norm_curr = _normalize_pwd(v_curr)

            if not hmac.compare_digest(norm_orig, norm_curr):
                old_desc = "[Vacío]" if not norm_orig else "[Protegido]"
                new_desc = "[Vacío]" if not norm_curr else "[Modificado]"
                diffs.append({
                    "status": "tampered",
                    "key_path": key_path,
                    "is_password": True,
                    "old_value": old_desc,
                    "new_value": new_desc
                })
        else:
            if v_orig != v_curr:
                diffs.append({
                    "status": "tampered",
                    "key_path": key_path,
                    "is_password": False,
                    "old_value": str(v_orig if v_orig is not None else ""),
                    "new_value": str(v_curr if v_curr is not None else "")
                })

    return diffs


def read_and_verify_config(
    context: AppConfigContext,
    edit_mode: bool = False,
) -> Tuple[Dict[str, Any], BaseFormatEngine, bytes, str, List[Any]]:
    """
    Función canónica única para lectura física, descifrado y verificación de integridad de configuración.
    Valida cabeceras, descifra payload con la clave activa y verifica sellado forense.
    Retorna tupla: (data, engine, key_bytes, detected_format, audit_diffs).
    """
    if not isinstance(context, AppConfigContext):
        raise TypeError(f"El parámetro 'context' debe ser AppConfigContext, recibido: {type(context).__name__}")

    abs_config = context.config_file_path
    if not abs_config or not os.path.exists(abs_config):
        raise FileNotFoundError(f"El archivo de configuración no existe: {abs_config}")

    key = get_key(context)
    with open(abs_config, "rb") as f:
        raw_bytes = f.read()

    try:
        detected_format, engine = detect_format_engine(raw_bytes)
    except ValueError as e:
        raise ValueError(f"El archivo no contiene una cabecera de formato válida: {abs_config}") from e

    lines = raw_bytes.strip().splitlines()
    data_lines = []
    header_found = False
    for l in lines:
        line_str = l.decode("utf-8", errors="ignore").strip()
        if not header_found:
            if line_str == engine.header:
                header_found = True
            continue
        if line_str.startswith("#"):
            continue
        data_lines.append(l)

    payload_bytes = b"\n".join(data_lines).strip()
    try:
        decrypted_bytes = engine.decrypt_payload(payload_bytes, key)
        data = json.loads(decrypted_bytes.decode("utf-8"))
    except Exception as e:
        raise ValueError(f"Falla al descifrar o decodificar el contenido de configuración en '{abs_config}': {e}") from e

    if not isinstance(data, dict):
        raise ValueError(f"El contenido de configuración en '{abs_config}' no es un diccionario válido.")

    audit_diffs: List[Any] = []
    sec_level = getattr(context, "security_level", 0)
    has_seal = isinstance(data, dict) and (NO_MODIFY_KEY in data)

    if detected_format == "plain":
        if sec_level == 1:
            sealed_token = data.get(NO_MODIFY_KEY) if isinstance(data, dict) else None
            if not sealed_token or not isinstance(sealed_token, str):
                msg = f"Inconsistencia de seguridad: security_level=1 pero falta la clave de sellado '{NO_MODIFY_KEY}' en el archivo."
                log_audit_event("SECURITY_LEVEL_MISMATCH", f"{msg} ({abs_config})")
                if not edit_mode:
                    logging.error(f"[SECURITY] {msg} ({abs_config})")
                    raise ValueError(msg)
                else:
                    logging.warning(f"[SECURITY] {msg} ({abs_config})")
                    audit_diffs.append({"status": "missing_seal", "key_path": NO_MODIFY_KEY, "error": msg})
            else:
                try:
                    plain_fernet_engine = FORMAT_MODES["fernet"]
                    dec_snapshot = plain_fernet_engine.decrypt_payload(sealed_token.encode("utf-8"), key)
                    snapshot_data = json.loads(dec_snapshot.decode("utf-8"))
                    current_data_clean = {k: v for k, v in data.items() if k != NO_MODIFY_KEY}
                    tamper_diffs = _compare_plain_snapshots(
                        snapshot_data,
                        current_data_clean,
                        pwd_set=set(getattr(context, "password_fields", [])),
                        engine=plain_fernet_engine,
                        key=key,
                    )
                    if tamper_diffs:
                        log_audit_event("AUDIT-TAMPER", f"Diferencias detectadas contra el snapshot firmado en {abs_config}")
                        audit_diffs.extend(tamper_diffs)
                except Exception as e:
                    msg = f"Inconsistencia de seguridad: Falla al descifrar snapshot forense en '{abs_config}': {e}"
                    log_audit_event("SECURITY_LEVEL_MISMATCH", msg)
                    if not edit_mode:
                        logging.error(f"[SECURITY] {msg}")
                        raise ValueError(msg)
                    else:
                        logging.warning(f"[SECURITY] {msg}")
                        audit_diffs.append({"status": "corrupt_token", "key_path": NO_MODIFY_KEY, "error": str(e)})
        else:
            if has_seal:
                msg = f"Inconsistencia de seguridad: security_level=0 pero existe la clave de sellado '{NO_MODIFY_KEY}' en el archivo."
                log_audit_event("SECURITY_LEVEL_MISMATCH", f"{msg} ({abs_config})")
                if not edit_mode:
                    logging.error(f"[SECURITY] {msg} ({abs_config})")
                    raise ValueError(msg)
                else:
                    logging.warning(f"[SECURITY] {msg} ({abs_config})")
                    audit_diffs.append({"status": "unexpected_seal", "key_path": NO_MODIFY_KEY, "error": msg})
    else:
        if has_seal:
            msg = f"Inconsistencia de seguridad: Formato '{detected_format}' no admite clave de sellado '{NO_MODIFY_KEY}' en el archivo."
            log_audit_event("SECURITY_LEVEL_MISMATCH", f"{msg} ({abs_config})")
            if not edit_mode:
                logging.error(f"[SECURITY] {msg} ({abs_config})")
                raise ValueError(msg)
            else:
                logging.warning(f"[SECURITY] {msg} ({abs_config})")
                audit_diffs.append({"status": "unexpected_seal", "key_path": NO_MODIFY_KEY, "error": msg})

    context.format_mode = detected_format
    return data, engine, key, detected_format, audit_diffs


# ==============================================================================
# PUNTO ÚNICO DE COMODINES SINTÁCTICOS
# ==============================================================================


def _handle_wildcard(
    val: Any,
    full_path: str,
    edit_mode: bool,
    errors: List[Dict[str, Any]],
) -> Tuple[Any, bool]:
    """
    Punto ÚNICO y centralizado para detección y resolución de comodines sintácticos ({ENV:...}).
    Retorna tupla: (valor_procesado, tenia_comodin)
    """
    if not has_wildcard(val):
        return val, False

    if edit_mode:
        return val, True

    try:
        resolved = resolve_wildcards(val, fail_on_missing=True)
        return (NULL_SENTINEL if resolved == "" else resolved), True
    except ValueError as ve:
        errors.append({
            "field_path": full_path,
            "reason": "env_missing",
            "description": str(ve),
            "value": val,
        })
        return val, True


# ==============================================================================
# CICLO ÚNICO DE CARGA Y VALIDACIÓN ACUMULATIVA (NIVEL 3)
# ==============================================================================


def load_config(context: AppConfigContext, edit_mode: Optional[bool] = None) -> ConfigDict:
    """
    Carga, descifra y valida la configuración aplicando reglas de esquema desde AppConfigContext.
    Autodetecta el formato dinámicamente usando detect_format_engine (Strategy).
    Implementa un único recorrido recursivo con validación acumulativa de errores.
    """
    if edit_mode is None:
        edit_mode = bool(getattr(context, "action", "") == "ui")

    abs_config = context.config_file_path
    def_cfg = context.default_config if context else {}
    val_rules = context.validation_rules if context else {}

    if not os.path.exists(abs_config):
        if not edit_mode:
            raise FileNotFoundError(f"El archivo de configuración no existe: {abs_config}")
        save_config(context, def_cfg)
        res = ConfigDict(context, def_cfg, default_config=def_cfg, validation_rules=val_rules)
        res.set_default_config(def_cfg)
        return res

    data, engine, key, detected_format, audit_diffs = read_and_verify_config(context, edit_mode=edit_mode)
    context.format_mode = detected_format

    # Construir índice plano del esquema para lookup O(1)
    schema_index = build_schema_index(val_rules)

    # Listas para acumulación de errores e inconsistencias
    errors: List[Dict[str, Any]] = []
    unencrypted_passwords: List[Tuple[str, Any]] = []

    # 1. Comprobación de perfiles requeridos
    schema_expects_profiles = bool(
        (isinstance(val_rules, dict) and SECTION_PROFILES in val_rules)
        or (isinstance(def_cfg, dict) and SECTION_PROFILES in def_cfg)
    )
    physical_profiles = (
        [p for p in data.get(SECTION_PROFILES, {}).keys() if not is_schema_directive(p)]
        if isinstance(data, dict) and isinstance(data.get(SECTION_PROFILES), dict)
        else []
    )
    if schema_expects_profiles and len(physical_profiles) == 0:
        err_item = {
            "field_path": SECTION_PROFILES,
            "reason": "profiles_missing",
            "description": f"El archivo '{abs_config}' no contiene perfiles registrados bajo '{SECTION_PROFILES}'.",
            "value": None,
        }
        errors.append(err_item)
        if edit_mode:
            logging.warning(f"[CONFIG] Advertencia: {err_item['description']}")
        else:
            logging.error(f"[CONFIG] Error: {err_item['description']}")
            log_audit_event("PROFILES_MISSING", err_item["description"])

    # 2. Comprobación temprana de campos protegidos faltantes (no presentes físicamente en data)
    expected_pwd_fields: List[Tuple[str, str, str]] = []  # (full_path, sec, fk)
    # Globales
    for sec_k, sec_v in val_rules.items():
        if is_schema_directive(sec_k) or is_special_section(sec_k) or sec_k == SECTION_PROFILES:
            continue
        if isinstance(sec_v, dict):
            for fk, fdef in sec_v.items():
                if isinstance(fdef, dict) and fdef.get("is_password") is True:
                    expected_pwd_fields.append((f"{sec_k}.{fk}", sec_k, fk))
    # Por cada perfil físico
    prof_template = val_rules.get(SECTION_PROFILES, {}).get("_template", {}) if isinstance(val_rules.get(SECTION_PROFILES), dict) else {}
    for p_code in sorted(physical_profiles):
        if isinstance(prof_template, dict):
            for p_sec, p_fields in prof_template.items():
                if isinstance(p_fields, dict):
                    for fk, fdef in p_fields.items():
                        if isinstance(fdef, dict) and fdef.get("is_password") is True:
                            expected_pwd_fields.append((f"{SECTION_PROFILES}.{p_code}.{p_sec}.{fk}", p_sec, fk))

    missing_paths: Set[str] = set()
    for full_path, sec, fk in expected_pwd_fields:
        parts = full_path.split(".")
        node = data
        missing = False
        for p in parts:
            if isinstance(node, dict) and p in node:
                node = node[p]
            else:
                missing = True
                break
        if missing:
            missing_paths.add(full_path)
            fail_desc = f"El campo requerido '{full_path}' no existe en el archivo."
            err_dict = {
                "field_path": full_path,
                "reason": "missing",
                "description": fail_desc,
                "value": None,
            }
            errors.append(err_dict)
            unencrypted_passwords.append((full_path, None))
            if edit_mode:
                logging.warning(f"[CONFIG] Advertencia en campo protegido '{full_path}': {fail_desc}")
            else:
                logging.error(f"[CONFIG] Error en campo protegido '{full_path}': {fail_desc}")

    # 3. Preparación de estructura base (dic_valores) guiada por el esquema
    dic_valores = copy.deepcopy(def_cfg) if def_cfg else {}
    if SECTION_PROFILES in dic_valores:
        dic_valores[SECTION_PROFILES] = {}

    # Si hay perfiles en data, inicializar cada uno con la plantilla por defecto
    if isinstance(data, dict) and SECTION_PROFILES in data and isinstance(data[SECTION_PROFILES], dict):
        for p_code in physical_profiles:
            p_entry = {}
            if isinstance(prof_template, dict):
                for p_sec, p_fields in prof_template.items():
                    if isinstance(p_fields, dict):
                        p_entry[p_sec] = {
                            k: (v.get("default") if isinstance(v, dict) else v)
                            for k, v in p_fields.items()
                            if not (isinstance(v, dict) and v.get("type") == "test_connection")
                        }
            dic_valores[SECTION_PROFILES][p_code] = p_entry

    # 4. Fusión de data cruda sobre la estructura base
    has_business = any(is_business_section(k) for k in val_rules.keys()) if val_rules else False
    if isinstance(data, dict):
        for sec, subdict in data.items():
            if sec == SECTION_PROFILES:
                if isinstance(subdict, dict):
                    for p_code, p_data in subdict.items():
                        if is_schema_directive(p_code) or not isinstance(p_data, dict):
                            continue
                        if p_code not in dic_valores[SECTION_PROFILES]:
                            dic_valores[SECTION_PROFILES][p_code] = {}
                        for p_sec, p_fields in p_data.items():
                            if prof_template and p_sec not in prof_template:
                                logging.warning(f"[CONFIG] Subsección '{p_sec}' en perfil '{p_code}' omitida (no existe en el esquema)")
                                continue
                            if not isinstance(p_fields, dict):
                                continue
                            if p_sec not in dic_valores[SECTION_PROFILES][p_code]:
                                dic_valores[SECTION_PROFILES][p_code][p_sec] = {}
                            sec_prules = prof_template.get(p_sec, {}) if prof_template else None
                            for fk, fv in p_fields.items():
                                if sec_prules is not None and fk not in sec_prules:
                                    logging.warning(f"[CONFIG] Clave1 '{p_sec}.{fk}' en perfil '{p_code}' omitida (no existe en el esquema)")
                                    continue
                                if sec_prules is not None and isinstance(sec_prules.get(fk), dict) and sec_prules[fk].get("type") == "test_connection":
                                    continue
                                dic_valores[SECTION_PROFILES][p_code][p_sec][fk] = fv
            elif has_business and sec not in def_cfg and not is_special_section(sec):
                logging.warning(f"[CONFIG] Sección raíz '{sec}' omitida (no existe en el esquema)")
            elif isinstance(subdict, dict):
                if sec not in dic_valores or not isinstance(dic_valores[sec], dict):
                    dic_valores[sec] = {}
                is_special = is_special_section(sec)
                sec_schema = def_cfg.get(sec, {}) if def_cfg else {}
                for fk, fv in subdict.items():
                    if has_business and not is_special and isinstance(sec_schema, dict) and fk not in sec_schema:
                        logging.warning(f"[CONFIG] Clave2 '{sec}.{fk}' omitida (no existe en el esquema)")
                    else:
                        dic_valores[sec][fk] = fv
            else:
                dic_valores[sec] = subdict

    # 5. ÚNICO RECORRIDO RECURSIVO: resolve_dic / resolve_valor
    def resolve_valor(full_path: str, val: Any) -> Any:
        if full_path in missing_paths:
            return val

        if full_path.startswith(f"{SECTION_PROFILES}."):
            parts = full_path.split(".")
            if len(parts) >= 4:
                canonical_path = f"{SECTION_PROFILES}.{'.'.join(parts[2:])}"
            else:
                canonical_path = full_path
        else:
            canonical_path = full_path

        info = schema_index.get(canonical_path)
        is_pwd = (
            (isinstance(info, dict) and info.get("is_password") is True)
            or (bool(context and canonical_path in context.password_fields))
            or (canonical_path.endswith(".password") and not info)
        )

        if is_pwd:
            # 1. Comodines sintácticos evaluados mediante el punto único _handle_wildcard
            val, is_wc = _handle_wildcard(val, full_path, edit_mode, errors)
            if is_wc:
                if edit_mode:
                    unencrypted_passwords.append((full_path, val))
                    return val
                return engine.encrypt_field(val, key) if (engine and key) else val

            # 2. Formato selectivo / PLAIN
            if not engine.is_full_encrypted:
                if val is None or val == "":
                    err_entry = {
                        "field_path": full_path,
                        "reason": "empty",
                        "description": f"El campo '{full_path}' está vacío en disco sin token canónico.",
                        "value": val,
                    }
                    errors.append(err_entry)
                    unencrypted_passwords.append((full_path, val))
                    return val
                if not isinstance(val, str) or not val.startswith(ENC_PREFIX):
                    err_entry = {
                        "field_path": full_path,
                        "reason": "unencrypted",
                        "description": f"El campo '{full_path}' no está cifrado (falta prefijo '{ENC_PREFIX}').",
                        "value": val,
                    }
                    errors.append(err_entry)
                    unencrypted_passwords.append((full_path, val))
                    return val
                token_body = val[len(ENC_PREFIX):].strip()
                if not token_body:
                    err_entry = {
                        "field_path": full_path,
                        "reason": "empty",
                        "description": f"El campo '{full_path}' contiene el prefijo '{ENC_PREFIX}' pero sin cuerpo.",
                        "value": val,
                    }
                    errors.append(err_entry)
                    unencrypted_passwords.append((full_path, val))
                    return val
                try:
                    dec = engine.decrypt_field(val, key)
                    if dec == NULL_SENTINEL or dec == "":
                        return NULL_SENTINEL
                    dec, dec_wc = _handle_wildcard(dec, full_path, edit_mode, errors)
                    if dec_wc:
                        if edit_mode:
                            unencrypted_passwords.append((full_path, dec))
                            return dec
                        return engine.encrypt_field(dec, key) if (engine and key) else dec
                    return val
                except Exception as e:
                    err_entry = {
                        "field_path": full_path,
                        "reason": "decrypt_error",
                        "description": f"Error al desencriptar campo '{full_path}': {e}",
                        "value": val,
                    }
                    errors.append(err_entry)
                    unencrypted_passwords.append((full_path, val))
                    return val

            # 3. Formato totalmente cifrado (Fernet, AES-GCM, ChaCha20)
            if val == NULL_SENTINEL:
                return NULL_SENTINEL
            if val is None or val == "":
                err_entry = {
                    "field_path": full_path,
                    "reason": "empty",
                    "description": f"Existe pero no tiene valor (nulo): '{full_path}'.",
                    "value": val,
                }
                errors.append(err_entry)
                return NULL_SENTINEL
            if isinstance(val, str) and val.startswith(ENC_PREFIX):
                token_body = val[len(ENC_PREFIX):].strip()
                if not token_body:
                    err_entry = {
                        "field_path": full_path,
                        "reason": "empty",
                        "description": f"El campo '{full_path}' contiene el prefijo '{ENC_PREFIX}' pero sin cuerpo.",
                        "value": val,
                    }
                    errors.append(err_entry)
                    return val
                try:
                    dec = engine.decrypt_field(val, key)
                    if dec == NULL_SENTINEL or dec == "":
                        return NULL_SENTINEL
                    dec, dec_wc = _handle_wildcard(dec, full_path, edit_mode, errors)
                    if dec_wc:
                        if edit_mode:
                            unencrypted_passwords.append((full_path, dec))
                            return dec
                        return engine.encrypt_field(dec, key) if (engine and key) else dec
                    return val
                except Exception as e:
                    err_entry = {
                        "field_path": full_path,
                        "reason": "decrypt_error",
                        "description": f"Error al desencriptar campo '{full_path}': {e}",
                        "value": val,
                    }
                    errors.append(err_entry)
                    return val
            else:
                return engine.encrypt_field(str(val), key) if (engine and key) else val

        # Campo no contraseña:
        # Desencriptar si viene cifrado (ej. secciones de seguridad como 'app')
        if isinstance(val, str) and val.startswith(ENC_PREFIX) and engine and key:
            try:
                dec = engine.decrypt_field(val, key)
                val = "" if dec == NULL_SENTINEL else dec
            except Exception:
                pass

        val, _ = _handle_wildcard(val, full_path, edit_mode, errors)

        if isinstance(info, dict):
            parts = full_path.split(".")
            sec = parts[0] if parts else ""
            fk = parts[-1] if parts else ""
            val = _apply_field_rule(sec, fk, val, info)

        return val

    def resolve_dic(node: Any, current_path: str = "") -> Any:
        if isinstance(node, dict):
            for k in list(node.keys()):
                if k == NO_MODIFY_KEY or is_schema_directive(k):
                    continue
                sub_path = f"{current_path}.{k}" if current_path else k
                v = node[k]
                if isinstance(v, dict):
                    node[k] = resolve_dic(v, current_path=sub_path)
                else:
                    node[k] = resolve_valor(sub_path, v)
            return node
        elif isinstance(node, list):
            for i, v in enumerate(node):
                if isinstance(v, (dict, list)):
                    node[i] = resolve_dic(v, current_path=current_path)
                else:
                    item_path = f"{current_path}[{i}]"
                    node[i], _ = _handle_wildcard(v, item_path, edit_mode, errors)
            return node
        return node

    raw_dic_valores = resolve_dic(dic_valores)

    # 6. Evaluación de errores acumulados
    if errors:
        if not edit_mode:
            for fail in errors:
                logging.error(f"[CONFIG] Error en campo protegido '{fail['field_path']}': {fail['description']}")
            log_audit_event("PASSWORD_INTEGRITY_FAILED", f"Fallas detectadas: {', '.join([f['field_path'] for f in errors])}")
            details = "\n".join([f"- {f['field_path']}: {f['description']}" for f in errors])
            raise ValueError(f"Falla de integridad en campos de contraseña de configuración:\n{details}")
        else:
            for fail in errors:
                logging.warning(f"[CONFIG] Advertencia en campo protegido '{fail['field_path']}': {fail['description']}")

    # 7. Construcción de ConfigDict resultante
    res = ConfigDict(
        context,
        raw_dic_valores,
        default_config=def_cfg,
        validation_rules=val_rules,
        unencrypted_passwords=unencrypted_passwords,
        password_failures=errors,
        audit_diffs=audit_diffs,
    )
    res.set_default_config(def_cfg)

    # 8. Limpieza radical de memoria en modo consume
    if not edit_mode:
        res.pop(NO_MODIFY_KEY, None)
        context.profile_template = {}
        context.validation_rules = {}
        context.backup_settings = {}
        context.public_fields = []
        res._validation_rules = {}
        res._unencrypted_passwords = []
        res._password_failures = []
        res._audit_diffs = []

    return res


# ==============================================================================
# PERSISTENCIA, RESPALDOS Y ACTUALIZACIONES QUIRÚRGICAS (NIVEL 3)
# ==============================================================================


def perform_backup(
    config_path: str,
    config_data: Optional[dict] = None,
    backup_settings: Optional[Dict[str, Any]] = None,
) -> Optional[str]:
    """Crea una copia de respaldo del archivo de configuración antes de sobrescribirlo."""
    if not os.path.exists(config_path):
        return None

    settings = dict(DEFAULT_BACKUP_SETTINGS)
    if isinstance(backup_settings, dict):
        settings.update(backup_settings)

    if not settings.get("enabled", True):
        return None

    method = str(settings.get("method", "timestamp")).strip().lower()
    if method == "none":
        return None

    raw_target = settings.get("target_dir", "{ROOT}/backups")
    if isinstance(raw_target, dict) and "schema_key" in raw_target:
        key_path = str(raw_target["schema_key"]).strip()
        val = _get_nested_dict_value(config_data or {}, key_path)
        target_candidate = val.strip() if (isinstance(val, str) and val.strip()) else "{ROOT}/backups"
    elif isinstance(raw_target, str) and raw_target.strip():
        target_candidate = raw_target.strip()
    else:
        target_candidate = "{ROOT}/backups"

    config_dir = os.path.dirname(os.path.abspath(config_path))
    target_dir = resolve_dir_path(target_candidate, base_dir=config_dir)

    try:
        os.makedirs(target_dir, exist_ok=True)
    except Exception as e:
        logging.warning(f"No se pudo crear el directorio de respaldo {target_dir}: {e}")
        return None

    basename_with_ext = os.path.basename(config_path)
    basename, ext = os.path.splitext(basename_with_ext)
    now = datetime.now()
    timestamp = now.strftime("%Y%m%d_%H%M%S")

    if method == "simple":
        backup_filename = f"{basename}{ext}.bak"
    else:
        raw_pattern = settings.get("filename_pattern", "{TIMESTAMP}-{BASENAME}{EXT}.bak")
        pattern = raw_pattern.strip() if isinstance(raw_pattern, str) and raw_pattern.strip() else "{TIMESTAMP}-{BASENAME}{EXT}.bak"
        backup_filename = (
            pattern.replace("{BASENAME}", basename)
            .replace("{EXT}", ext)
            .replace("{TIMESTAMP}", timestamp)
            .replace("{DATEYEAR}", now.strftime("%Y"))
            .replace("{DATEMONTH}", now.strftime("%m"))
            .replace("{DATEDAY}", now.strftime("%d"))
            .replace("{DATEHOUR}", now.strftime("%H"))
            .replace("{DATEMINUTE}", now.strftime("%M"))
            .replace("{DATESECOND}", now.strftime("%S"))
        )

    dest_path = os.path.join(target_dir, backup_filename)

    try:
        shutil.copy2(config_path, dest_path)
    except Exception as e:
        logging.warning(f"No se pudo crear copia de respaldo en {dest_path}: {e}")
        return None

    # Rotación histórica
    max_backups = int(settings.get("max_backups", 20))
    if method == "timestamp" and max_backups > 0:
        try:
            backups = sorted(
                [
                    os.path.join(target_dir, f)
                    for f in os.listdir(target_dir)
                    if f.endswith(".bak") and os.path.isfile(os.path.join(target_dir, f))
                ],
                key=os.path.getmtime,
            )
            while len(backups) > max_backups:
                oldest = backups.pop(0)
                try:
                    os.remove(oldest)
                except Exception:
                    pass
        except Exception:
            pass

    return backup_filename


def _process_password_fields(
    data: Dict[str, Any],
    key: Optional[Any],
    validation_rules: Optional[Dict[str, Any]] = None,
    encrypt: bool = True,
    edit_mode: bool = False,
    detected_unencrypted: Optional[List[Any]] = None,
    is_full_encrypted: bool = False,
    engine: Optional[BaseFormatEngine] = None,
) -> Dict[str, Any]:
    """Procesa selectivamente los campos protegidos para guardado (is_password: True)."""
    if not isinstance(data, dict):
        return data

    rules = validation_rules or {}

    def process_val(val: Any, is_pwd_field: bool, is_sec_protected: bool, field_path: str) -> Any:
        if encrypt:
            if is_pwd_field or is_sec_protected:
                if is_full_encrypted:
                    if val == "" or val is None or val == NULL_SENTINEL:
                        return NULL_SENTINEL
                    if isinstance(val, str) and val.startswith(ENC_PREFIX):
                        dec_str = engine.decrypt_field(val, key) if (engine and key) else val
                        return NULL_SENTINEL if dec_str == NULL_SENTINEL else dec_str
                    return val

                if isinstance(val, str) and val.startswith(ENC_PREFIX):
                    return val
                raw_to_enc = NULL_SENTINEL if (val == "" or val is None or val == NULL_SENTINEL) else str(val)
                return engine.encrypt_field(raw_to_enc, key) if (engine and key) else val
            return val
        return val

    def _process_node(container, fk, fv, rule, sec_prot, path):
        is_pwd = bool(isinstance(rule, dict) and rule.get("is_password") is True)
        container[fk] = process_val(fv, is_pwd, sec_prot, path)

    prof_rules = {}
    if rules and isinstance(rules.get(SECTION_PROFILES), dict) and "_template" in rules[SECTION_PROFILES]:
        prof_rules = rules[SECTION_PROFILES]["_template"]

    for sec_key, sec_val in data.items():
        if sec_key == SECTION_PROFILES and isinstance(sec_val, dict):
            for p_code, p_data in sec_val.items():
                if is_schema_directive(p_code) or not isinstance(p_data, dict):
                    continue
                for sub_sec, sub_fields in p_data.items():
                    if isinstance(sub_fields, dict):
                        sub_rules = prof_rules.get(sub_sec, rules.get(sub_sec, {}))
                        sec_prot = is_security_section(sub_sec)
                        for fk, fv in list(sub_fields.items()):
                            frule = sub_rules.get(fk, {}) if isinstance(sub_rules, dict) else {}
                            path = f"{sec_key}.{p_code}.{sub_sec}.{fk}"
                            _process_node(sub_fields, fk, fv, frule, sec_prot, path)
        elif isinstance(sec_val, dict):
            sec_rules = rules.get(sec_key, {})
            sec_prot = is_security_section(sec_key)
            for fk, fv in list(sec_val.items()):
                frule = sec_rules.get(fk, {}) if isinstance(sec_rules, dict) else {}
                path = f"{sec_key}.{fk}"
                _process_node(sec_val, fk, fv, frule, sec_prot, path)

    return data


def save_config(
    context: AppConfigContext,
    config_data: Optional[dict] = None,
    config_path: Optional[str] = None,
) -> Optional[str]:
    """
    Guarda la configuración validada en disco delegando en el motor FORMAT_MODES.
    Crea copia de respaldo automática y serializa comentarios # public.
    """
    if not isinstance(context, AppConfigContext):
        raise TypeError(f"El parámetro 'context' debe ser AppConfigContext, recibido: {type(context).__name__}")

    abs_config = config_path if config_path else context.config_file_path
    target_mode = context.format_mode or "plain"
    engine = FORMAT_MODES.get(target_mode) or get_format_engine(target_mode)
    context.format_mode = engine.mode_id

    def_cfg = context.default_config
    val_rules = context.validation_rules

    final_data = config_data if config_data is not None else (copy.deepcopy(def_cfg) if def_cfg else {})
    has_schema = bool(def_cfg or (val_rules and any(is_business_section(k) for k in val_rules.keys())))
    if has_schema:
        validated = validate_and_correct_config(
            final_data, validation_rules=val_rules, default_config=def_cfg, context=context
        )
        final_data = dict(validated)
    else:
        final_data = dict(final_data)

    if SECTION_PROFILES in final_data and isinstance(final_data[SECTION_PROFILES], dict):
        final_data[SECTION_PROFILES] = {
            code: val for code, val in final_data[SECTION_PROFILES].items() if not is_schema_directive(code)
        }

    for k in [k for k in final_data.keys() if is_schema_directive(k)]:
        del final_data[k]

    key = get_key(context)
    parent_dir = os.path.dirname(abs_config)
    if parent_dir:
        os.makedirs(parent_dir, exist_ok=True)

    backup_rules = (
        val_rules.get("_backup") if isinstance(val_rules, dict) and "_backup" in val_rules else context.backup_settings
    )
    backup_created = perform_backup(abs_config, final_data, backup_rules)

    dumps_data = copy.deepcopy(final_data)

    _process_password_fields(
        dumps_data,
        key,
        validation_rules=val_rules,
        encrypt=True,
        is_full_encrypted=engine.is_full_encrypted,
        engine=engine,
    )

    # Sellado forense en modo PLAIN con security_level = 1
    if engine.mode_id == "plain" and getattr(context, "security_level", 0) == 1:
        snapshot_clean = {k: v for k, v in dumps_data.items() if k != NO_MODIFY_KEY}
        snapshot_bytes = json.dumps(snapshot_clean, ensure_ascii=False, sort_keys=True).encode("utf-8")
        plain_fernet_engine = FORMAT_MODES["fernet"]
        sealed_token = plain_fernet_engine.encrypt_payload(snapshot_bytes, key).decode("utf-8")
        dumps_data[NO_MODIFY_KEY] = sealed_token
    else:
        dumps_data.pop(NO_MODIFY_KEY, None)

    public_comments = _collect_public_comments(final_data, getattr(context, "public_fields", []))

    json_bytes = json.dumps(dumps_data, indent=4, ensure_ascii=False).encode("utf-8")
    payload = engine.encrypt_payload(json_bytes, key)

    comment_bytes = b"".join(f"{c}\n".encode("utf-8") for c in public_comments)
    content = f"{engine.header}\n".encode("utf-8") + comment_bytes + payload + b"\n"

    # Escritura atómica vía archivo temporal
    temp_path = f"{abs_config}.tmp"
    with open(temp_path, "wb") as f:
        f.write(content)
    shutil.move(temp_path, abs_config)

    return backup_created


def save_values(
    context: AppConfigContext,
    updates: Dict[str, Any],
    config_instance: Optional[ConfigDict] = None,
) -> None:
    """
    Actualiza y persiste de forma quirúrgica claves específicas en disco sin reescribir todo el archivo.
    Garantiza concurrencia releyendo el archivo físico fresco, validando integridad, aplicando cifrado
    a contraseñas y actualizando el sellado forense y respaldos según corresponda.
    """
    if not isinstance(context, AppConfigContext):
        raise TypeError(f"El parámetro 'context' debe ser AppConfigContext, recibido: {type(context).__name__}")
    if not isinstance(updates, dict):
        raise TypeError(f"El parámetro 'updates' debe ser de tipo dict, recibido: {type(updates).__name__}")
    if not updates:
        raise ValueError("El diccionario 'updates' no puede estar vacío.")

    abs_config = context.config_file_path
    if not abs_config or not os.path.exists(abs_config):
        raise FileNotFoundError(f"El archivo de configuración no existe: {abs_config}")

    data, engine, key, detected_format, _ = read_and_verify_config(context, edit_mode=True)
    val_rules = context.validation_rules or {}

    prof_rules: Dict[str, Any] = {}
    if SECTION_PROFILES in val_rules and isinstance(val_rules[SECTION_PROFILES], dict):
        prof_rules = val_rules[SECTION_PROFILES].get("_template", {})

    schema_pwd_fields = set(getattr(context, "password_fields", []))

    for key_path, new_val in updates.items():
        if not isinstance(key_path, str) or not key_path.strip():
            raise ValueError(f"La ruta de clave '{key_path}' es inválida.")

        parts = key_path.strip().split(".")
        if parts[0] == SECTION_PROFILES:
            if len(parts) < 4:
                raise ValueError(f"Ruta de perfil incompleta: '{key_path}'. Formato: '@profiles.<codigo>.<sec>.<campo>'")
            p_code = parts[1]
            p_sec = parts[2]
            p_fk = parts[3]

            if SECTION_PROFILES not in data or not isinstance(data[SECTION_PROFILES], dict):
                data[SECTION_PROFILES] = {}
            if p_code not in data[SECTION_PROFILES] or not isinstance(data[SECTION_PROFILES][p_code], dict):
                data[SECTION_PROFILES][p_code] = {}
            if p_sec not in data[SECTION_PROFILES][p_code] or not isinstance(data[SECTION_PROFILES][p_code][p_sec], dict):
                data[SECTION_PROFILES][p_code][p_sec] = {}

            rule_path = f"{SECTION_PROFILES}.{p_sec}.{p_fk}"
            sec_r = prof_rules.get(p_sec, {}) if isinstance(prof_rules, dict) else {}
            frule = sec_r.get(p_fk, {}) if isinstance(sec_r, dict) else {}
            is_pwd = (frule.get("is_password") is True) or (rule_path in schema_pwd_fields) or (p_fk == "password")

            if is_pwd:
                if engine.is_full_encrypted:
                    val_to_store = NULL_SENTINEL if (new_val == "" or new_val is None or new_val == NULL_SENTINEL) else new_val
                else:
                    if new_val == "" or new_val is None or new_val == NULL_SENTINEL:
                        val_to_store = engine.encrypt_field(NULL_SENTINEL, key)
                    elif isinstance(new_val, str) and new_val.startswith(ENC_PREFIX):
                        val_to_store = new_val
                    else:
                        val_to_store = engine.encrypt_field(str(new_val), key)
            else:
                val_to_store = new_val

            data[SECTION_PROFILES][p_code][p_sec][p_fk] = val_to_store

        elif len(parts) >= 2:
            sec = parts[0]
            fk = parts[1]
            if sec not in data or not isinstance(data[sec], dict):
                data[sec] = {}

            rule_path = f"{sec}.{fk}"
            sec_r = val_rules.get(sec, {}) if isinstance(val_rules, dict) else {}
            frule = sec_r.get(fk, {}) if isinstance(sec_r, dict) else {}
            is_pwd = (frule.get("is_password") is True) or (rule_path in schema_pwd_fields) or (fk == "password") or is_security_section(sec)

            if is_pwd:
                if engine.is_full_encrypted:
                    val_to_store = NULL_SENTINEL if (new_val == "" or new_val is None or new_val == NULL_SENTINEL) else new_val
                else:
                    if new_val == "" or new_val is None or new_val == NULL_SENTINEL:
                        val_to_store = engine.encrypt_field(NULL_SENTINEL, key)
                    elif isinstance(new_val, str) and new_val.startswith(ENC_PREFIX):
                        val_to_store = new_val
                    else:
                        val_to_store = engine.encrypt_field(str(new_val), key)
            else:
                val_to_store = new_val

            data[sec][fk] = val_to_store
        else:
            data[key_path] = new_val

    # Respaldo automático
    backup_rules = (
        val_rules.get("_backup") if isinstance(val_rules, dict) and "_backup" in val_rules else context.backup_settings
    )
    perform_backup(abs_config, data, backup_rules)

    # Actualizar snapshot forense si security_level == 1 en plain
    if engine.mode_id == "plain" and getattr(context, "security_level", 0) == 1:
        snapshot_clean = {k: v for k, v in data.items() if k != NO_MODIFY_KEY}
        snapshot_bytes = json.dumps(snapshot_clean, ensure_ascii=False, sort_keys=True).encode("utf-8")
        plain_fernet_engine = FORMAT_MODES["fernet"]
        data[NO_MODIFY_KEY] = plain_fernet_engine.encrypt_payload(snapshot_bytes, key).decode("utf-8")
    else:
        data.pop(NO_MODIFY_KEY, None)

    public_comments = _collect_public_comments(data, getattr(context, "public_fields", []))

    json_bytes = json.dumps(data, indent=4, ensure_ascii=False).encode("utf-8")
    payload = engine.encrypt_payload(json_bytes, key)

    comment_bytes = b"".join(f"{c}\n".encode("utf-8") for c in public_comments)
    content = f"{engine.header}\n".encode("utf-8") + comment_bytes + payload + b"\n"

    temp_path = f"{abs_config}.tmp"
    with open(temp_path, "wb") as f:
        f.write(content)
    shutil.move(temp_path, abs_config)

    # Sincronización en caliente sobre config_instance
    if config_instance is not None and isinstance(config_instance, ConfigDict):
        for key_path, new_val in updates.items():
            parts = key_path.strip().split(".")
            if parts[0] == SECTION_PROFILES and len(parts) >= 4:
                p_code, p_sec, p_fk = parts[1], parts[2], parts[3]
                if SECTION_PROFILES not in config_instance:
                    config_instance[SECTION_PROFILES] = {}
                if p_code not in config_instance[SECTION_PROFILES]:
                    config_instance[SECTION_PROFILES][p_code] = {}
                if p_sec not in config_instance[SECTION_PROFILES][p_code]:
                    config_instance[SECTION_PROFILES][p_code][p_sec] = {}
                config_instance[SECTION_PROFILES][p_code][p_sec][p_fk] = data[SECTION_PROFILES][p_code][p_sec][p_fk]
            elif len(parts) >= 2:
                sec, fk = parts[0], parts[1]
                if sec not in config_instance:
                    config_instance[sec] = {}
                config_instance[sec][fk] = data[sec][fk]
            else:
                config_instance[key_path] = data[key_path]


# ==============================================================================
# ACCIONES CLI Y EXPORTACIÓN DE ESQUEMA
# ==============================================================================


def export_config_schema(source_path: str, target_path: str) -> int:
    """Exporta / copia el archivo de esquema resuelto desde source_path hacia target_path."""
    try:
        resolved_src = os.path.abspath(source_path)
        resolved_dst = os.path.abspath(target_path)

        if not os.path.exists(resolved_src):
            print(f"[ERROR] Archivo origen de esquema no existe: {resolved_src}", file=sys.stderr)
            return 1

        if os.path.isdir(resolved_dst):
            resolved_dst = os.path.join(resolved_dst, os.path.basename(resolved_src))
        else:
            parent_dir = os.path.dirname(resolved_dst)
            if parent_dir:
                os.makedirs(parent_dir, exist_ok=True)

        if resolved_src == resolved_dst:
            print(f"[INFO] El archivo de esquema ya existe en destino: {resolved_dst}")
            return 0

        shutil.copy2(resolved_src, resolved_dst)
        print(f"[INFO] Archivo de esquema generado exitosamente en: {resolved_dst}")
        return 0
    except Exception as e:
        print(f"[ERROR] No se pudo exportar el archivo de esquema: {e}", file=sys.stderr)
        return 1


def execute_app_action(
    context: AppConfigContext,
    exit_on_finish: bool = False,
    *,
    overwrite_key: bool = False,
    i18n_path: Optional[str] = None,
    edit: bool = False,
    reset_admin_pass: bool = False,
    theme: str = "dark",
    is_install_mode: bool = False,
    new_admin_pass: Optional[str] = None,
) -> Optional[int]:
    """
    Ejecuta centralizadamente la acción correspondiente al contexto de la aplicación.
    - Para 'generate_key', 'export_schema' y 'ui': ejecuta y retorna el código de salida (int).
    - Para 'consume': retorna None permitiendo continuar la ejecución de la aplicación consumidora.
    """
    action = context.action
    eff_overwrite = bool(overwrite_key)
    eff_i18n = i18n_path
    eff_edit = bool(edit)
    eff_reset = bool(reset_admin_pass)
    eff_theme = str(theme or "dark")

    if action == "generate_key":
        try:
            generate_key_file(context=context, overwrite=eff_overwrite)
            print(f"[INFO] Archivo de clave generado exitosamente en: {context.key_file_path}")
            code = 0
        except Exception as e:
            print(f"[ERROR] No se pudo generar el archivo de clave: {e}", file=sys.stderr)
            code = 1
        if exit_on_finish:
            sys.exit(code)
        return code

    if action == "export_schema":
        code = export_config_schema(source_path=context.schema_file_path, target_path=context.base_dir)
        if exit_on_finish:
            sys.exit(code)
        return code

    if action == "ui" or eff_reset:
        resolved_config = context.config_file_path

        if eff_reset:
            is_elevated = context.dev_mode or is_admin()
            if not is_elevated:
                print(
                    "[ERROR] Se requiere elevación de privilegios para ejecutar esta opción. Deteniendo ejecución.",
                    file=sys.stderr,
                )
                code = 1
                if exit_on_finish:
                    sys.exit(code)
                return code

            key_status, key_detail = verify_key_integrity(context)
            if key_status in ("missing", "corrupted"):
                print(
                    f"[ERROR] El archivo de clave .key está alterado o faltante ({key_detail}).",
                    file=sys.stderr,
                )
                code = 1
                if exit_on_finish:
                    sys.exit(code)
                return code
            try:
                eff_new_pass = new_admin_pass
                if not eff_new_pass:
                    try:
                        import getpass
                        eff_new_pass = getpass.getpass("Ingrese la nueva clave de administración (mín. 4 caracteres): ").strip()
                        confirm_pass = getpass.getpass("Confirme la nueva clave de administración: ").strip()
                        if len(eff_new_pass) < 4:
                            raise ValueError("La clave debe tener al menos 4 caracteres.")
                        if eff_new_pass != confirm_pass:
                            raise ValueError("Las contraseñas no coinciden.")
                    except (EOFError, KeyboardInterrupt):
                        raise RuntimeError("Operación cancelada por el usuario.")
                cfg = load_config(context, edit_mode=True)
                set_admin_password(cfg, eff_new_pass)
                save_config(context, dict(cfg))
                log_audit_event("ADMIN_PASS_RESET_CLI", f"Clave admin restablecida en {resolved_config}")
                print("[INFO] La clave de administración ha sido restablecida exitosamente.")
                code = 0
            except Exception as e:
                print(f"[ERROR] No se pudo restablecer la contraseña de administrador: {e}", file=sys.stderr)
                code = 1
            if exit_on_finish:
                sys.exit(code)
            return code

        # Lanzamiento bajo demanda de la interfaz CustomTkinter (Aislamiento de UI)
        try:
            from asiscfg.ui.app import ConfigApp

            app = ConfigApp(
                context=context,
                i18n_path=eff_i18n,
                dev_mode=context.dev_mode,
                allow_app_edit=eff_edit,
                theme=eff_theme,
                is_install_mode=is_install_mode,
            )
            app.mainloop()
            code = 0
        except Exception as e:
            print(f"[ERROR] UI: {e}", file=sys.stderr)
            code = 1
        if exit_on_finish:
            sys.exit(code)
        return code

    # Modo 'consume'
    return None

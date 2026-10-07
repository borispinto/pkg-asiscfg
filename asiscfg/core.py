# -*- coding: utf-8 -*-
# SPDX-FileCopyrightText: 2026 Asisnet Computacion, CA <proyectos@asisnet.net>
# SPDX-License-Identifier: MIT
# Autor: Boris Pinto <borispinto@asisnet.net>
# File: asiscfg/core.py

"""
Módulo Core de Infraestructura de Configuración: Cifrado, I/O en disco y carga de esquemas unificados.
"""

import sys
import os
import json
import logging
import shutil
import copy
from datetime import datetime
from typing import Dict, Any, Tuple, Optional, List
from asiscfg.models import ConfigDict, AppConfigContext
from asiscfg.schema import (
    validate_and_correct_config,
    DEFAULT_BACKUP_SETTINGS
)
from asiscfg.security import set_admin_password, log_audit_event, is_admin
from asiscfg.constants import (
    get_format_engine,
    detect_format_engine,
    BaseFormatEngine,
    ENC_PREFIX,
    NULL_SENTINEL,
    SECTION_PROFILES,
    is_security_section,
    is_schema_directive,
    is_special_section,
    is_business_section
)

from i18n import t18n, get_i18n_instance


def get_key(
    context: AppConfigContext,
    forzar: bool = False,
    key_path: Optional[str] = None
) -> bytes:
    """
    Obtiene la clave criptográfica en bytes desde el contexto en memoria o leyendo el archivo de disco.
    Lanza FileNotFoundError si el archivo de clave no existe en disco.
    """
    target_path = os.path.abspath(key_path) if key_path else (context.key_file_path if context else "")

    if not forzar and context and context.key_bytes and (not key_path or target_path == context.key_file_path):
        return context.key_bytes

    try:
        with open(target_path, "rb") as f:
            key_bytes = f.read().strip()
    except Exception as e:
        raise FileNotFoundError(
            t18n("asiscfg.err_key_file_read", "Error al leer el archivo de clave {path}: {e}", path=target_path, e=e)
        )

    if context and (not key_path or target_path == context.key_file_path):
        context.key_bytes = key_bytes
    return key_bytes


def verify_key_integrity(
    context: AppConfigContext,
    config_path: Optional[str] = None,
    key_path: Optional[str] = None
) -> Tuple[str, str]:
    """
    Verifica de forma estricta la existencia y validez del archivo de clave criptográfica (.key).
    Detecta si el archivo está faltante, corrupto, con formato inválido o alterado
    respecto a un archivo de configuración existente.

    Retorna una tupla (status, detail):
      - status: "ok", "missing", o "corrupted"
      - detail: Mensaje descriptivo con el motivo o causa del fallo.
    """
    abs_config = os.path.abspath(config_path) if config_path else context.config_file_path
    abs_key = os.path.abspath(key_path) if key_path else context.key_file_path

    if not os.path.exists(abs_key):
        return "missing", t18n("asiscfg.err_key_not_found", "El archivo de clave no existe en la ruta: {path}", path=abs_key)

    try:
        with open(abs_key, "rb") as f:
            key_bytes = f.read().strip()
    except Exception as e:
        return "corrupted", t18n("asiscfg.err_key_read", "No se pudo leer el archivo de clave: {err}", err=e)

    if not key_bytes:
        return "corrupted", t18n("asiscfg.err_key_empty", "El archivo de clave está vacío (0 bytes).")

    # Si el archivo de configuración existe en disco, validar compatibilidad y descifrado real
    if os.path.exists(abs_config):
        try:
            with open(abs_config, "rb") as f:
                raw_config = f.read().strip()
        except Exception as e:
            return "corrupted", t18n("asiscfg.err_config_read", "No se pudo leer el archivo de configuración: {err}", err=e)

        try:
            detected_format, engine = detect_format_engine(raw_config)
        except Exception as e:
            return "corrupted", t18n("asiscfg.err_config_header_invalid", "El archivo de configuración no contiene una cabecera de formato válida reconocida: {err}", err=e)

        if not engine.validate_key(key_bytes):
            return "corrupted", t18n("asiscfg.err_key_invalid_engine", "La clave no posee un formato válido para el motor '{name}'.", name=engine.name)

        lines = raw_config.splitlines()
        payload_bytes = b"\n".join(lines[1:]).strip()

        if engine.is_full_encrypted:
            try:
                decrypted = engine.decrypt_payload(payload_bytes, key_bytes)
                json.loads(decrypted.decode("utf-8"))
            except Exception as e:
                return "corrupted", t18n("asiscfg.err_key_mismatch_payload", "La clave está alterada o no coincide con los datos cifrados del archivo de configuración.")
        else:
            # Modo plain: validar descifrado de campos protegidos con ENC:
            try:
                data = json.loads(payload_bytes.decode("utf-8"))
                enc_tokens = []

                def _collect_enc_tokens(node):
                    if isinstance(node, dict):
                        for v in node.values():
                            _collect_enc_tokens(v)
                    elif isinstance(node, list):
                        for item in node:
                            _collect_enc_tokens(item)
                    elif isinstance(node, str) and node.startswith(ENC_PREFIX):
                        enc_tokens.append(node)

                _collect_enc_tokens(data)
                for token in enc_tokens:
                    try:
                        dec_val = engine.decrypt_field(token, key_bytes)
                        if dec_val.startswith(ENC_PREFIX):
                            return "corrupted", t18n("asiscfg.err_key_mismatch_field", "La clave está alterada o no coincide con los campos protegidos cifrados.")
                    except Exception:
                        return "corrupted", t18n("asiscfg.err_key_mismatch_field", "La clave está alterada o no coincide con los campos protegidos cifrados.")
            except Exception as e:
                return "corrupted", t18n("asiscfg.err_config_json_invalid", "El archivo de configuración contiene un JSON inválido.")
    else:
        # Si la configuración aún no existe, validar que la clave sea válida para el modo del contexto o cualquier motor
        target_mode = getattr(context, "format_mode", "plain") or "plain"
        engine = get_format_engine(target_mode)
        if not engine.validate_key(key_bytes):
            return "corrupted", t18n("asiscfg.err_key_invalid_format", "El formato del archivo de clave no es válido para el modo '{mode}'.", mode=target_mode)

    return "ok", ""

def generate_key_file(
    context: AppConfigContext,
    overwrite: bool = False,
    key_path: Optional[str] = None,
    format_mode: Optional[str] = None
) -> bytes:
    """
    Genera de forma explícita un nuevo archivo de clave criptográfica delegando en el motor de formato correspondiente.
    Lanza FileExistsError si el archivo ya existe y overwrite es False.
    """
    if key_path:
        key_path = os.path.abspath(key_path)
    else:
        key_path = context.key_file_path

    if os.path.exists(key_path) and not overwrite:
        raise FileExistsError(
            t18n("asiscfg.err_key_file_exists", "El archivo de clave ya existe: {path}", path=key_path)
        )
    key_bytes = None
    try:
        mode = format_mode or getattr(context, "format_mode", None)
        engine = get_format_engine(mode)
        key = engine.generate_key()
        os.makedirs(os.path.dirname(key_path), exist_ok=True)
        with open(key_path, "wb") as f:
            f.write(key)
        key_bytes = key
    except Exception as e:
        if isinstance(e, FileExistsError):
            raise
        raise FileExistsError(
            t18n("asiscfg.err_key_file_write", "Error al crear el archivo de clave {path}: {e}", path=key_path, e=e)
        )
    if context and (not key_path or key_path == context.key_file_path):
        context.key_bytes = key_bytes
    return key_bytes


def _detect_password_field_failures(
    data: Dict[str, Any],
    key: bytes,
    validation_rules: Optional[Dict[str, Any]],
    default_config: Optional[Dict[str, Any]],
    engine: BaseFormatEngine,
    context: Optional[AppConfigContext] = None
) -> List[Dict[str, Any]]:
    """
    Detecta fallas en campos tipo contraseña durante la lectura de un archivo de configuración existente:
      1. No existe la clave en el archivo.
      2. Existe pero no tiene valor, no está encriptado o da error al desencriptar.
    Retorna una lista de diccionarios con:
      - field_path: Ruta canónica del campo (ej. "app.api_key", "@profiles.01.db.password")
      - reason: Código de falla ("missing", "empty", "unencrypted", "decrypt_error")
      - description: Mensaje descriptivo de la falla
      - value: Valor crudo presente en el archivo o None si no existe
    """
    failures: List[Dict[str, Any]] = []
    val_rules = validation_rules or {}
    def_cfg = default_config or {}

    expected_fields: List[Tuple[str, Optional[str], str, str, str]] = []
    # Tupla: (scope: "global"|"profile", profile_code, sec, field_name, full_path)

    # 1. Recolectar campos password globales
    global_secs = set()
    if isinstance(val_rules, dict):
        for sec in val_rules.keys():
            if is_business_section(sec) or is_security_section(sec):
                global_secs.add(sec)
    if isinstance(def_cfg, dict):
        for sec in def_cfg.keys():
            if is_business_section(sec) or is_security_section(sec):
                global_secs.add(sec)

    for sec in sorted(global_secs):
        sec_rules = val_rules.get(sec, {}) if isinstance(val_rules, dict) else {}
        sec_def = def_cfg.get(sec, {}) if isinstance(def_cfg, dict) else {}
        field_keys = set()
        if isinstance(sec_rules, dict):
            field_keys.update(sec_rules.keys())
        if isinstance(sec_def, dict):
            field_keys.update(sec_def.keys())

        for fk in sorted(field_keys):
            r = sec_rules.get(fk, {}) if isinstance(sec_rules, dict) else {}
            is_pwd = (isinstance(r, dict) and r.get("is_password") is True) or (
                bool(context and f"{sec}.{fk}" in context.password_fields)
            )
            if is_pwd:
                expected_fields.append(("global", None, sec, fk, f"{sec}.{fk}"))

    # 2. Recolectar campos password de perfiles (@profiles)
    prof_rules: Dict[str, Any] = {}
    if isinstance(val_rules, dict):
        if isinstance(val_rules.get(SECTION_PROFILES), dict) and "_template" in val_rules[SECTION_PROFILES]:
            prof_rules = val_rules[SECTION_PROFILES]["_template"]
        elif "_template" in val_rules and isinstance(val_rules["_template"], dict):
            prof_rules = val_rules["_template"]

    prof_codes = set()
    if isinstance(data, dict) and SECTION_PROFILES in data and isinstance(data[SECTION_PROFILES], dict):
        for p in data[SECTION_PROFILES].keys():
            if not is_schema_directive(p):
                prof_codes.add(p)

    for p_code in sorted(prof_codes):
        for sub_sec, sub_fields in prof_rules.items():
            if isinstance(sub_fields, dict):
                for fk, r in sub_fields.items():
                    is_pwd = (isinstance(r, dict) and r.get("is_password") is True) or (
                        bool(context and f"{SECTION_PROFILES}.{sub_sec}.{fk}" in context.password_fields)
                    )
                    if is_pwd:
                        full_path = f"{SECTION_PROFILES}.{p_code}.{sub_sec}.{fk}"
                        expected_fields.append(("profile", p_code, sub_sec, fk, full_path))

    # 3. Evaluar cada campo esperado contra data según las 4 condiciones canónicas
    for scope, p_code, sec, fk, full_path in expected_fields:
        # Condición 1: La clave siempre debe existir en el archivo físico. Si no aparece es faltante
        if scope == "global":
            if not isinstance(data, dict) or sec not in data or not isinstance(data[sec], dict) or fk not in data[sec]:
                failures.append({
                    "field_path": full_path,
                    "reason": "missing",
                    "description": t18n("asiscfg.err_pwd_missing", "No existe la clave en el archivo físico (faltante)."),
                    "value": None
                })
                continue
            val = data[sec][fk]
        else:
            if (
                not isinstance(data, dict)
                or SECTION_PROFILES not in data
                or not isinstance(data[SECTION_PROFILES], dict)
                or p_code not in data[SECTION_PROFILES]
                or not isinstance(data[SECTION_PROFILES][p_code], dict)
                or sec not in data[SECTION_PROFILES][p_code]
                or not isinstance(data[SECTION_PROFILES][p_code][sec], dict)
                or fk not in data[SECTION_PROFILES][p_code][sec]
            ):
                failures.append({
                    "field_path": full_path,
                    "reason": "missing",
                    "description": t18n("asiscfg.err_pwd_missing", "No existe la clave en el archivo físico (faltante)."),
                    "value": None
                })
                continue
            val = data[SECTION_PROFILES][p_code][sec][fk]

        if not engine.is_full_encrypted:
            # Modo texto plano / cifrado selectivo por campo
            # Condición 2: Existe pero no inicia con ENC_PREFIX
            if not isinstance(val, str) or not val.startswith(ENC_PREFIX):
                failures.append({
                    "field_path": full_path,
                    "reason": "unencrypted",
                    "description": t18n("asiscfg.err_pwd_no_prefix", "Existe pero no inicia con prefijo '{prefix}'.", prefix=ENC_PREFIX),
                    "value": val
                })
            else:
                enc_body = val[len(ENC_PREFIX):].strip()
                # Condición 3: Existe, inicia con ENC_PREFIX pero no tiene valor (ej: "ENC:")
                if enc_body == "":
                    failures.append({
                        "field_path": full_path,
                        "reason": "empty",
                        "description": t18n("asiscfg.err_pwd_empty_prefix", "Existe, inicia con '{prefix}' pero no tiene valor.", prefix=ENC_PREFIX),
                        "value": val
                    })
                else:
                    try:
                        dec_val = engine.decrypt_field(val, key)
                        # Si desencripta exitosamente (incluyendo NULL_SENTINEL), es un valor válido.
                    except Exception as e:
                        # Condición 4: Existe, inicia con ENC_PREFIX pero falla al desencriptar
                        failures.append({
                            "field_path": full_path,
                            "reason": "decrypt_error",
                            "description": t18n("asiscfg.err_pwd_decrypt", "Existe, inicia con '{prefix}' pero falla al desencriptar ({err}).", prefix=ENC_PREFIX, err=e),
                            "value": val
                        })
        else:
            # Modo cifrado total: el archivo completo ya fue descifrado
            if val == NULL_SENTINEL:
                # Es correcto (valor vacío cifrado intencionalmente)
                pass
            elif val is None:
                failures.append({
                    "field_path": full_path,
                    "reason": "empty",
                    "description": t18n("asiscfg.err_pwd_empty", "Existe pero no tiene valor (nulo)."),
                    "value": val
                })
            elif isinstance(val, str) and val.startswith(ENC_PREFIX):
                enc_body = val[len(ENC_PREFIX):].strip()
                if enc_body == "":
                    failures.append({
                        "field_path": full_path,
                        "reason": "empty",
                        "description": t18n("asiscfg.err_pwd_empty_prefix", "Existe, inicia con '{prefix}' pero no tiene valor.", prefix=ENC_PREFIX),
                        "value": val
                    })
                else:
                    try:
                        dec_val = engine.decrypt_field(val, key)
                        # Si desencripta exitosamente (incluyendo NULL_SENTINEL), es válido.
                    except Exception as e:
                        failures.append({
                            "field_path": full_path,
                            "reason": "decrypt_error",
                            "description": t18n("asiscfg.err_pwd_decrypt", "Existe, inicia con '{prefix}' pero falla al desencriptar ({err}).", prefix=ENC_PREFIX, err=e),
                            "value": val
                        })

    return failures


def _process_password_fields(
    data: Dict[str, Any],
    key: Optional[Any],
    validation_rules: Optional[Dict[str, Any]] = None,
    encrypt: bool = True,
    edit_mode: bool = False,
    detected_unencrypted: Optional[List[Any]] = None,
    is_full_encrypted: bool = False,
    engine: Optional[BaseFormatEngine] = None
) -> Dict[str, Any]:
    """
    Procesa selectivamente los campos definidos con 'is_password': True o en secciones de seguridad.
    - Si encrypt=True (al guardar):
        - En modo cifrado total (is_full_encrypted=True): desenvuelve contraseñas a texto plano para el payload cifrado, preservando NULL_SENTINEL.
        - En modo texto plano (is_full_encrypted=False): cifra campos protegidos con prefijo ENC: y normaliza vacíos a NULL_SENTINEL.
    - Si encrypt=False (al cargar):
        - Campos con 'is_password': True: se valida su cifrado pero se MANTIENEN cifrados en memoria (Lazy Decryption).
        - Campos en SECURITY_SECTIONS con 'is_password': False: se descifran automáticamente a texto claro en memoria.
        - Variables regulares: se conservan en texto claro.
    """
    if not isinstance(data, dict):
        return data

    rules = validation_rules or {}

    def process_val(val: Any, is_pwd_field: bool, is_sec_protected: bool, field_path: str) -> Any:
        if not encrypt:
            # --- Carga desde archivo a memoria ---
            if is_pwd_field:
                if isinstance(val, str) and val.startswith(ENC_PREFIX):
                    if engine and key:
                        try:
                            dec = engine.decrypt_field(val, key)
                            if dec == NULL_SENTINEL or dec == "":
                                return NULL_SENTINEL
                            return val
                        except Exception:
                            if edit_mode:
                                return NULL_SENTINEL
                            raise
                    return val
                elif is_full_encrypted and (val == NULL_SENTINEL or val == "" or val is None):
                    return NULL_SENTINEL
                elif is_full_encrypted:
                    return engine.encrypt_field(str(val), key) if (engine and key) else val
                else:
                    # En modo plain, el campo en disco no tiene prefijo ENC_PREFIX
                    if edit_mode:
                        if detected_unencrypted is not None and (field_path, val) not in detected_unencrypted:
                            detected_unencrypted.append((field_path, val))
                        return val
                    raise ValueError(f"Falla de carga: El parámetro protegido '{field_path}' no está encriptado o es inválido.")

            elif is_sec_protected:
                if isinstance(val, str) and val.startswith(ENC_PREFIX):
                    dec_str = engine.decrypt_field(val, key) if (engine and key) else val
                    return "" if dec_str == NULL_SENTINEL else dec_str
                if not is_full_encrypted and val != "":
                    if edit_mode:
                        if detected_unencrypted is not None and (field_path, val) not in detected_unencrypted:
                            detected_unencrypted.append((field_path, val))
                        return val
                    raise ValueError(f"Falla de carga: El parámetro protegido '{field_path}' no está encriptado o es inválido.")
                return "" if str(val) == NULL_SENTINEL else val

            else:
                return "" if str(val) == NULL_SENTINEL else val

        else:
            # --- Guardado de memoria a archivo ---
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

    def _process_single_field_node(
        container: Dict[str, Any],
        field_key: str,
        field_val: Any,
        field_rule: Dict[str, Any],
        is_sec_protected: bool,
        field_path: str
    ) -> None:
        """Subrutina unificada para evaluar y transformar cualquier campo sin importar su nivel de anidamiento."""
        is_pwd_field = bool(isinstance(field_rule, dict) and field_rule.get("is_password") is True)
        container[field_key] = process_val(field_val, is_pwd_field, is_sec_protected, field_path)

    prof_rules = {}
    if rules and isinstance(rules.get(SECTION_PROFILES), dict) and "_template" in rules[SECTION_PROFILES]:
        prof_rules = rules[SECTION_PROFILES]["_template"]
    elif rules and "_template" in rules:
        prof_rules = rules["_template"]
    else:
        prof_rules = rules

    for sec_key, sec_val in data.items():
        if sec_key == SECTION_PROFILES and isinstance(sec_val, dict):
            for prof_code, prof_data in sec_val.items():
                if is_schema_directive(prof_code) or not isinstance(prof_data, dict):
                    continue
                for sub_sec, sub_fields in prof_data.items():
                    if isinstance(sub_fields, dict):
                        sub_rules = prof_rules.get(sub_sec, rules.get(sub_sec, {}))
                        is_sub_sec_protected = is_security_section(sub_sec)
                        for field_key, field_val in list(sub_fields.items()):
                            field_rule = sub_rules.get(field_key, {}) if isinstance(sub_rules, dict) else {}
                            field_path = f"{sec_key}.{prof_code}.{sub_sec}.{field_key}"
                            _process_single_field_node(
                                sub_fields,
                                field_key,
                                field_val,
                                field_rule,
                                is_sub_sec_protected,
                                field_path
                            )
        elif isinstance(sec_val, dict):
            sec_rules = rules.get(sec_key, {})
            is_sec_protected = is_security_section(sec_key)
            for field_key, field_val in list(sec_val.items()):
                field_rule = sec_rules.get(field_key, {}) if isinstance(sec_rules, dict) else {}
                field_path = f"{sec_key}.{field_key}"
                _process_single_field_node(
                    sec_val,
                    field_key,
                    field_val,
                    field_rule,
                    is_sec_protected,
                    field_path
                )

    return data


def load_config(
    context: AppConfigContext,
    default_config: Optional[Dict[str, Any]] = None,
    validation_rules: Optional[Dict[str, Any]] = None,
    edit_mode: bool = False,
    config_path: Optional[str] = None,
    key_path: Optional[str] = None
) -> ConfigDict:
    """
    Carga, descifra y valida la configuración aplicando reglas de validación y fallbacks.
    Autodetecta el formato (Texto Plano # ASISCFG_PLAIN vs Cifrado Total).
    Si el archivo no existe:
      - Si edit_mode es False: Lanza FileNotFoundError y no continúa.
      - Si edit_mode es True: Inicializa el archivo con los valores por defecto en modo plain.
    """
    abs_config = os.path.abspath(config_path) if config_path else context.config_file_path
    abs_key = os.path.abspath(key_path) if key_path else context.key_file_path

    def_cfg = default_config if default_config is not None else (context.default_config if context else {})
    val_rules = validation_rules if validation_rules is not None else (context.validation_rules if context else {})

    if not os.path.exists(abs_config):
        if not edit_mode:
            raise FileNotFoundError(
                t18n("asiscfg.err_config_file_not_found", "El archivo de configuración no existe: {path}", path=abs_config)
            )
        save_config(context, def_cfg, validation_rules=val_rules, default_config=def_cfg, format_mode=context.format_mode, config_path=abs_config, key_path=abs_key)

        res = ConfigDict(context, def_cfg, validation_rules=val_rules)
        res.set_default_config(def_cfg)
        return res

    try:
        key = get_key(context, key_path=abs_key)
        with open(abs_config, "rb") as f:
            raw_bytes = f.read()

        stripped_raw = raw_bytes.strip()
        detected_unencrypted_passwords: List[Any] = []

        # Detección estricta y despacho directo a través del motor de formato registrado
        try:
            detected_format, engine = detect_format_engine(raw_bytes)
        except ValueError:
            raise ValueError(
                t18n("asiscfg.err_invalid_header", "El archivo no contiene una cabecera de formato válida reconocida: {path}", path=abs_config)
            )

        lines = stripped_raw.splitlines()
        payload_bytes = b"\n".join(lines[1:]).strip()
        decrypted_bytes = engine.decrypt_payload(payload_bytes, key)
        data = json.loads(decrypted_bytes.decode("utf-8"))

        # Detección estricta de fallas en campos tipo password en archivos existentes
        pwd_failures = _detect_password_field_failures(
            data=data,
            key=key,
            validation_rules=val_rules,
            default_config=def_cfg,
            engine=engine,
            context=context
        )

        if pwd_failures:
            if not edit_mode:
                for fail in pwd_failures:
                    logging.error(f"[CONFIG] Error en campo protegido '{fail['field_path']}': {fail['description']}")
                log_audit_event("PASSWORD_INTEGRITY_FAILED", f"Fallas detectadas en campos de contraseña: {', '.join([f['field_path'] for f in pwd_failures])}")
                details = "\n".join([f"- {f['field_path']}: {f['description']}" for f in pwd_failures])
                raise ValueError(
                    t18n(
                        "asiscfg.err_password_integrity",
                        "Falla de integridad en campos de contraseña de configuración:\n{details}",
                        details=details
                    )
                )
            else:
                for fail in pwd_failures:
                    logging.warning(f"[CONFIG] Advertencia en campo protegido '{fail['field_path']}': {fail['description']}")
                    detected_unencrypted_passwords.append((fail["field_path"], fail["value"]))

        # Verificación estricta de presencia de perfiles requeridos por el esquema
        schema_expects_profiles = bool(
            (isinstance(val_rules, dict) and SECTION_PROFILES in val_rules)
            or (isinstance(def_cfg, dict) and SECTION_PROFILES in def_cfg)
        )

        physical_profiles = [
            p for p in data.get(SECTION_PROFILES, {}).keys()
            if not is_schema_directive(p)
        ] if isinstance(data, dict) and isinstance(data.get(SECTION_PROFILES), dict) else []

        if schema_expects_profiles and len(physical_profiles) == 0:
            if not edit_mode:
                logging.error(f"[CONFIG] Error: El esquema requiere perfiles multiempresa ('{SECTION_PROFILES}'), pero el archivo físico no contiene ningún perfil.")
                log_audit_event("PROFILES_MISSING", f"El archivo de configuración '{abs_config}' no contiene ningún perfil bajo '{SECTION_PROFILES}'.")
                raise ValueError(
                    t18n(
                        "asiscfg.err_profiles_missing",
                        "El archivo de configuración '{path}' no contiene ningún perfil registrado bajo '{section}', el cual es requerido por el esquema.",
                        path=abs_config,
                        section=SECTION_PROFILES
                    )
                )
            else:
                logging.warning(f"[CONFIG] Advertencia: El esquema requiere perfiles multiempresa ('{SECTION_PROFILES}'), pero el archivo físico no contiene ningún perfil.")

        if isinstance(data, dict):
            _process_password_fields(
                data,
                key,
                validation_rules=val_rules,
                encrypt=False,
                edit_mode=edit_mode,
                detected_unencrypted=detected_unencrypted_passwords,
                is_full_encrypted=engine.is_full_encrypted,
                engine=engine
            )

        context.format_mode = detected_format

        merged = json.loads(json.dumps(def_cfg)) if def_cfg else {}
        if SECTION_PROFILES in merged:
            merged[SECTION_PROFILES] = {}

        # Determinar reglas/plantilla de perfil para filtrado
        prof_rules = {}
        if isinstance(val_rules, dict):
            if isinstance(val_rules.get(SECTION_PROFILES), dict) and "_template" in val_rules[SECTION_PROFILES]:
                prof_rules = val_rules[SECTION_PROFILES]["_template"]
            elif "_template" in val_rules and isinstance(val_rules["_template"], dict):
                prof_rules = val_rules["_template"]

        business_secs = [k for k in def_cfg.keys() if is_business_section(k)] if def_cfg else []

        if isinstance(data, dict):
            for sec, subdict in data.items():
                if sec == SECTION_PROFILES:
                    if not isinstance(subdict, dict):
                        continue
                    filtered_profiles = {}
                    for prof_code, prof_data in subdict.items():
                        if is_schema_directive(prof_code) or not isinstance(prof_data, dict):
                            continue
                        
                        # Inicializar perfil con valores por defecto del esquema/plantilla
                        prof_entry = {}
                        if prof_rules:
                            for p_sec, p_fields in prof_rules.items():
                                if isinstance(p_fields, dict):
                                    prof_entry[p_sec] = {
                                        k: (v.get("default") if isinstance(v, dict) else v)
                                        for k, v in p_fields.items()
                                        if not (isinstance(v, dict) and v.get("type") == "test_connection")
                                    }
                        
                        # Cargar y filtrar campos del archivo local para este perfil
                        for p_sec, p_fields in prof_data.items():
                            if prof_rules and p_sec not in prof_rules:
                                logging.warning(f"[CONFIG] Subsección '{p_sec}' en perfil '{prof_code}' omitida (no existe en el esquema)")
                                continue
                            if not isinstance(p_fields, dict):
                                continue
                            if p_sec not in prof_entry:
                                prof_entry[p_sec] = {}
                            
                            valid_field_rules = prof_rules.get(p_sec, {}) if prof_rules else None
                            for fk, fv in p_fields.items():
                                if valid_field_rules is not None:
                                    if fk not in valid_field_rules:
                                        logging.warning(f"[CONFIG] Clave1 '{p_sec}.{fk}' en perfil '{prof_code}' omitida (no existe en el esquema)")
                                        continue
                                    if isinstance(valid_field_rules.get(fk), dict) and valid_field_rules[fk].get("type") == "test_connection":
                                        continue
                                prof_entry[p_sec][fk] = fv
                        
                        filtered_profiles[prof_code] = prof_entry

                    if filtered_profiles:
                        merged[SECTION_PROFILES] = filtered_profiles

                elif business_secs and sec not in def_cfg and not is_special_section(sec):
                    logging.warning(f"[CONFIG] Sección raíz '{sec}' omitida (no existe en el esquema)")
                elif isinstance(subdict, dict):
                    if sec not in merged or not isinstance(merged[sec], dict):
                        merged[sec] = {}
                    is_special = is_special_section(sec)
                    sec_schema = def_cfg.get(sec, {}) if def_cfg else {}
                    for fk, fv in subdict.items():
                        if business_secs and not is_special and isinstance(sec_schema, dict) and fk not in sec_schema:
                            logging.warning(f"[CONFIG] Clave2 '{sec}.{fk}' omitida (no existe en el esquema)")
                        else:
                            merged[sec][fk] = fv
                else:
                    merged[sec] = subdict
        res = ConfigDict(
            context,
            merged,
            default_config=def_cfg,
            validation_rules=val_rules,
            unencrypted_passwords=detected_unencrypted_passwords,
            password_failures=pwd_failures
        )
        res.set_default_config(def_cfg)
        has_schema = bool(business_secs or (val_rules and any(k for k in val_rules.keys() if is_business_section(k))))
        if has_schema:
            return validate_and_correct_config(
                res,
                validation_rules=val_rules,
                default_config=def_cfg,
                context=context
            )
        return res
    except Exception as e:
        if not edit_mode:
            raise
        logging.warning(f"[WARN] Error al descifrar o procesar {abs_config}: {e}. Usando esquema por defecto.")
        res = ConfigDict(
            context,
            def_cfg,
            default_config=def_cfg,
            validation_rules=val_rules
        )
        res.set_default_config(def_cfg)
        return res


def perform_backup(
    config_path: str,
    config_data: Optional[dict] = None,
    backup_settings: Optional[Dict[str, Any]] = None
) -> Optional[str]:
    """
    Crea una copia de respaldo del archivo de configuración antes de sobrescribirlo,
    según la política definida en la metaclave _backup.
    Retorna el nombre del archivo de respaldo creado o None si no se creó.
    """
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

    # 1. Resolver target_dir (Literal vs SCHEMA_KEY)
    raw_target = settings.get("target_dir", "{ROOT}/backups")
    if isinstance(raw_target, dict) and "schema_key" in raw_target:
        key_path = str(raw_target["schema_key"]).strip()
        val = config_data or {}
        for part in key_path.split("."):
            if isinstance(val, dict) and part in val:
                val = val[part]
            else:
                val = None
                break
        if isinstance(val, str) and val.strip():
            target_dir = val.strip()
        else:
            target_dir = "{ROOT}/backups"
    elif isinstance(raw_target, str) and raw_target.strip():
        target_dir = raw_target.strip()
    else:
        target_dir = "{ROOT}/backups"

    # Expandir token {ROOT} y normalizar ruta
    config_dir = os.path.dirname(os.path.abspath(config_path))
    target_dir = target_dir.replace("{ROOT}", config_dir)
    if not os.path.isabs(target_dir):
        target_dir = os.path.join(config_dir, target_dir)
    target_dir = os.path.abspath(target_dir)

    try:
        os.makedirs(target_dir, exist_ok=True)
    except Exception as e:
        logging.warning(f"No se pudo crear el directorio de respaldo {target_dir}: {e}")
        return None

    # 2. Resolver nombre de archivo
    basename_with_ext = os.path.basename(config_path)
    basename, ext = os.path.splitext(basename_with_ext)
    now = datetime.now()
    timestamp = now.strftime("%Y%m%d_%H%M%S")

    if method == "simple":
        backup_filename = f"{basename}{ext}.bak"
    else:
        raw_pattern = settings.get("filename_pattern", "{TIMESTAMP}-{BASENAME}{EXT}.bak")
        if isinstance(raw_pattern, dict) and "schema_key" in raw_pattern:
            key_path = str(raw_pattern["schema_key"]).strip()
            val = config_data or {}
            for part in key_path.split("."):
                if isinstance(val, dict) and part in val:
                    val = val[part]
                else:
                    val = None
                    break
            if isinstance(val, str) and val.strip():
                pattern = val.strip()
            else:
                pattern = "{TIMESTAMP}-{BASENAME}{EXT}.bak"
        elif isinstance(raw_pattern, str) and raw_pattern.strip():
            pattern = raw_pattern.strip()
        else:
            pattern = "{TIMESTAMP}-{BASENAME}{EXT}.bak"

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
        if not backup_filename:
            backup_filename = f"{timestamp} - {basename}{ext}.bak"

    dest_path = os.path.join(target_dir, backup_filename)

    # 3. Copiar archivo existente
    try:
        shutil.copy2(config_path, dest_path)
    except Exception as e:
        logging.warning(f"No se pudo crear copia de respaldo en {dest_path}: {e}")
        return None

    # 4. Rotación de respaldos históricos (solo para method timestamp)
    max_backups = int(settings.get("max_backups", 20))
    if method == "timestamp" and max_backups > 0:
        try:
            backups = sorted(
                [
                    os.path.join(target_dir, f) for f in os.listdir(target_dir)
                    if f.endswith(".bak") and os.path.isfile(os.path.join(target_dir, f))
                ],
                key=os.path.getmtime
            )
            while len(backups) > max_backups:
                oldest = backups.pop(0)
                try:
                    os.remove(oldest)
                except Exception:
                    pass
        except Exception as e:
            logging.debug(f"Error durante rotación de respaldos: {e}")

    return backup_filename


def save_config(
    context: AppConfigContext,
    config_data: Optional[dict] = None,
    validation_rules: Optional[Dict[str, Any]] = None,
    default_config: Optional[Dict[str, Any]] = None,
    format_mode: Optional[str] = None,
    config_path: Optional[str] = None,
    key_path: Optional[str] = None
) -> Optional[str]:
    """
    Guarda la configuración validada en disco (creando copia de respaldo según la política _backup).
    Soporta formato 'plain' (texto plano con claves cifradas individuales) o 'encrypted' (archivo cifrado completo).
    Retorna el nombre del archivo de respaldo creado, o None si no se creó.
    """
    if not isinstance(context, AppConfigContext):
        raise TypeError(f"El parámetro 'context' debe ser una instancia de AppConfigContext, recibido: {type(context).__name__}")

    abs_config = os.path.abspath(config_path) if config_path else context.config_file_path
    abs_key = os.path.abspath(key_path) if key_path else context.key_file_path

    target_mode = format_mode if (format_mode is not None and str(format_mode).strip() != "") else context.format_mode
    engine = get_format_engine(target_mode)
    context.format_mode = engine.mode_id

    def_cfg = default_config if default_config is not None else context.default_config
    val_rules = validation_rules if validation_rules is not None else context.validation_rules

    final_data = config_data if config_data is not None else (copy.deepcopy(def_cfg) if def_cfg else {})
    has_schema = bool(def_cfg or (val_rules and any(k for k in val_rules.keys() if is_business_section(k))))
    if has_schema:
        validated = validate_and_correct_config(
            final_data,
            validation_rules=val_rules,
            default_config=def_cfg,
            context=context
        )
        final_data = dict(validated)
    else:
        final_data = dict(final_data)

    # Asegurar que directivas de esquema de perfiles no se guarden en el archivo
    if SECTION_PROFILES in final_data and isinstance(final_data[SECTION_PROFILES], dict):
        final_data[SECTION_PROFILES] = {
            code: val for code, val in final_data[SECTION_PROFILES].items()
            if not is_schema_directive(code)
        }

    # Limpiar directivas/metaclaves raíz (como _backup) de final_data antes de persistir
    for k in [k for k in final_data.keys() if is_schema_directive(k)]:
        del final_data[k]

    key = get_key(context, key_path=abs_key)
    parent_dir = os.path.dirname(abs_config)
    if parent_dir:
        os.makedirs(parent_dir, exist_ok=True)

    # Ejecutar respaldo unificado
    backup_rules = val_rules.get("_backup") if isinstance(val_rules, dict) and "_backup" in val_rules else context.backup_settings
    backup_created = perform_backup(abs_config, final_data, backup_rules)

    dumps_data = copy.deepcopy(final_data)
    _process_password_fields(
        dumps_data,
        key,
        validation_rules=val_rules,
        encrypt=True,
        is_full_encrypted=engine.is_full_encrypted,
        engine=engine
    )
    json_bytes = json.dumps(dumps_data, indent=4, ensure_ascii=False).encode("utf-8")
    payload = engine.encrypt_payload(json_bytes, key)
    content = f"{engine.header}\n".encode("utf-8") + payload + b"\n"
    with open(abs_config, "wb") as f:
        f.write(content)

    return backup_created


def export_config_schema(
    source_path: str,
    target_path: str
) -> int:
    """
    Exporta / copia el archivo de esquema resuelto desde source_path hacia target_path.
    Retorna 0 en caso de éxito y 1 en caso de error.
    """
    try:
        resolved_src = os.path.abspath(source_path)
        resolved_dst = os.path.abspath(target_path)

        target_dir = os.path.dirname(resolved_dst)
        if target_dir:
            os.makedirs(target_dir, exist_ok=True)

        if resolved_src == resolved_dst:
            print(f"[INFO] El archivo de esquema ya existe en la ruta de destino: {resolved_dst}")
            return 0

        shutil.copy2(resolved_src, resolved_dst)
        print(f"[INFO] Archivo de esquema generado exitosamente en: {resolved_dst}")
        return 0
    except Exception as e:
        print(f"[ERROR] No se pudo generar el archivo de esquema en {target_path}: {e}", file=sys.stderr)
        return 1


def run_asiscfg(
    context: AppConfigContext,
    i18n_path: Optional[str] = None,
    dev_mode: bool = False,
    allow_app_edit: bool = False,
    reset_admin_pass: bool = False,
    theme: str = "dark"
) -> int:
    """
    Ejecuta la interfaz gráfica o las operaciones de administración (reinicio de contraseña)
    de asiscfg con los parámetros especificados en el contexto.
    Retorna 0 en caso de éxito y 1 en caso de error.
    """
    resolved_config = context.config_file_path
    #resolved_key = context.key_file_path
    #resolved_schema = context.schema_file_path

    if i18n_path and os.path.exists(i18n_path):
        get_i18n_instance().set_external_languages_dir(i18n_path)

    if reset_admin_pass:
        key_status, key_detail = verify_key_integrity(context)
        if key_status in ("missing", "corrupted"):
            is_elevated = dev_mode or is_admin()
            if not is_elevated:
                print(t18n("asiscfg.err_key_stop_execution", "[ERROR] El archivo de clave .key está alterado o faltante. Deteniendo la ejecución."), file=sys.stderr)
                return 1
            else:
                print(t18n("asiscfg.err_key_admin_warning", "[ERROR] El archivo de clave .key está alterado o faltante ({detail}). Debe buscar un respaldo del archivo .key o generar uno nuevo con --generate-key (perdiendo los valores encriptados previamente).", detail=key_detail), file=sys.stderr)
                return 1
        try:
            cfg = load_config(context, edit_mode=True)
            set_admin_password(cfg, "admin")
            save_config(context, dict(cfg))
            log_audit_event("ADMIN_PASS_RESET_CLI", t18n("asiscfg.audit_admin_pass_reset", "Clave de administración restablecida al valor por defecto via CLI en {path}.", path=resolved_config))
            print(t18n("asiscfg.msg_admin_pass_reset", "[INFO] La clave de administración ha sido restablecida exitosamente al valor por defecto ('admin')."))
            return 0
        except Exception as e:
            print(f"[ERROR] No se pudo restablecer la contraseña de administrador: {e}", file=sys.stderr)
            return 1

    try:
        from asiscfg.ui.app import ConfigApp
        app = ConfigApp(
            context=context,
            i18n_path=i18n_path,
            dev_mode=dev_mode,
            allow_app_edit=allow_app_edit,
            theme=theme
        )
        app.mainloop()
        return 0
    except Exception as e:
        print(f"[ERROR] Error al iniciar la herramienta de configuración: {e}", file=sys.stderr)
        return 1


def execute_app_action(
    context: AppConfigContext,
    overwrite_key: bool = False,
    i18n_path: Optional[str] = None,
    allow_app_edit: bool = False,
    reset_admin_pass: bool = False,
    theme: str = "dark",
    exit_on_finish: bool = False
) -> Optional[int]:
    """
    Ejecuta centralizadamente la acción correspondiente al contexto de la aplicación.

    - Para 'generate_key', 'export_schema' y 'ui': ejecuta la tarea y retorna el código de salida (int).
      Si exit_on_finish=True, invoca sys.exit(code).
    - Para 'consume': retorna None permitiendo continuar la ejecución de la aplicación consumidora.
    """
    action = context.action

    if action == "generate_key":
        try:
            generate_key_file(context=context, overwrite=overwrite_key)
            print(t18n("asiscfg.msg_key_generated", "[INFO] Archivo de clave Fernet generado exitosamente en: {path}", path=context.key_file_path))
            code = 0
        except Exception as e:
            print(f"[ERROR] No se pudo generar el archivo de clave: {e}", file=sys.stderr)
            code = 1
        if exit_on_finish:
            sys.exit(code)
        return code
    if action == "export_schema":
        code = export_config_schema(
            source_path=context.schema_file_path,
            target_path=context.base_dir
        )
        if exit_on_finish:
            sys.exit(code)
        return code

    if action == "ui":
        try:
            code = run_asiscfg(
                context=context,
                i18n_path=i18n_path,
                dev_mode=context.dev_mode,
                allow_app_edit=allow_app_edit,
                reset_admin_pass=reset_admin_pass,
                theme=theme
            )
        except Exception as e:
            print(f"[ERROR] ui: {e}", file=sys.stderr)
            code = 1
        if exit_on_finish:
            sys.exit(code)
        return code
    
    # Modo "consume" -> Retorna None para continuar el flujo de consumo
    return None




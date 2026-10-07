# -*- coding: utf-8 -*-
# SPDX-FileCopyrightText: 2026 Asisnet Computacion, CA <proyectos@asisnet.net>
# SPDX-License-Identifier: MIT
# Autor: Boris Pinto <borispinto@asisnet.net>
# File: asiscfg/schema.py

"""
Módulo de motor de esquemas y reglas de validación de configuración (Versión 1).
Soporta esquema unificado (DEFAULT_CONFIG con reglas integradas y soporte _template para perfiles).
"""

import os
import logging
import importlib.util
from typing import Dict, Any, Tuple, Optional, List
from asiscfg.constants import (
    SECTION_PROFILES,
    SECTION_ASISCFG,
    is_schema_directive,
    is_special_section,
    is_business_section
)
from asiscfg.security import hash_password
from asiscfg.models import ConfigDict, AppConfigContext
from i18n import t18n


def LITERAL(val: Any) -> Dict[str, Any]:
    """Helper para definir un valor constante/literal en el mapping de un test de conexión."""
    return {"literal": val}


def SCHEMA_KEY(key_path: str) -> Dict[str, Any]:
    """Helper para referenciar dinámicamente un valor de la configuración por su ruta por puntos."""
    return {"schema_key": key_path}


VALOR_SCHEMA = SCHEMA_KEY


DEFAULT_BACKUP_SETTINGS: Dict[str, Any] = {
    "enabled": True,
    "method": "timestamp",
    "target_dir": "{ROOT}/backups",
    "filename_pattern": "{TIMESTAMP}-{BASENAME}{EXT}.bak",
    "max_backups": 20
}


def normalize_field_def(key_path: str, raw_def: Any) -> Dict[str, Any]:
    """
    Normaliza cualquier definición de campo (escalar o diccionario) a una estructura estándar:
    {
        "default": ...,
        "type": "str"|"int"|"float"|"bool"|"enum",
        "min": ...,
        "max": ...,
        "options": [...],
        "is_password": bool,
        "description": "..."
    }
    """
    if not isinstance(raw_def, dict):
        # Caso simplificado: valor directo
        val_type = "str"
        if isinstance(raw_def, bool):
            val_type = "bool"
        elif isinstance(raw_def, int):
            val_type = "int"
        elif isinstance(raw_def, float):
            val_type = "float"
        return {
            "default": raw_def,
            "type": val_type,
            "description": ""
        }

    # Si es un diccionario con metadata
    field_info = raw_def.copy()
    default_val = field_info.get("default", "")
    
    # Inferir tipo si no está explícito
    if "type" not in field_info:
        if isinstance(default_val, bool):
            field_info["type"] = "bool"
        elif isinstance(default_val, int):
            field_info["type"] = "int"
        elif isinstance(default_val, float):
            field_info["type"] = "float"
        elif "options" in field_info:
            field_info["type"] = "enum"
        else:
            field_info["type"] = "str"

    # Procesar prefijo t18n# en la descripción
    desc = field_info.get("description", "")
    if isinstance(desc, str) and desc.startswith("t18n#"):
        raw_text = desc[5:]
        field_info["description"] = t18n(key_path, raw_text, suppress_markers=True)

    return field_info


def extract_schema_metadata(unified_schema: Dict[str, Any]) -> Dict[str, Any]:
    """
    Descompone el esquema unificado en sus componentes canónicos de forma pura:
      - default_config: Diccionario puro de valores por defecto (generales + perfiles iniciales).
      - validation_rules: Diccionario de reglas y metadata (generales + subsecciones de perfil + directiva _backup).
      - profile_template: Plantilla (_template) con la definición de pestañas y campos para perfiles.
      - password_fields: Lista de rutas canónicas de campos protegidos (is_password=True).
      - backup_settings: Diccionario de configuración de respaldos derivado de _backup.
      - admin_pass_hash: Hash de contraseña de administración de @asiscfg.
    """
    default_values: Dict[str, Any] = {}
    metadata_rules: Dict[str, Any] = {}
    profile_template: Dict[str, Any] = {}
    password_fields: List[str] = []

    if not isinstance(unified_schema, dict):
        backup_settings = dict(DEFAULT_BACKUP_SETTINGS)
        metadata_rules["_backup"] = backup_settings
        default_values[SECTION_ASISCFG] = {"admin_pass_hash": hash_password("admin")}
        return {
            "default_config": default_values,
            "validation_rules": metadata_rules,
            "profile_template": profile_template,
            "password_fields": password_fields,
            "backup_settings": backup_settings,
            "admin_pass_hash": hash_password("admin"),
        }

    # Procesar metaclave _backup con defaults automáticos
    backup_settings = dict(DEFAULT_BACKUP_SETTINGS)
    if "_backup" in unified_schema and isinstance(unified_schema["_backup"], dict):
        backup_settings.update(unified_schema["_backup"])
    metadata_rules["_backup"] = backup_settings

    for sec_key, sec_val in unified_schema.items():
        if is_schema_directive(sec_key):
            continue  # Omitir metaclaves raíz (_backup, _template, etc.) de los valores por defecto

        if not isinstance(sec_val, dict):
            default_values[sec_key] = sec_val
            continue

        if sec_key == SECTION_PROFILES:
            default_values[SECTION_PROFILES] = {}
            profile_rules = {}
            raw_template = sec_val.get("_template", {})
            
            # Normalizar _template para perfiles
            for sub_sec, sub_fields in raw_template.items():
                if isinstance(sub_fields, dict):
                    profile_template[sub_sec] = {}
                    profile_rules[sub_sec] = {}
                    for field_key, raw_field in sub_fields.items():
                        norm = normalize_field_def(f"{SECTION_PROFILES}.{sub_sec}.{field_key}", raw_field)
                        profile_template[sub_sec][field_key] = norm
                        profile_rules[sub_sec][field_key] = norm
                        if norm.get("is_password") is True:
                            pwd_key = f"{SECTION_PROFILES}.{sub_sec}.{field_key}"
                            if pwd_key not in password_fields:
                                password_fields.append(pwd_key)

            metadata_rules[SECTION_PROFILES] = {"_template": profile_rules}

            # Procesar perfiles concretos definidos en el esquema (ej. "01", "02")
            for prof_code, prof_data in sec_val.items():
                if is_schema_directive(prof_code):
                    continue  # Ignorar metaclaves como _template

                default_values[SECTION_PROFILES][prof_code] = {}
                # Inicializar con los defaults de la plantilla (omitiendo campos de tipo test_connection)
                for sub_sec, sub_fields in profile_template.items():
                    default_values[SECTION_PROFILES][prof_code][sub_sec] = {
                        k: v.get("default") for k, v in sub_fields.items() if v.get("type") != "test_connection"
                    }

                # Sobreescribir con los valores específicos del perfil
                if isinstance(prof_data, dict):
                    for sub_sec, sub_fields in prof_data.items():
                        if isinstance(sub_fields, dict):
                            if sub_sec not in default_values[SECTION_PROFILES][prof_code]:
                                default_values[SECTION_PROFILES][prof_code][sub_sec] = {}
                            for fk, fv in sub_fields.items():
                                if isinstance(fv, dict):
                                    if fv.get("type") == "test_connection":
                                        continue
                                    if "default" in fv:
                                        default_values[SECTION_PROFILES][prof_code][sub_sec][fk] = fv["default"]
                                    else:
                                        default_values[SECTION_PROFILES][prof_code][sub_sec][fk] = fv
                                else:
                                    default_values[SECTION_PROFILES][prof_code][sub_sec][fk] = fv
                        else:
                            default_values[SECTION_PROFILES][prof_code][sub_sec] = sub_fields
        else:
            # Sección General (Ámbito Global / Negocio u otras)
            default_values[sec_key] = {}
            metadata_rules[sec_key] = {}
            for field_key, raw_field in sec_val.items():
                norm = normalize_field_def(f"{sec_key}.{field_key}", raw_field)
                if norm.get("type") != "test_connection":
                    default_values[sec_key][field_key] = norm.get("default")
                metadata_rules[sec_key][field_key] = norm
                if norm.get("is_password") is True:
                    pwd_key = f"{sec_key}.{field_key}"
                    if pwd_key not in password_fields:
                        password_fields.append(pwd_key)

    # Asegurar sección @asiscfg con contraseña admin por defecto si no está definida
    if SECTION_ASISCFG not in default_values or not isinstance(default_values[SECTION_ASISCFG], dict):
        default_values[SECTION_ASISCFG] = {}
    if "admin_pass_hash" not in default_values[SECTION_ASISCFG]:
        default_values[SECTION_ASISCFG]["admin_pass_hash"] = hash_password("admin")
    admin_pass_hash = default_values[SECTION_ASISCFG]["admin_pass_hash"]

    # Si hay @profiles pero no hay perfiles registrados, inicializar DEFAULT si hay template
    if SECTION_PROFILES in default_values and isinstance(default_values[SECTION_PROFILES], dict):
        if not default_values[SECTION_PROFILES] and profile_template:
            default_values[SECTION_PROFILES]["DEFAULT"] = {
                sub_sec: {k: v.get("default") for k, v in sub_fields.items() if v.get("type") != "test_connection"}
                for sub_sec, sub_fields in profile_template.items()
            }

    return {
        "default_config": default_values,
        "validation_rules": metadata_rules,
        "profile_template": profile_template,
        "password_fields": password_fields,
        "backup_settings": backup_settings,
        "admin_pass_hash": admin_pass_hash,
    }


def load_schema_definition(schema_path: str) -> Dict[str, Any]:
    """
    Carga y analiza dinámicamente un archivo de esquema .py de forma 100% independiente.
    No requiere ni accede a archivos de configuración ni a datos de cliente.
    
    Retorna un diccionario con:
      - default_config: Diccionario con los valores por defecto del esquema.
      - validation_rules: Diccionario con las reglas y metadata de los campos.
      - profile_template: Plantilla para secciones multiperfil (_template).
      - password_fields: Lista de claves de campos protegidos (is_password=True).
      - backup_settings: Diccionario de configuración de backups (_backup).
      - admin_pass_hash: Hash administrativo de @asiscfg.
    """
    raw_schema = {}
    if schema_path and os.path.exists(schema_path):
        try:
            module_name = "dynamic_config_schema"
            spec = importlib.util.spec_from_file_location(module_name, schema_path)
            if spec and spec.loader:
                module = importlib.util.module_from_spec(spec)
                spec.loader.exec_module(module)
                raw_schema = getattr(module, "DEFAULT_CONFIG", {})
        except Exception as e:
            logging.warning(f"[WARN] No se pudo cargar el esquema de {schema_path}: {e}")

    return extract_schema_metadata(raw_schema if isinstance(raw_schema, dict) else {})


def _apply_field_rule(sec: str, key: str, val: Any, rule: Dict[str, Any]) -> Any:
    """Aplica la regla de tipo y rango (min/max) de forma estricta a un valor."""
    if val is None:
        return rule.get("default")

    field_type = rule.get("type", "str")

    if field_type == "int":
        try:
            val_num = int(val)
            if "min" in rule and val_num < rule["min"]:
                logging.error(
                    t18n(
                        "asiscfg.config.out_of_range",
                        "[APPLICATION] Parámetro '{param_key}' ({val}) en sección '{section}' fuera de rango [{min} - {max}]. Tomando default ({def_val}).",
                        section=sec, param_key=key, val=val_num, min=rule.get("min"), max=rule.get("max"), def_val=rule.get("default")
                    )
                )
                return rule.get("default")
            if "max" in rule and val_num > rule["max"]:
                logging.error(
                    t18n(
                        "asiscfg.config.out_of_range",
                        "[APPLICATION] Parámetro '{param_key}' ({val}) en sección '{section}' fuera de rango [{min} - {max}]. Tomando default ({def_val}).",
                        section=sec, param_key=key, val=val_num, min=rule.get("min"), max=rule.get("max"), def_val=rule.get("default")
                    )
                )
                return rule.get("default")
            return val_num
        except (ValueError, TypeError):
            return rule.get("default")

    elif field_type == "float":
        try:
            val_num = float(val)
            if "min" in rule and val_num < rule["min"]:
                logging.error(
                    t18n(
                        "asiscfg.config.out_of_range",
                        "[APPLICATION] Parámetro '{param_key}' ({val}) en sección '{section}' fuera de rango [{min} - {max}]. Tomando default ({def_val}).",
                        section=sec, param_key=key, val=val_num, min=rule.get("min"), max=rule.get("max"), def_val=rule.get("default")
                    )
                )
                return rule.get("default")
            if "max" in rule and val_num > rule["max"]:
                logging.error(
                    t18n(
                        "asiscfg.config.out_of_range",
                        "[APPLICATION] Parámetro '{param_key}' ({val}) en sección '{section}' fuera de rango [{min} - {max}]. Tomando default ({def_val}).",
                        section=sec, param_key=key, val=val_num, min=rule.get("min"), max=rule.get("max"), def_val=rule.get("default")
                    )
                )
                return rule.get("default")
            return val_num
        except (ValueError, TypeError):
            return rule.get("default")

    elif field_type == "bool":
        if isinstance(val, bool):
            return val
        if str(val).lower() in ("true", "1", "yes", "si"):
            return True
        if str(val).lower() in ("false", "0", "no"):
            return False
        return bool(rule.get("default", False))

    else:
        # "str", "enum" o cualquier otro tipo por defecto
        return str(val) if val is not None else ""


def validate_and_correct_config(
    config: Dict[str, Any],
    validation_rules: Dict[str, Any],
    default_config: Dict[str, Any],
    context: AppConfigContext
) -> ConfigDict:
    """
    Valida y corrige la configuración respetando estrictamente el aislamiento de jerarquías:
    - Secciones generales se validan en la raíz.
    - Secciones de perfil se validan dentro de @profiles[cod][seccion].
    - NUNCA se inyectan claves de perfiles en la raíz.
    """
    if not isinstance(config, dict):
        raise TypeError(f"El parámetro 'config' debe ser de tipo dict o ConfigDict, recibido: {type(config).__name__}")
    if not isinstance(validation_rules, dict):
        raise TypeError(f"El parámetro 'validation_rules' debe ser de tipo dict, recibido: {type(validation_rules).__name__}")
    if not isinstance(default_config, dict):
        raise TypeError(f"El parámetro 'default_config' debe ser de tipo dict, recibido: {type(default_config).__name__}")
    if not isinstance(context, AppConfigContext):
        raise TypeError(f"El parámetro 'context' debe ser de tipo AppConfigContext, recibido: {type(context).__name__}")

    validated = config.copy()
    def_cfg = default_config
    rules_dict = validation_rules

    # 1. Asegurar secciones generales por defecto en la raíz
    for sec_key, sec_val in def_cfg.items():
        if sec_key == SECTION_PROFILES:
            continue
        if sec_key not in validated or not isinstance(validated[sec_key], dict):
            validated[sec_key] = sec_val.copy() if isinstance(sec_val, dict) else sec_val
        elif isinstance(sec_val, dict):
            # Rellenar claves faltantes en secciones generales
            for k, v in sec_val.items():
                if k not in validated[sec_key]:
                    validated[sec_key][k] = v

    # Determinar reglas de perfil si existen
    prof_rules_dict = {}
    if isinstance(rules_dict.get(SECTION_PROFILES), dict) and "_template" in rules_dict[SECTION_PROFILES]:
        prof_rules_dict = rules_dict[SECTION_PROFILES]["_template"]
    elif "_template" in rules_dict and isinstance(rules_dict["_template"], dict):
        prof_rules_dict = rules_dict["_template"]
    else:
        general_keys = [k for k in def_cfg.keys() if is_business_section(k)]
        prof_rules_dict = {k: v for k, v in rules_dict.items() if k not in general_keys and not is_special_section(k)}

    # 2. Validar reglas sobre secciones generales en la raíz
    general_secs = [k for k in def_cfg.keys() if is_business_section(k)]
    for sec in general_secs:
        rules = rules_dict.get(sec, {})
        if not isinstance(rules, dict):
            rules = {}
        # Purgar botones de test_connection declarados en la raíz o en plantillas
        tmpl_rules = prof_rules_dict.get(sec, {}) if isinstance(prof_rules_dict, dict) else {}
        for k, r in list(rules.items()) + list(tmpl_rules.items()):
            if isinstance(r, dict) and r.get("type") == "test_connection":
                if sec in validated and isinstance(validated[sec], dict) and k in validated[sec]:
                    del validated[sec][k]

        for key, rule in rules.items():
            if not isinstance(rule, dict) or rule.get("type") == "test_connection":
                continue
            val = validated[sec].get(key)
            validated[sec][key] = _apply_field_rule(sec, key, val, rule)

    # 3. Validar secciones multi-perfil dentro de @profiles
    has_profiles = SECTION_PROFILES in validated and isinstance(validated[SECTION_PROFILES], dict)
    if has_profiles:
        for prof_code, prof_dict in list(validated[SECTION_PROFILES].items()):
            if not isinstance(prof_dict, dict) or is_schema_directive(prof_code):
                continue
            for p_sec, p_rules in prof_rules_dict.items():
                if not isinstance(p_rules, dict) or is_special_section(p_sec) or is_schema_directive(p_sec):
                    continue
                if p_sec not in prof_dict or not isinstance(prof_dict[p_sec], dict):
                    prof_dict[p_sec] = {}
                for key, rule in p_rules.items():
                    if not isinstance(rule, dict):
                        continue
                    if rule.get("type") == "test_connection":
                        if key in prof_dict[p_sec]:
                            del prof_dict[p_sec][key]
                        continue
                    val = prof_dict[p_sec].get(key)
                    prof_dict[p_sec][key] = _apply_field_rule(p_sec, key, val, rule)

    # 4. Purgar cualquier sección general o clave que no esté en el esquema
    business_secs = [k for k in def_cfg.keys() if is_business_section(k)]
    if business_secs:
        for sec in list(validated.keys()):
            if is_special_section(sec):
                continue
            if sec not in def_cfg:
                del validated[sec]
            elif isinstance(validated[sec], dict) and isinstance(def_cfg.get(sec), dict):
                for k in list(validated[sec].keys()):
                    if k not in def_cfg[sec]:
                        del validated[sec][k]

    # 5. Purgar subsecciones o claves de perfil que no estén en la plantilla
    if has_profiles and prof_rules_dict:
        for prof_code, prof_dict in list(validated[SECTION_PROFILES].items()):
            if not isinstance(prof_dict, dict) or is_schema_directive(prof_code):
                continue
            for sub_sec in list(prof_dict.keys()):
                if sub_sec not in prof_rules_dict:
                    del prof_dict[sub_sec]
                elif isinstance(prof_dict[sub_sec], dict):
                    for k in list(prof_dict[sub_sec].keys()):
                        if k not in prof_rules_dict[sub_sec]:
                            del prof_dict[sub_sec][k]

    # 6. Purgar cualquier clave de perfil que haya quedado erróneamente en la raíz
    if has_profiles and business_secs:
        for spurious_key in list(validated.keys()):
            if spurious_key not in def_cfg and not is_special_section(spurious_key):
                del validated[spurious_key]

    unenc = getattr(config, "_unencrypted_passwords", []) if isinstance(config, ConfigDict) else []
    pwd_fails = getattr(config, "_password_failures", []) if isinstance(config, ConfigDict) else []

    res_dict = ConfigDict(
        context,
        validated,
        default_config=def_cfg,
        validation_rules=rules_dict,
        unencrypted_passwords=unenc,
        password_failures=pwd_fails
    )
    return res_dict




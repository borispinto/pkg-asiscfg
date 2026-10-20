# -*- coding: utf-8 -*-
# SPDX-FileCopyrightText: 2026 ASISNET Computación, CA <proyectos@asisnet.net>
# SPDX-FileCopyrightText: 2026 Boris Pinto <borispinto@gmail.com>
# SPDX-License-Identifier: MIT
# Autor: Boris Pinto <borispinto@gmail.com>
# Contacto Institucional: ASISNET Computación, CA <proyectos@asisnet.net>
# File: asiscfg/schema.py


"""
Módulo de motor de esquemas y reglas de validación de configuración.
Soporta esquema unificado (CONFIG_SCHEMA con reglas integradas y soporte _template para perfiles).
"""

import copy
import importlib.util
import logging
import os
from typing import Any, Dict, List, Optional

from asiscfg.constants import (
    SECTION_ASISCFG,
    SECTION_PROFILES,
    is_business_section,
    is_schema_directive,
    is_special_section,
)
from i18n import t18n


def LITERAL(val: Any) -> Dict[str, Any]:
    """Helper para definir un valor constante/literal en el mapping de un test de conexión."""
    return {"literal": val}


def SCHEMA_KEY(key_path: str) -> Dict[str, Any]:
    """Helper para referenciar dinámicamente un valor de la configuración por su ruta por puntos."""
    return {"schema_key": key_path}


VALOR_SCHEMA = SCHEMA_KEY


DEFAULT_BACKUP_SETTINGS: Dict[str, Any] = {}


def normalize_field_def(key_path: str, raw_def: Any) -> Dict[str, Any]:
    """
    Normaliza cualquier definición de campo (escalar o diccionario) a una estructura estándar:
    {
        "default": ...,
        "type": "str"|"int"|"float"|"bool"|"enum"|"test_connection",
        "min": ...,
        "max": ...,
        "options": [...],
        "is_password": bool,
        "public": bool,
        "description": "..."
    }
    """
    if not isinstance(raw_def, dict):
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
            "is_password": False,
            "public": False,
            "description": "",
        }

    field_info = raw_def.copy()
    default_val = field_info.get("default", "")

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

    if "is_password" not in field_info:
        field_info["is_password"] = False
    if "public" not in field_info:
        field_info["public"] = False

    # Si la propiedad is_password está explícita, el campo public siempre es False
    if field_info.get("is_password") is True:
        field_info["public"] = False

    desc = field_info.get("description", "")
    if isinstance(desc, str) and desc.startswith("t18n#"):
        raw_text = desc[5:]
        field_info["description"] = t18n(key_path, raw_text, suppress_markers=True)

    return field_info


def extract_schema_metadata(unified_schema: Dict[str, Any]) -> Dict[str, Any]:
    """
    Descompone un esquema unificado en diccionarios especializados:
    - default_config: Estructura plana de valores por defecto listos para JSON.
    - validation_rules: Reglas de validación, tipos, rangos y descripciones.
    - profile_template: Plantilla limpia de subsecciones para un nuevo perfil bajo @profiles.
    - password_fields: Lista de rutas canónicas marcadas con 'is_password': True.
    - public_fields: Lista de rutas canónicas marcadas con 'public': True (no contraseñas).
    - security_level: Nivel de seguridad (0 = estándar, 1 = sellado con snapshot forense en PLAIN).
    - backup_settings: Política de copias de seguridad de la metaclave '_backup'.
    - admin_pass_hash: Hash de clave de administración si está configurado en el esquema.
    """
    default_cfg: Dict[str, Any] = {}
    validation_rules: Dict[str, Any] = {}
    profile_template: Dict[str, Any] = {}
    password_fields: List[str] = []
    public_fields: List[str] = []
    backup_settings: Dict[str, Any] = {}
    admin_pass_hash: Optional[str] = None
    security_level = 0

    if not isinstance(unified_schema, dict):
        return {
            "default_config": default_cfg,
            "validation_rules": validation_rules,
            "profile_template": profile_template,
            "password_fields": password_fields,
            "public_fields": public_fields,
            "security_level": security_level,
            "backup_settings": backup_settings,
            "admin_pass_hash": admin_pass_hash,
        }

    # Directiva global de nivel de seguridad

    if "_security_level" in unified_schema:
        try:
            security_level = int(unified_schema["_security_level"])
        except (ValueError, TypeError):
            security_level = 0
    # Metaclave de backup global '_backup'
    if "_backup" in unified_schema and isinstance(unified_schema["_backup"], dict):
        backup_settings.update(unified_schema["_backup"])
        validation_rules["_backup"] = unified_schema["_backup"]

    # Procesar secciones de primer nivel
    for sec_key, sec_val in unified_schema.items():
        if is_schema_directive(sec_key):
            continue

        if sec_key == SECTION_ASISCFG and isinstance(sec_val, dict):
            default_cfg[sec_key] = copy.deepcopy(sec_val)
            validation_rules[sec_key] = copy.deepcopy(sec_val)
            if "admin_pass_hash" in sec_val:
                admin_pass_hash = sec_val["admin_pass_hash"]
            continue

        if sec_key == SECTION_PROFILES and isinstance(sec_val, dict):
            default_cfg[sec_key] = {}
            validation_rules[sec_key] = {}

            template_def = sec_val.get("_template", {})
            if isinstance(template_def, dict):
                validation_rules[sec_key]["_template"] = {}
                for sub_sec, sub_fields in template_def.items():
                    if isinstance(sub_fields, dict):
                        profile_template[sub_sec] = {}
                        validation_rules[sec_key]["_template"][sub_sec] = {}
                        for fk, fdef in sub_fields.items():
                            norm = normalize_field_def(f"{SECTION_PROFILES}.{sub_sec}.{fk}", fdef)
                            validation_rules[sec_key]["_template"][sub_sec][fk] = norm
                            profile_template[sub_sec][fk] = norm
                            if norm.get("is_password") is True:
                                password_fields.append(f"{SECTION_PROFILES}.{sub_sec}.{fk}")
                            elif norm.get("public") is True:
                                public_fields.append(f"{SECTION_PROFILES}.{sub_sec}.{fk}")

            # Inicializar perfiles explícitos definidos en el esquema (ej. '01')
            for prof_code, prof_data in sec_val.items():
                if is_schema_directive(prof_code) or not isinstance(prof_data, dict):
                    continue
                prof_entry = {}
                for p_sec, p_fields in profile_template.items():
                    prof_entry[p_sec] = {
                        k: v.get("default") for k, v in p_fields.items() if v.get("type") != "test_connection"
                    }
                for p_sec, p_fields in prof_data.items():
                    if isinstance(p_fields, dict):
                        if p_sec not in prof_entry:
                            prof_entry[p_sec] = {}
                        for fk, fval in p_fields.items():
                            if isinstance(fval, dict):
                                if fval.get("type") == "test_connection":
                                    continue
                                val = fval.get("default", fval)
                            else:
                                val = fval
                            prof_entry[p_sec][fk] = val
                default_cfg[sec_key][prof_code] = prof_entry

            continue

        # Secciones regulares globales
        if isinstance(sec_val, dict):
            default_cfg[sec_key] = {}
            validation_rules[sec_key] = {}
            for fk, fdef in sec_val.items():
                norm = normalize_field_def(f"{sec_key}.{fk}", fdef)
                validation_rules[sec_key][fk] = norm
                if norm.get("type") != "test_connection":
                    default_cfg[sec_key][fk] = norm.get("default")
                if norm.get("is_password") is True:
                    password_fields.append(f"{sec_key}.{fk}")
                elif norm.get("public") is True:
                    public_fields.append(f"{sec_key}.{fk}")
        else:
            default_cfg[sec_key] = sec_val
            validation_rules[sec_key] = sec_val

    return {
        "default_config": default_cfg,
        "validation_rules": validation_rules,
        "profile_template": profile_template,
        "password_fields": password_fields,
        "public_fields": public_fields,
        "security_level": security_level,
        "backup_settings": backup_settings,
        "admin_pass_hash": admin_pass_hash,
    }


def load_schema_definition(schema_path: str) -> Dict[str, Any]:
    """
    Carga de forma directa el esquema desde el archivo Python especificado.
    Retorna la estructura estructurada por extract_schema_metadata.
    El archivo de esquema es obligatorio y debe definir la variable canónica 'CONFIG_SCHEMA'.
    """
    if not schema_path or not os.path.exists(schema_path):
        raise FileNotFoundError(f"Archivo de esquema no existe: '{schema_path}'")

    try:
        module_name = f"asiscfg_dynamic_schema_{abs(hash(schema_path))}"
        spec = importlib.util.spec_from_file_location(module_name, schema_path)
        if not spec or not spec.loader:
            raise RuntimeError(f"No se pudo crear especificación de módulo para el esquema: '{schema_path}'")
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
    except Exception as e:
        raise RuntimeError(f"Error al cargar el archivo de esquema '{schema_path}': {e}") from e

    if not hasattr(mod, "CONFIG_SCHEMA"):
        raise AttributeError(
            f"El archivo de esquema '{schema_path}' no define la variable canónica 'CONFIG_SCHEMA'."
        )

    raw_schema = getattr(mod, "CONFIG_SCHEMA")
    if not isinstance(raw_schema, dict):
        raise TypeError(
            f"La variable 'CONFIG_SCHEMA' en '{schema_path}' debe ser de tipo dict, se obtuvo {type(raw_schema).__name__}."
        )

    return extract_schema_metadata(raw_schema)


def _apply_field_rule(sec: str, key: str, val: Any, rule: Dict[str, Any]) -> Any:
    """Aplica de forma pura y determinista la conversión de tipo, rango (min/max) y opciones."""
    if val is None:
        return rule.get("default")

    target_type = rule.get("type", "str")
    try:
        if target_type == "int":
            if val == "":
                return rule.get("default")
            val_num = int(val)
            if "min" in rule and val_num < rule["min"]:
                return rule.get("default")
            elif "max" in rule and val_num > rule["max"]:
                return rule.get("default")
            return val_num
        elif target_type == "float":
            if val == "":
                return rule.get("default")
            val_num = float(val)
            if "min" in rule and val_num < rule["min"]:
                return rule.get("default")
            elif "max" in rule and val_num > rule["max"]:
                return rule.get("default")
            return val_num
        elif target_type == "bool":
            if isinstance(val, bool):
                return val
            return str(val).strip().lower() in ("true", "1", "yes", "si")
        elif target_type == "enum" and "options" in rule:
            opts = rule["options"]
            if str(val) not in [str(o) for o in opts]:
                return rule.get("default")
            return val
        elif target_type == "str":
            return str(val)
    except (ValueError, TypeError):
        return rule.get("default")
    return val


def validate_and_correct_config(
    config: Any,
    validation_rules: Dict[str, Any],
    default_config: Dict[str, Any],
    context: Any,
) -> Any:
    """
    Valida y sanea recursivamente los tipos de datos, rangos y opciones permitidas
    contra las reglas del esquema. Rellena claves requeridas faltantes y purga secciones espurias.
    """
    if not isinstance(config, dict):
        raise TypeError(f"El parámetro 'config' debe ser dict, recibido: {type(config).__name__}")
    if not isinstance(validation_rules, dict):
        raise TypeError(f"El parámetro 'validation_rules' debe ser dict, recibido: {type(validation_rules).__name__}")
    if not isinstance(default_config, dict):
        raise TypeError(f"El parámetro 'default_config' debe ser dict, recibido: {type(default_config).__name__}")
    if not hasattr(context, "config_file_path"):
        raise TypeError(f"El parámetro 'context' debe ser AppConfigContext, recibido: {type(context).__name__}")

    has_business_rules = any(is_business_section(k) for k in validation_rules.keys())

    # 1. Asegurar secciones generales por defecto en la raíz
    for sec_key, sec_val in default_config.items():
        if sec_key == SECTION_PROFILES:
            continue
        if sec_key not in config or not isinstance(config[sec_key], dict):
            config[sec_key] = copy.deepcopy(sec_val) if isinstance(sec_val, dict) else sec_val
        elif isinstance(sec_val, dict):
            for k, v in sec_val.items():
                if k not in config[sec_key]:
                    config[sec_key][k] = copy.deepcopy(v) if isinstance(v, (dict, list)) else v

    # 2. Validar secciones globales
    for sec_key, sec_data in list(config.items()):
        if sec_key == SECTION_PROFILES:
            continue
        if is_special_section(sec_key):
            continue
        if has_business_rules and sec_key not in validation_rules and is_business_section(sec_key):
            logging.warning(f"[VALIDATION] Sección de negocio no reconocida '{sec_key}' eliminada.")
            del config[sec_key]
            continue

        if isinstance(sec_data, dict) and sec_key in validation_rules:
            sec_rules = validation_rules[sec_key]
            if isinstance(sec_rules, dict):
                # Validar campos existentes y aplicar reglas
                for fk, fval in list(sec_data.items()):
                    if has_business_rules and fk not in sec_rules:
                        logging.warning(f"[VALIDATION] Clave no reconocida '{sec_key}.{fk}' eliminada.")
                        del sec_data[fk]
                        continue
                    rule = sec_rules.get(fk)
                    if isinstance(rule, dict):
                        if rule.get("type") == "test_connection":
                            del sec_data[fk]
                            continue
                        sec_data[fk] = _apply_field_rule(sec_key, fk, fval, rule)

    # 3. Validar perfiles (@profiles)
    prof_dict = config.get(SECTION_PROFILES)
    if isinstance(prof_dict, dict):
        prof_rules: Dict[str, Any] = {}
        if SECTION_PROFILES in validation_rules and isinstance(validation_rules[SECTION_PROFILES], dict):
            prof_rules = validation_rules[SECTION_PROFILES].get("_template", {})

        for prof_code, prof_data in list(prof_dict.items()):
            if is_schema_directive(prof_code) or not isinstance(prof_data, dict):
                continue

            # Rellenar y validar subsecciones y campos según la plantilla
            if prof_rules:
                for p_sec, p_fields in prof_rules.items():
                    if not isinstance(p_fields, dict) or is_special_section(p_sec) or is_schema_directive(p_sec):
                        continue
                    if p_sec not in prof_data or not isinstance(prof_data[p_sec], dict):
                        prof_data[p_sec] = {}
                    sec_target = prof_data[p_sec]
                    for fk, fdef in p_fields.items():
                        if not isinstance(fdef, dict):
                            continue
                        if fdef.get("type") == "test_connection":
                            if fk in sec_target:
                                del sec_target[fk]
                            continue
                        val = sec_target.get(fk)
                        sec_target[fk] = _apply_field_rule(p_sec, fk, val, fdef)

            # Purgar subsecciones y claves no reconocidas en este perfil
            for p_sec in list(prof_data.keys()):
                if prof_rules and p_sec not in prof_rules:
                    logging.warning(f"[VALIDATION] Subsección '{p_sec}' en perfil '{prof_code}' no existe en esquema.")
                    del prof_data[p_sec]
                    continue
                if isinstance(prof_data[p_sec], dict) and prof_rules:
                    sec_prules = prof_rules.get(p_sec, {})
                    for fk in list(prof_data[p_sec].keys()):
                        if fk not in sec_prules:
                            logging.warning(f"[VALIDATION] Clave '{p_sec}.{fk}' en perfil '{prof_code}' no existe en esquema.")
                            del prof_data[p_sec][fk]

    from asiscfg.models import ConfigDict

    unenc = getattr(config, "_unencrypted_passwords", []) if isinstance(config, ConfigDict) else []
    pwd_fails = getattr(config, "_password_failures", []) if isinstance(config, ConfigDict) else []
    audit_diffs = getattr(config, "_audit_diffs", []) if isinstance(config, ConfigDict) else []
    return ConfigDict(
        context,
        config,
        default_config=default_config,
        validation_rules=validation_rules,
        unencrypted_passwords=unenc,
        password_failures=pwd_fails,
        audit_diffs=audit_diffs,
    )

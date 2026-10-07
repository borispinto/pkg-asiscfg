# -*- coding: utf-8 -*-
# SPDX-FileCopyrightText: 2026 Asisnet Computacion, CA <proyectos@asisnet.net>
# SPDX-License-Identifier: MIT
# Autor: Boris Pinto <borispinto@asisnet.net>
# File: asiscfg/models.py

"""
Módulo de modelos de datos para la configuración (ConfigDict).
Proporciona navegación anidada por clave punto (.valor) y soporte multi-perfil (.valor_profile).
"""

import sys
import os
from dataclasses import dataclass, field
from typing import Dict, Any, List, Optional
from asiscfg.constants import (
    BASE_DIR,
    DEFAULT_CONFIG_FILENAME,
    DEFAULT_KEY_FILENAME,
    DEFAULT_SCHEMA_FILENAME,
    get_format_engine,
    SECTION_PROFILES,
    SECTION_ASISCFG,
    VALID_ACTIONS,
    ENC_PREFIX,
    NULL_SENTINEL,
    is_schema_directive
)


@dataclass
class AppConfigContext:
    """
    Contexto canónico unificado de ejecución para asiscfg.
    Centraliza rutas absolutas de archivos, estado criptográfico y parámetros de runtime.
    """
    config_file_path: str = ""
    config_file_name: str = ""
    key_file_path: str = ""
    key_file_name: str = ""
    schema_file_path: str = ""
    schema_file_name: str = ""
    base_dir: str = ""
    action: str = "consume"
    is_standalone: bool = False
    dev_mode: bool = False
    key_status: str = "ok"
    key_detail: str = ""
    default_config: Dict[str, Any] = field(default_factory=dict)
    validation_rules: Dict[str, Any] = field(default_factory=dict)
    profile_template: Dict[str, Any] = field(default_factory=dict)
    password_fields: List[str] = field(default_factory=list)
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
            raise ValueError(f"Acción '{self.action}' inválida en AppConfigContext. Debe ser una de: {', '.join(VALID_ACTIONS)}")
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


def resolve_schema_path(
    schema_param: Optional[str],
    default_name: str,
    base_dir: str,
    is_standalone: bool = False
) -> str:
    """
    Resuelve la ruta del archivo de esquema (config_schema.py) según el escenario:
    
    1. Escenario 1 (Compilado Individual / Standalone CLI/UI, is_standalone=True):
       - Siempre debe existir físicamente en disco (en la ruta indicada o en base_dir).
       
    2. Escenario 2 (Compilado Integrado con app cliente, is_standalone=False):
       - 1º Buscar físicamente en la ruta recibida (si se proporcionó y existe).
       - 2º Si no existe físicamente o no se suministró y la app está congelada (sys.frozen), tomar de sys._MEIPASS.
       - 3º Si está en modo interpretado:
         * Si se especificó schema_param explícito, retornar su ruta absoluta.
         * Si no se suministró schema_param, retornar "" (NUNCA tomar de base_dir).
    """
    is_frozen = bool(getattr(sys, "frozen", False) and hasattr(sys, "_MEIPASS"))

    # 1. Escenario 1: Standalone resuelve físicamente contra base_dir
    if is_standalone:
        return resolve_file_path(schema_param, default_name, base_dir)

    # 2. Escenario 2: Integrado
    # 2.1 Si se especificó una ruta explícita, verificar si existe físicamente
    if schema_param and str(schema_param).strip():
        param_str = str(schema_param).strip()
        candidate = param_str if os.path.isabs(param_str) else os.path.join(base_dir, param_str)
        candidate = os.path.abspath(candidate)
        if os.path.isdir(candidate):
            candidate = os.path.join(candidate, default_name)
        if os.path.exists(candidate):
            return candidate
        if not is_frozen:
            return candidate

    # 2.2 Si está congelado/empaquetado en app cliente: buscar en sys._MEIPASS
    if is_frozen:
        meipass_dir = getattr(sys, "_MEIPASS", "")
        candidates = [
            os.path.join(meipass_dir, default_name),
            os.path.join(meipass_dir, "src", default_name),
        ]
        if schema_param and str(schema_param).strip():
            base_name = os.path.basename(str(schema_param).strip())
            candidates.insert(0, os.path.join(meipass_dir, base_name))
            candidates.insert(1, os.path.join(meipass_dir, "src", base_name))

        for c in candidates:
            if os.path.exists(c):
                return os.path.abspath(c)

        # Si no existe en _MEIPASS, retornar la ruta empaquetada por defecto (NUNCA base_dir)
        return os.path.abspath(os.path.join(meipass_dir, default_name))

    # 2.3 En modo interpretado integrado sin schema_param: NO asumir base_dir
    return ""


def create_app_context(
    action: str = "consume",
    config_file: Optional[str] = None,
    key_file: Optional[str] = None,
    schema_file: Optional[str] = None,
    base_dir: Optional[str] = None,
    admin_pass_hash: Optional[str] = None,
    key_bytes: Optional[bytes] = None,
    format_mode: str = "plain",
    active_profile: Optional[str] = None,
    is_standalone: bool = False,
    dev_mode: bool = False,
    metadata: Optional[Dict[str, Any]] = None,
) -> AppConfigContext:
    """
    Resuelve y normaliza el contexto de ejecución canónico según la acción solicitada.
    Acciones soportadas: 'consume', 'ui', 'generate_key', 'export_schema'.
    """
    norm_action = str(action).strip().lower() if action else "consume"
    if norm_action not in VALID_ACTIONS:
        raise ValueError(f"Acción '{action}' inválida. Debe ser una de: {', '.join(VALID_ACTIONS)}")

    engine = get_format_engine(format_mode)
    base_dir = os.path.abspath(base_dir) if (base_dir and base_dir.strip()) else BASE_DIR    
    resolved_config = resolve_file_path(config_file, DEFAULT_CONFIG_FILENAME, base_dir)
    resolved_key = resolve_file_path(key_file, DEFAULT_KEY_FILENAME, base_dir)
    resolved_schema = resolve_schema_path(schema_file, DEFAULT_SCHEMA_FILENAME, base_dir, is_standalone=is_standalone)

    # 1. Instanciación única con los valores base resueltos
    ctx = AppConfigContext(
        config_file_path=resolved_config,
        config_file_name=os.path.basename(resolved_config),
        key_file_path=resolved_key,
        key_file_name=os.path.basename(resolved_key),
        schema_file_path=resolved_schema,
        schema_file_name=os.path.basename(resolved_schema),
        base_dir=base_dir,
        action=norm_action,
        is_standalone=is_standalone,
        dev_mode=dev_mode,
        key_bytes=key_bytes,
        format_mode=engine.mode_id,
        active_profile=active_profile,
        metadata=dict(metadata) if metadata else {},
    )

    # Para acciones de utilidad que no requieren validar clave ni cargar esquema
    if norm_action in ["generate_key", "export_schema"]:
        return ctx

    # 2. Verificación y resolución de clave criptográfica (key_file_path)
    key_status = "ok"
    key_detail = ""
    if ctx.key_bytes is None:
        if not os.path.exists(resolved_key):
            key_status = "missing"
            key_detail = f"El archivo de clave no existe en la ruta: {resolved_key}"
        elif os.path.getsize(resolved_key) == 0:
            key_status = "empty"
            key_detail = f"El archivo de clave está vacío (0 bytes): {resolved_key}"
        else:
            try:
                with open(resolved_key, "rb") as f:
                    ctx.key_bytes = f.read().strip()
            except Exception as e:
                key_status = "corrupted"
                key_detail = f"Error al leer el archivo de clave: {e}"

    ctx.key_status = key_status
    ctx.key_detail = key_detail

    # 3. Carga del esquema mediante el proceso 100% nuevo (solo ve schema_file_path)
    from asiscfg.schema import load_schema_definition
    schema_info = load_schema_definition(resolved_schema)
    ctx.default_config = schema_info.get("default_config", {})
    ctx.validation_rules = schema_info.get("validation_rules", {})
    ctx.profile_template = schema_info.get("profile_template", {})
    ctx.password_fields = schema_info.get("password_fields", [])
    ctx.backup_settings = schema_info.get("backup_settings", {})

    # 4. Asignación de admin_pass_hash
    resolved_admin_hash = admin_pass_hash
    if not resolved_admin_hash:
        resolved_admin_hash = ctx.default_config.get(SECTION_ASISCFG, {}).get("admin_pass_hash")

    ctx.admin_pass_hash = resolved_admin_hash

    return ctx


class ConfigDict(dict):
    """
    Estructura de datos basada en dict con métodos de conveniencia para acceder
    a configuraciones globales (.valor, .valorpass) y por perfil (.valor_profile, .valorpass_profile).
    """

    def __init__(
        self,
        context: AppConfigContext,
        *args,
        default_config: Optional[Dict[str, Any]] = None,
        validation_rules: Optional[Dict[str, Any]] = None,
        unencrypted_passwords: Optional[List[Any]] = None,
        password_failures: Optional[List[Dict[str, Any]]] = None,
        **kwargs
    ):
        super().__init__(*args, **kwargs)
        self.context = context
        self._default_config = default_config if default_config is not None else context.default_config
        self._validation_rules = validation_rules if validation_rules is not None else context.validation_rules
        self._key_path = context.key_file_path
        self._key = context.key_bytes
        self.format_mode = context.format_mode
        self._unencrypted_passwords = list(unencrypted_passwords) if unencrypted_passwords else []
        self._password_failures = list(password_failures) if password_failures else []

    def get_unencrypted_passwords(self) -> List[Any]:
        """Retorna la lista de parámetros protegidos detectados sin cifrar o con fallas en el archivo."""
        return list(self._unencrypted_passwords)

    def get_password_failures(self) -> List[Dict[str, Any]]:
        """Retorna la lista de fallas detectadas en campos de contraseña."""
        return list(self._password_failures)

    def set_default_config(self, default_config: Dict[str, Any]) -> None:
        """Establece el esquema por defecto para fallbacks."""
        self._default_config = default_config or {}

    def set_validation_rules(self, validation_rules: Dict[str, Any]) -> None:
        """Establece las reglas de validación y metadata del esquema."""
        self._validation_rules = validation_rules or {}

    def set_key_path(self, key_path: str) -> None:
        """Establece la ruta de la clave de cifrado y resetea la clave en memoria si la ruta cambia."""
        if self._key_path != key_path:
            self._key_path = key_path
            self._key = None
            self.context.key_file_path = key_path
            self.context.key_bytes = None

    def set_key(self, key: Any) -> None:
        """Establece directamente la clave activa de cifrado."""
        self._key = key
        self.context.key_bytes = key

    def _get_key(self) -> Optional[Any]:
        """Obtiene la clave criptográfica en bytes desde el contexto o la instancia."""
        if self._key is not None:
            return self._key
        if self.context.key_bytes is not None:
            self._key = self.context.key_bytes
            return self._key
        return None

    def _is_password_field(self, key_path: str, profile_code: str = "") -> bool:
        """Verifica si la clave es contraseña consultando directamente la lista del contexto."""
        target_key = f"{SECTION_PROFILES}.{key_path}" if profile_code else key_path
        return target_key in self.context.password_fields

    def _decrypt_value(self, val: Any) -> str:
        """Descifra de forma Just-In-Time (JIT) un valor protegido delegando al motor criptográfico del contexto."""
        if val is None or val == "" or val == NULL_SENTINEL:
            return ""
        if not isinstance(val, str):
            val = str(val)
        if val.startswith(ENC_PREFIX):
            key = self._get_key()
            if key:
                try:
                    engine = get_format_engine(self.context.format_mode)
                    dec_str = engine.decrypt_field(val, key)
                    if dec_str == NULL_SENTINEL:
                        return ""
                    return dec_str
                except Exception:
                    return val
            return val
        elif any((isinstance(u, (tuple, list)) and len(u) > 1 and str(u[1]) == val) for u in self._unencrypted_passwords):
            return val
        else:
            val = f"ERR_ENCRYPTION({val})"
        return val

    def _get_only_value(
        self,
        key_path: str,
        default: Any = None,
        is_pass_mode: bool = False,
        sep: str = "."
    ) -> Any:
        """Obtiene el valor crudo en memoria o en el esquema por defecto sin procesar enmascaramiento."""
        claves = key_path.split(sep)
        valor = self

        for clave in claves:
            if isinstance(valor, dict) and clave in valor:
                valor = valor[clave]
            else:
                valor = None
                break

        if valor is None and isinstance(self._default_config, dict):
            def_val = self._default_config
            for clave in claves:
                if isinstance(def_val, dict) and clave in def_val:
                    def_val = def_val[clave]
                else:
                    def_val = None
                    break
            if def_val is not None:
                valor = def_val

        if valor is None:
            valor = default

        if is_pass_mode and valor is not None:
            valor = self._decrypt_value(valor)

        return valor

    def _get_raw_unique_value(
        self,
        key_path: str,
        profile_code: str = "",
        key_path_parent: str = "",
        default: Any = None,
        is_pass_mode: bool = False,
        is_parent: bool = False,
        valor_compara: Any = None,
        debug: bool = False
    ) -> Any:
        """
        Punto único de resolución de valores y evaluación de parámetros protegidos (password).

        - key_path: Clave en notación por puntos (ej. 'database.password' o 'database').
        - profile_code: Código del perfil si aplica (ej. '01').
        - key_path_parent: Clave en notación por puntos del padre si aplica, por defecto es key_path (ej. 'database').
        - default: Valor de respaldo si la clave no existe.
        - is_parent: Si True, resuelve con herencia en cascada (Perfil -> Global -> Default).
        - is_pass_mode: Si True, opera en modo valorpass (espera campo password para desencriptar).
                        Si False, opera en modo valor (espera campo regular para entregar valor plano).
        - valor_compara: Si no es None y el campo es password, retorna True/False según coincidencia.
        """
        is_pwd = self._is_password_field(key_path, profile_code=profile_code)
        if not is_pwd and is_parent:
            parent_key = key_path_parent if key_path_parent else key_path
            is_pwd = self._is_password_field(parent_key)

        if debug:
            print(f"DEBUG: [ASISCFG] _get_raw_unique_value - key_path: {key_path}, profile_code: {profile_code}, key_path_parent: {key_path_parent}, default: {default}, is_pass_mode: {is_pass_mode}, is_parent: {is_parent}, valor_compara: {valor_compara}, is_pwd: {is_pwd}")
        # 1. Enmascaramiento si el tipo de campo no coincide con el modo de acceso
        if not is_pass_mode and is_pwd:
            return f"<pass_{key_path}>"
        if is_pass_mode and not is_pwd:
            return f"<var_{key_path}>"

        def _is_empty(v: Any) -> bool:
            if v is None:
                return True
            if isinstance(v, str) and v.strip() == "":
                return True
            return False

        raw_val = None
        if is_parent:
            if profile_code:
                profile_target_key = f"{SECTION_PROFILES}.{profile_code}.{key_path}"
                val = self._get_only_value(profile_target_key, default=None, is_pass_mode=is_pass_mode)
                if not _is_empty(val):
                    raw_val = val

            if raw_val is None:
                parent_target_key = key_path_parent if key_path_parent else key_path
                val = self._get_only_value(parent_target_key, default=None, is_pass_mode=is_pass_mode)
                if not _is_empty(val):
                    raw_val = val

            if raw_val is None:
                raw_val = default
        else:
            target_key = f"{SECTION_PROFILES}.{profile_code}.{key_path}" if profile_code else key_path
            raw_val = self._get_only_value(target_key, default=default, is_pass_mode=is_pass_mode)

        if is_pwd and valor_compara is not None:
            raw_val = (raw_val == str(valor_compara))

        return raw_val

    def valor(self, key_path: str, default: Any = None) -> Any:
        """
        Acceso a configuraciones generales/globales usando notación por puntos (ej. 'seccion.clave').
        Si el parámetro es de tipo contraseña, retorna la máscara '<pass_{key_path}>'.
        """
        return self._get_raw_unique_value(
            key_path=key_path,
            default=default
        )

    def valor_profile(self, profile_code: str, key_path: str, default: Any = None, debug: bool = False) -> Any:
        """
        Acceso directo a configuraciones de un perfil específico.
        Si el parámetro es de tipo contraseña, retorna la máscara '<pass_{key_path}>'.
        """
        return self._get_raw_unique_value(
            key_path=key_path,
            profile_code=profile_code,
            default=default,
            debug=debug
        )

    def valor_parent(
        self,
        key_path: str,
        profile_code: str = "",
        default: Any = "",
        key_path_parent: str = "",
        debug: bool = False
    ) -> Any:
        """
        Retorna el valor con herencia jerárquica en cascada: 
        Perfil (@profiles.<profile_code>.<key_path>) -> Global (<key_path_parent|key_path>) -> Default.
        Si el parámetro es de tipo contraseña, retorna la máscara '<pass_{key_path}>'.
        """
        return self._get_raw_unique_value(
            key_path=key_path,
            profile_code=profile_code,
            key_path_parent=key_path_parent,
            default=default,
            is_parent=True,
            debug=debug
        )

    def valorpass(self, key_path: str, default: Any = "", valor_compara: Any = None) -> Any:
        """
        Acceso seguro Just-In-Time (JIT) a parámetros protegidos de tipo contraseña.
        - Si el campo NO es contraseña: retorna la máscara '<var_{key_path}>'.
        - Si el campo ES contraseña:
            - Si 'valor_compara' is not None: retorna True si coincide con el valor desencriptado, False si no.
            - Si 'valor_compara' is None: retorna el valor desencriptado.
        """
        return self._get_raw_unique_value(
            key_path=key_path,
            default=default,
            is_pass_mode=True,
            valor_compara=valor_compara
        )

    def valorpass_profile(
        self,
        profile_code: str,
        key_path: str,
        default: Any = "",
        valor_compara: Any = None
    ) -> Any:
        """
        Acceso seguro Just-In-Time (JIT) a parámetros protegidos de perfil.
        - Si el campo NO es contraseña: retorna la máscara '<var_{key_path}>'.
        - Si el campo ES contraseña:
            - Si 'valor_compara' is not None: retorna True si coincide con el valor desencriptado, False si no.
            - Si 'valor_compara' is None: retorna el valor desencriptado.
        """
        return self._get_raw_unique_value(
            key_path=key_path,
            profile_code=profile_code,
            default=default,
            is_pass_mode=True,
            valor_compara=valor_compara
        )

    def valorpass_parent(
        self,
        key_path: str,
        profile_code: str = "",
        default: Any = "",
        key_path_parent: str = "",
        valor_compara: Any = None,
        debug: bool = False
    ) -> Any:
        """
        Acceso seguro Just-In-Time (JIT) con herencia en cascada para parámetros de tipo contraseña.
        - Si el campo NO es contraseña: retorna la máscara '<var_{key_path}>'.
        - Si el campo ES contraseña:
            - Si 'valor_compara' is not None: retorna True si coincide con el valor desencriptado, False si no.
            - Si 'valor_compara' is None: retorna el valor desencriptado.
        """
        return self._get_raw_unique_value(
            key_path=key_path,
            profile_code=profile_code,
            key_path_parent=key_path_parent,
            default=default,
            is_pass_mode=True,
            is_parent=True,
            valor_compara=valor_compara,
            debug=debug
        )

    def get_profiles(self) -> List[str]:
        """Retorna la lista de códigos de perfiles registrados bajo '@profiles' o lista vacía."""
        profiles = self.get(SECTION_PROFILES)
        if isinstance(profiles, dict) and profiles:
            return [k for k in profiles.keys() if not is_schema_directive(k)]
        return []

    def has_profiles(self) -> bool:
        """Indica si la configuración utiliza el módulo multiperfil ('@profiles')."""
        return len(self.get_profiles()) > 0

    def get_profile_config(self, profile_code: str) -> dict:
        """Retorna el diccionario de configuración completo del perfil indicado."""
        profiles = self.get(SECTION_PROFILES)
        if isinstance(profiles, dict) and profile_code in profiles:
            return profiles[profile_code]
        return {}




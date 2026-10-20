# -*- coding: utf-8 -*-
# SPDX-FileCopyrightText: 2026 ASISNET Computación, CA <proyectos@asisnet.net>
# SPDX-FileCopyrightText: 2026 Boris Pinto <borispinto@gmail.com>
# SPDX-License-Identifier: MIT
# Autor: Boris Pinto <borispinto@gmail.com>
# Contacto Institucional: ASISNET Computación, CA <proyectos@asisnet.net>
# File: asiscfg/models.py

"""
Modelos de datos en memoria para la configuración (Nivel 4 y 5).
ConfigDict proporciona navegación anidada (.valor, .valorpass) con ultra alta velocidad O(1).
ConfigBootstrap proporciona retorno estructurado inmutable con mínima sobrecarga de memoria (__slots__).
"""

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Set

from asiscfg.constants import (
    ENC_PREFIX,
    NULL_SENTINEL,
    SECTION_PROFILES,
    is_schema_directive,
)
from asiscfg.context import AppConfigContext
from asiscfg.crypto import FORMAT_MODES, get_format_engine


class ConfigDict(dict):
    """
    Estructura de datos en memoria basada en dict para configuración.
    Optimizado para consultas frecuentes O(1) y evaluación Just-In-Time (JIT) de contraseñas.
    """

    def __init__(
        self,
        context: AppConfigContext,
        *args,
        default_config: Optional[Dict[str, Any]] = None,
        validation_rules: Optional[Dict[str, Any]] = None,
        unencrypted_passwords: Optional[List[Any]] = None,
        password_failures: Optional[List[Dict[str, Any]]] = None,
        audit_diffs: Optional[List[Any]] = None,
        **kwargs,
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
        self._audit_diffs = list(audit_diffs) if audit_diffs else []
        self._pwd_set: Set[str] = set(context.password_fields) if context else set()

    def get_unencrypted_passwords(self) -> List[Any]:
        """Retorna la lista de parámetros protegidos detectados sin cifrar o con fallas en el archivo."""
        return list(self._unencrypted_passwords)

    def get_password_failures(self) -> List[Dict[str, Any]]:
        """Retorna la lista de fallas detectadas en campos de contraseña."""
        return list(self._password_failures)

    def get_audit_diffs(self) -> List[Any]:
        """Retorna diferencias forenses detectadas en modo PLAIN (security_level = 1)."""
        return list(self._audit_diffs)

    def set_default_config(self, default_config: Dict[str, Any]) -> None:
        """Establece el esquema por defecto para fallbacks."""
        self._default_config = default_config or {}

    def set_validation_rules(self, validation_rules: Dict[str, Any]) -> None:
        """Establece las reglas de validación y metadata del esquema."""
        self._validation_rules = validation_rules or {}

    def set_key_path(self, key_path: str) -> None:
        """Establece la ruta de la clave de cifrado y resetea la clave en memoria si cambia."""
        if self._key_path != key_path:
            self._key_path = key_path
            self._key = None
            if self.context:
                self.context.key_file_path = key_path
                self.context.key_bytes = None

    def set_key(self, key: Any) -> None:
        """Establece directamente la clave activa de cifrado."""
        self._key = key
        if self.context:
            self.context.key_bytes = key

    def _get_key(self) -> Optional[Any]:
        """Obtiene la clave criptográfica en bytes desde el contexto o la instancia."""
        if self._key is not None:
            return self._key
        if self.context and self.context.key_bytes is not None:
            self._key = self.context.key_bytes
            return self._key
        return None

    def _is_password_field(self, key_path: str, profile_code: str = "") -> bool:
        """Verifica en O(1) si la clave es contraseña consultando directamente el set indexado."""
        target_key = f"{SECTION_PROFILES}.{key_path}" if profile_code else key_path
        return target_key in self._pwd_set

    def _decrypt_value(self, val: Any, key_path: str = "") -> str:
        """Descifra de forma Just-In-Time (JIT) un valor protegido delegando al motor criptográfico."""
        if val is None or val == "" or val == NULL_SENTINEL:
            return ""
        if not isinstance(val, str):
            val = str(val)
        if val.startswith(ENC_PREFIX):
            key = self._get_key()
            if key:
                try:
                    engine = FORMAT_MODES.get(self.context.format_mode)
                    if not engine:
                        engine = get_format_engine(self.context.format_mode)
                    dec_str = engine.decrypt_field(val, key)
                    if dec_str == NULL_SENTINEL:
                        return ""
                    return dec_str
                except Exception:
                    return val
            return val
        elif any(
            (isinstance(u, (tuple, list)) and (
                (len(u) > 1 and str(u[1]) == val) or
                (bool(key_path) and str(u[0]) == key_path)
            ))
            for u in self._unencrypted_passwords
        ):
            return val
        elif any(
            (isinstance(f, dict) and bool(key_path) and f.get("field_path") == key_path)
            for f in self._password_failures
        ):
            return val
        else:
            val = f"ERR_ENCRYPTION({val})"
        return val

    def _get_only_value(
        self,
        key_path: str,
        default: Any = None,
        is_pass_mode: bool = False,
        sep: str = ".",
    ) -> Any:
        """Obtiene el valor en memoria o en el esquema por defecto sin procesar enmascaramiento."""
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
            valor = self._decrypt_value(valor, key_path=key_path)

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
        debug: bool = False,
    ) -> Any:
        """Punto único de resolución de valores y evaluación de parámetros protegidos (Nivel 5)."""
        is_pwd = self._is_password_field(key_path, profile_code=profile_code)
        if not is_pwd and is_parent:
            parent_key = key_path_parent if key_path_parent else key_path
            is_pwd = self._is_password_field(parent_key)

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
            raw_val = raw_val == str(valor_compara)

        return raw_val

    def valor(self, key_path: str, default: Any = None) -> Any:
        """Acceso a configuraciones generales/globales usando notación por puntos (ej. 'app.name')."""
        return self._get_raw_unique_value(key_path=key_path, default=default)

    def valor_profile(
        self, key_path: str, profile_code: str, default: Any = None, debug: bool = False
    ) -> Any:
        """Acceso directo a configuraciones de un perfil específico."""
        return self._get_raw_unique_value(
            key_path=key_path,
            profile_code=profile_code,
            default=default,
            debug=debug,
        )

    def valor_parent(
        self,
        key_path: str,
        profile_code: str = "",
        default: Any = "",
        key_path_parent: str = "",
        debug: bool = False,
    ) -> Any:
        """Retorna el valor con herencia jerárquica en cascada: Perfil -> Global -> Default."""
        return self._get_raw_unique_value(
            key_path=key_path,
            profile_code=profile_code,
            key_path_parent=key_path_parent,
            default=default,
            is_parent=True,
            debug=debug,
        )

    def valorpass(self, key_path: str, default: Any = "", valor_compara: Any = None) -> Any:
        """Acceso seguro Just-In-Time (JIT) a parámetros protegidos de tipo contraseña."""
        return self._get_raw_unique_value(
            key_path=key_path,
            default=default,
            is_pass_mode=True,
            valor_compara=valor_compara,
        )

    def valorpass_profile(
        self,
        key_path: str,
        profile_code: str,
        default: Any = "",
        valor_compara: Any = None,
    ) -> Any:
        """Acceso seguro Just-In-Time (JIT) a parámetros protegidos de perfil."""
        return self._get_raw_unique_value(
            key_path=key_path,
            profile_code=profile_code,
            default=default,
            is_pass_mode=True,
            valor_compara=valor_compara,
        )

    def valorpass_parent(
        self,
        key_path: str,
        profile_code: str = "",
        default: Any = "",
        key_path_parent: str = "",
        valor_compara: Any = None,
        debug: bool = False,
    ) -> Any:
        """Acceso seguro Just-In-Time (JIT) con herencia en cascada para parámetros de tipo contraseña."""
        return self._get_raw_unique_value(
            key_path=key_path,
            profile_code=profile_code,
            key_path_parent=key_path_parent,
            default=default,
            is_pass_mode=True,
            is_parent=True,
            valor_compara=valor_compara,
            debug=debug,
        )

    def get_profiles(self) -> List[str]:
        """Retorna la lista de códigos de perfiles registrados bajo '@profiles' o lista vacía."""
        profiles = self.get(SECTION_PROFILES)
        if isinstance(profiles, dict) and profiles:
            return sorted([k for k in profiles.keys() if not is_schema_directive(k)])
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

    def save(self, config_path: Optional[str] = None) -> Optional[str]:
        """Persiste el estado actual de la configuración en disco usando su contexto asociado."""
        from asiscfg.storage import save_config

        return save_config(self.context, self, config_path=config_path)


@dataclass(frozen=True, slots=True)
class ConfigBootstrap:
    """
    Resultado estructurado inmutable retornado por init_app_config.
    Proporciona acceso tipado a la configuración, contexto, argumentos restantes y banderas de ejecución.
    """

    config: Optional[ConfigDict] = None
    context: Optional[AppConfigContext] = None
    exit_code: Optional[int] = None
    remaining_args: List[str] = field(default_factory=list)
    params: Dict[str, Any] = field(default_factory=dict)
    debug: bool = False
    dev_mode: bool = False
    show_modals: bool = False

    def param(self, key: str, default: Any = None) -> Any:
        """Acceso tipado directo a parámetros parseados y validados de la aplicación."""
        return self.params.get(key, default)

    def valor(self, key_path: str, default: Any = None) -> Any:
        """Acceso a valor global delegando directamente en la configuración cargada."""
        if self.config is None:
            return default
        return self.config.valor(key_path, default=default)

    def valorpass(self, key_path: str, default: Any = "", valor_compara: Any = None) -> str:
        """Acceso a contraseña global desencriptada delegando en la configuración cargada."""
        if self.config is None:
            return default
        return self.config.valorpass(key_path, default=default, valor_compara=valor_compara)

    def valor_profile(
        self, key_path: str, profile_code: str, default: Any = None, debug: bool = False
    ) -> Any:
        """Acceso a valor por perfil delegando en la configuración cargada."""
        if self.config is None:
            return default
        return self.config.valor_profile(key_path, profile_code, default=default, debug=debug)

    def valorpass_profile(
        self,
        key_path: str,
        profile_code: str,
        default: Any = "",
        valor_compara: Any = None,
    ) -> str:
        """Acceso a contraseña por perfil desencriptada delegando en la configuración cargada."""
        if self.config is None:
            return default
        return self.config.valorpass_profile(
            key_path, profile_code, default=default, valor_compara=valor_compara
        )

    def valor_parent(
        self,
        key_path: str,
        profile_code: str = "",
        default: Any = "",
        key_path_parent: str = "",
        debug: bool = False,
    ) -> Any:
        """Acceso con herencia jerárquica en cascada delegando en la configuración cargada."""
        if self.config is None:
            return default
        return self.config.valor_parent(
            key_path,
            profile_code=profile_code,
            default=default,
            key_path_parent=key_path_parent,
            debug=debug,
        )

    def valorpass_parent(
        self,
        key_path: str,
        profile_code: str = "",
        default: Any = "",
        key_path_parent: str = "",
        valor_compara: Any = None,
        debug: bool = False,
    ) -> str:
        """Acceso a contraseña con herencia en cascada delegando en la configuración cargada."""
        if self.config is None:
            return default
        return self.config.valorpass_parent(
            key_path,
            profile_code=profile_code,
            default=default,
            key_path_parent=key_path_parent,
            valor_compara=valor_compara,
            debug=debug,
        )

    def save(self, config_path: Optional[str] = None) -> Optional[str]:
        """Persiste la configuración en disco delegando en la instancia activa."""
        if self.config is None:
            raise RuntimeError("No hay una instancia de configuración activa cargada para guardar.")
        return self.config.save(config_path=config_path)

    def __getattr__(self, name: str) -> Any:
        if self.config is not None and hasattr(self.config, name):
            return getattr(self.config, name)
        raise AttributeError(f"'{type(self).__name__}' object has no attribute '{name}'")

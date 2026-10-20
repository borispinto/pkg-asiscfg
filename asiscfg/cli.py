# -*- coding: utf-8 -*-
# SPDX-FileCopyrightText: 2026 ASISNET Computación, CA <proyectos@asisnet.net>
# SPDX-FileCopyrightText: 2026 Boris Pinto <borispinto@gmail.com>
# SPDX-License-Identifier: MIT
# Autor: Boris Pinto <borispinto@gmail.com>
# Contacto Institucional: ASISNET Computación, CA <proyectos@asisnet.net>
# File: asiscfg/cli.py

"""
Módulo de interfaz de línea de comandos (CLI) y arranque canónico para aplicaciones anfitrionas (Nivel 1).
"""

import argparse
import os
import sys
from typing import Any, Dict, List, Optional, Sequence, Tuple

from asiscfg.constants import (
    DEFAULT_CONFIG_FILENAME,
    DEFAULT_KEY_FILENAME,
)
from asiscfg.context import create_app_context
from asiscfg.crypto import FORMAT_MODES
from asiscfg.models import ConfigBootstrap
from asiscfg.security import is_admin
from asiscfg.storage import execute_app_action, generate_key_file, load_config, save_config


def normalize_app_help_and_params(
    app_help: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """
    Normaliza y valida estrictamente la definición declarativa de ayuda y parámetros del anfitrión.
    Acepta exclusivamente un diccionario con la directiva 'params' o None. No realiza adivinanzas.

    Campos mínimos requeridos por cada parámetro:
    - 'name': Nombre canónico del parámetro (opcional si coincide con la clave en 'params').
    - 'type': Tipo de dato determinista (ej. str, int, float, bool).

    Ejemplo Mínimo:
    ----------------
    app_help = {
        "params": {
            "empresa": {"name": "empresa", "type": str},
            "silent": {"name": "silent", "type": bool},
        }
    }

    Ejemplo Completo:
    -----------------
    app_help = {
        "description": "Procesador de Asientos Contables",
        "epilog": "Ejemplo: asientos.exe 202610010001 02 /empresa:01 --silent",
        "usage": "asientos.exe [opciones] comprobante origen",
        "params": {
            "empresa": {
                "name": "empresa",
                "type": str,
                "required": True,
                "choices": ["01", "02", "03"],
                "default": "01",
                "help": "Código de empresa contable a procesar",
                "aliases": ["cia", "company"],
            },
            "fecha": {
                "name": "fecha",
                "type": str,
                "required": False,
                "default": None,
                "help": "Fecha contable en formato YYYY-MM-DD",
            },
            "silent": {
                "name": "silent",
                "type": bool,
                "default": False,
                "help": "Ejecutar en modo desatendido sin interfaces",
            },
            "reintentos": {
                "name": "reintentos",
                "type": int,
                "default": 3,
                "help": "Número máximo de reintentos de conexión",
            },
        },
    }
    """
    result: Dict[str, Any] = {
        "description": None,
        "epilog": None,
        "usage": None,
        "formatter_class": None,
        "params": {},
    }

    if app_help is None:
        return result

    if not isinstance(app_help, dict):
        raise TypeError(
            f"app_help debe ser de tipo dict o None, se recibió {type(app_help).__name__}."
        )

    result["description"] = app_help.get("description")
    result["epilog"] = app_help.get("epilog")
    result["usage"] = app_help.get("usage")
    result["formatter_class"] = app_help.get("formatter_class")
    raw_params = app_help.get("params", {})

    if not isinstance(raw_params, dict):
        raise TypeError(
            f"La directiva 'params' en app_help debe ser un dict, se recibió {type(raw_params).__name__}."
        )

    for p_name, p_spec in raw_params.items():
        if not isinstance(p_spec, dict):
            raise TypeError(
                f"La especificación del parámetro '{p_name}' debe ser un dict, se recibió {type(p_spec).__name__}."
            )

        if "type" not in p_spec or p_spec["type"] is None:
            raise ValueError(
                f"El parámetro '{p_name}' debe especificar obligatoriamente 'type' (ej. str, int, float, bool)."
            )

        p_type = p_spec["type"]
        is_bool = p_type is bool
        name = str(p_spec.get("name") or p_name).strip()
        if not name:
            raise ValueError(f"El parámetro '{p_name}' debe tener un 'name' no vacío.")

        result["params"][name] = {
            "name": name,
            "type": p_type,
            "is_bool": is_bool,
            "default": p_spec.get("default", False if is_bool else None),
            "required": bool(p_spec.get("required", False)),
            "choices": p_spec.get("choices"),
            "help": p_spec.get("help", ""),
            "aliases": list(p_spec.get("aliases", [])),
        }

    return result


def parse_config_args(
    args: Optional[Sequence[str]] = None,
    default_action: str = "consume",
    app_params: Optional[Dict[str, Any]] = None,
) -> Tuple[Dict[str, Any], List[str]]:
    """
    Parsea y extrae de una lista de argumentos los tokens reconocidos por asiscfg y la aplicación,
    retornando un diccionario con los tokens y la lista de argumentos no consumidos
    en su orden relativo original (preservando argumentos posicionales del anfitrión).
    """
    if args is None:
        args = sys.argv[1:]
    elif isinstance(args, str):
        try:
            import shlex
            args = shlex.split(args, posix=False)
        except Exception:
            args = args.split()

    raw_tokens: List[str] = []
    for arg in args:
        if arg is None:
            continue
        arg_str = str(arg).strip()
        if not arg_str:
            continue
        if (arg_str.startswith('"') and arg_str.endswith('"')) or (
            arg_str.startswith("'") and arg_str.endswith("'")
        ):
            arg_str = arg_str[1:-1].strip()
        if arg_str:
            raw_tokens.append(arg_str)

    tokens: Dict[str, Any] = {
        "action": default_action,
        "export_schema": False,
        "generate_key": False,
        "ui": False,
        "config_file": None,
        "key_file": None,
        "schema_file": None,
        "format_mode": "plain",
        "i18n_path": None,
        "theme": "dark",
        "dev_mode": False,
        "debug": False,
        "show": False,
        "last_resource": False,
        "edit": False,
        "reset_admin_pass": False,
        "overwrite_key": False,
        "install": False,
        "help": False,
    }

    if app_params:
        for p_name, p_spec in app_params.items():
            tokens[p_name] = p_spec.get("default")

    remaining_args: List[str] = []

    separadores = ["/", "-", "--"]

    value_flag_bases = {
        "config-file": "config_file",
        "key-file": "key_file",
        "schema-file": "schema_file",
        "format-mode": "format_mode",
        "i18n-path": "i18n_path",
        "theme": "theme",
    }
    bool_flag_bases = {
        "export-schema": ("export_schema", True),
        "generate-key": ("generate_key", True),
        "ui": ("ui", True),
        "edit": ("edit", True),
        "dev": ("dev_mode", True),
        "debug": ("debug", True),
        "show": ("show", True),
        "last-resource": ("last_resource", True),
        "reset-admin-pass": ("reset_admin_pass", True),
        "overwrite-key": ("overwrite_key", True),
        "install": ("install", True),
        "help": ("help", True),
        "h": ("help", True),
        "?": ("help", True),
    }

    if app_params:
        for p_name, p_spec in app_params.items():
            is_bool = p_spec.get("is_bool", False)
            all_names = [p_name] + p_spec.get("aliases", [])
            for name_variant in all_names:
                clean_name = name_variant.lstrip("-/")
                if is_bool:
                    bool_flag_bases[clean_name] = (p_name, True)
                    bool_flag_bases[clean_name.replace("_", "-")] = (p_name, True)
                else:
                    value_flag_bases[clean_name] = p_name
                    value_flag_bases[clean_name.replace("_", "-")] = p_name

    value_flags = {
        f"{sep}{name}": key
        for name, key in value_flag_bases.items()
        for sep in separadores
    }

    bool_flags = {
        f"{sep}{name}": val
        for name, val in bool_flag_bases.items()
        for sep in separadores
    }

    idx = 0
    n = len(raw_tokens)
    while idx < n:
        tok = raw_tokens[idx]
        tok_lower = tok.lower()

        if tok_lower in value_flags:
            key_name = value_flags[tok_lower]
            if idx + 1 < n:
                val = raw_tokens[idx + 1]
                tokens[key_name] = val
                idx += 2
                continue
            else:
                idx += 1
                continue

        consumed_prefix = False
        for flag_name, key_name in value_flags.items():
            if tok_lower.startswith(f"{flag_name}=") or tok_lower.startswith(f"{flag_name}:"):
                val = tok[len(flag_name) + 1 :].strip()
                if (val.startswith('"') and val.endswith('"')) or (
                    val.startswith("'") and val.endswith("'")
                ):
                    val = val[1:-1].strip()
                tokens[key_name] = val
                consumed_prefix = True
                break
        if consumed_prefix:
            idx += 1
            continue

        if tok_lower in bool_flags:
            key_name, bool_val = bool_flags[tok_lower]
            tokens[key_name] = bool_val
            idx += 1
            continue

        remaining_args.append(tok)
        idx += 1

    # Precedencia de acción
    if tokens.get("install"):
        tokens["action"] = "install"
    elif tokens.get("export_schema"):
        tokens["action"] = "export_schema"
    elif tokens.get("generate_key"):
        tokens["action"] = "generate_key"
    elif tokens.get("ui"):
        tokens["action"] = "ui"
    else:
        tokens["action"] = default_action

    return tokens, remaining_args


def add_config_arguments(parser: argparse.ArgumentParser) -> None:
    """Registra en el ArgumentParser las opciones estándar del CLI."""
    parser.add_argument("--config-file", type=str, help="Ruta al archivo de configuración.")
    parser.add_argument("--key-file", type=str, help="Ruta al archivo de clave.")
    parser.add_argument("--schema-file", type=str, help="Ruta al archivo de esquema.")
    parser.add_argument(
        "--format-mode",
        type=str,
        choices=list(FORMAT_MODES.keys()),
        default="plain",
        help="Modo de formato y motor criptográfico.",
    )
    parser.add_argument("--ui", action="store_true", help="Iniciar interfaz gráfica de administración.")
    parser.add_argument("--generate-key", action="store_true", help="Generar un nuevo archivo de clave.")
    parser.add_argument("--export-schema", action="store_true", help="Exportar archivo de esquema.")
    parser.add_argument("--edit", action="store_true", help="Habilitar edición de la sección de aplicación.")
    parser.add_argument("--dev", action="store_true", help="Modo desarrollador.")
    parser.add_argument("--debug", action="store_true", help="Modo depuración detallado.")
    parser.add_argument("--show", action="store_true", help="Mostrar diálogos modales emergentes.")
    parser.add_argument("--install", action="store_true", help="Modo instalación asistida.")


def create_cli_parser(
    prog: str = "asiscfg",
    app_help: Any = None,
    help_info: Optional[Dict[str, Any]] = None,
) -> argparse.ArgumentParser:
    """Crea y configura el parser canónico de argumentos para el CLI."""
    description = "Herramienta de Configuración Cifrada (asiscfg)"
    epilog = None
    usage = None
    formatter_class = argparse.RawDescriptionHelpFormatter

    if help_info is None and app_help is not None:
        help_info = normalize_app_help_and_params(app_help)

    if help_info:
        if help_info.get("description"):
            description = help_info["description"]
        elif prog != "asiscfg":
            description = f"Herramienta {prog}"

        if help_info.get("epilog"):
            epilog = help_info["epilog"]
        if help_info.get("usage"):
            usage = help_info["usage"]
        if help_info.get("formatter_class"):
            formatter_class = help_info["formatter_class"]

    parser = argparse.ArgumentParser(
        prog=prog,
        description=description,
        epilog=epilog,
        usage=usage,
        formatter_class=formatter_class,
        prefix_chars="-/",
    )

    if help_info and help_info.get("params"):
        group_title = f"Parámetros de {prog}" if prog != "asiscfg" else "Parámetros de la Aplicación"
        grp = parser.add_argument_group(group_title)
        for name, spec in help_info["params"].items():
            flags = [f"--{name}", f"/{name}"]
            p_help = spec.get("help", "")
            if spec.get("is_bool"):
                grp.add_argument(*flags, action="store_true", help=p_help)
            else:
                p_type = spec.get("type", str)
                choices = spec.get("choices")
                default_val = spec.get("default")
                grp.add_argument(
                    *flags,
                    type=p_type if p_type in (int, float, str) else str,
                    choices=choices,
                    default=default_val,
                    help=p_help,
                )

    config_target = (
        parser.add_argument_group("Opciones de Configuración Cifrada (asiscfg)")
        if (app_help is not None or help_info is not None)
        else parser
    )
    add_config_arguments(config_target)
    return parser


def init_app_config(
    args: Optional[Sequence[str]] = None,
    *,
    app_title: str = "ASISCFG",
    app_files: Optional[str] = None,
    app_schema: Optional[str] = None,
    app_action: str = "consume",
    app_help: Any = None,
    is_standalone: bool = False,
) -> ConfigBootstrap:
    """
    Contrato canónico de entrada única para aplicaciones anfitrionas y modo herramienta (Paso 0 absoluto).
    """
    help_info = normalize_app_help_and_params(app_help)
    app_params = help_info.get("params",{})

    tokens, remaining_args = parse_config_args(
        args, default_action=app_action, app_params=app_params
    )

    debug_flag = bool(tokens.get("debug"))
    dev_flag = bool(tokens.get("dev_mode"))
    show_flag = bool(tokens.get("show"))
    install_flag = bool(tokens.get("install"))
    target_action = tokens.get("action")

    if show_flag:
        from asiscfg.ui.dialogs import show_modal_message_dialog
    else:
        show_modal_message_dialog = None

    if tokens.get("help"):
        parser = create_cli_parser(prog=app_title, app_help=app_help, help_info=help_info)
        parser.print_help()
        return ConfigBootstrap(
            config=None,
            context=None,
            exit_code=0,
            remaining_args=remaining_args,
            params={},
            debug=debug_flag,
            dev_mode=dev_flag,
            show_modals=show_flag,
        )

    # Validación determinista de parámetros de la aplicación
    client_params: Dict[str, Any] = {}
    validation_errors: List[str] = []

    if app_params:
        for name, spec in app_params.items():
            val = tokens.get(name)
            is_bool = spec.get("is_bool", False)
            required = spec.get("required", False)
            default_val = spec.get("default")
            p_type = spec.get("type", str)
            choices = spec.get("choices")

            if is_bool:
                client_params[name] = bool(val)
                continue

            if val is None or val == default_val:
                if required and val is None:
                    validation_errors.append(f"Falta el parámetro requerido obligatorio: --{name}")
                    continue
                client_params[name] = default_val
                continue

            if p_type is not None and p_type is not str:
                try:
                    val = p_type(val)
                except Exception:
                    t_name = getattr(p_type, "__name__", str(p_type))
                    validation_errors.append(
                        f"Tipo de dato inválido para --{name} ('{val}'): se esperaba {t_name}."
                    )
                    continue

            if choices is not None and val not in choices:
                validation_errors.append(
                    f"Valor inválido '{val}' para --{name}. Opciones permitidas: {list(choices)}."
                )
                continue

            client_params[name] = val

    if validation_errors:
        err_msg = "Error en parámetros de la aplicación:\n" + "\n".join(validation_errors)
        if debug_flag or tokens.get("last_resource"):
            print(f"[FATAL] {err_msg}", file=sys.stderr)
        if show_flag and show_modal_message_dialog:
            show_modal_message_dialog(f"{app_title} - Error de Parámetros", err_msg, icon_type="error")
        return ConfigBootstrap(
            config=None,
            context=None,
            exit_code=2,
            remaining_args=remaining_args,
            params=client_params,
            debug=debug_flag,
            dev_mode=dev_flag,
            show_modals=show_flag,
        )

    # Resolución autónoma de base_dir
    if getattr(sys, "frozen", False):
        base_dir = os.path.dirname(os.path.abspath(sys.executable))
    else:
        base_dir = os.path.abspath(os.getcwd())

    # Prioridad de archivos
    mi_config_file = tokens.get("config_file") or (os.path.join(base_dir, f"{app_files}.cfg") if app_files else None)
    mi_key_file = tokens.get("key_file") or (os.path.join(base_dir, f"{app_files}.key") if app_files else None)
    mi_schema_file = tokens.get("schema_file") or (app_schema if app_schema else None)

    is_install_mode = (target_action == "install")
    if is_install_mode:
        # 1. Permiso administrativo
        if not (dev_flag or is_admin()):
            err_msg = "[ERROR] El modo instalación (--install) requiere ejecutarse con privilegios elevados de Administrador."
            print(err_msg, file=sys.stderr)
            if show_flag and show_modal_message_dialog:
                show_modal_message_dialog(f"{app_title} - Error de Permisos", err_msg, icon_type="error")
            return ConfigBootstrap(
                config=None,
                context=None,
                exit_code=1,
                remaining_args=remaining_args,
                params=client_params,
                debug=debug_flag,
                dev_mode=dev_flag,
                show_modals=show_flag,
            )

        # 2. Detección de archivos previos y confirmación
        resolved_cfg_check = mi_config_file or os.path.join(base_dir, DEFAULT_CONFIG_FILENAME)
        resolved_key_check = mi_key_file or os.path.join(base_dir, DEFAULT_KEY_FILENAME)
        files_exist = os.path.exists(resolved_cfg_check) or os.path.exists(resolved_key_check)
        if files_exist:
            from asiscfg.ui.dialogs import confirm_action_dialog

            confirm_msg = (
                "Se han detectado archivos de configuración o claves existentes en el sistema:\n\n"
                f"- Configuración: {resolved_cfg_check}\n"
                f"- Clave: {resolved_key_check}\n\n"
                "Continuar con la instalación reinicializará la configuración y generará nuevas claves, "
                "lo que provocará la pérdida irreversible de los datos anteriores.\n\n"
                "¿Desea continuar con la instalación?"
            )
            confirmed = confirm_action_dialog(f"{app_title} - Confirmar Instalación", confirm_msg)
            if not confirmed:
                print("[INFO] Proceso de instalación cancelado por el usuario. Datos anteriores preservados.")
                return ConfigBootstrap(
                    config=None,
                    context=None,
                    exit_code=0,
                    remaining_args=remaining_args,
                    params=client_params,
                    debug=debug_flag,
                    dev_mode=dev_flag,
                    show_modals=show_flag,
                )

        target_action = "ui"

    error = ""
    if target_action == "consume":
        resolved_cfg_check = mi_config_file or os.path.join(base_dir, DEFAULT_CONFIG_FILENAME)
        resolved_key_check = mi_key_file or os.path.join(base_dir, DEFAULT_KEY_FILENAME)
        if not os.path.exists(resolved_cfg_check):
            error += f"FileNotFound: Archivo de configuración no encontrado en '{resolved_cfg_check}'.\n"
        if not os.path.exists(resolved_key_check):
            error += f"FileNotFound: Archivo de clave no encontrado en '{resolved_key_check}'.\n"

    if error:
        if debug_flag or tokens.get("last_resource"):
            print(f"[FATAL] {error}", file=sys.stderr)
        if show_flag and show_modal_message_dialog:
            show_modal_message_dialog(f"{app_title} - Error de Inicialización", error, icon_type="error")
        return ConfigBootstrap(
            config=None,
            context=None,
            exit_code=1,
            remaining_args=remaining_args,
            params=client_params,
            debug=debug_flag,
            dev_mode=dev_flag,
            show_modals=show_flag,
        )

    try:
        app_ctx = create_app_context(
            action=target_action,
            config_file=mi_config_file,
            key_file=mi_key_file,
            schema_file=mi_schema_file,
            base_dir=base_dir,
            app_title=app_title,
            format_mode=tokens.get("format_mode", "plain"),
            is_standalone=is_standalone,
            dev_mode=dev_flag,
            metadata={
                "debug": debug_flag,
                "show": show_flag,
                "last_resource": bool(tokens.get("last_resource")),
                "edit": bool(tokens.get("edit")),
                "install": is_install_mode,
                "tokens": tokens,
            },
        )
    except Exception as e:
        if debug_flag or tokens.get("last_resource"):
            print(f"[FATAL] Error inicializando contexto de configuración: {e}", file=sys.stderr)
        if show_flag and show_modal_message_dialog:
            show_modal_message_dialog(
                f"{app_title} - Error Fatal",
                f"Error inicializando contexto de configuración:\n{e}",
                icon_type="error",
            )
        return ConfigBootstrap(
            config=None,
            context=None,
            exit_code=1,
            remaining_args=remaining_args,
            params=client_params,
            debug=debug_flag,
            dev_mode=dev_flag,
            show_modals=show_flag,
        )

    # Inicialización base de archivos ante modo instalación
    if is_install_mode:
        try:
            generate_key_file(context=app_ctx, overwrite=True)
            save_config(context=app_ctx, config_data=app_ctx.default_config)
        except Exception as e:
            err_init = f"No se pudo inicializar la configuración de instalación: {e}"
            print(f"[FATAL] {err_init}", file=sys.stderr)
            if show_flag and show_modal_message_dialog:
                show_modal_message_dialog(f"{app_title} - Error de Inicialización", err_init, icon_type="error")
            return ConfigBootstrap(
                config=None,
                context=app_ctx,
                exit_code=1,
                remaining_args=remaining_args,
                params=client_params,
                debug=debug_flag,
                dev_mode=dev_flag,
                show_modals=show_flag,
            )

    # Delegación de acciones de asiscfg
    action_result = execute_app_action(context=app_ctx, exit_on_finish=False)
    if action_result is not None:
        return ConfigBootstrap(
            config=None,
            context=app_ctx,
            exit_code=action_result,
            remaining_args=remaining_args,
            params=client_params,
            debug=debug_flag,
            dev_mode=dev_flag,
            show_modals=show_flag,
        )

    # Flujo de consumo para el anfitrión
    try:
        config = load_config(context=app_ctx)
    except Exception as e:
        if debug_flag or tokens.get("last_resource"):
            print(f"[FATAL] Error cargando configuración: {e}", file=sys.stderr)
        if show_flag and show_modal_message_dialog:
            show_modal_message_dialog(
                f"{app_title} - Error de Configuración",
                f"No se pudo cargar la configuración:\n{e}",
                icon_type="error",
            )
        return ConfigBootstrap(
            config=None,
            context=app_ctx,
            exit_code=1,
            remaining_args=remaining_args,
            params=client_params,
            debug=debug_flag,
            dev_mode=dev_flag,
            show_modals=show_flag,
        )

    return ConfigBootstrap(
        config=config,
        context=app_ctx,
        exit_code=None,
        remaining_args=remaining_args,
        params=client_params,
        debug=debug_flag,
        dev_mode=dev_flag,
        show_modals=show_flag,
    )


def main(args: Optional[Sequence[str]] = None) -> int:
    """Punto de entrada canónico para CLI standalone de asiscfg."""
    bootstrap = init_app_config(
        args=args,
        app_title="Herramienta de Configuración Cifrada (asiscfg)",
        app_files=None,
        app_schema=None,
        app_action="ui",
        is_standalone=True,
    )
    if bootstrap.exit_code is not None:
        return bootstrap.exit_code

    if bootstrap.config is None and bootstrap.context is None:
        return 1
    return 0

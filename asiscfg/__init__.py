# -*- coding: utf-8 -*-
# SPDX-FileCopyrightText: 2026 ASISNET Computación, CA <proyectos@asisnet.net>
# SPDX-FileCopyrightText: 2026 Boris Pinto <borispinto@gmail.com>
# SPDX-License-Identifier: MIT
# Autor: Boris Pinto <borispinto@gmail.com>
# Contacto Institucional: ASISNET Computación, CA <proyectos@asisnet.net>
# File: asiscfg/__init__.py


"""
Librería pkg-asiscfg: Gestión Centralizada y Unificada de Configuración Cifrada de Alto Rendimiento.
"""

__title__ = "pkg-asiscfg"
__version__ = "1.0.0"
__author__ = "Boris Pinto"
__email__ = "borispinto@asisnet.net"
__maintainer__ = "Asisnet Computacion, CA"
__maintainer_email__ = "proyectos@asisnet.net"
__copyright__ = "Copyright (c) 2026 Asisnet Computacion, CA"
__license__ = "MIT"

from asiscfg.cli import (
    add_config_arguments,
    init_app_config,
    main,
    parse_config_args,
)
from asiscfg.constants import (
    BASE_DIR,
    DEFAULT_CONFIG_FILENAME,
    DEFAULT_KEY_FILENAME,
    DEFAULT_SCHEMA_FILENAME,
    ENC_PREFIX,
    NO_MODIFY_KEY,
    NULL_SENTINEL,
    PREFIX_SCHEMA_DIRECTIVE,
    PREFIX_SPECIAL_SECTION,
    PUBLIC_PREFIX,
    SECTION_ASISCFG,
    SECTION_PROFILES,
    SECURITY_SECTIONS,
    VALID_ACTIONS,
    is_business_section,
    is_schema_directive,
    is_security_section,
    is_special_section,
)
from asiscfg.context import (
    AppConfigContext,
    create_app_context,
    resolve_dir_path,
    resolve_file_path,
    resolve_schema_path,
)
from asiscfg.crypto import (
    FORMAT_MODES,
    Aes256GcmFormatEngine,
    BaseFormatEngine,
    ChaCha20FormatEngine,
    FernetFormatEngine,
    PlainFormatEngine,
    detect_format_engine,
    get_format_engine,
)
from asiscfg.models import ConfigBootstrap, ConfigDict
from asiscfg.schema import (
    DEFAULT_BACKUP_SETTINGS,
    LITERAL,
    SCHEMA_KEY,
    VALOR_SCHEMA,
    extract_schema_metadata,
    load_schema_definition,
    validate_and_correct_config,
)
from asiscfg.security import (
    check_admin_password,
    hash_password,
    is_admin,
    log_audit_event,
    set_admin_password,
)
from asiscfg.storage import (
    execute_app_action,
    export_config_schema,
    generate_key_file,
    get_key,
    load_config,
    perform_backup,
    read_and_verify_config,
    save_config,
    save_values,
    verify_key_integrity,
)

try:
    import i18n
    from i18n import (
        I18nManager,
        get_i18n_instance,
        translate,
        t18n,
    )
    register_defaults = lambda d: get_i18n_instance().register_defaults(d)
    register_section_defaults = lambda sec, d: get_i18n_instance().register_section_defaults(sec, d)
except ImportError:
    pass

try:
    import asisdb
    from asisdb import (
        ConnectionConfig,
        build_db_url,
        get_db_engine,
        test_connection,
        get_supported_drivers,
    )
except ImportError:
    pass

__all__ = [
    # Metadatos del Paquete
    "__title__",
    "__version__",
    "__author__",
    "__email__",
    "__maintainer__",
    "__maintainer_email__",
    "__copyright__",
    "__license__",
    # Constantes y Clasificación
    "DEFAULT_CONFIG_FILENAME",
    "DEFAULT_KEY_FILENAME",
    "DEFAULT_SCHEMA_FILENAME",
    "BASE_DIR",
    "ENC_PREFIX",
    "NULL_SENTINEL",
    "NO_MODIFY_KEY",
    "PUBLIC_PREFIX",
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
    # Motores Criptográficos
    "FORMAT_MODES",
    "BaseFormatEngine",
    "PlainFormatEngine",
    "FernetFormatEngine",
    "Aes256GcmFormatEngine",
    "ChaCha20FormatEngine",
    "get_format_engine",
    "detect_format_engine",
    # Contexto y Modelos
    "AppConfigContext",
    "create_app_context",
    "resolve_dir_path",
    "resolve_file_path",
    "resolve_schema_path",
    "ConfigDict",
    "ConfigBootstrap",
    # Esquema
    "load_schema_definition",
    "extract_schema_metadata",
    "validate_and_correct_config",
    "LITERAL",
    "SCHEMA_KEY",
    "VALOR_SCHEMA",
    "DEFAULT_BACKUP_SETTINGS",
    # Seguridad
    "hash_password",
    "check_admin_password",
    "set_admin_password",
    "is_admin",
    "log_audit_event",
    # Persistencia y Almacenamiento
    "read_and_verify_config",
    "load_config",
    "save_config",
    "save_values",
    "get_key",
    "generate_key_file",
    "verify_key_integrity",
    "perform_backup",
    "export_config_schema",
    "execute_app_action",
    # CLI y Bootstrap
    "parse_config_args",
    "add_config_arguments",
    "init_app_config",
    "main",
    # Fachada i18n
    "t18n",
    "I18nManager",
    "get_i18n_instance",
    "translate",
    # Fachada asisdb
    "ConnectionConfig",
    "build_db_url",
    "get_db_engine",
    "test_connection",
    "get_supported_drivers",
]

# -*- coding: utf-8 -*-
# SPDX-FileCopyrightText: 2026 Asisnet Computacion, CA <proyectos@asisnet.net>
# SPDX-License-Identifier: MIT
# Autor: Boris Pinto <borispinto@asisnet.net>
# File: asiscfg/__init__.py

"""
Librería asiscfg (V1): Gestión Centralizada y Unificada de Archivos de Configuración.
Ofrece:
- Carga y guardado cifrado (load_config, save_config)
- Navegación anidada por clave punto (.valor) y soporte multi-perfil (.valor_profile) vía ConfigDict
- Carga dinámica de esquemas (load_dynamic_schema) y validación de rangos (validate_and_correct_config)
- Hashing de contraseñas de administración (hash_password, check_admin_password)
"""

__title__ = "pkg-asiscfg"
__version__ = "1.0.0"
__author__ = "Boris Pinto"
__email__ = "borispinto@asisnet.net"
__maintainer__ = "Asisnet Computacion, CA"
__maintainer_email__ = "proyectos@asisnet.net"
__copyright__ = "Copyright (c) 2026 Asisnet Computacion, CA"
__license__ = "MIT"

from .constants import (
    DEFAULT_CONFIG_FILENAME,
    DEFAULT_KEY_FILENAME,
    DEFAULT_SCHEMA_FILENAME,
    BASE_DIR,
    FORMAT_MODES,
    ENC_PREFIX,
    NULL_SENTINEL,
    PREFIX_SCHEMA_DIRECTIVE,
    PREFIX_SPECIAL_SECTION,
    SECTION_PROFILES,
    SECTION_ASISCFG,
    SECURITY_SECTIONS,
    VALID_ACTIONS,
    is_security_section,
    is_schema_directive,
    is_special_section,
    is_business_section,
    BaseFormatEngine,
    PlainFormatEngine,
    FernetFormatEngine,
    Aes256GcmFormatEngine,
    ChaCha20FormatEngine,
    get_format_engine,
    detect_format_engine
)
from .models import (
    ConfigDict,
    AppConfigContext,
    create_app_context,
    resolve_file_path,
    resolve_schema_path
)
from .schema import (
    validate_and_correct_config,
    load_schema_definition,
    extract_schema_metadata,
    LITERAL,
    SCHEMA_KEY,
    VALOR_SCHEMA,
    DEFAULT_BACKUP_SETTINGS
)

from .security import (
    hash_password,
    check_admin_password,
    set_admin_password,
    is_admin,
    log_audit_event
)
from .core import (
    load_config,
    save_config,
    get_key,
    generate_key_file,
    verify_key_integrity,
    export_config_schema,
    run_asiscfg,
    execute_app_action
)
import i18n
from i18n import (
    I18nManager,
    get_i18n_instance,
    translate,
    t18n
)

register_defaults = lambda d: get_i18n_instance().register_defaults(d)
register_section_defaults = lambda sec, d: get_i18n_instance().register_section_defaults(sec, d)
import asisdb
from asisdb import (
    ConnectionConfig,
    interpolate_placeholders,
    interpolate_db_url_placeholders,
    build_db_url,
    get_db_engine,
    init_db,
    verify_db_structure,
    reset_engine,
    close_engine,
    execute_query,
    execute_statement,
    LITERAL,
    test_connection,
    test_db_connection,
    get_supported_drivers,
    SUPPORTED_DRIVERS,
    MSSQL_ODBC_DRIVERS_PRIORITY,
    get_best_mssql_odbc_driver,
    resolve_odbc_driver_for_machine,
    get_machine_cached_odbc_driver,
    save_machine_cached_odbc_driver,
    DBFReader,
    DBFCacheManager,
    get_dbf_cache,
    DEFAULT_DB_MESSAGES
)

__all__ = [
    # Package Metadata
    "__title__",
    "__version__",
    "__author__",
    "__email__",
    "__copyright__",
    "__license__",
    # Constants & Crypto Engines
    "DEFAULT_CONFIG_FILENAME",
    "DEFAULT_KEY_FILENAME",
    "DEFAULT_SCHEMA_FILENAME",
    "BASE_DIR",
    "FORMAT_MODES",
    "ENC_PREFIX",
    "NULL_SENTINEL",
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
    "BaseFormatEngine",
    "PlainFormatEngine",
    "FernetFormatEngine",
    "Aes256GcmFormatEngine",
    "ChaCha20FormatEngine",
    "get_format_engine",
    "detect_format_engine",
    # Models & Schema
    "AppConfigContext",
    "create_app_context",
    "ConfigDict",
    "validate_and_correct_config",
    "load_schema_definition",
    "extract_schema_metadata",
    "LITERAL",
    "SCHEMA_KEY",
    "VALOR_SCHEMA",
    "DEFAULT_BACKUP_SETTINGS",
    "resolve_file_path",
    "resolve_schema_path",
    # Security
    "hash_password",
    "check_admin_password",
    "set_admin_password",
    "is_admin",
    "log_audit_event",
    # Core
    "load_config",
    "save_config",
    "get_key",
    "generate_key_file",
    "verify_key_integrity",
    "export_config_schema",
    "run_asiscfg",
    "execute_app_action",
    # Submodules
    "i18n",
    "asisdb",
    # i18n Facade
    "I18nManager",
    "get_i18n_instance",
    "translate",
    "t18n",
    "register_defaults",
    "register_section_defaults",
    # asisdb Facade
    "ConnectionConfig",
    "interpolate_placeholders",
    "interpolate_db_url_placeholders",
    "build_db_url",
    "get_db_engine",
    "init_db",
    "verify_db_structure",
    "reset_engine",
    "close_engine",
    "execute_query",
    "execute_statement",
    "test_connection",
    "test_db_connection",
    "get_supported_drivers",
    "SUPPORTED_DRIVERS",
    "MSSQL_ODBC_DRIVERS_PRIORITY",
    "get_best_mssql_odbc_driver",
    "resolve_odbc_driver_for_machine",
    "get_machine_cached_odbc_driver",
    "save_machine_cached_odbc_driver",
    "DBFReader",
    "DBFCacheManager",
    "get_dbf_cache",
    "DEFAULT_DB_MESSAGES"
]



# -*- coding: utf-8 -*-
# SPDX-FileCopyrightText: 2026 Asisnet Computacion, CA <proyectos@asisnet.net>
# SPDX-License-Identifier: MIT
# Autor: Boris Pinto <borispinto@asisnet.net>
# File: PRUEBA/SCHEMA/config_schema.py

from typing import Dict, Any
from asisdb import get_supported_drivers, LITERAL
from asiscfg import SCHEMA_KEY

"""
Módulo de Esquema de Configuración para el Proyecto ASIENTOS.
Centraliza servidor SQL, credenciales y plantillas con comodines {empresa_destino} y {empresa_origen}.
"""
DEFAULT_CONFIG: Dict[str, Any] = {
    # ── 1. Metadatos de la Aplicación ──
    "app": {
        "name": {"default": "ASISNET - Asientos Contables", "description": "t18n#Nombre del sistema de sincronización."},
        "version": {"default": "v1.0.0", "description": "t18n#Versión del aplicativo."},
        "client": {"default": "ASISNET", "description": "t18n#Cliente o empresa propietaria."}
    },

    # ── 2. Parámetros Generales ──
    "general": {
        "active_language": {"default": "es", "description": "t18n#Código del idioma activo (ej. es)."},
        "log_filename_pattern": {"default": "{TIMESTAMP}.log", "description": "t18n#Patrón de nombres de logs."},
        "backup_config_pattern": {"default": "{TIMESTAMP}-{BASENAME}{EXT}.bak", "description": "t18n#Patrón de nombres de backups de configuración."},
        "monto_tolerance": {"default": "0.01", "description": "t18n#Tolerancia para la cuadratura contable."},
    },

    # ── 3. Rutas Globales ──
    "paths": {
        "resources": {"default": "resources", "description": "t18n#Directorio de recursos e interfaz."},
        "languages": {"default": "resources/languages", "description": "t18n#Directorio de idiomas e i18n."},
        "logs": {"default": "logs", "description": "t18n#Directorio de almacenamiento de logs."},
        "asientos_ini": {"default": "asientos.ini", "description": "t18n#Ruta al archivo asientos.ini del sistema."},
        "schema_campos_path": {"default": "campos.json", "description": "t18n#Ruta al archivo con campos extras/modificados/excluidos."},
        "backup_config_path": {"default": "{ROOT}/backups", "description": "t18n#Ruta al archivo de respaldo de la configuración."}
    },

    # ── 4. Conexiones Fox / SQL Globales ──
    "conexiones": {
        # Plantilla global FoxPro (acepta comodín {empresa_origen})
        "fox_path": {
            "default": "\\\\SRV\\ORBIS\\ORBISDAT\\CONDAT{empresa_origen}", 
            "description": "t18n#Plantilla de ruta FoxPro/SA (soporta comodín {empresa_origen})."
        },
        # Motor y credenciales SQL Globales
        "driver": {
            "default": "mssql", 
            "description": "t18n#Motor de Base de Datos SQL global.", 
            "type": "enum", 
            "options": get_supported_drivers()
        },
        "host": {"default": "SQLSERVER", "description": "t18n#Servidor SQL principal para todas las empresas."},
        "port": {"default": "", "description": "t18n#Puerto de escucha TCP/IP SQL (vacío para default del driver)."},
        "user": {"default": "sa", "description": "t18n#Usuario SQL principal."},
        "password": {"default": "", "description": "t18n#Contraseña SQL principal.", "is_password": True},
        # Plantilla de base de datos (acepta comodín {empresa_destino})
        "database": {
            "default": "DAT{empresa_destino}DBSQL", 
            "description": "t18n#Plantilla de Base de Datos SQL (soporta comodín {empresa_destino})."
        },
        "odbc_driver": {"default": "", "description": "t18n#Driver ODBC a utilizar (opcional)."},
        "sql_driver_autodetect": {"default": "False", "description": "t18n#Autodetectar Driver ODBC instalado."},
        "tds_version": {"default": "", "description": "t18n#Versión del protocolo TDS para pymssql (7.2, 7.4, etc)."}
    },

    # ── 5. Configuración Multi-Perfil ──
    "@profiles": {
        "_template": {
            "info": {
                "name": {"default": "", "description": "t18n#Razón Social de la empresa."},
                "empresa_origen": {"default": "01", "description": "t18n#Código de Empresa Origen (FoxPro)."},
                "empresa_destino": {"default": "01", "description": "t18n#Código de Empresa Destino (SQL Server)."}
            },
            "conexiones": {
                "fox_path": {"default": "", "description": "t18n#Ruta FoxPro específica (dejar vacío para heredar de conexiones.fox_path)."},
                "btn_test_foxpro": {
                    "type": "test_connection",
                    "description": "t18n#📁 Probar Conexión FoxPro",
                    "mapping": {
                        "driver": LITERAL("foxpro"),
                        "path": ["fox_path", "conexiones.fox_path"],
                        "empresa_origen": "info.empresa_origen",
                        "empresa_destino": "info.empresa_destino"
                    }
                },
                # Sobreescritura específica por empresa (vacío hereda de conexiones global)
                "driver": {
                    "default": "", 
                    "description": "t18n#Motor SQL específico (dejar vacío para heredar de conexiones.driver).", 
                    "type": "enum", 
                    "options": ["", *get_supported_drivers()]
                },
                "host": {"default": "", "description": "t18n#Servidor SQL específico (dejar vacío para heredar de conexiones.host)."},
                "port": {"default": "", "description": "t18n#Puerto de escucha TCP/IP SQL (dejar vacío para heredar de conexiones.port)."},
                "user": {"default": "", "description": "t18n#Usuario SQL específico (dejar vacío para heredar de conexiones.user)."},
                "password": {"default": "", "description": "t18n#Contraseña específica (dejar vacío para heredar de conexiones.password).", "is_password": True},
                "database": {"default": "", "description": "t18n#Base de datos específica (dejar vacío para heredar de conexiones.database)."},
                "odbc_driver": {"default": "", "description": "t18n#Driver ODBC específico (dejar vacío para heredar de conexiones.odbc_driver)."},
                "sql_driver_autodetect": {
                    "default": "", 
                    "description": "t18n#Autodetectar Driver ODBC instalado (dejar vacío para heredar de conexiones.sql_driver_autodetect)." 
                },
                "tds_version": {"default": "", "description": "t18n#Versión del protocolo TDS (dejar vacío para heredar de conexiones.tds_version)."},
                "btn_test_sql": {
                    "type": "test_connection",
                    "description": "t18n#🔌 Probar Conexión SQL Empresa",
                    "mapping": {
                        "driver": ["driver", "conexiones.driver"],
                        "host": ["host", "conexiones.host"],
                        "port": ["port", "conexiones.port"],
                        "database": ["database", "conexiones.database"],
                        "user": ["user", "conexiones.user"],
                        "password": ["password", "conexiones.password"],
                        "odbc_driver": ["odbc_driver", "conexiones.odbc_driver"],
                        "empresa_destino": "info.empresa_destino",
                        "empresa_origen": "info.empresa_origen",
                        "sql_driver_autodetect": ["sql_driver_autodetect", "conexiones.sql_driver_autodetect"],
                        "tds_version": ["tds_version", "conexiones.tds_version"]
                    }
                }
            }
        },

        # Empresa inicial por defecto
        "01": {
            "info": {
                "name": "",
                "empresa_origen": "",
                "empresa_destino": ""
            },
            "conexiones": {
                "fox_path": "",
                "driver": "",
                "host": "",
                "port": "",
                "user": "",
                "password": "",
                "database": "",
                "odbc_driver": "",
                "sql_driver_autodetect": "",
                "tds_version": ""
            }
        }
    },

    # ── Política de Respaldos de Configuración ──
    "_backup": {
        "enabled": True,
        "method": "timestamp",
        "target_dir": SCHEMA_KEY("paths.backup_config_path"),
        "filename_pattern": SCHEMA_KEY("general.backup_config_pattern"),
        "max_backups": 20
    }
}


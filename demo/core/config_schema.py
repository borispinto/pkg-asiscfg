# -*- coding: utf-8 -*-
# SPDX-FileCopyrightText: 2026 ASISNET Computación, CA <proyectos@asisnet.net>
# SPDX-FileCopyrightText: 2026 Boris Pinto <borispinto@gmail.com>
# SPDX-License-Identifier: MIT
# Autor: Boris Pinto <borispinto@gmail.com>
# Contacto Institucional: ASISNET Computación, CA <proyectos@asisnet.net>
# File: demo/config_schema.py

from asiscfg import LITERAL

"""
Esquema de configuración unificado y portable para pkg-asiscfg (Demo SQLite).
Demuestra:
  1. Parámetros de aplicación y seguridad ('app').
  2. Parámetros generales de negocio ('general').
  3. Configuración global padre de base de datos SQLite con botón test_connection ('database').
  4. Multiperfil bajo '@profiles' con plantilla '_template' y perfiles '01' y '02'.
  5. Herencia jerárquica en cascada: Perfil -> Sección Global -> Default.
"""

CONFIG_SCHEMA = {
    # ── Políticas de Configuración ──
    "_security_level": 1,
    "_backup": {
        "enabled": True,
        "method": "timestamp",
        "target_dir": "{ROOT}/backups",
        "filename_pattern": "{TIMESTAMP}-{BASENAME}{EXT}.bak",
        "max_backups": 20
    },

    # ── 1. Sección de Aplicación y Seguridad ──
    "app": {
        "nombre": {
            "type": "str",
            "default": "Demo Conector Empresarial",
            "description": "Nombre de la Aplicación",
            "public": True
        },
        "version": {
            "type": "str",
            "default": "1.0.0",
            "description": "Versión del Software",
            "public": True
        },
        "debug": {
            "type": "bool",
            "default": False,
            "description": "Habilitar Modo Depuración"
        }
    },

    # ── 2. Sección General de Negocio ──
    "general": {
        "idioma": {
            "type": "str",
            "default": "es",
            "description": "Código de Idioma Activo",
            "public": True
        },
        "empresa": {
            "type": "str",
            "default": "Corporación Demo C.A.",
            "description": "Nombre de la Empresa",
            "public": True
        }
    },

    # ── 3. Sección Global (Padre): Base de Datos Compartida ──
    "database": {
        "driver": {
            "type": "str",
            "default": "sqlite",
            "description": "Motor de Base de Datos Global",
            "public": True
        },
        "database": {
            "type": "str",
            "default": "demo_{profile}.db",
            "description": "Archivo de BD Global"
        },
        "user": {
            "type": "str",
            "default": "admin_general",
            "description": "Usuario Global por Defecto"
        },
        "password": {
            "type": "str",
            "default": "ClaveGlobal123",
            "is_password": True,
            "description": "Contraseña Global por Defecto"
        },
        "btn_test_db_global": {
            "type": "test_connection",
            "description": "🔌 Probar Conexión Global",
            "mapping": {
                "driver": "database.driver",
                "database": LITERAL("demo_global.db"),
                "user": "database.user",
                "password": "database.password"
            }
        }
    },

    # ── 4. Sección Multiperfil (@profiles): Sucursales y Herencia ──
    "@profiles": {
        "_template": {
            "info": {
                "nombre": {
                    "type": "str",
                    "default": "",
                    "description": "Nombre de la Sucursal",
                    "public": True
                },
                "codigo": {
                    "type": "str",
                    "default": "01",
                    "description": "Código de Sucursal"
                }
            },
            "database": {
                "driver": {
                    "type": "str",
                    "default": "",
                    "description": "Motor (vacío = hereda del padre global)"
                },
                "database": {
                    "type": "str",
                    "default": "",
                    "description": "Archivo de BD del Perfil (vacío = hereda)"
                },
                "user": {
                    "type": "str",
                    "default": "",
                    "description": "Usuario (vacío = hereda del padre global)"
                },
                "password": {
                    "type": "str",
                    "default": "",
                    "is_password": True,
                    "description": "Contraseña (vacía = hereda del padre global)"
                },
                "btn_test_db": {
                    "type": "test_connection",
                    "description": "🔌 Probar Conexión Perfil",
                    "mapping": {
                        "driver": ["driver", "database.driver"],
                        "database": ["database", "database.database"],
                        "user": ["user", "database.user"],
                        "password": ["password", "database.password"]
                    }
                }
            }
        },
        # Perfil 01: Sucursal Principal en Caracas
        "01": {
            "info": {
                "nombre": "Sucursal Principal",
                "codigo": "01"
            },
            "database": {
                "database": "demo_01.db"
            }
        },
        # Perfil 02: Sucursal Secundaria con usuario propio
        "02": {
            "info": {
                "nombre": "Sucursal Secundaria",
                "codigo": "02"
            },
            "database": {
                "user": "supervisor_sucursal_02"
            }
        }
    }
}

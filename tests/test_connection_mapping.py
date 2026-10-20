# -*- coding: utf-8 -*-
# SPDX-FileCopyrightText: 2026 Asisnet Computacion, CA <proyectos@asisnet.net>
# SPDX-License-Identifier: MIT
# Autor: Boris Pinto <borispinto@asisnet.net>
# File: tests/test_connection_mapping.py

"""
Pruebas unitarias para la rutina canónica test_connection y la resolución de parámetros con Fallback Chaining.
"""

import os
import tempfile
import unittest
from asisdb.engine import test_connection
from asiscfg.schema import extract_schema_metadata, validate_and_correct_config
from asiscfg.models import AppConfigContext
from asiscfg.ui.app import ConfigApp


class TestConnectionMapping(unittest.TestCase):
    def test_driver_required_strictly(self):
        """El parámetro driver es obligatorio y explícito; no debe asumir nada."""
        success, msg, diag = test_connection(driver="")
        self.assertFalse(success)
        self.assertIn("driver", msg.lower())
        self.assertEqual(diag["target_url"], "")

    def test_foxpro_connection_missing_path(self):
        """FoxPro requiere una ruta válida."""
        success, msg, diag = test_connection(driver="foxpro", path="")
        self.assertFalse(success)
        self.assertIn("vacía", msg.lower())

    def test_foxpro_connection_valid_temp_dir(self):
        """FoxPro reconoce directorios accesibles."""
        with tempfile.TemporaryDirectory() as tmp_dir:
            success, msg, diag = test_connection(driver="foxpro", path=tmp_dir)
            self.assertTrue(success)
            self.assertIn("accesible", msg.lower())
            self.assertEqual(diag["target_url"], os.path.abspath(tmp_dir))
            self.assertIn("driver", diag["used_params"])
            self.assertIn("path", diag["used_params"])

    def test_sqlite_connection_and_masking(self):
        """Prueba SQLite con motor relacional y enmascaramiento de contraseñas."""
        with tempfile.TemporaryDirectory() as tmp_dir:
            db_path = os.path.join(tmp_dir, "test_db.db")
            success, msg, diag = test_connection(
                driver="sqlite",
                database=db_path,
                password="MiPasswordSecreto123"
            )
            self.assertTrue(success)
            self.assertIn("sqlite", msg.lower())
            self.assertEqual(diag["used_params"].get("password"), "<password>")
            self.assertNotIn("MiPasswordSecreto123", diag["target_url"])

    def test_resolve_test_params_fallback_chaining(self):
        """Verifica que la resolución de mapeos procese listas de prioridad y notación de puntos."""
        app_dummy = type("DummyApp", (), {
            "resolve_test_params": ConfigApp.resolve_test_params
        })()

        from asiscfg.schema import LITERAL

        mapping = {
            "driver": LITERAL("foxpro"),
            "host": ["host_local", "general.default_host", "literal:127.0.0.1"],
            "database": "database",
            "tds_version": ["tds_version", "general.tds_version", "otro.tds"],
            "sql_driver_autodetect": ["sql_driver_autodetect", "general.sql_driver_autodetect"],
            "odbc_driver": "odbc_driver",
            "ambiente": LITERAL("PRODUCCION")
        }

        # Caso 1: Valores locales tienen prioridad y literales se resuelven
        current_sec = {
            "host_local": "192.168.1.50",
            "database": "BD_EMPRESA_01",
            "tds_version": "7.4",
            "sql_driver_autodetect": True
        }
        full_config = {
            "general": {
                "default_host": "10.0.0.1",
                "tds_version": "7.2",
                "sql_driver_autodetect": False
            }
        }

        resolved = app_dummy.resolve_test_params(mapping, current_sec, full_config)
        self.assertEqual(resolved["driver"], "foxpro")
        self.assertEqual(resolved["host"], "192.168.1.50")
        self.assertEqual(resolved["database"], "BD_EMPRESA_01")
        self.assertEqual(resolved["tds_version"], "7.4")
        self.assertTrue(resolved["sql_driver_autodetect"])
        self.assertEqual(resolved["odbc_driver"], "")
        self.assertEqual(resolved["ambiente"], "PRODUCCION")

        # Caso 2: Valores locales vacíos hacen fallback a 'general' y luego a literal
        current_sec_empty = {
            "host_local": "",
            "database": "BD_EMPRESA_02",
            "tds_version": "",
            "sql_driver_autodetect": None
        }
        full_config_empty_host = {
            "general": {
                "default_host": "",
                "tds_version": "7.2",
                "sql_driver_autodetect": False
            }
        }
        resolved_fallback = app_dummy.resolve_test_params(mapping, current_sec_empty, full_config_empty_host)
        self.assertEqual(resolved_fallback["driver"], "foxpro")
        self.assertEqual(resolved_fallback["host"], "127.0.0.1")
        self.assertEqual(resolved_fallback["tds_version"], "7.2")
        self.assertFalse(resolved_fallback["sql_driver_autodetect"])

    def test_schema_metadata_omits_test_connection_from_defaults(self):
        """El schema no debe inyectar campos test_connection en default_values persistibles."""
        sample_schema = {
            "general": {
                "app_name": {"default": "MiApp"}
            },
            "db_sql": {
                "driver": {"default": "mssql"},
                "btn_test": {
                    "type": "test_connection",
                    "description": "Probar Conexión",
                    "mapping": {"driver": "driver"}
                }
            }
        }

        meta = extract_schema_metadata(sample_schema)
        def_vals = meta["default_config"]
        rules = meta["validation_rules"]
        self.assertNotIn("btn_test", def_vals["db_sql"])
        self.assertIn("btn_test", rules["db_sql"])

        cleaned_cfg = validate_and_correct_config(
            {"db_sql": {"driver": "mssql", "btn_test": "ignorar"}},
            validation_rules=rules,
            default_config=def_vals,
            context=AppConfigContext()
        )
        self.assertNotIn("btn_test", cleaned_cfg.get("db_sql", {}))

    def test_interpolate_placeholders_syntax_and_fallbacks(self):
        """Verifica la sintaxis dual ([campo] y {campo}) y los fallbacks inteligentes."""
        from asisdb.engine import interpolate_placeholders

        # Caso 1: Comodines explícitos
        ctx1 = {"empresa": "01", "empresa_destino": "02", "empresa_origen": "01", "custom_tag": "PROD"}
        tpl1 = "DAT[empresa_destino]RICUPEROSQL_{custom_tag}"
        res1 = interpolate_placeholders(tpl1, ctx1)
        self.assertEqual(res1, "DAT02RICUPEROSQL_PROD")

        # Caso 2: Comodines explícitos en contexto
        ctx2 = {"empresa": "99", "empresa_destino": "99", "empresa_origen": "99"}
        tpl2 = "DAT[empresa_destino]RICUPEROSQL / PATH/[empresa_origen]"
        res2 = interpolate_placeholders(tpl2, ctx2)
        self.assertEqual(res2, "DAT99RICUPEROSQL / PATH/99")

        # Caso 3: Sintaxis con llaves y mayúsculas/minúsculas
        tpl3 = "DAT{EMPRESA_DESTINO}RICUPEROSQL"
        res3 = interpolate_placeholders(tpl3, ctx1)
        self.assertEqual(res3, "DAT02RICUPEROSQL")

    def test_resolve_test_params_with_placeholders_and_inheritance(self):
        """Prueba que resolve_test_params herede de general e interpole con el contexto de empresa."""
        app_dummy = type("DummyApp", (), {
            "resolve_test_params": ConfigApp.resolve_test_params
        })()

        from asiscfg.schema import LITERAL

        mapping = {
            "driver": LITERAL("mssql"),
            "host": ["host", "general.host"],
            "database": ["database", "general.database"],
            "user": ["user", "general.user"],
            "empresa_destino": "empresa_destino"
        }

        full_config = {
            "general": {
                "host": "192.168.1.100",
                "user": "sa",
                "database": "DAT[empresa_destino]RICUPEROSQL"
            }
        }

        # Empresa 01: no define database ni host, los hereda de general
        current_sec_01 = {
            "empresa_destino": "01",
            "host": "",
            "database": ""
        }
        ctx_01 = {"empresa": "01", "empresa_destino": "01"}
        resolved_01 = app_dummy.resolve_test_params(mapping, current_sec_01, full_config, context=ctx_01)

        self.assertEqual(resolved_01["host"], "192.168.1.100")
        self.assertEqual(resolved_01["user"], "sa")
        self.assertEqual(resolved_01["database"], "DAT01RICUPEROSQL")
        self.assertEqual(resolved_01["empresa_destino"], "01")

        # Empresa 99: Sobreescribe database explícitamente
        current_sec_99 = {
            "empresa_destino": "99",
            "host": "10.0.0.99",
            "database": "BD_ESPECIAL_REMOTA"
        }
        ctx_99 = {"empresa": "99", "empresa_destino": "99"}
        resolved_99 = app_dummy.resolve_test_params(mapping, current_sec_99, full_config, context=ctx_99)

        self.assertEqual(resolved_99["host"], "10.0.0.99")
        self.assertEqual(resolved_99["database"], "BD_ESPECIAL_REMOTA")

    def test_button_isolation_with_shared_section_name(self):
        """Los botones definidos en @profiles._template no deben inyectarse en la sección raíz con el mismo nombre."""
        schema_asientos = {
            "conexiones": {
                "host": {"default": "192.168.1.1", "description": "Servidor"},
                "user": {"default": "sa", "description": "Usuario"},
                "password": {"default": "secret", "is_password": True}
            },
            "@profiles": {
                "_template": {
                    "conexiones": {
                        "database": {"default": "EMP_{empresa}", "description": "BD"},
                        "btn_test_db": {
                            "type": "test_connection",
                            "description": "🔌 Probar Perfil",
                            "mapping": {
                                "host": "conexiones.host",
                                "database": "conexiones.database"
                            }
                        }
                    }
                },
                "01": {
                    "conexiones": {
                        "database": "EMP_01_PROD"
                    }
                }
            }
        }

        meta = extract_schema_metadata(schema_asientos)
        def_vals = meta["default_config"]
        val_rules = meta["validation_rules"]
        prof_tmpl = meta["profile_template"]

        # 1. En la raíz, 'conexiones' NO debe contener 'btn_test_db' ni 'database'
        self.assertIn("host", val_rules["conexiones"])
        self.assertIn("user", val_rules["conexiones"])
        self.assertNotIn("btn_test_db", val_rules["conexiones"])
        self.assertNotIn("database", val_rules["conexiones"])

        # 2. En prof_tmpl y en val_rules["@profiles"]["_template"], 'conexiones' SÍ debe contener el botón
        self.assertIn("btn_test_db", prof_tmpl["conexiones"])
        self.assertIn("database", prof_tmpl["conexiones"])
        self.assertIn("btn_test_db", val_rules["@profiles"]["_template"]["conexiones"])

        # 3. Validación y corrección de configuración
        cfg_test = {
            "conexiones": {
                "host": "10.0.0.1",
                "btn_test_db": "debe_ser_removido"
            },
            "@profiles": {
                "01": {
                    "conexiones": {
                        "database": "EMP_01_PROD",
                        "btn_test_db": "debe_ser_removido"
                    }
                }
            }
        }
        cleaned = validate_and_correct_config(
            cfg_test,
            validation_rules=val_rules,
            default_config=def_vals,
            context=AppConfigContext()
        )
        self.assertEqual(cleaned["conexiones"]["host"], "10.0.0.1")
        self.assertEqual(cleaned["conexiones"]["user"], "sa")
        self.assertNotIn("btn_test_db", cleaned["conexiones"])
        self.assertNotIn("btn_test_db", cleaned["@profiles"]["01"]["conexiones"])
        self.assertEqual(cleaned["@profiles"]["01"]["conexiones"]["database"], "EMP_01_PROD")

        # 4. Resolución de parámetros con herencia en cascada (Perfil -> Raíz)
        app_dummy = ConfigApp.__new__(ConfigApp)
        mapping = prof_tmpl["conexiones"]["btn_test_db"]["mapping"]
        current_sec = cleaned["@profiles"]["01"]["conexiones"]
        ctx = {"profile": "01", "empresa": "01", "section": "conexiones"}
        resolved = app_dummy.resolve_test_params(mapping, current_sec, cleaned, context=ctx)
        self.assertEqual(resolved["host"], "10.0.0.1")
        self.assertEqual(resolved["database"], "EMP_01_PROD")

    def test_resolve_test_params_with_cross_section_placeholders(self):
        """Verifica que comodines como [empresa_destino] se interpólen correctamente con el valor mapeado."""
        app_dummy = ConfigApp.__new__(ConfigApp)

        mapping = {
            "driver": ["driver", "conexiones.driver"],
            "host": ["host", "conexiones.host"],
            "database": ["database", "conexiones.database"],
            "odbc_driver": ["odbc_driver", "conexiones.odbc_driver"],
            "empresa_destino": "info.empresa_destino",
            "empresa_origen": "info.empresa_origen"
        }

        full_config = {
            "conexiones": {
                "driver": "mssql",
                "host": "DESKTOP-IHSG45L",
                "database": "DAT[empresa_destino]RICUPEROSQL",
                "odbc_driver": "ODBC Driver 17 for SQL Server"
            },
            "@profiles": {
                "02": {
                    "info": {
                        "empresa_origen": "01",
                        "empresa_destino": "01"
                    },
                    "conexiones": {
                        "driver": "",
                        "host": "",
                        "database": "",
                        "odbc_driver": ""
                    }
                }
            }
        }

        current_sec = full_config["@profiles"]["02"]["conexiones"]
        ctx = {"profile": "02", "empresa": "02", "company": "02", "section": "conexiones"}

        resolved = app_dummy.resolve_test_params(mapping, current_sec, full_config, context=ctx)

        self.assertEqual(resolved["driver"], "mssql")
        self.assertEqual(resolved["host"], "DESKTOP-IHSG45L")
        self.assertEqual(resolved["empresa_destino"], "01")
        self.assertEqual(resolved["empresa_origen"], "01")
        self.assertEqual(resolved["odbc_driver"], "ODBC Driver 17 for SQL Server")

        self.assertEqual(resolved["database"], "DAT01RICUPEROSQL")


if __name__ == "__main__":
    unittest.main()

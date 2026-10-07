# -*- coding: utf-8 -*-
# SPDX-FileCopyrightText: 2026 Asisnet Computacion, CA <proyectos@asisnet.net>
# SPDX-License-Identifier: MIT
# Autor: Boris Pinto <borispinto@asisnet.net>
# File: tests/test_create_app_context_stage1.py

import os
import tempfile
import unittest
from asiscfg.models import create_app_context, AppConfigContext
from asiscfg.schema import load_schema_definition
from asiscfg.security import hash_password


class TestCreateAppContextStage1(unittest.TestCase):
    """Pruebas unitarias para la centralización y enriquecimiento de AppConfigContext (Etapa 1)."""

    def setUp(self):
        self.test_dir = tempfile.mkdtemp()
        self.config_path = os.path.join(self.test_dir, "test_config.enc")
        self.key_path = os.path.join(self.test_dir, "test_key.key")
        self.schema_path = os.path.join(self.test_dir, "custom_schema.py")

        # Crear archivo de clave válido
        with open(self.key_path, "wb") as f:
            f.write(b"SAMPLE_KEY_CONTENT_1234567890")

        # Crear archivo de esquema de prueba
        schema_content = """# -*- coding: utf-8 -*-
DEFAULT_CONFIG = {
    "_backup": {
        "enabled": True,
        "max_backups": 10
    },
    "app": {
        "name": {"default": "MiSistema", "type": "str", "description": "Nombre de la aplicación"},
        "secret_token": {"default": "token_xyz", "type": "str", "is_password": True}
    },
    "database": {
        "host": {"default": "127.0.0.1", "type": "str"},
        "port": {"default": 5432, "type": "int", "min": 1, "max": 65535}
    },
    "@profiles": {
        "_template": {
            "db_empresa": {
                "nombre_bd": {"default": "BD_DEFAULT", "type": "str"},
                "clave_bd": {"default": "clave_123", "type": "str", "is_password": True}
            }
        },
        "01": {
            "db_empresa": {
                "nombre_bd": "BD_SEDE_01"
            }
        }
    },
    "@asiscfg": {
        "admin_pass_hash": "8c6976e5b5410415bde908bd4dee15dfb167a9c873fc4bb8a81f6f2ab448a918"
    }
}
"""
        with open(self.schema_path, "w", encoding="utf-8") as f:
            f.write(schema_content)

    def test_load_schema_definition_independent(self):
        """Verifica que load_schema_definition cargue y extraiga toda la estructura del esquema sin tocar config."""
        res = load_schema_definition(self.schema_path)
        self.assertIn("default_config", res)
        self.assertIn("validation_rules", res)
        self.assertIn("profile_template", res)
        self.assertIn("password_fields", res)
        self.assertIn("backup_settings", res)

        # Verificar valores por defecto
        def_cfg = res["default_config"]
        self.assertEqual(def_cfg["app"]["name"], "MiSistema")
        self.assertEqual(def_cfg["database"]["port"], 5432)
        self.assertEqual(def_cfg["@profiles"]["01"]["db_empresa"]["nombre_bd"], "BD_SEDE_01")

        # Verificar campos de contraseña
        pwd_fields = res["password_fields"]
        self.assertIn("app.secret_token", pwd_fields)
        self.assertIn("@profiles.db_empresa.clave_bd", pwd_fields)

        # Verificar backup settings
        self.assertEqual(res["backup_settings"]["max_backups"], 10)

    def test_create_app_context_populates_all_schema_info(self):
        """Verifica que create_app_context en modo consume contenga toda la información y metadata del esquema."""
        ctx = create_app_context(
            action="consume",
            config_file=self.config_path,
            key_file=self.key_path,
            schema_file=self.schema_path,
            base_dir=self.test_dir
        )

        self.assertIsInstance(ctx, AppConfigContext)
        self.assertEqual(ctx.action, "consume")
        self.assertEqual(ctx.key_status, "ok")
        self.assertIsNotNone(ctx.key_bytes)
        self.assertEqual(ctx.default_config["app"]["name"], "MiSistema")
        self.assertIn("app.secret_token", ctx.password_fields)
        self.assertIn("@profiles.db_empresa.clave_bd", ctx.password_fields)
        self.assertEqual(ctx.admin_pass_hash, "8c6976e5b5410415bde908bd4dee15dfb167a9c873fc4bb8a81f6f2ab448a918")

    def test_create_app_context_key_status_missing_ui(self):
        """Verifica que un archivo de clave inexistente establezca key_status='missing' en modo ui."""
        missing_key = os.path.join(self.test_dir, "missing.key")
        ctx = create_app_context(
            action="ui",
            config_file=self.config_path,
            key_file=missing_key,
            schema_file=self.schema_path,
            base_dir=self.test_dir,
            dev_mode=True
        )
        self.assertEqual(ctx.action, "ui")
        self.assertEqual(ctx.key_status, "missing")
        self.assertTrue(len(ctx.key_detail) > 0)

    def test_create_app_context_key_status_empty_ui(self):
        """Verifica que un archivo de clave vacío (0 bytes) establezca key_status='empty' en modo ui."""
        empty_key = os.path.join(self.test_dir, "empty.key")
        with open(empty_key, "wb") as f:
            pass
        ctx = create_app_context(
            action="ui",
            config_file=self.config_path,
            key_file=empty_key,
            schema_file=self.schema_path,
            base_dir=self.test_dir,
            dev_mode=True
        )
        self.assertEqual(ctx.action, "ui")
        self.assertEqual(ctx.key_status, "empty")
        self.assertIn("vacío", ctx.key_detail.lower())

    def test_create_app_context_generate_key_action(self):
        """Verifica que action='generate_key' cree el contexto sin requerir existencia de clave previa."""
        nonexistent_key = os.path.join(self.test_dir, "to_be_generated.key")
        ctx = create_app_context(
            action="generate_key",
            config_file=self.config_path,
            key_file=nonexistent_key,
            base_dir=self.test_dir
        )
        self.assertEqual(ctx.action, "generate_key")
        self.assertEqual(ctx.key_file_path, os.path.abspath(nonexistent_key))

    def test_create_app_context_export_schema_action(self):
        """Verifica que action='export_schema' cree el contexto de exportación."""
        ctx = create_app_context(
            action="export_schema",
            schema_file="custom_export.py",
            base_dir=self.test_dir
        )
        self.assertEqual(ctx.action, "export_schema")
        self.assertEqual(ctx.schema_file_name, "custom_export.py")

    def test_create_app_context_invalid_action(self):
        """Verifica que una acción no válida lance ValueError."""
        with self.assertRaises(ValueError):
            create_app_context(action="invalid_action_xyz")


if __name__ == "__main__":
    unittest.main()

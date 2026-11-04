# -*- coding: utf-8 -*-
# SPDX-FileCopyrightText: 2026 Asisnet Computacion, CA <proyectos@asisnet.net>
# SPDX-License-Identifier: MIT
# Autor: Boris Pinto <borispinto@asisnet.net>
# File: tests/test_config_schema_strict.py

import os
import shutil
import tempfile
import unittest

from asiscfg.context import create_app_context, resolve_schema_path
from asiscfg.schema import load_schema_definition


class TestConfigSchemaStrictLoading(unittest.TestCase):
    """
    Pruebas unitarias para validar la carga estricta, obligatoria y fail-fast
    del esquema de configuración bajo el nombre canónico único CONFIG_SCHEMA.
    """

    def setUp(self):
        self.test_dir = tempfile.mkdtemp()
        self.config_file = os.path.join(self.test_dir, "test.cfg")
        self.key_file = os.path.join(self.test_dir, "test.key")
        with open(self.key_file, "wb") as f:
            f.write(b"SAMPLE_KEY_CONTENT_1234567890_VALID")

    def tearDown(self):
        shutil.rmtree(self.test_dir, ignore_errors=True)

    def test_load_schema_definition_missing_file_raises_filenotfound(self):
        """Verifica que load_schema_definition falle con FileNotFoundError si el archivo no existe."""
        missing_path = os.path.join(self.test_dir, "non_existent_schema.py")
        with self.assertRaises(FileNotFoundError):
            load_schema_definition(missing_path)

    def test_create_app_context_missing_schema_raises_filenotfound(self):
        """Verifica que create_app_context en modo consume falle si el esquema no existe."""
        missing_path = os.path.join(self.test_dir, "missing_schema.py")
        with self.assertRaises(FileNotFoundError):
            create_app_context(
                action="consume",
                config_file=self.config_file,
                key_file=self.key_file,
                schema_file=missing_path,
                base_dir=self.test_dir,
            )

    def test_load_schema_definition_syntax_error_raises_runtimeerror(self):
        """Verifica que errores de sintaxis o ejecución en el esquema lancen RuntimeError."""
        bad_schema = os.path.join(self.test_dir, "bad_syntax_schema.py")
        with open(bad_schema, "w", encoding="utf-8") as f:
            f.write("CONFIG_SCHEMA = { invalid syntax here\n")

        with self.assertRaises(RuntimeError):
            load_schema_definition(bad_schema)

    def test_load_schema_definition_missing_config_schema_attr_raises_attributeerror(self):
        """Verifica que si el archivo no define 'CONFIG_SCHEMA' se lance AttributeError."""
        legacy_schema = os.path.join(self.test_dir, "legacy_schema.py")
        with open(legacy_schema, "w", encoding="utf-8") as f:
            f.write("DEFAULT_CONFIG = {'app': {'name': 'Legacy'}}\n")

        with self.assertRaises(AttributeError) as ctx:
            load_schema_definition(legacy_schema)
        self.assertIn("CONFIG_SCHEMA", str(ctx.exception))

    def test_load_schema_definition_non_dict_config_schema_raises_typeerror(self):
        """Verifica que si 'CONFIG_SCHEMA' no es un dict se lance TypeError."""
        invalid_type_schema = os.path.join(self.test_dir, "invalid_type_schema.py")
        with open(invalid_type_schema, "w", encoding="utf-8") as f:
            f.write("CONFIG_SCHEMA = ['not', 'a', 'dict']\n")

        with self.assertRaises(TypeError) as ctx:
            load_schema_definition(invalid_type_schema)
        self.assertIn("CONFIG_SCHEMA", str(ctx.exception))

    def test_no_invented_backup_settings_when_omitted(self):
        """Verifica que no se inventen valores significativos de backup cuando _backup no está en CONFIG_SCHEMA."""
        schema_path = os.path.join(self.test_dir, "clean_schema.py")
        with open(schema_path, "w", encoding="utf-8") as f:
            f.write("CONFIG_SCHEMA = {'app': {'name': {'default': 'MiApp'}}}\n")

        res = load_schema_definition(schema_path)
        self.assertEqual(res["backup_settings"], {})
        self.assertNotIn("_backup", res["validation_rules"])

    def test_valid_config_schema_successful_load(self):
        """Verifica que un esquema válido con CONFIG_SCHEMA se cargue correctamente de forma determinista."""
        schema_path = os.path.join(self.test_dir, "valid_schema.py")
        schema_content = """
CONFIG_SCHEMA = {
    "_backup": {
        "enabled": True,
        "max_backups": 5
    },
    "app": {
        "title": {"default": "Sistema Central", "type": "str"},
        "token": {"default": "tok_123", "is_password": True}
    }
}
"""
        with open(schema_path, "w", encoding="utf-8") as f:
            f.write(schema_content)

        ctx = create_app_context(
            action="consume",
            config_file=self.config_file,
            key_file=self.key_file,
            schema_file=schema_path,
            base_dir=self.test_dir,
        )

        self.assertEqual(ctx.default_config["app"]["title"], "Sistema Central")
        self.assertIn("app.token", ctx.password_fields)
        self.assertEqual(ctx.backup_settings["max_backups"], 5)
        self.assertTrue(ctx.backup_settings["enabled"])

    def test_resolve_schema_path_compiled_host_relative_path(self):
        """Verifica que en modo compilado encuentre primero el esquema en el camino relativo indicado."""
        import sys
        temp_mei = tempfile.mkdtemp()
        orig_frozen = getattr(sys, "frozen", None)
        orig_meipass = getattr(sys, "_MEIPASS", None)
        try:
            sys.frozen = True
            sys._MEIPASS = temp_mei
            bundled_dir = os.path.join(temp_mei, "src", "core")
            os.makedirs(bundled_dir, exist_ok=True)
            bundled_file = os.path.join(bundled_dir, "config_schema.py")
            with open(bundled_file, "w", encoding="utf-8") as f:
                f.write("CONFIG_SCHEMA = {}")

            # Camino indicado por el anfitrión que no existe físicamente en base_dir
            resolved = resolve_schema_path(
                schema_param="src/core/config_schema.py",
                default_name="config_schema.py",
                base_dir=self.test_dir,
                is_standalone=False
            )
            self.assertEqual(resolved, os.path.abspath(bundled_file))
        finally:
            if orig_frozen is None:
                if hasattr(sys, "frozen"):
                    del sys.frozen
            else:
                sys.frozen = orig_frozen
            if orig_meipass is None:
                if hasattr(sys, "_MEIPASS"):
                    del sys._MEIPASS
            else:
                sys._MEIPASS = orig_meipass
            shutil.rmtree(temp_mei, ignore_errors=True)

    def test_resolve_schema_path_compiled_root_fallback(self):
        """Verifica que en modo compilado encuentre el esquema en la raíz del bundle si no está en la subcarpeta."""
        import sys
        temp_mei = tempfile.mkdtemp()
        orig_frozen = getattr(sys, "frozen", None)
        orig_meipass = getattr(sys, "_MEIPASS", None)
        try:
            sys.frozen = True
            sys._MEIPASS = temp_mei
            root_file = os.path.join(temp_mei, "config_schema.py")
            with open(root_file, "w", encoding="utf-8") as f:
                f.write("CONFIG_SCHEMA = {}")

            resolved = resolve_schema_path(
                schema_param="src/core/config_schema.py",
                default_name="config_schema.py",
                base_dir=self.test_dir,
                is_standalone=False
            )
            self.assertEqual(resolved, os.path.abspath(root_file))
        finally:
            if orig_frozen is None:
                if hasattr(sys, "frozen"):
                    del sys.frozen
            else:
                sys.frozen = orig_frozen
            if orig_meipass is None:
                if hasattr(sys, "_MEIPASS"):
                    del sys._MEIPASS
            else:
                sys._MEIPASS = orig_meipass
            shutil.rmtree(temp_mei, ignore_errors=True)

    def test_resolve_schema_path_compiled_missing_raises_filenotfound(self):
        """Verifica que en modo compilado lance FileNotFoundError si no existe en el bundle."""
        import sys
        temp_mei = tempfile.mkdtemp()
        orig_frozen = getattr(sys, "frozen", None)
        orig_meipass = getattr(sys, "_MEIPASS", None)
        try:
            sys.frozen = True
            sys._MEIPASS = temp_mei
            with self.assertRaises(FileNotFoundError):
                resolve_schema_path(
                    schema_param="src/core/config_schema.py",
                    default_name="config_schema.py",
                    base_dir=self.test_dir,
                    is_standalone=False
                )
        finally:
            if orig_frozen is None:
                if hasattr(sys, "frozen"):
                    del sys.frozen
            else:
                sys.frozen = orig_frozen
            if orig_meipass is None:
                if hasattr(sys, "_MEIPASS"):
                    del sys._MEIPASS
            else:
                sys._MEIPASS = orig_meipass
            shutil.rmtree(temp_mei, ignore_errors=True)


if __name__ == "__main__":
    unittest.main()

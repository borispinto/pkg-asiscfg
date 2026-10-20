# -*- coding: utf-8 -*-
# SPDX-FileCopyrightText: 2026 Asisnet Computacion, CA <proyectos@asisnet.net>
# SPDX-License-Identifier: MIT
# Autor: Boris Pinto <borispinto@asisnet.net>
# File: tests/test_public_header_and_reload.py

"""
Pruebas unitarias para validar la cabecera canónica en la Línea 1,
el posicionamiento de claves informativas públicas ('# <key>: <val>'),
la invariante de que 'is_password: True' fuerza 'public: False',
y el ciclo completo de grabado y recarga sin discrepancias.
"""

import os
import shutil
import tempfile
import unittest

from asiscfg.context import create_app_context
from asiscfg.crypto import detect_format_engine
from asiscfg.storage import generate_key_file, load_config, save_config


class TestPublicHeaderAndReload(unittest.TestCase):

    def setUp(self):
        self.test_dir = tempfile.mkdtemp()
        self.config_file = os.path.join(self.test_dir, "test_app.cfg")
        self.key_file = os.path.join(self.test_dir, "test_app.key")
        self.schema_file = os.path.join(self.test_dir, "config_schema.py")

        schema_code = '''
CONFIG_SCHEMA = {
    "app": {
        "name": {"default": "Sistema Test", "public": True},
        "version": {"default": "v2.5.0", "public": True},
        "secret_token": {"default": "12345", "is_password": True}
    },
    "general": {
        "active_language": {"default": "es", "public": True},
        "timeout": {"default": 30, "type": "int"}
    },
    "@profiles": {
        "_template": {
            "info": {
                "razon_social": {"default": "Empresa Base", "public": True}
            },
            "conexiones": {
                "host": {"default": "localhost"},
                "password": {"default": "pass123", "is_password": True}
            }
        },
        "01": {
            "info": {
                "razon_social": "Empresa Uno S.A."
            },
            "conexiones": {
                "host": "sql.local",
                "password": "mi_password"
            }
        }
    }
}
'''
        with open(self.schema_file, "w", encoding="utf-8") as f:
            f.write(schema_code)

        self.context = create_app_context(
            action="ui",
            config_file=self.config_file,
            key_file=self.key_file,
            schema_file=self.schema_file,
            is_standalone=True,
        )
        generate_key_file(self.context)
        # Recargar contexto con la clave recién generada
        self.context = create_app_context(
            action="ui",
            config_file=self.config_file,
            key_file=self.key_file,
            schema_file=self.schema_file,
            is_standalone=True,
        )

    def tearDown(self):
        shutil.rmtree(self.test_dir, ignore_errors=True)

    def test_is_password_fields_are_never_public(self):
        """Verifica que si is_password es True, el campo no entra a public_fields ni se publica."""
        from asiscfg.schema import extract_schema_metadata
        schema = {
            "app": {
                "token": {"default": "secret123", "is_password": True, "public": True}
            }
        }
        meta = extract_schema_metadata(schema)
        self.assertIn("app.token", meta["password_fields"])
        self.assertNotIn("app.token", meta["public_fields"])

    def test_save_places_format_header_on_line_1_and_public_keys_after(self):
        """
        Verifica que save_config coloca la cabecera canónica en la Línea 1,
        seguida de todas las claves marcadas como 'public: True' (incluyendo app.*).
        """
        save_config(self.context, self.context.default_config)
        self.assertTrue(os.path.exists(self.config_file))

        with open(self.config_file, "r", encoding="utf-8", errors="ignore") as f:
            lines = [f.readline().rstrip() for _ in range(10)]

        # Línea 1: Cabecera canónica
        self.assertEqual(lines[0], "# ASISCFG_PLAIN")
        # Líneas informativas públicas
        self.assertEqual(lines[1], "# app.name: Sistema Test")
        self.assertEqual(lines[2], "# app.version: v2.5.0")
        self.assertEqual(lines[3], "# general.active_language: es")
        self.assertEqual(lines[4], "# @profiles.01.info.razon_social: Empresa Uno S.A.")

    def test_reload_config_succeeds_without_error(self):
        """Verifica que load_config recarga el archivo sin fallas tras ser guardado."""
        save_config(self.context, self.context.default_config)
        reloaded = load_config(self.context, edit_mode=True)

        self.assertEqual(reloaded.valor("app.name"), "Sistema Test")
        self.assertEqual(reloaded.valor("app.version"), "v2.5.0")
        self.assertEqual(reloaded.valor("general.active_language"), "es")
        self.assertEqual(reloaded.valor_profile("info.razon_social", "01"), "Empresa Uno S.A.")
        self.assertEqual(reloaded.valorpass_profile("conexiones.password", "01"), "mi_password")

    def test_detect_format_engine_tolerates_comments_and_first_line(self):
        """Verifica que detect_format_engine detecta tanto en Línea 1 como con comentarios previos."""
        data_line1 = b"# ASISCFG_PLAIN\n# app.name: Test\n{}"
        mode, engine = detect_format_engine(data_line1)
        self.assertEqual(mode, "plain")
        self.assertEqual(engine.header, "# ASISCFG_PLAIN")

        data_preceded_by_comments = b"# app.name: Test\n# ASISCFG_FERNET\ngAAAAAB..."
        mode_f, engine_f = detect_format_engine(data_preceded_by_comments)
        self.assertEqual(mode_f, "fernet")
        self.assertEqual(engine_f.header, "# ASISCFG_FERNET")


if __name__ == "__main__":
    unittest.main()

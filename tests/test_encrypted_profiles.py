# -*- coding: utf-8 -*-
# SPDX-FileCopyrightText: 2026 Asisnet Computacion, CA <proyectos@asisnet.net>
# SPDX-License-Identifier: MIT
# Autor: Boris Pinto <borispinto@asisnet.net>
# File: tests/test_encrypted_profiles.py

import os
import shutil
import tempfile
import unittest
from unittest.mock import patch
from asiscfg.context import create_app_context
from asiscfg.storage import save_config, generate_key_file
from asiscfg.ui.app import ConfigApp

SCHEMA_CONTENT = """
CONFIG_SCHEMA = {
    "app": {
        "name": {"default": "Test App"},
    },
    "@asiscfg": {
        "admin_pass_hash": "2a97516c354b68848cdbd8f54a226a0a55b21ed138e207ad6c5cbb9c00aa5aea"
    },
    "@profiles": {
        "_template": {
            "conexiones": {
                "user": {"default": "sa"},
                "password": {"default": "secret123", "is_password": True},
            }
        },
        "01": {
            "conexiones": {
                "user": "sa",
                "password": "secret123"
            }
        }
    }
}
"""

class TestEncryptedProfiles(unittest.TestCase):
    """Pruebas para verificar la ausencia de diferencias falsas en campos encriptados de perfiles."""

    def setUp(self):
        self.test_dir = tempfile.mkdtemp()
        self.config_path = os.path.join(self.test_dir, "test.cfg")
        self.key_path = os.path.join(self.test_dir, "test.key")
        self.schema_path = os.path.join(self.test_dir, "test_schema.py")

        with open(self.schema_path, "w", encoding="utf-8") as f:
            f.write(SCHEMA_CONTENT)

        self.ctx = create_app_context(
            config_file=self.config_path,
            key_file=self.key_path,
            schema_file=self.schema_path,
            format_mode="fernet"
        )
        generate_key_file(self.ctx)

    def tearDown(self):
        shutil.rmtree(self.test_dir, ignore_errors=True)

    def test_load_encrypted_and_check_no_false_diffs(self):
        """Verifica que al cargar un archivo en formato totalmente encriptado no se reporten diferencias falsas."""
        save_config(self.ctx)

        app = ConfigApp(context=self.ctx, dev_mode=True)
        if hasattr(app, "login_frame") and app.login_frame:
            app.login_frame.destroy()
        app._build_main_ui()

        try:
            diffs = app.has_unsaved_changes()
            self.assertEqual(diffs, [])
        finally:
            app.destroy()

    @patch("asiscfg.ui.app.messagebox.askyesno", return_value=True)
    @patch("asiscfg.ui.app.messagebox.showinfo", return_value=True)
    def test_save_encrypted_and_check_no_false_diffs(self, mock_info, mock_ask):
        """Verifica que al guardar en formato encriptado no se reporten diferencias falsas al intentar salir."""
        app = ConfigApp(context=self.ctx, dev_mode=True)
        if hasattr(app, "login_frame") and app.login_frame:
            app.login_frame.destroy()
        app._build_main_ui()

        try:
            app._perform_save(format_mode="fernet")
            diffs = app.has_unsaved_changes()
            self.assertEqual(diffs, [])
        finally:
            app.destroy()

if __name__ == "__main__":
    unittest.main()

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
from asiscfg.models import create_app_context
from asiscfg.core import save_config, load_config, generate_key_file
from asiscfg.ui.app import ConfigApp
from PRUEBA.SCHEMA.config_schema import DEFAULT_CONFIG

class TestEncryptedProfiles(unittest.TestCase):
    """Pruebas para verificar la ausencia de diferencias falsas en campos encriptados de perfiles."""

    def setUp(self):
        self.test_dir = tempfile.mkdtemp()
        self.config_path = os.path.join(self.test_dir, "test.cfg")
        self.key_path = os.path.join(self.test_dir, "test.key")
        self.schema_path = os.path.join(self.test_dir, "test_schema.py")

        # Generar schema file
        with open("PRUEBA/SCHEMA/config_schema.py", "r", encoding="utf-8") as f:
            content = f.read()
        with open(self.schema_path, "w", encoding="utf-8") as f:
            f.write(content)

        self.ctx = create_app_context(
            config_file=self.config_path,
            key_file=self.key_path,
            schema_file=self.schema_path
        )
        generate_key_file(self.ctx, key_path=self.key_path)

    def tearDown(self):
        shutil.rmtree(self.test_dir, ignore_errors=True)

    def test_load_encrypted_and_check_no_false_diffs(self):
        """Verifica que al cargar un archivo en formato totalmente encriptado no se reporten diferencias falsas."""
        save_config(
            self.ctx,
            format_mode="fernet"
        )

        app = ConfigApp(context=self.ctx, dev_mode=True)
        if hasattr(app, "login_frame") and app.login_frame:
            app.login_frame.destroy()
        app._build_main_ui()

        try:
            diffs = app.has_unsaved_changes()
            self.assertEqual(diffs, [])
        finally:
            app.destroy()

    @patch("tkinter.messagebox.askyesno", return_value=True)
    @patch("tkinter.messagebox.showinfo", return_value=True)
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

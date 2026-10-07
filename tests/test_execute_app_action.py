# -*- coding: utf-8 -*-
# SPDX-FileCopyrightText: 2026 Asisnet Computacion, CA <proyectos@asisnet.net>
# SPDX-License-Identifier: MIT
# Autor: Boris Pinto <borispinto@asisnet.net>
# File: tests/test_execute_app_action.py

import os
import tempfile
import unittest
from unittest.mock import patch, MagicMock
from asiscfg.models import create_app_context, AppConfigContext
from asiscfg.core import execute_app_action


class TestExecuteAppAction(unittest.TestCase):
    """Pruebas unitarias para execute_app_action."""

    def setUp(self):
        self.test_dir = tempfile.mkdtemp()
        self.config_path = os.path.join(self.test_dir, "test_config.enc")
        self.key_path = os.path.join(self.test_dir, "test_key.key")
        self.schema_path = os.path.join(self.test_dir, "custom_schema.py")

        with open(self.key_path, "wb") as f:
            f.write(b"SAMPLE_KEY_CONTENT_1234567890")

        with open(self.schema_path, "w", encoding="utf-8") as f:
            f.write("DEFAULT_CONFIG = {'app': {'val': '123'}}\n")

    def test_execute_app_action_consume_returns_none(self):
        ctx = create_app_context(
            action="consume",
            config_file=self.config_path,
            key_file=self.key_path,
            schema_file=self.schema_path
        )
        res = execute_app_action(ctx)
        self.assertIsNone(res)

    @patch("asiscfg.core.generate_key_file")
    def test_execute_app_action_generate_key_success(self, mock_gen):
        mock_gen.return_value = b"NEW_KEY"
        target_key = os.path.join(self.test_dir, "new_generated.key")
        ctx = create_app_context(
            action="generate_key",
            key_file=target_key
        )
        res = execute_app_action(ctx, overwrite_key=True)
        self.assertEqual(res, 0)
        mock_gen.assert_called_once_with(context=ctx, overwrite=True)

    @patch("asiscfg.core.generate_key_file", side_effect=Exception("Disk full"))
    def test_execute_app_action_generate_key_error(self, mock_gen):
        target_key = os.path.join(self.test_dir, "new_generated.key")
        ctx = create_app_context(
            action="generate_key",
            key_file=target_key
        )
        res = execute_app_action(ctx, overwrite_key=False)
        self.assertEqual(res, 1)

    @patch("asiscfg.core.export_config_schema")
    def test_execute_app_action_export_schema_success(self, mock_export):
        mock_export.return_value = 0
        target_schema = os.path.join(self.test_dir, "exported_schema.py")
        ctx = create_app_context(
            action="export_schema",
            schema_file=target_schema
        )
        res = execute_app_action(ctx)
        self.assertEqual(res, 0)
        mock_export.assert_called_once_with(
            source_path=ctx.schema_file_path,
            target_path=ctx.base_dir
        )

    @patch("asiscfg.core.run_asiscfg")
    def test_execute_app_action_ui_success(self, mock_run_ui):
        mock_run_ui.return_value = 0
        ctx = create_app_context(
            action="ui",
            config_file=self.config_path,
            key_file=self.key_path,
            schema_file=self.schema_path,
            dev_mode=True
        )
        res = execute_app_action(
            context=ctx,
            theme="light",
            allow_app_edit=True
        )
        self.assertEqual(res, 0)
        mock_run_ui.assert_called_once_with(
            context=ctx,
            i18n_path=None,
            dev_mode=True,
            allow_app_edit=True,
            reset_admin_pass=False,
            theme="light"
        )

    @patch("asiscfg.core.sys.exit")
    @patch("asiscfg.core.export_config_schema", return_value=0)
    def test_execute_app_action_exit_on_finish(self, mock_export, mock_exit):
        target_schema = os.path.join(self.test_dir, "exported_schema.py")
        ctx = create_app_context(
            action="export_schema",
            schema_file=target_schema
        )
        res = execute_app_action(ctx, exit_on_finish=True)
        mock_exit.assert_called_once_with(0)

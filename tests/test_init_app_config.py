# -*- coding: utf-8 -*-
# SPDX-FileCopyrightText: 2026 Asisnet Computacion, CA <proyectos@asisnet.net>
# SPDX-License-Identifier: MIT
# Autor: Boris Pinto <borispinto@asisnet.net>
# File: tests/test_init_app_config.py

import os
import sys
import tempfile
import unittest
from unittest.mock import patch, MagicMock
from asiscfg.cli import (
    parse_config_args,
    init_app_config,
)
from asiscfg.context import AppConfigContext
from asiscfg.models import ConfigDict, ConfigBootstrap


class TestInitAppConfig(unittest.TestCase):
    """Pruebas unitarias para init_app_config y ciclo CLI."""

    def setUp(self):
        self.test_dir = tempfile.mkdtemp()
        self.config_path = os.path.join(self.test_dir, "test_config.enc")
        self.key_path = os.path.join(self.test_dir, "test_key.key")
        self.schema_path = os.path.join(self.test_dir, "custom_schema.py")

        with open(self.config_path, "wb") as f:
            f.write(b"# ASISCFG_PLAIN\n{\"app\": {\"val\": \"123\"}}\n")

        with open(self.key_path, "wb") as f:
            f.write(b"SAMPLE_KEY_CONTENT_1234567890")

        with open(self.schema_path, "w", encoding="utf-8") as f:
            f.write("CONFIG_SCHEMA = {'app': {'val': '123'}}\nVALIDATION_RULES = {}\n")

    def test_parse_config_args_separates_known_and_remaining(self):
        args = [
            "20260100300001",
            "02",
            "/config-file",
            "client/asientos.cfg",
            "/key-file",
            "secret.key",
            "/debug",
            "/dev"
        ]
        tokens, remaining = parse_config_args(args)
        self.assertEqual(tokens["config_file"], "client/asientos.cfg")
        self.assertEqual(tokens["key_file"], "secret.key")
        self.assertTrue(tokens["debug"])
        self.assertFalse(tokens["show"])
        self.assertTrue(tokens["dev_mode"])
        # /debug es consumido limpiamente por asiscfg y ya no se filtra a remaining_args
        self.assertEqual(remaining, ["20260100300001", "02"])

    def test_parse_config_args_handles_paths_with_spaces_and_quotes(self):
        """Verifica que rutas con espacios en blanco no sean partidas y se limpien comillas."""
        schema_path = r"D:\COMSISA Proyectos\asisnet-asientos\src\core\config_schema.py"
        config_path = r"D:\COMSISA Proyectos\asisnet-asientos\clientes\LOCAL\proyecto.cfg"
        key_path = r"D:\COMSISA Proyectos\asisnet-asientos\proyecto.key"

        args = [
            "--schema-file",
            schema_path,
            "--config-file",
            f'"{config_path}"',
            "--key-file",
            key_path,
            "--dev",
            "--ui",
            "--theme",
            "dark"
        ]
        tokens, remaining = parse_config_args(args)
        self.assertEqual(tokens["schema_file"], schema_path)
        self.assertEqual(tokens["config_file"], config_path)
        self.assertEqual(tokens["key_file"], key_path)
        self.assertTrue(tokens["dev_mode"])
        self.assertTrue(tokens["ui"])
        self.assertEqual(tokens["theme"], "dark")
        self.assertEqual(remaining, [])

    def test_parse_config_args_handles_inline_flags_with_spaces(self):
        """Verifica que flags con '=' o ':' integrado y rutas con espacios se procesen íntegramente."""
        cfg_path = r"C:\Archivos de Programa\Mi Empresa\sistema.cfg"
        key_path = r"C:\Archivos de Programa\Mi Empresa\sistema.key"

        args = [
            f"--config-file={cfg_path}",
            f'/key-file:"{key_path}"',
            "--dev"
        ]
        tokens, remaining = parse_config_args(args)
        self.assertEqual(tokens["config_file"], cfg_path)
        self.assertEqual(tokens["key_file"], key_path)
        self.assertTrue(tokens["dev_mode"])
        self.assertEqual(remaining, [])

    def test_parse_config_args_handles_single_command_string(self):
        """Verifica que una cadena CLI completa como string sea parseada respetando comillas en rutas con espacios."""
        cmd = r'--schema-file "D:\COMSISA Proyectos\schema.py" --dev --theme dark'
        tokens, remaining = parse_config_args(cmd)
        self.assertEqual(tokens["schema_file"], r"D:\COMSISA Proyectos\schema.py")
        self.assertTrue(tokens["dev_mode"])
        self.assertEqual(tokens["theme"], "dark")
        self.assertEqual(remaining, [])

    def test_parse_config_args_standardizes_remaining_args_separator(self):
        """Verifica que remaining_args estandarice separadores a '/' respetando números y tokens aislados."""
        args = [
            "20260100300001",
            "02",
            "--custom-flag",
            "--param=test",
            "-shortflag",
            "-level:3",
            "/already-slash",
            "-5",
            "-1.5",
            "--",
            "-",
            "001",
        ]
        tokens, remaining = parse_config_args(args)
        expected = [
            "20260100300001",
            "02",
            "/custom-flag",
            "/param=test",
            "/shortflag",
            "/level:3",
            "/already-slash",
            "-5",
            "-1.5",
            "--",
            "-",
            "001",
        ]
        self.assertEqual(remaining, expected)

    @patch("asiscfg.cli.load_config")
    def test_init_app_config_consume_success_with_args(self, mock_load):
        mock_cfg = MagicMock(spec=ConfigDict)
        mock_load.return_value = mock_cfg

        args = [
            "20260100300001",
            "02",
            "--config-file",
            self.config_path,
            "--key-file",
            self.key_path,
            "--schema-file",
            self.schema_path,
            "--dev"
        ]

        boot = init_app_config(
            args=args,
            app_title="TEST_APP",
            app_files="test_app",
            app_schema=self.schema_path
        )

        self.assertEqual(boot.config, mock_cfg)
        self.assertIsInstance(boot.context, AppConfigContext)
        self.assertIsNone(boot.exit_code)
        self.assertEqual(boot.remaining_args, ["20260100300001", "02"])
        mock_load.assert_called_once_with(context=boot.context)

    @patch("asiscfg.cli.load_config")
    def test_init_app_config_consume_success_with_defaults(self, mock_load):
        mock_cfg = MagicMock(spec=ConfigDict)
        mock_load.return_value = mock_cfg

        args = [
            "--config-file",
            self.config_path,
            "--key-file",
            self.key_path,
            "--dev"
        ]

        boot = init_app_config(
            args=args,
            app_title="TEST_APP",
            app_files="test_app",
            app_schema=self.schema_path
        )

        self.assertEqual(boot.config, mock_cfg)
        self.assertIsInstance(boot.context, AppConfigContext)
        self.assertIsNone(boot.exit_code)
        mock_load.assert_called_once_with(context=boot.context)

    @patch("asiscfg.cli.execute_app_action", return_value=0)
    def test_init_app_config_ui_action_delegation(self, mock_exec_action):
        args = [
            "/ui",
            "/config-file",
            self.config_path,
            "/key-file",
            self.key_path,
            "/theme",
            "light",
            "/edit",
            "/format-mode",
            "fernet"
        ]

        boot = init_app_config(
            args=args,
            app_title="TEST_APP",
            app_files="test_app",
            app_schema=self.schema_path
        )

        self.assertIsNone(boot.config)
        self.assertIsInstance(boot.context, AppConfigContext)
        self.assertEqual(boot.context.action, "ui")
        self.assertEqual(boot.context.format_mode, "fernet")
        self.assertEqual(boot.exit_code, 0)
        mock_exec_action.assert_called_once()

    @patch("asiscfg.ui.dialogs.show_modal_message_dialog")
    @patch("asiscfg.cli.create_app_context", side_effect=ValueError("Invalid Schema Format"))
    def test_init_app_config_context_init_failure_with_modal(self, mock_create, mock_modal):
        args = [
            "--show",
            "--config-file",
            self.config_path,
            "--key-file",
            self.key_path
        ]

        boot = init_app_config(
            args=args,
            app_title="MI_APP",
            app_files="test_app",
            app_schema=self.schema_path
        )

        self.assertIsNone(boot.config)
        self.assertIsNone(boot.context)
        self.assertEqual(boot.exit_code, 1)
        mock_modal.assert_called_once()
        call_kwargs = mock_modal.call_args[1] if mock_modal.call_args[1] else {}
        if "title" in call_kwargs:
            self.assertIn("MI_APP - Error Fatal", call_kwargs["title"])

    @patch("asiscfg.ui.dialogs.show_modal_message_dialog")
    @patch("asiscfg.cli.load_config", side_effect=Exception("Corrupt config file"))
    def test_init_app_config_load_config_failure_with_modal(self, mock_load, mock_modal):
        args = [
            "--show",
            "--config-file",
            self.config_path,
            "--key-file",
            self.key_path,
            "--last-resource"
        ]

        boot = init_app_config(
            args=args,
            app_title="MI_APP",
            app_files="test_app",
            app_schema=self.schema_path
        )

        self.assertIsNone(boot.config)
        self.assertIsInstance(boot.context, AppConfigContext)
        self.assertEqual(boot.exit_code, 1)
        mock_modal.assert_called_once()

    @patch("asiscfg.cli.execute_app_action", return_value=0)
    def test_main_standalone_execution(self, mock_exec):
        from asiscfg.cli import main as cli_main
        args = [
            "--config-file",
            self.config_path,
            "--key-file",
            self.key_path,
            "--schema-file",
            self.schema_path,
            "--edit",
            "--format-mode",
            "plain"
        ]
        code = cli_main(args)
        self.assertEqual(code, 0)
        mock_exec.assert_called_once()
        ctx_called = mock_exec.call_args[1]["context"]
        self.assertEqual(ctx_called.action, "ui")
        self.assertEqual(ctx_called.format_mode, "plain")
        self.assertTrue(mock_exec.call_args[1].get("edit"))

    @patch("asiscfg.cli.load_config")
    def test_foxpro_call_immutable_arguments(self, mock_load):
        mock_cfg = MagicMock(spec=ConfigDict)
        mock_load.return_value = mock_cfg

        args = [
            "20261020500001",
            "02",
            "--config-file",
            self.config_path,
            "--key-file",
            self.key_path
        ]
        boot = init_app_config(
            args=args,
            app_title="ASIENTOS",
            app_files="test_app",
            app_schema=self.schema_path
        )

        self.assertIsNone(boot.exit_code)
        self.assertEqual(boot.config, mock_cfg)
        self.assertEqual(boot.remaining_args, ["20261020500001", "02"])

    @patch("asiscfg.cli.load_config")
    def test_foxpro_with_flags_preserves_positional_arguments(self, mock_load):
        mock_cfg = MagicMock(spec=ConfigDict)
        mock_load.return_value = mock_cfg

        # FoxPro o diagnóstico pasando flag con valor seguido inmediatamente de posicionales
        args = [
            "--config-file",
            self.config_path,
            "20261020500001",
            "02",
            "--debug",
            "--key-file",
            self.key_path
        ]
        boot = init_app_config(
            args=args,
            app_title="ASIENTOS",
            app_files="test_app",
            app_schema=self.schema_path
        )

        self.assertIsNone(boot.exit_code)
        self.assertEqual(boot.config, mock_cfg)
        self.assertEqual(boot.remaining_args, ["20261020500001", "02"])
        self.assertTrue(boot.debug)
        self.assertFalse(boot.dev_mode)
        self.assertFalse(boot.context.dev_mode)

    def test_config_bootstrap_delegation_methods(self):
        mock_cfg = MagicMock(spec=ConfigDict)
        mock_cfg.valor.return_value = "host_123"
        mock_cfg.valorpass.return_value = "pass_secret"
        mock_cfg.valor_profile.return_value = "prof_host"
        mock_cfg.valorpass_profile.return_value = "prof_pass"
        mock_cfg.valor_parent.return_value = "parent_val"
        mock_cfg.valorpass_parent.return_value = "parent_pass"

        boot = ConfigBootstrap(config=mock_cfg, remaining_args=["arg1"])
        self.assertEqual(boot.valor("db.host"), "host_123")
        self.assertEqual(boot.valorpass("db.pass"), "pass_secret")
        self.assertEqual(boot.valor_profile("db.host", "01"), "prof_host")
        self.assertEqual(boot.valorpass_profile("db.pass", "01"), "prof_pass")
        self.assertEqual(boot.valor_parent("db.host", "01"), "parent_val")
        self.assertEqual(boot.valorpass_parent("db.pass", "01"), "parent_pass")

        # Comportamiento seguro ante config is None
        empty_boot = ConfigBootstrap(config=None)
        self.assertEqual(empty_boot.valor("db.host", default="def"), "def")
        self.assertEqual(empty_boot.valorpass("db.pass", default="def_pass"), "def_pass")
        self.assertEqual(empty_boot.valor_profile("db.host", "01", default="def_prof"), "def_prof")
        self.assertEqual(empty_boot.valorpass_profile("db.pass", "01", default="def_pass_prof"), "def_pass_prof")
        self.assertEqual(empty_boot.valor_parent("db.host", "01", default="def_parent"), "def_parent")
        self.assertEqual(empty_boot.valorpass_parent("db.pass", "01", default="def_pass_parent"), "def_pass_parent")

    def test_action_priority_sequence(self):
        # 1. Por defecto es consume
        tokens, _ = parse_config_args([])
        self.assertEqual(tokens["action"], "consume")

        # 2. --export-schema tiene máxima prioridad
        tokens, _ = parse_config_args(["--export-schema", "--generate-key", "--ui"])
        self.assertEqual(tokens["action"], "export_schema")

        tokens, _ = parse_config_args(["/export-schema"])
        self.assertEqual(tokens["action"], "export_schema")

        # 3. --generate-key tiene prioridad sobre --ui
        tokens, _ = parse_config_args(["--generate-key", "--ui"])
        self.assertEqual(tokens["action"], "generate_key")

        tokens, _ = parse_config_args(["/generate-key"])
        self.assertEqual(tokens["action"], "generate_key")

        # 4. --ui sobre consume
        tokens, _ = parse_config_args(["--ui"])
        self.assertEqual(tokens["action"], "ui")

        tokens, _ = parse_config_args(["/ui"])
        self.assertEqual(tokens["action"], "ui")

    def test_show_and_shared_flags_behavior(self):
        # Default es show: False
        tokens, remaining = parse_config_args([])
        self.assertFalse(tokens["show"])

        # --show activa show: True y es consumido limpiamente (remaining vacío)
        tokens, remaining = parse_config_args(["--show"])
        self.assertTrue(tokens["show"])
        self.assertEqual(remaining, [])

        # -show activa show: True y es consumido limpiamente
        tokens, remaining = parse_config_args(["-show"])
        self.assertTrue(tokens["show"])
        self.assertEqual(remaining, [])

        # /show activa show: True y es consumido limpiamente
        tokens, remaining = parse_config_args(["/show"])
        self.assertTrue(tokens["show"])
        self.assertEqual(remaining, [])

    def test_all_separators_for_value_and_bool_flags(self):
        """Verifica que los separadores ['/', '-', '--'] funcionen de manera simétrica para value y bool flags."""
        separadores = ["/", "-", "--"]

        for sep in separadores:
            # Value flags con espacio
            tokens, _ = parse_config_args([f"{sep}config-file", "app.cfg", f"{sep}format-mode", "fernet"])
            self.assertEqual(tokens["config_file"], "app.cfg")
            self.assertEqual(tokens["format_mode"], "fernet")

            # Value flags con '='
            tokens, _ = parse_config_args([f"{sep}config-file=app.cfg", f"{sep}format-mode=aes256_gcm"])
            self.assertEqual(tokens["config_file"], "app.cfg")
            self.assertEqual(tokens["format_mode"], "aes256_gcm")

            # Value flags con ':'
            tokens, _ = parse_config_args([f"{sep}key-file:secret.key", f"{sep}theme:light"])
            self.assertEqual(tokens["key_file"], "secret.key")
            self.assertEqual(tokens["theme"], "light")

            # Bool flags
            tokens, _ = parse_config_args([f"{sep}dev", f"{sep}edit", f"{sep}last-resource", f"{sep}reset-admin-pass"])
            self.assertTrue(tokens["dev_mode"])
            self.assertTrue(tokens["edit"])
            self.assertTrue(tokens["last_resource"])
            self.assertTrue(tokens["reset_admin_pass"])

            # Action flags
            tokens, _ = parse_config_args([f"{sep}ui"])
            self.assertEqual(tokens["action"], "ui")

            tokens, _ = parse_config_args([f"{sep}generate-key"])
            self.assertEqual(tokens["action"], "generate_key")

            tokens, _ = parse_config_args([f"{sep}export-schema"])
            self.assertEqual(tokens["action"], "export_schema")

            # Help flags
            for h_flag in ["help", "h", "?"]:
                tokens, _ = parse_config_args([f"{sep}{h_flag}"])
                self.assertTrue(tokens["help"])

    def test_create_cli_parser_help_no_action_no_noshow(self):
        from asiscfg.cli import create_cli_parser
        parser = create_cli_parser()
        help_text = parser.format_help()

        # No debe contener /action como argumento directo
        self.assertNotIn("/action", help_text)
        # No debe contener /noshow
        self.assertNotIn("/noshow", help_text)
        # Debe contener /show
        self.assertIn("/show", help_text)
        # Debe contener flags de acción en orden con prefijo '/'
        self.assertIn("/export-schema", help_text)
        self.assertIn("/generate-key", help_text)
        self.assertIn("/ui", help_text)
        self.assertIn("/help", help_text)
        self.assertIn("/h", help_text)
        self.assertIn("/?", help_text)
        self.assertIn("Separadores válidos: ['-', '--', '/']", help_text)

    def test_init_app_config_install_mode_creates_files(self):
        new_dir = tempfile.mkdtemp()
        cfg_path = os.path.join(new_dir, "myapp.cfg")
        key_path = os.path.join(new_dir, "myapp.key")

        self.assertFalse(os.path.exists(cfg_path))
        self.assertFalse(os.path.exists(key_path))

        args = [
            "--install",
            "--dev",
            "--config-file", cfg_path,
            "--key-file", key_path,
        ]

        with unittest.mock.patch("asiscfg.cli.execute_app_action", return_value=0) as mock_exec:
            boot = init_app_config(
                args=args,
                app_title="INSTALL_TEST",
                app_files="myapp",
                app_schema=self.schema_path
            )

        self.assertEqual(boot.exit_code, 0)
        self.assertTrue(os.path.exists(key_path))
        self.assertTrue(os.path.exists(cfg_path))
        mock_exec.assert_called_once()

    def test_create_cli_parser_with_app_help_dict(self):
        from asiscfg.cli import create_cli_parser

        app_help = {
            "description": "Descripción de Mi Aplicación",
            "epilog": "Ejemplo: MIAPP 123",
            "params": {
                "identificador": {"type": str, "help": "ID del recurso"},
                "custom-flag": {"type": bool, "help": "Flag personalizada"},
            },
        }

        parser = create_cli_parser(prog="MIAPP", app_help=app_help)
        help_text = parser.format_help()

        self.assertIn("Descripción de Mi Aplicación", help_text)
        self.assertIn("Ejemplo: MIAPP 123", help_text)
        self.assertIn("Parámetros de MIAPP:", help_text)
        self.assertIn("/identificador", help_text)
        self.assertIn("/custom-flag", help_text)
        self.assertIn("Opciones de Configuración Cifrada (asiscfg):", help_text)
        self.assertIn("/config-file", help_text)
        self.assertIn("Separadores válidos: ['-', '--', '/']", help_text)

    def test_create_cli_parser_with_minimal_app_help_dict(self):
        from asiscfg.cli import create_cli_parser

        app_help = {
            "params": {
                "only-arg": {"name": "only-arg", "type": bool, "help": "Solo un argumento"}
            }
        }

        parser = create_cli_parser(prog="TESTPROG", app_help=app_help)
        help_text = parser.format_help()
        self.assertIn("/only-arg", help_text)
        self.assertIn("Herramienta TESTPROG", help_text)
        self.assertIn("Opciones de Configuración Cifrada (asiscfg):", help_text)
        self.assertIn("Separadores válidos: ['-', '--', '/']", help_text)

    def test_init_app_config_help_invokes_app_help(self):
        from unittest.mock import patch
        import io

        app_help = {
            "description": "App Help Test",
            "params": {
                "custom-arg": {"type": str, "help": "Argumento de ayuda"}
            }
        }

        with patch("sys.stdout", new_callable=io.StringIO) as mock_stdout:
            boot = init_app_config(
                args=["-h"],
                app_title="DUMMY_APP",
                app_help=app_help,
            )

            self.assertEqual(boot.exit_code, 0)
            output = mock_stdout.getvalue()
            self.assertIn("App Help Test", output)
            self.assertIn("/custom-arg", output)
            self.assertIn("Opciones de Configuración Cifrada (asiscfg):", output)
            self.assertIn("Separadores válidos: ['-', '--', '/']", output)

    def test_normalize_app_help_and_params_rejects_invalid_structures(self):
        from asiscfg.cli import normalize_app_help_and_params

        # 1. No es un dict
        with self.assertRaises(TypeError):
            normalize_app_help_and_params("no_es_un_dict")

        with self.assertRaises(TypeError):
            normalize_app_help_and_params(12345)

        with self.assertRaises(TypeError):
            normalize_app_help_and_params(["lista"])

        class ObjetoNoSoportado:
            pass

        with self.assertRaises(TypeError):
            normalize_app_help_and_params(ObjetoNoSoportado())

        # 2. 'params' no es un dict
        with self.assertRaises(TypeError):
            normalize_app_help_and_params({"params": ["no_es_dict"]})

        # 3. Especificación de parámetro no es dict
        with self.assertRaises(TypeError):
            normalize_app_help_and_params({"params": {"empresa": "str"}})

        # 4. Falta 'type' obligatorio
        with self.assertRaises(ValueError):
            normalize_app_help_and_params({"params": {"empresa": {"name": "empresa"}}})

        # 5. 'type' es None
        with self.assertRaises(ValueError):
            normalize_app_help_and_params({"params": {"empresa": {"type": None}}})

    def test_init_app_config_with_declarative_app_help_and_separators(self):
        """Verifica que app_help declarativo reconozca valores con /, -, --, =, : y booleanos."""
        app_help = {
            "description": "App Contable",
            "params": {
                "empresa": {"type": str, "help": "Código de empresa", "required": True},
                "fecha": {"type": str, "help": "Fecha contable", "default": "2026-01-01"},
                "silent": {"type": bool, "help": "Modo silencioso"},
                "reintentos": {"type": int, "help": "Intentos", "default": 1},
            }
        }

        # Prueba con mezcla de separadores: /empresa:01, --silent, -reintentos=5 y posicionales FoxPro
        args = [
            "202610010001",
            "02",
            f"--config-file={self.config_path}",
            f"/key-file:{self.key_path}",
            f"--schema-file={self.schema_path}",
            "/empresa:01",
            "--silent",
            "-reintentos=5",
            "/debug"
        ]

        boot = init_app_config(
            args=args,
            app_title="Contabilidad",
            app_help=app_help,
        )

        self.assertIsNone(boot.exit_code)
        self.assertIsNotNone(boot.config)
        self.assertTrue(boot.debug)
        # Los posicionales FoxPro quedan 100% limpios
        self.assertEqual(boot.remaining_args, ["202610010001", "02"])
        # Parámetros parseados y tipados
        self.assertEqual(boot.param("empresa"), "01")
        self.assertEqual(boot.param("fecha"), "2026-01-01")
        self.assertTrue(boot.param("silent"))
        self.assertEqual(boot.param("reintentos"), 5)

    def test_init_app_config_validates_required_parameters(self):
        """Verifica que si falta un parámetro con required=True falle con exit_code=2."""
        app_help = {
            "params": {
                "empresa": {"type": str, "required": True, "help": "Empresa requerida"}
            }
        }

        args = [
            f"--config-file={self.config_path}",
            f"--key-file={self.key_path}",
            f"--schema-file={self.schema_path}",
        ]

        boot = init_app_config(args=args, app_help=app_help)
        self.assertEqual(boot.exit_code, 2)
        self.assertIsNone(boot.config)

    def test_init_app_config_validates_choices(self):
        """Verifica que un valor no perteneciente a choices resulte en exit_code=2."""
        app_help = {
            "params": {
                "modo": {"type": str, "choices": ["auto", "manual"], "default": "auto"}
            }
        }

        args = [
            f"--config-file={self.config_path}",
            f"--key-file={self.key_path}",
            f"--schema-file={self.schema_path}",
            "--modo", "invalido"
        ]

        boot = init_app_config(args=args, app_help=app_help)
        self.assertEqual(boot.exit_code, 2)
        self.assertIsNone(boot.config)

    def test_init_app_config_type_casting_failure(self):
        """Verifica que un valor no convertible al tipo requerido resulte en exit_code=2."""
        app_help = {
            "params": {
                "puerto": {"type": int, "default": 8080}
            }
        }

        args = [
            f"--config-file={self.config_path}",
            f"--key-file={self.key_path}",
            f"--schema-file={self.schema_path}",
            "/puerto:no_es_un_numero"
        ]

        boot = init_app_config(args=args, app_help=app_help)
        self.assertEqual(boot.exit_code, 2)
        self.assertIsNone(boot.config)

    def test_init_app_config_help_with_declarative_dict(self):
        """Verifica que --help genere la ayuda estructurada a partir del diccionario declarativo."""
        from unittest.mock import patch
        import io

        app_help = {
            "description": "Sistema de Prueba Declarativo",
            "epilog": "Ejemplo: test /param1:val",
            "params": {
                "param1": {"type": str, "help": "Primer parámetro"},
                "flag1": {"type": bool, "help": "Bandera booleana"},
            }
        }

        with patch("sys.stdout", new_callable=io.StringIO) as mock_stdout:
            boot = init_app_config(
                args=["--help"],
                app_title="DECLARATIVE_APP",
                app_help=app_help,
            )

            self.assertEqual(boot.exit_code, 0)
            output = mock_stdout.getvalue()
            self.assertIn("Sistema de Prueba Declarativo", output)
            self.assertIn("Ejemplo: test /param1:val", output)
            self.assertIn("Parámetros de DECLARATIVE_APP:", output)
            self.assertIn("/param1", output)
            self.assertIn("/flag1", output)
            self.assertIn("Separadores válidos: ['-', '--', '/']", output)
            self.assertIn("Opciones de Configuración Cifrada (asiscfg):", output)

    def test_install_priority_over_other_actions(self):
        """Verifica que --install tenga prioridad 1 sobre --ui, --generate-key, --export-schema."""
        from unittest.mock import patch
        cfg_path = os.path.join(self.test_dir, "pri_app.cfg")
        key_path = os.path.join(self.test_dir, "pri_app.key")

        args = [
            "--export-schema",
            "--generate-key",
            "--ui",
            "--install",
            "--dev",
            "--config-file", cfg_path,
            "--key-file", key_path,
        ]

        with patch("asiscfg.cli.execute_app_action", return_value=0) as mock_exec:
            boot = init_app_config(
                args=args,
                app_title="PRIORITY_TEST",
                app_schema=self.schema_path
            )

        self.assertEqual(boot.exit_code, 0)
        self.assertTrue(os.path.exists(key_path))
        self.assertTrue(os.path.exists(cfg_path))
        mock_exec.assert_called_once()

    def test_install_requires_administrative_privileges(self):
        """Verifica que --install falle tempranamente (exit_code=1) si no tiene privilegios de Administrador."""
        from unittest.mock import patch
        args = ["--install"]

        with patch("asiscfg.cli.is_admin", return_value=False):
            boot = init_app_config(
                args=args,
                app_title="ADMIN_FAIL_TEST",
                app_schema=self.schema_path
            )

        self.assertEqual(boot.exit_code, 1)
        self.assertIsNone(boot.config)

    def test_install_prompts_confirmation_when_files_exist_and_cancels(self):
        """Verifica que si existen archivos previos y el usuario cancela la confirmación, se interrumpa limpiamente."""
        from unittest.mock import patch
        cfg_path = os.path.join(self.test_dir, "exist_app.cfg")
        key_path = os.path.join(self.test_dir, "exist_app.key")

        with open(cfg_path, "w", encoding="utf-8") as f:
            f.write("EXISTING_DATA")

        args = ["--install", "--dev", "--config-file", cfg_path, "--key-file", key_path]

        with patch("asiscfg.ui.dialogs.confirm_action_dialog", return_value=False):
            boot = init_app_config(
                args=args,
                app_title="CANCEL_INSTALL_TEST",
                app_schema=self.schema_path
            )

        self.assertEqual(boot.exit_code, 0)
        # Asegurar que los datos originales no fueron modificados
        with open(cfg_path, "r", encoding="utf-8") as f:
            self.assertEqual(f.read(), "EXISTING_DATA")

    def test_install_prompts_confirmation_when_files_exist_and_proceeds(self):
        """Verifica que si existen archivos previos y el usuario confirma, se reinicialicen los archivos y lance UI."""
        from unittest.mock import patch
        cfg_path = os.path.join(self.test_dir, "over_app.cfg")
        key_path = os.path.join(self.test_dir, "over_app.key")

        with open(cfg_path, "w", encoding="utf-8") as f:
            f.write("OLD_DATA")

        args = ["--install", "--dev", "--config-file", cfg_path, "--key-file", key_path]

        with patch("asiscfg.ui.dialogs.confirm_action_dialog", return_value=True), \
             patch("asiscfg.cli.execute_app_action", return_value=0) as mock_exec:
            boot = init_app_config(
                args=args,
                app_title="PROCEED_INSTALL_TEST",
                app_schema=self.schema_path
            )

        self.assertEqual(boot.exit_code, 0)
        self.assertTrue(os.path.exists(key_path))
        with open(cfg_path, "r", encoding="utf-8") as f:
            content = f.read()
            self.assertNotEqual(content, "OLD_DATA")
        mock_exec.assert_called_once()

    def test_check_admin_password_strict_no_default_admin(self):
        """Verifica que check_admin_password retorne False si no hay hash y nunca asuma 'admin' por defecto."""
        from asiscfg.security import check_admin_password, hash_password
        # 1. Configuración vacía o sin sección @asiscfg
        self.assertFalse(check_admin_password("admin", {}))
        self.assertFalse(check_admin_password("admin", None))
        self.assertFalse(check_admin_password("admin", ""))

        # 2. Sección @asiscfg existe pero sin admin_pass_hash o con valor None/vacío
        self.assertFalse(check_admin_password("admin", {"@asiscfg": {}}))
        self.assertFalse(check_admin_password("admin", {"@asiscfg": {"admin_pass_hash": None}}))
        self.assertFalse(check_admin_password("admin", {"@asiscfg": {"admin_pass_hash": ""}}))

        # 3. Hash configurado explícitamente: solo valida la clave correcta
        cfg = {"@asiscfg": {"admin_pass_hash": hash_password("SuperSecret123")}}
        self.assertFalse(check_admin_password("admin", cfg))
        self.assertFalse(check_admin_password("wrong", cfg))
        self.assertTrue(check_admin_password("SuperSecret123", cfg))


    def test_bootstrap_repr_esbelto_sin_context_ni_metadata(self):
        """Verifica que ConfigBootstrap tenga repr esbelto (sin context) y que AppConfigContext carezca de metadata."""
        args = [
            "--config-file",
            self.config_path,
            "--key-file",
            self.key_path,
            "--schema-file",
            self.schema_path,
        ]
        boot = init_app_config(args=args, app_title="REPR_TEST")
        self.assertIsNone(boot.exit_code)
        self.assertIsNotNone(boot.config)

        boot_repr = repr(boot)
        # 1. No debe mostrar context= en el repr
        self.assertNotIn("context=", boot_repr)
        self.assertNotIn("AppConfigContext", boot_repr)
        # 2. No debe existir metadata en el repr ni en el contexto
        self.assertNotIn("metadata", boot_repr)
        self.assertFalse(hasattr(boot.context, "metadata"))
        # 3. context es accesible vía propiedad
        self.assertIsInstance(boot.context, AppConfigContext)
        # 4. repr contiene únicamente las claves útiles
        self.assertIn("config=", boot_repr)
        self.assertIn("exit_code=None", boot_repr)
        self.assertIn("remaining_args=", boot_repr)
        self.assertIn("params=", boot_repr)
        self.assertIn("debug=", boot_repr)
        self.assertIn("dev_mode=", boot_repr)
        self.assertIn("show_modals=", boot_repr)


if __name__ == "__main__":
    unittest.main()


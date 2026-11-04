# -*- coding: utf-8 -*-
# SPDX-FileCopyrightText: 2026 Asisnet Computacion, CA <proyectos@asisnet.net>
# SPDX-License-Identifier: MIT
# Autor: Boris Pinto <borispinto@asisnet.net>
# File: tests/test_headless_and_env_placeholders.py

"""
Pruebas unitarias para el blindaje headless y soporte de comodines {ENV:...}.
Verifica la resolución temprana, validación Fail-Fast, cifrado en memoria para campos protegidos
y la resiliencia en ejecución sin entorno gráfico.
"""

import os
import shutil
import tempfile
import unittest
from unittest.mock import patch

from asiscfg.constants import (
    ENC_PREFIX,
    NULL_SENTINEL,
    resolve_env_string,
    has_wildcard,
    resolve_wildcards,
    WILDCARD_HANDLERS,
)
from asiscfg.context import create_app_context
from asiscfg.cli import init_app_config
from asiscfg.storage import generate_key_file, load_config, save_config


class TestHeadlessAndEnvPlaceholders(unittest.TestCase):
    def setUp(self):
        self.test_dir = tempfile.mkdtemp()
        self.config_path = os.path.join(self.test_dir, "test.cfg")
        self.key_path = os.path.join(self.test_dir, "test.key")
        self.schema_path = os.path.join(self.test_dir, "config_schema.py")

        # Guardar estado de variables de entorno para restauración
        self._orig_env = dict(os.environ)

    def tearDown(self):
        # Restaurar variables de entorno originales
        os.environ.clear()
        os.environ.update(self._orig_env)
        shutil.rmtree(self.test_dir, ignore_errors=True)

    def _write_schema(self, content: str) -> None:
        with open(self.schema_path, "w", encoding="utf-8") as f:
            f.write(content)

    def test_resolve_env_string_direct(self):
        """Prueba directa de la función resolve_env_string con distintas sintaxis."""
        os.environ["TEST_HOST"] = "192.168.1.50"
        os.environ["TEST_PORT"] = "1433"

        # Variable existente
        self.assertEqual(resolve_env_string("{ENV:TEST_HOST}"), "192.168.1.50")

        # Variable inexistente con default
        self.assertEqual(resolve_env_string("{ENV:MISSING_VAR:localhost}"), "localhost")

        # Variable inexistente con default vacío
        self.assertEqual(resolve_env_string("{ENV:MISSING_VAR:}"), "")

        # Variable existente ignora default
        self.assertEqual(resolve_env_string("{ENV:TEST_PORT:8080}"), "1433")

        # Múltiples comodines incrustados en una cadena
        full_url = resolve_env_string("http://{ENV:TEST_HOST}:{ENV:TEST_PORT}/api")
        self.assertEqual(full_url, "http://192.168.1.50:1433/api")

        # Cadena sin comodín se preserva intacta
        self.assertEqual(resolve_env_string("cadena_estandar"), "cadena_estandar")

        # Fail-fast ante variable faltante sin default
        with self.assertRaises(ValueError) as ctx:
            resolve_env_string("{ENV:NO_EXISTE}", fail_on_missing=True)
        self.assertIn("NO_EXISTE", str(ctx.exception))

        # En modo no fail (fail_on_missing=False), preserva el comodín
        preserved = resolve_env_string("{ENV:NO_EXISTE}", fail_on_missing=False)
        self.assertEqual(preserved, "{ENV:NO_EXISTE}")

    def test_wildcard_dispatcher_and_custom_handler(self):
        """Verifica la extensibilidad del despachador de comodines y soporte de nuevos comodines."""
        # has_wildcard
        self.assertTrue(has_wildcard("{ENV:PORT}"))
        self.assertFalse(has_wildcard("valor_normal"))
        self.assertFalse(has_wildcard(1234))

        # resolve_wildcards con {ENV:...}
        os.environ["API_HOST"] = "api.asisnet.net"
        self.assertEqual(resolve_wildcards("{ENV:API_HOST}"), "api.asisnet.net")
        self.assertEqual(resolve_wildcards("normal"), "normal")
        self.assertEqual(resolve_wildcards(42), 42)

        # resolve_wildcards en listas y dicts anidados
        nested = {
            "server": "{ENV:API_HOST}",
            "ports": ["{ENV:MISSING:80}", "{ENV:MISSING:443}"],
        }
        resolved_nested = resolve_wildcards(nested)
        self.assertEqual(resolved_nested["server"], "api.asisnet.net")
        self.assertEqual(resolved_nested["ports"], ["80", "443"])

        # Simular registro de un nuevo comodín {VAULT:...} sin modificar el núcleo
        def fake_vault_resolver(val: str, fail_on_missing: bool = True) -> str:
            return val.replace("{VAULT:secret_token}", "tok_ultra_seguro_999")

        import asiscfg.constants as consts
        orig_handlers = consts.WILDCARD_HANDLERS
        try:
            consts.WILDCARD_HANDLERS = orig_handlers + (("{VAULT:", fake_vault_resolver),)
            self.assertTrue(has_wildcard("{VAULT:secret_token}"))
            self.assertEqual(resolve_wildcards("{VAULT:secret_token}"), "tok_ultra_seguro_999")
        finally:
            consts.WILDCARD_HANDLERS = orig_handlers

    def test_plain_fields_with_env_placeholders(self):
        """Verifica que campos planos con {ENV:...} se resuelvan en load_config en memoria."""
        schema = """
CONFIG_SCHEMA = {
    "database": {
        "host": {"type": "str", "default": "127.0.0.1"},
        "port": {"type": "int", "default": 1433},
        "url": {"type": "str", "default": "localhost"},
    }
}
"""
        self._write_schema(schema)

        os.environ["ENV_DB_HOST"] = "10.0.0.99"
        os.environ["ENV_DB_PORT"] = "5432"

        ctx = create_app_context(
            action="consume",
            config_file=self.config_path,
            key_file=self.key_path,
            schema_file=self.schema_path,
            base_dir=self.test_dir,
            format_mode="plain",
        )
        generate_key_file(ctx)

        # Grabar configuración en disco con comodines
        raw_config = {
            "database": {
                "host": "{ENV:ENV_DB_HOST}",
                "port": "{ENV:ENV_DB_PORT}",
                "url": "http://{ENV:ENV_DB_HOST}:{ENV:ENV_DB_PORT}/db",
            }
        }
        save_config(ctx, raw_config)

        # Cargar configuración en modo producción (consume)
        cfg = load_config(ctx, edit_mode=False)

        # Verificar acceso O(1) con los valores resueltos y tipados
        self.assertEqual(cfg.valor("database.host"), "10.0.0.99")
        self.assertEqual(cfg.valor("database.port"), 5432)  # int tipado por el esquema
        self.assertEqual(cfg.valor("database.url"), "http://10.0.0.99:5432/db")

    def test_plain_field_env_missing_fails_fast(self):
        """Verifica interrupción inmediata (Fail-Fast) si un comodín plano no tiene variable en el SO."""
        schema = """
CONFIG_SCHEMA = {
    "server": {
        "host": {"type": "str", "default": "127.0.0.1"},
    }
}
"""
        self._write_schema(schema)

        ctx = create_app_context(
            action="consume",
            config_file=self.config_path,
            key_file=self.key_path,
            schema_file=self.schema_path,
            base_dir=self.test_dir,
            format_mode="plain",
        )
        generate_key_file(ctx)

        raw_config = {"server": {"host": "{ENV:UNSET_SERVER_HOST}"}}
        save_config(ctx, raw_config)

        # Debe lanzar ValueError de inmediato
        with self.assertRaises(ValueError) as err:
            load_config(ctx, edit_mode=False)
        self.assertIn("UNSET_SERVER_HOST", str(err.exception))

    def test_password_field_with_env_placeholder_resolved_and_encrypted(self):
        """
        Verifica que campos de contraseña con {ENV:...} se validen tempranamente,
        se cifren de inmediato en memoria como ENC:... y se consulten vía valorpass en O(1).
        """
        schema = """
CONFIG_SCHEMA = {
    "database": {
        "user": {"type": "str", "default": "sa"},
        "password": {"type": "str", "is_password": True, "default": ""},
    }
}
"""
        self._write_schema(schema)

        os.environ["SECRET_DB_PASS"] = "MiPasswordUltraSeguro2026!"

        ctx = create_app_context(
            action="consume",
            config_file=self.config_path,
            key_file=self.key_path,
            schema_file=self.schema_path,
            base_dir=self.test_dir,
            format_mode="plain",
        )
        generate_key_file(ctx)

        # En disco se coloca el comodín
        raw_config = {
            "database": {
                "user": "sa",
                "password": "{ENV:SECRET_DB_PASS}",
            }
        }
        save_config(ctx, raw_config)

        # Carga en modo consumo
        cfg = load_config(ctx, edit_mode=False)

        # En memoria debe estar cifrado canónicamente
        stored_raw = cfg["database"]["password"]
        self.assertTrue(stored_raw.startswith(ENC_PREFIX), f"Esperaba prefijo ENC:, se obtuvo: {stored_raw}")

        # valorpass debe retornar la contraseña desencriptada Just-In-Time
        self.assertEqual(cfg.valorpass("database.password"), "MiPasswordUltraSeguro2026!")

        # Enmascaramiento preventivo: valor() no debe exponer contraseñas
        self.assertEqual(cfg.valor("database.password"), "<pass_database.password>")

    def test_password_field_env_missing_fails_fast(self):
        """Verifica fail-fast si un campo protegido usa un comodín cuya variable no existe."""
        schema = """
CONFIG_SCHEMA = {
    "auth": {
        "api_key": {"type": "str", "is_password": True, "default": ""},
    }
}
"""
        self._write_schema(schema)

        ctx = create_app_context(
            action="consume",
            config_file=self.config_path,
            key_file=self.key_path,
            schema_file=self.schema_path,
            base_dir=self.test_dir,
            format_mode="plain",
        )
        generate_key_file(ctx)

        raw_config = {"auth": {"api_key": "{ENV:NON_EXISTENT_API_KEY}"}}
        save_config(ctx, raw_config)

        with self.assertRaises(ValueError) as err:
            load_config(ctx, edit_mode=False)
        self.assertIn("NON_EXISTENT_API_KEY", str(err.exception))

    def test_profile_password_field_with_env_placeholder(self):
        """Verifica comodines en campos de contraseña dentro de perfiles multi-empresa (@profiles)."""
        schema = """
CONFIG_SCHEMA = {
    "@profiles": {
        "_template": {
            "db": {
                "server": {"type": "str", "default": "localhost"},
                "password": {"type": "str", "is_password": True, "default": ""},
            }
        }
    }
}
"""
        self._write_schema(schema)

        os.environ["TENANT_01_PASS"] = "TenantSecret99#"

        ctx = create_app_context(
            action="consume",
            config_file=self.config_path,
            key_file=self.key_path,
            schema_file=self.schema_path,
            base_dir=self.test_dir,
            format_mode="plain",
        )
        generate_key_file(ctx)

        raw_config = {
            "@profiles": {
                "01": {
                    "db": {
                        "server": "10.0.1.10",
                        "password": "{ENV:TENANT_01_PASS}",
                    }
                }
            }
        }
        save_config(ctx, raw_config)

        cfg = load_config(ctx, edit_mode=False)

        # Consulta directa por perfil
        self.assertEqual(cfg.valor_profile("db.server", "01"), "10.0.1.10")
        self.assertEqual(cfg.valorpass_profile("db.password", "01"), "TenantSecret99#")

    def test_ui_mode_preserves_placeholders(self):
        """Verifica que en modo edición (edit_mode=True / UI), los comodines se preserven sin resolver destructivamente."""
        schema = """
CONFIG_SCHEMA = {
    "conexiones": {
        "host": {"type": "str", "default": "localhost"},
        "password": {"type": "str", "is_password": True, "default": ""},
    }
}
"""
        self._write_schema(schema)

        ctx = create_app_context(
            action="ui",
            config_file=self.config_path,
            key_file=self.key_path,
            schema_file=self.schema_path,
            base_dir=self.test_dir,
            format_mode="plain",
        )
        generate_key_file(ctx)

        raw_config = {
            "conexiones": {
                "host": "{ENV:VARIABLE_PENDIENTE_HOST}",
                "password": "{ENV:VARIABLE_PENDIENTE_PASS}",
            }
        }
        save_config(ctx, raw_config)

        # En modo UI (edit_mode=True), no debe fallar aunque las variables no existan en el SO
        cfg_ui = load_config(ctx, edit_mode=True)

        self.assertEqual(cfg_ui["conexiones"]["host"], "{ENV:VARIABLE_PENDIENTE_HOST}")
        # En la UI, al consultar la contraseña para mostrar en el formulario, se obtiene el comodín original
        self.assertEqual(cfg_ui.valorpass("conexiones.password"), "{ENV:VARIABLE_PENDIENTE_PASS}")

    def test_headless_resilience_when_show_modal_fails(self):
        """Verifica que si se usa --show pero el entorno no soporta GUI, el sistema capture el error y no caiga."""
        schema = """
CONFIG_SCHEMA = {
    "app": {
        "name": {"type": "str", "default": "DemoApp"},
    }
}
"""
        self._write_schema(schema)

        # Simular fallo en show_modal_message_dialog (ej. ImportError de Tkinter o TclError por falta de DISPLAY)
        with patch("asiscfg.ui.dialogs.show_modal_message_dialog", side_effect=RuntimeError("no display available")):
            # Invocar CLI con --show y un archivo de configuración faltante
            non_existent_cfg = os.path.join(self.test_dir, "missing.cfg")
            bootstrap = init_app_config(
                args=["--show", f"--config-file={non_existent_cfg}"],
                app_title="TestHeadless",
                app_files=None,
                app_schema=self.schema_path,
                app_action="consume",
            )

            # Debe retornar ordenadamente exit_code=1 sin traceback no controlado
            self.assertEqual(bootstrap.exit_code, 1)
            self.assertIsNone(bootstrap.config)


if __name__ == "__main__":
    unittest.main()
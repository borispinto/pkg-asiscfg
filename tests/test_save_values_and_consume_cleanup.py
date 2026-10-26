# -*- coding: utf-8 -*-
# SPDX-FileCopyrightText: 2026 Asisnet Computacion, CA <proyectos@asisnet.net>
# SPDX-License-Identifier: MIT
# Autor: Boris Pinto <borispinto@asisnet.net>
# File: tests/test_save_values_and_consume_cleanup.py

"""
Pruebas unitarias para la depuración de memoria en modo consume
y el procedimiento de guardado atómico quirúrgico save_values().
"""

import json
import os
import shutil
import tempfile
import unittest

from asiscfg import init_app_config
from asiscfg.constants import NO_MODIFY_KEY
from asiscfg.context import create_app_context
from asiscfg.crypto import detect_format_engine
from asiscfg.models import ConfigDict
from asiscfg.storage import generate_key_file, load_config, save_config, save_values


class TestSaveValuesAndConsumeCleanup(unittest.TestCase):
    def setUp(self):
        self.test_dir = tempfile.mkdtemp()
        self.config_path = os.path.join(self.test_dir, "test.cfg")
        self.key_path = os.path.join(self.test_dir, "test.key")
        self.schema_path = os.path.join(self.test_dir, "config_schema.py")

        schema_content = """# config_schema.py
CONFIG_SCHEMA = {
    "_security_level": 1,
    "_backup": {
        "enabled": False,
        "target_dir": "{ROOT}/backups",
    },
    "app": {
        "name": {"type": "str", "default": "AppDemo", "public": True},
        "version": {"type": "str", "default": "1.0.0", "public": True},
    },
    "general": {
        "empresa": {"type": "str", "default": "Empresa Base", "public": True},
        "cierre": {"type": "str", "default": "2026-01-01"},
    },
    "database": {
        "driver": {"type": "str", "default": "sqlite"},
        "user": {"type": "str", "default": "admin"},
        "password": {"type": "str", "default": "clave_original", "is_password": True},
    },
    "@profiles": {
        "_template": {
            "info": {
                "name": {"type": "str", "default": "Perfil Base", "public": True},
            },
            "db": {
                "host": {"type": "str", "default": "localhost"},
                "password": {"type": "str", "default": "pass_prof", "is_password": True},
            }
        },
        "01": {
            "info": {"name": "Sucursal Uno"},
            "db": {"host": "192.168.1.10", "password": "pass_sucursal_01"},
        }
    }
}
"""
        with open(self.schema_path, "w", encoding="utf-8") as f:
            f.write(schema_content)

        # Generar clave y archivo inicial
        self.context = create_app_context(
            action="consume",
            config_file=self.config_path,
            key_file=self.key_path,
            schema_file=self.schema_path,
            base_dir=self.test_dir,
        )
        generate_key_file(self.context)
        save_config(self.context)

    def tearDown(self):
        shutil.rmtree(self.test_dir, ignore_errors=True)

    def test_consume_mode_purges_redundant_memory_structures(self):
        """Verifica que en modo consume se depuren profile_template, validation_rules y sellos."""
        loaded = load_config(self.context, edit_mode=False)

        # 1. El diccionario devuelto no debe contener el sello forense
        self.assertNotIn(NO_MODIFY_KEY, loaded)

        # 2. El contexto asociado debe haber liberado metadatos pesados de UI y reglas
        self.assertEqual(self.context.profile_template, {})
        self.assertEqual(self.context.validation_rules, {})
        self.assertEqual(self.context.backup_settings, {})
        self.assertEqual(self.context.public_fields, [])

        # 3. La instancia ConfigDict debe haber liberado diagnósticos de UI y reglas
        self.assertEqual(loaded._validation_rules, {})
        self.assertEqual(loaded._unencrypted_passwords, [])
        self.assertEqual(loaded._password_failures, [])
        self.assertEqual(loaded._audit_diffs, [])

        # 4. Datos de negocio deben permanecer 100% operativos
        self.assertEqual(loaded.valor("app.name"), "AppDemo")
        self.assertEqual(loaded.valor("general.empresa"), "Empresa Base")
        self.assertEqual(loaded.valorpass("database.password"), "clave_original")
        self.assertEqual(loaded.valor_profile("info.name", "01"), "Sucursal Uno")

    def test_save_disabled_in_consume_mode(self):
        """Verifica que save() masivo falle de inmediato en modo consume para prevenir sobreescrituras."""
        loaded = load_config(self.context, edit_mode=False)
        with self.assertRaises(RuntimeError) as cm:
            loaded.save()
        self.assertIn("guardado masivo está deshabilitado", str(cm.exception))

    def test_save_values_type_and_argument_validation(self):
        """Verifica validación estricta de tipos y contratos en save_values."""
        # updates debe ser dict obligatorio
        with self.assertRaises(TypeError):
            save_values(self.context, updates=["no_es_dict"])  # type: ignore

        # updates no puede estar vacío
        with self.assertRaises(ValueError):
            save_values(self.context, updates={})

        # claves deben ser cadenas no vacías
        with self.assertRaises(ValueError):
            save_values(self.context, updates={"": "valor"})

    def test_save_values_atomic_disk_update_and_hot_sync(self):
        """Verifica que save_values persista en disco y sincronice en caliente el objeto en memoria."""
        config = load_config(self.context, edit_mode=False)

        # Actualizar dos claves específicas
        updates = {
            "general.empresa": "Corporación Nueva C.A.",
            "general.cierre": "2026-10-23",
        }
        config.save_values(updates)

        # 1. Sincronización en caliente en la instancia en memoria
        self.assertEqual(config.valor("general.empresa"), "Corporación Nueva C.A.")
        self.assertEqual(config.valor("general.cierre"), "2026-10-23")

        # 2. Verificación de persistencia real en disco
        with open(self.config_path, "rb") as f:
            raw = f.read()
        _, engine = detect_format_engine(raw)
        lines = [l for l in raw.strip().splitlines() if not l.startswith(b"#") or l.strip() == engine.header.encode("utf-8")]
        # payload
        data_lines = [l for l in lines if l.strip() != engine.header.encode("utf-8")]
        dec = engine.decrypt_payload(b"\n".join(data_lines), self.context.key_bytes)
        on_disk = json.loads(dec.decode("utf-8"))

        self.assertEqual(on_disk["general"]["empresa"], "Corporación Nueva C.A.")
        self.assertEqual(on_disk["general"]["cierre"], "2026-10-23")
        self.assertTrue(on_disk["app"]["name"].startswith("ENC:"))
        self.assertEqual(config.valor("app.name"), "AppDemo")
        self.assertEqual(on_disk["@profiles"]["01"]["info"]["name"], "Sucursal Uno")

    def test_save_values_encrypts_passwords_properly(self):
        """Verifica que si una clave actualizada es contraseña, se encripte físicamente en disco."""
        config = load_config(self.context, edit_mode=False)

        config.save_values({"database.password": "nueva_clave_secreta_999"})

        # Memoria: valor() enmascara y valorpass() desencripta
        self.assertEqual(config.valor("database.password"), "<pass_database.password>")
        self.assertEqual(config.valorpass("database.password"), "nueva_clave_secreta_999")

        # Disco: el valor debe estar cifrado con ENC:
        with open(self.config_path, "rb") as f:
            raw = f.read()
        _, engine = detect_format_engine(raw)
        lines = [l for l in raw.strip().splitlines() if not l.startswith(b"#") or l.strip() == engine.header.encode("utf-8")]
        data_lines = [l for l in lines if l.strip() != engine.header.encode("utf-8")]
        dec = engine.decrypt_payload(b"\n".join(data_lines), self.context.key_bytes)
        on_disk = json.loads(dec.decode("utf-8"))

        disk_pass = on_disk["database"]["password"]
        self.assertTrue(disk_pass.startswith("ENC:"))
        self.assertNotEqual(disk_pass, "nueva_clave_secreta_999")

    def test_save_values_preserves_external_concurrent_updates(self):
        """Verifica que actualizaciones externas en disco no se pierdan al ejecutar save_values."""
        # 1. Proceso A carga configuración
        config_a = load_config(self.context, edit_mode=False)

        # 2. Proceso B modifica concurrentemente otra sección directamente en el archivo
        with open(self.config_path, "rb") as f:
            raw = f.read()
        _, engine = detect_format_engine(raw)
        lines = [l for l in raw.strip().splitlines() if not l.startswith(b"#") or l.strip() == engine.header.encode("utf-8")]
        data_lines = [l for l in lines if l.strip() != engine.header.encode("utf-8")]
        dec = engine.decrypt_payload(b"\n".join(data_lines), self.context.key_bytes)
        disk_data = json.loads(dec.decode("utf-8"))

        disk_data["app"]["name"] = "NombreModificadoExternamente"
        json_b = json.dumps(disk_data, indent=4).encode("utf-8")
        payload = engine.encrypt_payload(json_b, self.context.key_bytes)
        with open(self.config_path, "wb") as f:
            f.write(f"{engine.header}\n".encode("utf-8") + payload)

        # 3. Proceso A ejecuta save_values sobre "general.empresa"
        config_a.save_values({"general.empresa": "Mi Empresa A"})

        # 4. Verificar que en disco coexistan el cambio externo de B y el cambio de A
        with open(self.config_path, "rb") as f:
            raw2 = f.read()
        data_lines2 = [l for l in raw2.strip().splitlines() if not l.startswith(b"#")]
        dec2 = engine.decrypt_payload(b"\n".join(data_lines2), self.context.key_bytes)
        final_disk = json.loads(dec2.decode("utf-8"))

        self.assertEqual(final_disk["app"]["name"], "NombreModificadoExternamente")
        self.assertEqual(final_disk["general"]["empresa"], "Mi Empresa A")

    def test_bootstrap_save_values_integration(self):
        """Verifica la delegación de save_values y bloqueo de save() desde ConfigBootstrap."""
        bootstrap = init_app_config(
            args=[f"--config-file={self.config_path}", f"--key-file={self.key_path}", f"--schema-file={self.schema_path}"],
            app_title="Test App",
        )
        self.assertIsNone(bootstrap.exit_code)

        # save() masivo bloqueado
        with self.assertRaises(RuntimeError):
            bootstrap.save()

        # save_values() operativo
        bootstrap.save_values({"general.empresa": "Empresa Bootstrap"})
        self.assertEqual(bootstrap.valor("general.empresa"), "Empresa Bootstrap")


if __name__ == "__main__":
    unittest.main()

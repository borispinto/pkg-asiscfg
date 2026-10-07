# -*- coding: utf-8 -*-
# SPDX-FileCopyrightText: 2026 Asisnet Computacion, CA <proyectos@asisnet.net>
# SPDX-License-Identifier: MIT
# Autor: Boris Pinto <borispinto@asisnet.net>
# File: tests/test_config_package.py

"""
Pruebas unitarias automatizadas para la librería modular asiscfg (Versión 1).
Incluye pruebas del motor de Esquema Unificado y aislamiento multi-empresa.
"""

import os
import json
import shutil
import tempfile
import unittest
from asiscfg import (
    load_config,
    save_config,
    generate_key_file,
    get_key,
    verify_key_integrity,
    resolve_file_path,
    resolve_schema_path,
    export_config_schema,
    run_asiscfg,
    ConfigDict,
    AppConfigContext,
    create_app_context,
    validate_and_correct_config,
    hash_password,
    check_admin_password,
    DEFAULT_CONFIG_FILENAME,
    DEFAULT_KEY_FILENAME,
    DEFAULT_SCHEMA_FILENAME,
    FORMAT_MODES,
    ENC_PREFIX,
    NULL_SENTINEL,
    SECURITY_SECTIONS,
    is_security_section
)
from asiscfg.schema import extract_schema_metadata


class TestConfigToolPackage(unittest.TestCase):

    def test_constants_definitions(self):
        self.assertEqual(DEFAULT_CONFIG_FILENAME, "config.enc")
        self.assertEqual(DEFAULT_KEY_FILENAME, "config.key")
        self.assertEqual(DEFAULT_SCHEMA_FILENAME, "config_schema.py")
        self.assertEqual(FORMAT_MODES["plain"].header, "# ASISCFG_PLAIN")
        self.assertEqual(FORMAT_MODES["fernet"].header, "# ASISCFG_FERNET")
        self.assertEqual(FORMAT_MODES["aes256_gcm"].header, "# ASISCFG_AES256GCM")
        self.assertEqual(FORMAT_MODES["chacha20"].header, "# ASISCFG_CHACHA20")
        self.assertEqual(ENC_PREFIX, "ENC:")

    def setUp(self):
        self.test_dir = tempfile.mkdtemp()
        self.config_path = os.path.join(self.test_dir, "test_config.enc")
        self.key_path = os.path.join(self.test_dir, "test_secret.key")
        self.context = create_app_context(config_file=self.config_path, key_file=self.key_path)
        generate_key_file(self.context)

        # Esquema Unificado de Prueba con campos generales, multi-empresa y passwords
        self.sample_unified_schema = {
            "app": {
                "name": {"default": "TestApp", "description": "t18n#Nombre de la app"},
                "port": {"default": 8080, "type": "int", "min": 1000, "max": 9999},
                "api_key": {"default": "secret_api_key_999", "is_password": True}
            },
            "general": {
                "active_language": "es"
            },
            "@profiles": {
                "_template": {
                    "info": {
                        "name": {"default": "Perfil Base", "description": "t18n#Razón Social"}
                    },
                    "db": {
                        "host": "localhost",
                        "password": {"default": "pass_profile_default", "is_password": True},
                        "pool_size": {"default": 10, "type": "int", "min": 1, "max": 50}
                    }
                },
                "01": {
                    "info": {"name": "Perfil Uno"},
                    "db": {"host": "192.168.1.50", "password": "mi_clave_secreta_01"}
                }
            }
        }

        meta = extract_schema_metadata(self.sample_unified_schema)
        self.def_values = meta["default_config"]
        self.val_rules = meta["validation_rules"]
        self.prof_template = meta["profile_template"]
        self.password_fields = meta["password_fields"]
        self.context.password_fields = list(self.password_fields)
        self.context.default_config = self.def_values
        self.context.validation_rules = self.val_rules
        self.context.profile_template = self.prof_template

    def tearDown(self):
        shutil.rmtree(self.test_dir, ignore_errors=True)

    def test_unified_schema_extraction(self):
        self.assertIn("app", self.def_values)
        self.assertIn("general", self.def_values)
        self.assertIn("@profiles", self.def_values)
        self.assertNotIn("_template", self.def_values["@profiles"])
        self.assertIn("01", self.def_values["@profiles"])
        self.assertEqual(self.def_values["@profiles"]["01"]["info"]["name"], "Perfil Uno")
        self.assertEqual(self.def_values["@profiles"]["01"]["db"]["pool_size"], 10)
        self.assertEqual(self.def_values["@profiles"]["01"]["db"]["password"], "mi_clave_secreta_01")

    def test_config_dict_navigation(self):
        cfg = ConfigDict(self.context, self.def_values)
        cfg.set_default_config(self.def_values)

        self.assertEqual(cfg.valor("app.name"), "TestApp")
        self.assertEqual(cfg.valor("general.active_language"), "es")
        self.assertTrue(cfg.has_profiles())
        self.assertEqual(cfg.get_profiles(), ["01"])
        self.assertEqual(cfg.valor_profile("01", "info.name"), "Perfil Uno")
        self.assertEqual(cfg.valor_profile("01", "db.host"), "192.168.1.50")
        self.assertEqual(cfg.valor_profile("99", "info.name", default="N/A"), "N/A")

    def test_save_and_load_plain_mode_with_selective_password_encryption(self):
        # 1. Guardar en modo texto plano (por defecto format_mode="plain")
        save_config(
            self.context,
            self.def_values,
            validation_rules=self.val_rules,
            default_config=self.def_values,
            format_mode="plain"
        )

        # 2. Inspeccionar físicamente el archivo en disco
        with open(self.config_path, "r", encoding="utf-8") as f:
            raw_text = f.read()

        lines = raw_text.splitlines()
        self.assertEqual(lines[0], FORMAT_MODES["plain"].header)

        # Verificar que sea JSON válido descartando el encabezado
        import json
        parsed_disk = json.loads("\n".join(lines[1:]))

        # Campos de secciones normales no confidenciales legibles en claro
        self.assertEqual(parsed_disk["@profiles"]["01"]["db"]["host"], "192.168.1.50")

        # Campos de secciones en SECURITY_SECTIONS se cifran todos con prefijo ENC:
        self.assertTrue(parsed_disk["app"]["name"].startswith(ENC_PREFIX))
        self.assertTrue(parsed_disk["app"]["port"].startswith(ENC_PREFIX))
        self.assertTrue(parsed_disk["app"]["api_key"].startswith(ENC_PREFIX))

        # Campos con is_password: True cifrados individualmente con prefijo ENC:
        self.assertTrue(parsed_disk["@profiles"]["01"]["db"]["password"].startswith(ENC_PREFIX))
        self.assertNotIn("mi_clave_secreta_01", raw_text)
        self.assertNotIn("secret_api_key_999", raw_text)


        # 3. Cargar de forma transparente (sin pasar modo)
        loaded = load_config(
            self.context,
            default_config=self.def_values,
            validation_rules=self.val_rules
        )

        self.assertIsInstance(loaded, ConfigDict)
        self.assertEqual(loaded.format_mode, "plain")
        self.assertEqual(loaded.valor("app.name"), "TestApp")
        self.assertEqual(loaded.valor("app.api_key"), "<pass_app.api_key>")
        self.assertEqual(loaded.valorpass("app.api_key"), "secret_api_key_999")
        self.assertTrue(loaded.valorpass("app.api_key", valor_compara="secret_api_key_999"))
        self.assertFalse(loaded.valorpass("app.api_key", valor_compara="incorrecta"))
        self.assertEqual(loaded.valor_profile("01", "db.password"), "<pass_db.password>")
        self.assertEqual(loaded.valorpass_profile("01", "db.password"), "mi_clave_secreta_01")
        self.assertTrue(loaded.valorpass_profile("01", "db.password", valor_compara="mi_clave_secreta_01"))

    def test_save_and_load_encrypted_mode(self):
        ctx_enc = create_app_context(config_file=self.config_path, key_file=self.key_path, format_mode="fernet")
        # Guardar en modo completamente cifrado
        save_config(
            ctx_enc,
            self.def_values,
            validation_rules=self.val_rules,
            default_config=self.def_values,
            format_mode="fernet"
        )

        with open(self.config_path, "rb") as f:
            raw_bytes = f.read()

        # Debe tener la cabecera fernet y no la plain
        self.assertTrue(raw_bytes.startswith(FORMAT_MODES["fernet"].header.encode("utf-8")))
        self.assertFalse(raw_bytes.startswith(FORMAT_MODES["plain"].header.encode("utf-8")))

        # Cargar transparentemente con un contexto limpio
        ctx_clean = create_app_context(config_file=self.config_path, key_file=self.key_path)
        ctx_clean.password_fields = list(self.password_fields)
        loaded = load_config(
            ctx_clean,
            default_config=self.def_values,
            validation_rules=self.val_rules
        )
        self.assertEqual(loaded.format_mode, "fernet")
        self.assertEqual(ctx_clean.format_mode, "fernet")
        self.assertEqual(loaded.valor("app.name"), "TestApp")
        self.assertEqual(loaded.valor_profile("01", "db.password"), "<pass_db.password>")
        self.assertEqual(loaded.valorpass_profile("01", "db.password"), "mi_clave_secreta_01")

    def test_save_and_load_aes256_gcm_mode(self):
        ctx_gcm = create_app_context(config_file=self.config_path, key_file=self.key_path, format_mode="aes256_gcm")
        save_config(
            ctx_gcm,
            self.def_values,
            validation_rules=self.val_rules,
            default_config=self.def_values,
            format_mode="aes256_gcm"
        )

        with open(self.config_path, "rb") as f:
            raw_bytes = f.read()

        self.assertTrue(raw_bytes.startswith(FORMAT_MODES["aes256_gcm"].header.encode("utf-8")))

        ctx_clean = create_app_context(config_file=self.config_path, key_file=self.key_path)
        ctx_clean.password_fields = list(self.password_fields)
        loaded = load_config(
            ctx_clean,
            default_config=self.def_values,
            validation_rules=self.val_rules
        )
        self.assertEqual(loaded.format_mode, "aes256_gcm")
        self.assertEqual(ctx_clean.format_mode, "aes256_gcm")
        self.assertEqual(loaded.valor("app.name"), "TestApp")
        self.assertEqual(loaded.valorpass_profile("01", "db.password"), "mi_clave_secreta_01")

    def test_save_and_load_chacha20_mode(self):
        ctx_chacha = create_app_context(config_file=self.config_path, key_file=self.key_path, format_mode="chacha20")
        save_config(
            ctx_chacha,
            self.def_values,
            validation_rules=self.val_rules,
            default_config=self.def_values,
            format_mode="chacha20"
        )

        with open(self.config_path, "rb") as f:
            raw_bytes = f.read()

        self.assertTrue(raw_bytes.startswith(FORMAT_MODES["chacha20"].header.encode("utf-8")))

        ctx_clean = create_app_context(config_file=self.config_path, key_file=self.key_path)
        ctx_clean.password_fields = list(self.password_fields)
        loaded = load_config(
            ctx_clean,
            default_config=self.def_values,
            validation_rules=self.val_rules
        )
        self.assertEqual(loaded.format_mode, "chacha20")
        self.assertEqual(ctx_clean.format_mode, "chacha20")
        self.assertEqual(loaded.valor("app.name"), "TestApp")
        self.assertEqual(loaded.valorpass_profile("01", "db.password"), "mi_clave_secreta_01")

    def test_load_config_invalid_or_missing_header_raises_error(self):
        # Archivo sin cabecera válida registrada (ej. JSON crudo o cabecera desconocida)
        raw_invalid_path = os.path.join(self.test_dir, "invalid_header.cfg")
        with open(raw_invalid_path, "w", encoding="utf-8") as f:
            f.write('{"app": {"name": "NoHeaderApp"}}\n')

        ctx_invalid = create_app_context(config_file=raw_invalid_path, key_file=self.key_path)
        with self.assertRaises(ValueError):
            load_config(ctx_invalid, default_config=self.def_values, validation_rules=self.val_rules)

        # Archivo con cabecera no reconocida
        with open(raw_invalid_path, "w", encoding="utf-8") as f:
            f.write('# UNKNOWN_HEADER\n{"app": {"name": "UnknownHeaderApp"}}\n')

        with self.assertRaises(ValueError):
            load_config(ctx_invalid, default_config=self.def_values, validation_rules=self.val_rules)

    def test_save_config_invalid_format_mode_raises_error(self):
        # Verificar que save_config y create_app_context fallen si format_mode no existe en FORMAT_MODES o está vacío
        with self.assertRaises(ValueError):
            save_config(self.context, self.def_values, format_mode="invalid_mode")

        with self.assertRaises(ValueError):
            save_config(self.context, self.def_values, format_mode="encrypted")

        with self.assertRaises(ValueError):
            create_app_context(config_file=self.config_path, key_file=self.key_path, format_mode="")

        with self.assertRaises(ValueError):
            create_app_context(config_file=self.config_path, key_file=self.key_path, format_mode="invalid_mode")

    def test_arbitrary_filename_and_extension(self):
        # Comprobar que cualquier nombre o extensión (.cfg, .json, .custom) funcione transparentemente
        cfg_file = os.path.join(self.test_dir, "miarchivo.cfg")
        ctx_arb = create_app_context(config_file=cfg_file, key_file=self.key_path, format_mode="PLAIN")
        ctx_arb.password_fields = list(self.password_fields)
        save_config(
            ctx_arb,
            self.def_values,
            validation_rules=self.val_rules,
            default_config=self.def_values,
            format_mode="PLAIN"  # prueba case-insensitivity
        )

        loaded = load_config(ctx_arb, default_config=self.def_values, validation_rules=self.val_rules)
        self.assertEqual(loaded.valor("app.port"), 8080)
        self.assertEqual(loaded.valor_profile("01", "db.password"), "<pass_db.password>")
        self.assertEqual(loaded.valorpass_profile("01", "db.password"), "mi_clave_secreta_01")

    def test_manual_editing_plain_text_password_recovery(self):
        # 1. Guardar en modo plain
        save_config(
            self.context,
            self.def_values,
            validation_rules=self.val_rules,
            default_config=self.def_values,
            format_mode="plain"
        )

        # 2. Simular que el usuario abre el archivo con un editor de texto y cambia la clave a texto plano sin prefijo ENC:
        with open(self.config_path, "r", encoding="utf-8") as f:
            raw_text = f.read()

        import json
        lines = raw_text.splitlines()
        disk_data = json.loads("\n".join(lines[1:]))
        disk_data["@profiles"]["01"]["db"]["password"] = "clave_manual_en_texto_plano"
        disk_data["@profiles"]["01"]["info"]["name"] = "Perfil Modificado Manual"

        with open(self.config_path, "w", encoding="utf-8") as f:
            f.write(f"{FORMAT_MODES['plain'].header}\n" + json.dumps(disk_data, indent=4))

        # 3. En modo productivo (edit_mode=False), el archivo con contraseñas en claro debe fallar estrictamente
        with self.assertRaises(ValueError):
            load_config(
                self.context,
                default_config=self.def_values,
                validation_rules=self.val_rules,
                edit_mode=False
            )

        # 4. En modo edición (edit_mode=True), el administrador puede abrir el archivo.
        # El valor para edición en memoria es el registrado en el archivo ('clave_manual_en_texto_plano')
        # y se registra en get_unencrypted_passwords() para alertar y usar el default como línea base.
        loaded = load_config(
            self.context,
            default_config=self.def_values,
            validation_rules=self.val_rules,
            edit_mode=True
        )
        self.assertEqual(loaded.valor_profile("01", "info.name"), "Perfil Modificado Manual")
        self.assertEqual(loaded.valor_profile("01", "db.password"), "<pass_db.password>")
        self.assertEqual(loaded.valorpass_profile("01", "db.password"), "clave_manual_en_texto_plano")
        unencrypted = loaded.get_unencrypted_passwords()
        self.assertTrue(any("@profiles.01.db.password" in str(u) for u in unencrypted))

        # 5. Al volver a guardar, la clave debe volver a cifrarse automáticamente con ENC:
        save_config(
            self.context,
            dict(loaded),
            validation_rules=self.val_rules,
            default_config=self.def_values,
            format_mode="plain"
        )

        with open(self.config_path, "r", encoding="utf-8") as f:
            new_text = f.read()

        new_lines = new_text.splitlines()
        new_data = json.loads("\n".join(new_lines[1:]))
        self.assertTrue(new_data["@profiles"]["01"]["db"]["password"].startswith(ENC_PREFIX))
        self.assertNotIn("clave_manual_en_texto_plano", new_text)

    def test_admin_pass_hash_remains_visible_in_plain_mode(self):
        cfg_data = dict(self.def_values)
        cfg_data["@asiscfg"] = {"admin_pass_hash": hash_password("admin")}
        save_config(
            self.context,
            cfg_data,
            validation_rules=self.val_rules,
            default_config=cfg_data,
            format_mode="plain"
        )

        with open(self.config_path, "r", encoding="utf-8") as f:
            raw_text = f.read()

        import json
        lines = raw_text.splitlines()
        data = json.loads("\n".join(lines[1:]))
        self.assertIn("@asiscfg", data)
        self.assertIn("admin_pass_hash", data["@asiscfg"])
        # No debe tener ENC_PREFIX porque es un hash SHA-256 visible
        self.assertFalse(data["@asiscfg"]["admin_pass_hash"].startswith(ENC_PREFIX))
        self.assertEqual(data["@asiscfg"]["admin_pass_hash"], hash_password("admin"))

    def test_load_config_preserves_special_section_asiscfg_without_schema_warning(self):
        cfg_data = dict(self.def_values)
        cfg_data["@asiscfg"] = {"admin_pass_hash": hash_password("admin")}
        save_config(
            self.context,
            cfg_data,
            validation_rules=self.val_rules,
            default_config=cfg_data,
            format_mode="plain"
        )

        with self.assertLogs(level="WARNING") as cm:
            # def_values no tiene @asiscfg
            loaded = load_config(
                self.context,
                default_config=self.def_values,
                validation_rules=self.val_rules
            )
            # Emitir un log dummy para evitar fallo si no hubo logs
            import logging
            logging.warning("DUMMY_LOG")

        # Verificar que no se haya generado advertencia de clave omitida para @asiscfg
        omitted_warnings = [m for m in cm.output if "@asiscfg" in m and "omitida" in m]
        self.assertEqual(len(omitted_warnings), 0)
        self.assertIn("@asiscfg", loaded)
        self.assertEqual(loaded["@asiscfg"]["admin_pass_hash"], hash_password("admin"))

    def test_save_backup_creation_and_policy(self):
        # 1. Primer guardado: el archivo no existía previamente, no debe haber backup
        bak_res = save_config(self.context, self.def_values, validation_rules=self.val_rules)
        self.assertIsNone(bak_res)
        self.assertFalse(os.path.exists(self.config_path + ".bak"))

        # 2. Segundo guardado con _backup por defecto: debe crearse en backups/ y NO en la raíz
        mod_config = self.def_values.copy()
        mod_config["app"]["port"] = 9000
        bak_res2 = save_config(self.context, mod_config, validation_rules=self.val_rules)
        self.assertIsNotNone(bak_res2)
        backup_dir = os.path.join(self.test_dir, "backups")
        self.assertTrue(os.path.exists(backup_dir))
        self.assertTrue(os.path.exists(os.path.join(backup_dir, bak_res2)))
        self.assertFalse(os.path.exists(self.config_path + ".bak"))

        # 3. Guardado con clave puente SCHEMA_KEY
        schema_bridge = {
            "_backup": {
                "enabled": True,
                "target_dir": {"schema_key": "paths.custom_bak"},
                "filename_pattern": "custom_{TIMESTAMP}.bak",
                "max_backups": 5
            },
            "paths": {
                "custom_bak": os.path.join(self.test_dir, "custom_backups_dir")
            },
            "app": {
                "port": 9001
            }
        }
        meta_v = extract_schema_metadata(schema_bridge)
        def_v, rules_v = meta_v["default_config"], meta_v["validation_rules"]
        bak_bridge = save_config(self.context, def_v, validation_rules=rules_v, default_config=def_v)
        self.assertIsNotNone(bak_bridge)
        custom_dir = os.path.join(self.test_dir, "custom_backups_dir")
        self.assertTrue(os.path.exists(custom_dir))
        self.assertTrue(os.path.exists(os.path.join(custom_dir, bak_bridge)))

        # 4. Guardado con backup deshabilitado
        schema_disabled = {
            "_backup": {"enabled": False},
            "app": {"port": 9002}
        }
        meta_dis = extract_schema_metadata(schema_disabled)
        def_dis, rules_dis = meta_dis["default_config"], meta_dis["validation_rules"]
        bak_dis = save_config(self.context, def_dis, validation_rules=rules_dis, default_config=def_dis)
        self.assertIsNone(bak_dis)

    def test_profile_sub_section_validation_out_of_range(self):
        invalid_data = {
            "app": {"port": 999999},  # Fuera de rango [1000-9999]
            "@profiles": {
                "01": {
                    "db": {"pool_size": 999}  # Fuera de rango [1-50]
                }
            }
        }
        validated = validate_and_correct_config(
            invalid_data,
            validation_rules=self.val_rules,
            default_config=self.def_values,
            context=self.context
        )

        self.assertEqual(validated.valor("app.port"), 8080)
        self.assertEqual(validated.valor_profile("01", "db.pool_size"), 10)
        self.assertNotIn("db", validated)

    def test_strict_typing_and_string_preservation(self):
        # Esquema con campo str que contiene dígitos y campo int
        custom_schema = {
            "db_sql": {
                "empresa_destino": {"default": "01", "type": "str", "description": "Código empresa"},
                "timeout": {"default": 30, "type": "int", "min": 1, "max": 120}
            }
        }
        meta_custom = extract_schema_metadata(custom_schema)
        def_vals, val_rules = meta_custom["default_config"], meta_custom["validation_rules"]

        # 1. Si en el diccionario viene un int para empresa_destino, el validador lo convierte a str
        raw_input = {
            "db_sql": {
                "empresa_destino": 1,  # Como entero
                "timeout": "45"       # Como string numérico
            }
        }
        validated = validate_and_correct_config(
            raw_input,
            validation_rules=val_rules,
            default_config=def_vals,
            context=self.context
        )
        self.assertIsInstance(validated["db_sql"]["empresa_destino"], str)
        self.assertEqual(validated["db_sql"]["empresa_destino"], "1")
        self.assertIsInstance(validated["db_sql"]["timeout"], int)
        self.assertEqual(validated["db_sql"]["timeout"], 45)

        # 2. Guardar y verificar que en disco se preserve como string con comillas
        save_config(
            self.context,
            validated,
            validation_rules=val_rules,
            default_config=def_vals,
            format_mode="plain"
        )
        with open(self.config_path, "r", encoding="utf-8") as f:
            content = f.read()
        import json
        lines = content.splitlines()
        loaded_json = json.loads("\n".join(lines[1:]))
        self.assertIsInstance(loaded_json["db_sql"]["empresa_destino"], str)
        self.assertEqual(loaded_json["db_sql"]["empresa_destino"], "1")

    def test_validate_and_correct_config_strict_types(self):
        """Verifica que validate_and_correct_config falle tempranamente si algún parámetro no tiene el tipo esperado."""
        # config no dict
        with self.assertRaises(TypeError):
            validate_and_correct_config("not_a_dict", {}, {}, self.context)

        # validation_rules no dict
        with self.assertRaises(TypeError):
            validate_and_correct_config({}, "not_a_dict", {}, self.context)

        # default_config no dict
        with self.assertRaises(TypeError):
            validate_and_correct_config({}, {}, "not_a_dict", self.context)

        # context no AppConfigContext
        with self.assertRaises(TypeError):
            validate_and_correct_config({}, {}, {}, "not_a_context")

    def test_schema_driven_loading_and_cleanup_of_obsolete_keys(self):
        # 1. Guardar primero una configuración válida con contraseñas cifradas
        save_data = {
            "app": {
                "name": "AppModificada",
                "port": 9090,
                "api_key": "nueva_api_key_123",
            },
            "@profiles": {
                "01": {
                    "info": {
                        "name": "Perfil Uno Modificado",
                    },
                    "db": {
                        "host": "10.0.0.1",
                        "password": "clave_local_01",
                    }
                },
                "02": {
                    "info": {
                        "name": "Perfil Dos Nuevo"
                    },
                    "db": {
                        "host": "10.0.0.2"
                    }
                }
            }
        }
        save_config(
            self.context,
            save_data,
            validation_rules=self.val_rules,
            default_config=self.def_values,
            format_mode="plain"
        )

        # 2. Inyectar secciones y claves obsoletas directamente en el JSON en disco
        with open(self.config_path, "r", encoding="utf-8") as f:
            raw_text = f.read()

        import json
        lines = raw_text.splitlines()
        dirty_json = json.loads("\n".join(lines[1:]))
        dirty_json["app"]["clave_obsoleta_en_app"] = "deberia_ignorarse"
        dirty_json["seccion_obsoleta_raiz"] = {"param_viejo": 123}
        dirty_json["@profiles"]["01"]["info"]["extra_info_invalido"] = "descartar"
        dirty_json["@profiles"]["01"]["db"]["param_db_obsoleto"] = 999
        dirty_json["@profiles"]["01"]["subseccion_invalida"] = {"campo_x": "valor_x"}

        with open(self.config_path, "w", encoding="utf-8") as f:
            f.write(f"{FORMAT_MODES['plain'].header}\n" + json.dumps(dirty_json, indent=4))

        # 3. Cargar la configuración interceptando los logs de warning
        with self.assertLogs(level="WARNING") as log_context:
            loaded = load_config(
                self.context,
                default_config=self.def_values,
                validation_rules=self.val_rules,
                edit_mode=True
            )

        log_output = "\n".join(log_context.output)

        # Verificar que se hayan emitido warnings para cada elemento omitido
        self.assertIn("clave_obsoleta_en_app", log_output)
        self.assertIn("seccion_obsoleta_raiz", log_output)
        self.assertIn("extra_info_invalido", log_output)
        self.assertIn("param_db_obsoleto", log_output)
        self.assertIn("subseccion_invalida", log_output)

        # Verificar que la configuración cargada en memoria solo contiene las claves del esquema
        self.assertEqual(loaded.valor("app.name"), "AppModificada")
        self.assertEqual(loaded.valor("app.port"), 9090)
        self.assertEqual(loaded.valor("app.api_key"), "<pass_app.api_key>")
        self.assertEqual(loaded.valorpass("app.api_key"), "nueva_api_key_123")
        self.assertNotIn("clave_obsoleta_en_app", loaded.get("app", {}))
        self.assertNotIn("seccion_obsoleta_raiz", loaded)

        # En general.active_language no venía en el archivo local, debe haber tomado el default del esquema
        self.assertEqual(loaded.valor("general.active_language"), "es")

        # Verificar datos de perfil 01
        self.assertEqual(loaded.valor_profile("01", "info.name"), "Perfil Uno Modificado")
        self.assertNotIn("extra_info_invalido", loaded.get("@profiles", {}).get("01", {}).get("info", {}))
        self.assertEqual(loaded.valor_profile("01", "db.host"), "10.0.0.1")
        self.assertNotIn("param_db_obsoleto", loaded.get("@profiles", {}).get("01", {}).get("db", {}))
        self.assertNotIn("subseccion_invalida", loaded.get("@profiles", {}).get("01", {}))
        # pool_size no venía en el perfil 01 del archivo local, debe haber tomado el default (10)
        self.assertEqual(loaded.valor_profile("01", "db.pool_size"), 10)

        # Verificar perfil 02 creado por el usuario
        self.assertEqual(loaded.valor_profile("02", "info.name"), "Perfil Dos Nuevo")
        self.assertEqual(loaded.valor_profile("02", "db.host"), "10.0.0.2")
        self.assertEqual(loaded.valor_profile("02", "db.password"), "<pass_db.password>")
        self.assertEqual(loaded.valorpass_profile("02", "db.password"), "pass_profile_default")


        # 3. Guardar la configuración a disco y comprobar que el archivo queda limpio
        save_config(
            self.context,
            dict(loaded),
            validation_rules=self.val_rules,
            default_config=self.def_values,
            format_mode="plain"
        )

        with open(self.config_path, "r", encoding="utf-8") as f:
            disk_text = f.read()

        self.assertNotIn("clave_obsoleta_en_app", disk_text)
        self.assertNotIn("seccion_obsoleta_raiz", disk_text)
        self.assertNotIn("extra_info_invalido", disk_text)
        self.assertNotIn("param_db_obsoleto", disk_text)
        self.assertNotIn("subseccion_invalida", disk_text)

    def test_resolve_file_path(self):
        base_d = os.path.abspath("C:\\my_project")
        default_name = "default_config.enc"
        expected_default = os.path.abspath(os.path.join(base_d, default_name))

        # 1. Parámetro None o vacío -> Retorna base_dir/default_name
        self.assertEqual(resolve_file_path(None, default_name, base_d), expected_default)
        self.assertEqual(resolve_file_path("", default_name, base_d), expected_default)
        self.assertEqual(resolve_file_path("   ", default_name, base_d), expected_default)

        # 2. Solo nombre de archivo -> Se une a base_dir
        res_name = resolve_file_path("custom.enc", default_name, base_d)
        expected_name = os.path.abspath(os.path.join(base_d, "custom.enc"))
        self.assertEqual(res_name, expected_name)

        # 3. Camino relativo o absoluto con subcarpetas
        res_rel = resolve_file_path("./data/other.enc", default_name, base_d)
        self.assertEqual(res_rel, os.path.abspath(os.path.join(base_d, "./data/other.enc")))

        res_abs = resolve_file_path("D:\\configs\\prod.enc", default_name, base_d)
        self.assertEqual(res_abs, os.path.abspath("D:\\configs\\prod.enc"))

    def test_resolve_schema_path_rules(self):
        # 1. Escenario 1: Standalone (is_standalone=True) resuelve físicamente en base_dir
        schema_standalone = resolve_schema_path(None, "config_schema.py", self.test_dir, is_standalone=True)
        self.assertEqual(schema_standalone, os.path.abspath(os.path.join(self.test_dir, "config_schema.py")))

        # 2. Ruta física explícita existente en modo integrado (is_standalone=False)
        explicit_file = os.path.join(self.test_dir, "custom_schema.py")
        with open(explicit_file, "w", encoding="utf-8") as f:
            f.write("# custom schema")
        found_explicit = resolve_schema_path(explicit_file, "config_schema.py", self.test_dir, is_standalone=False)
        self.assertEqual(found_explicit, os.path.abspath(explicit_file))

        # 3. Modo integrado sin schema explícito ni empaquetado -> no asume base_dir
        empty_schema = resolve_schema_path(None, "config_schema.py", self.test_dir, is_standalone=False)
        self.assertEqual(empty_schema, "")

    def test_load_config_non_existent_file_modes(self):
        non_existent_cfg = os.path.join(self.test_dir, "does_not_exist.enc")
        non_existent_ctx = create_app_context(config_file=non_existent_cfg, key_file=self.key_path)

        # Modo lectura/no edición (edit_mode=False por defecto) -> Debe lanzar FileNotFoundError
        with self.assertRaises(FileNotFoundError):
            load_config(non_existent_ctx, default_config=self.def_values, edit_mode=False)

        self.assertFalse(os.path.exists(non_existent_cfg))

        # Modo edición (edit_mode=True) -> Debe crear el archivo y retornar ConfigDict con defaults
        cfg = load_config(non_existent_ctx, default_config=self.def_values, edit_mode=True)
        self.assertTrue(os.path.exists(non_existent_cfg))
        self.assertIsInstance(cfg, ConfigDict)
        self.assertEqual(cfg.valor("app.name"), "TestApp")

    def test_i18n_namespacing_and_optional_external_path(self):
        import json
        from i18n import I18nManager

        # 1. Crear un diccionario maestro externo simulando un proyecto anfitrión (Host App)
        ext_lang_dir = os.path.join(self.test_dir, "languages")
        os.makedirs(ext_lang_dir, exist_ok=True)
        
        master_dict = {
            "_language_name": "Español",
            "host_app": {
                "btn_save": "Guardar en Host App"
            },
            "asiscfg": {
                "btn_save_pass": "Guardar Clave Personalizada Host",
                "custom_override": "Texto Sobrescrito por Host"
            }
        }
        with open(os.path.join(ext_lang_dir, "es.json"), "w", encoding="utf-8") as f:
            json.dump(master_dict, f, ensure_ascii=False)

        # 2. Instancia de i18n con el directorio externo provisto (como haría --i18n-path)
        mgr = I18nManager(external_dir=ext_lang_dir)
        mgr.register_defaults({
            "asiscfg": {
                "btn_save_pass": "Guardar Nueva Clave",
                "internal_only": "Texto Solo Interno"
            }
        })

        # Las claves con namespace asiscfg.* leen la sobreescritura externa
        self.assertEqual(mgr.translate("asiscfg.btn_save_pass"), "Guardar Clave Personalizada Host")
        self.assertEqual(mgr.translate("asiscfg.custom_override"), "Texto Sobrescrito por Host")
        self.assertEqual(mgr.translate("asiscfg.internal_only"), "Texto Solo Interno")
        
        # Las claves del host app conviven en el mismo archivo sin colisión
        self.assertEqual(mgr.translate("host_app.btn_save"), "Guardar en Host App")

        # 3. Fallback cuando no existe ruta externa (usando Capa 0 de defaults registrados)
        mgr_standalone = I18nManager(external_dir=None)
        mgr_standalone.register_defaults({"asiscfg": {"clave_registrada": "Texto de Rescate"}})
        self.assertEqual(mgr_standalone.translate("asiscfg.clave_registrada"), "Texto de Rescate")


    def test_export_config_schema_success(self):
        # Crear archivo de esquema resuelto
        schema_src = os.path.join(self.test_dir, "custom_schema.py")
        with open(schema_src, "w", encoding="utf-8") as f:
            f.write('DEFAULT_CONFIG = {"app": {"name": "TestProject"}}\n')

        target_file = os.path.join(self.test_dir, "exported_config_schema.py")
        code = export_config_schema(
            source_path=schema_src,
            target_path=target_file
        )
        self.assertEqual(code, 0)
        self.assertTrue(os.path.exists(target_file))
        with open(target_file, "r", encoding="utf-8") as f:
            content = f.read()
        self.assertIn("TestProject", content)

    def test_export_config_schema_same_file(self):
        schema_src = os.path.join(self.test_dir, "same_schema.py")
        with open(schema_src, "w", encoding="utf-8") as f:
            f.write('DEFAULT_CONFIG = {"app": {"name": "SameFile"}}\n')

        code = export_config_schema(
            source_path=schema_src,
            target_path=schema_src
        )
        self.assertEqual(code, 0)

    def test_export_config_schema_error_handling(self):
        non_existent_source = os.path.join(self.test_dir, "non_existent_schema.py")
        target_file = os.path.join(self.test_dir, "failed_export.py")
        code = export_config_schema(
            source_path=non_existent_source,
            target_path=target_file
        )
        self.assertEqual(code, 1)
        self.assertFalse(os.path.exists(target_file))

    def test_run_asiscfg_reset_admin_pass(self):
        # Probar reset_admin_pass a través de run_asiscfg
        code = run_asiscfg(
            context=self.context,
            reset_admin_pass=True
        )
        self.assertEqual(code, 0)
        self.assertTrue(os.path.exists(self.config_path))
        cfg = load_config(self.context)
        self.assertTrue(check_admin_password("admin", cfg))

    def test_nested_namespace_and_facade_imports(self):
        """Verifica que i18n y db_asisnet sean accesibles anidados y vía fachada principal."""
        import asiscfg
        from asiscfg import (
            t18n,
            I18nManager,
            get_i18n_instance,
            get_db_engine,
            test_connection,
            get_supported_drivers,
            ConnectionConfig,
            build_db_url
        )
        from i18n import t18n as i18n_t18n, I18nManager as NestedI18nManager
        from asisdb import (
            test_connection as db_test_conn,
            get_supported_drivers as db_drivers,
            ConnectionConfig as db_ConnectionConfig,
            build_db_url as db_build_url
        )
        # 1. Validar identidad de funciones y clases re-exportadas
        self.assertIs(t18n, i18n_t18n)
        self.assertIs(I18nManager, NestedI18nManager)
        self.assertIs(test_connection, db_test_conn)
        self.assertIs(get_supported_drivers, db_drivers)
        self.assertIs(ConnectionConfig, db_ConnectionConfig)
        self.assertIs(build_db_url, db_build_url)

        # 2. Validar ejecución de funciones básicas
        drivers = get_supported_drivers()
        self.assertIn("mssql", drivers)
        self.assertIn("sqlite", drivers)

        # 3. Validar traducción básica y registro de defaults
        asiscfg.register_defaults({"test": {"key": "Texto por Defecto"}})
        msg = t18n("test.key", "Texto por Defecto")
        self.assertEqual(msg, "Texto por Defecto")

        # 4. Validar acceso a submódulos directos
        self.assertTrue(hasattr(asiscfg, "i18n"))
        self.assertTrue(hasattr(asiscfg, "asisdb"))

    def test_security_sections_dynamic_treatment(self):
        # 1. Validar helper is_security_section
        self.assertIn("app", SECURITY_SECTIONS)
        self.assertTrue(is_security_section("app"))
        self.assertFalse(is_security_section("other_sec"))
        self.assertFalse(is_security_section(""))

        # 2. Agregar dinámicamente otra sección a SECURITY_SECTIONS y verificar cifrado en modo plain
        test_custom_sec = "custom_sec"
        SECURITY_SECTIONS.append(test_custom_sec)
        try:
            self.assertTrue(is_security_section(test_custom_sec))

            schema_dyn = {
                "custom_sec": {
                    "token": {"default": "mi_token_123"},
                    "max_retries": {"default": 5}
                },
                "normal_sec": {
                    "visible_param": {"default": "publico"}
                }
            }
            meta_dyn = extract_schema_metadata(schema_dyn)
            def_v, rules_v = meta_dyn["default_config"], meta_dyn["validation_rules"]

            save_config(
                self.context,
                def_v,
                validation_rules=rules_v,
                default_config=def_v,
                format_mode="plain"
            )

            # Inspeccionar disco: custom_sec debe tener todos los campos con prefijo ENC:
            with open(self.config_path, "r", encoding="utf-8") as f:
                content = f.read()

            import json
            lines = content.splitlines()
            disk_data = json.loads("\n".join(lines[1:]))

            # Sección normal no se cifra
            self.assertEqual(disk_data["normal_sec"]["visible_param"], "publico")

            # Sección en SECURITY_SECTIONS cifra todos sus valores
            self.assertTrue(disk_data["custom_sec"]["token"].startswith(ENC_PREFIX))
            self.assertTrue(disk_data["custom_sec"]["max_retries"].startswith(ENC_PREFIX))
            self.assertNotIn("mi_token_123", content)

            # Cargar y verificar descifrado transparente
            loaded = load_config(
                self.context,
                default_config=def_v,
                validation_rules=rules_v
            )
            self.assertEqual(loaded.valor("custom_sec.token"), "mi_token_123")
            self.assertEqual(loaded.valor("custom_sec.max_retries"), 5)
            self.assertEqual(loaded.valor("normal_sec.visible_param"), "publico")
        finally:
            if test_custom_sec in SECURITY_SECTIONS:
                SECURITY_SECTIONS.remove(test_custom_sec)

    def test_null_sentinel_empty_password_handling(self):
        """Verifica que campos clave vacíos se guarden como NULL_SENTINEL y se carguen como cadena vacía."""
        data_to_save = {
            "app": {
                "name": "SentinelApp",
                "port": 8080,
                "api_key": ""
            },
            "@profiles": {
                "01": {
                    "info": {"name": "Test Co"},
                    "db": {
                        "host": "localhost",
                        "password": ""
                    }
                }
            }
        }

        # Guardar en modo plain
        save_config(
            self.context,
            data_to_save,
            validation_rules=self.val_rules,
            default_config=self.def_values,
            format_mode="plain"
        )

        with open(self.config_path, "r", encoding="utf-8") as f:
            raw_text = f.read()

        import json
        lines = raw_text.splitlines()
        disk_data = json.loads("\n".join(lines[1:]))

        # En disco, el campo de contraseña vacío debe estar cifrado con prefijo ENC_PREFIX
        self.assertTrue(disk_data["@profiles"]["01"]["db"]["password"].startswith(ENC_PREFIX))
        self.assertTrue(disk_data["app"]["api_key"].startswith(ENC_PREFIX))
        self.assertNotEqual(disk_data["@profiles"]["01"]["db"]["password"], NULL_SENTINEL)
        self.assertNotEqual(disk_data["app"]["api_key"], NULL_SENTINEL)

        # Al cargar en modo productivo (edit_mode=False), es válido y entrega cadena vacía ""
        loaded_prod = load_config(
            self.context,
            default_config=self.def_values,
            validation_rules=self.val_rules,
            edit_mode=False
        )
        self.assertEqual(loaded_prod.valor_profile("01", "db.password"), "<pass_db.password>")
        self.assertEqual(loaded_prod.valorpass_profile("01", "db.password"), "")
        self.assertEqual(loaded_prod.valor("app.api_key"), "<pass_app.api_key>")
        self.assertEqual(loaded_prod.valorpass("app.api_key"), "")
        self.assertEqual(len(loaded_prod.get_password_failures()), 0)

        # Al cargar en modo edición (edit_mode=True), se permite la carga para edición y retorna ""
        loaded = load_config(
            self.context,
            default_config=self.def_values,
            validation_rules=self.val_rules,
            edit_mode=True
        )
        self.assertEqual(loaded.valor_profile("01", "db.password"), "<pass_db.password>")
        self.assertEqual(loaded.valorpass_profile("01", "db.password"), "")
        self.assertEqual(loaded.valor("app.api_key"), "<pass_app.api_key>")
        self.assertEqual(loaded.valorpass("app.api_key"), "")
        failures = loaded.get_password_failures()
        self.assertEqual(len(failures), 0)

        # Si alguien coloca NULL_SENTINEL en texto plano en disco sin ENC:, debe fallar en modo productivo
        plain_tampered = {
            "app": {
                "name": "TamperedApp",
                "port": 8080,
                "api_key": NULL_SENTINEL
            }
        }
        with open(self.config_path, "w", encoding="utf-8") as f:
            f.write(f"{FORMAT_MODES['plain'].header}\n" + json.dumps(plain_tampered, indent=4))

        with self.assertRaises(ValueError):
            load_config(
                self.context,
                default_config=self.def_values,
                validation_rules=self.val_rules,
                edit_mode=False
            )

    def test_corporate_color_palette_structure(self):
        """Verifica que la paleta corporativa estándar (OrbisPDF) contenga todas las especificaciones Light/Dark."""
        from asiscfg.ui.utils import PALETTE, CTkToolTip
        
        # 1. Main Button
        self.assertEqual(PALETTE["MainButton"]["fg_color"], ("#2FA572", "#2FA572"))
        self.assertEqual(PALETTE["MainButton"]["hover_color"], ("#248259", "#248259"))
        self.assertEqual(PALETTE["MainButton"]["text_color"], ("#FFFFFF", "#FFFFFF"))
        
        # 2. Danger Button
        self.assertEqual(PALETTE["DangerButton"]["fg_color"], ("#C0392B", "#C0392B"))
        self.assertEqual(PALETTE["DangerButton"]["hover_color"], ("#922B21", "#922B21"))
        self.assertEqual(PALETTE["DangerButton"]["text_color"], ("#FFFFFF", "#FFFFFF"))
        
        # 3. Table (Zebra & Selection)
        self.assertEqual(PALETTE["Table"]["row_main"], ("#FFFFFF", "#1D1E22"))
        self.assertEqual(PALETTE["Table"]["row_alt"], ("#F2F2F2", "#2E3038"))
        self.assertEqual(PALETTE["Table"]["text_normal"], ("#1A1A1A", "#E6E6E6"))
        self.assertEqual(PALETTE["Table"]["selection_bg"], ("#3B8ED0", "#1F6AA5"))
        self.assertEqual(PALETTE["Table"]["selection_text"], ("#FFFFFF", "#FFFFFF"))
        self.assertEqual(PALETTE["Table"]["border_inactive"], ("#CCCCCC", "#3A3A3A"))
        self.assertEqual(PALETTE["Table"]["error_text"], "#FF3333")
        
        # 4. Tooltips
        self.assertEqual(PALETTE["Tooltip"]["bg_color"], ("#FFFFE0", "#82F19A"))
        self.assertEqual(PALETTE["Tooltip"]["text_color"], ("#000000", "#0C0B0B"))
        
        # 5. Links & Separators
        self.assertEqual(PALETTE["Link"]["text_color"], ("#1F6AA5", "#3B8ED0"))
        self.assertEqual(PALETTE["Separator"]["fg_color"], ("#CCCCCC", "#555555"))
        self.assertEqual(PALETTE["Disabled"]["text_color"], "gray")

    def test_theme_parameter_configuration(self):
        """Verifica que el parámetro de tema/modo de apariencia visual se procese correctamente."""
        import customtkinter as ctk
        from asiscfg.ui.app import ConfigApp
        from asiscfg.core import save_config

        # Crear archivo de configuración para evitar el diálogo interactivo de creación
        save_config(self.context, {"app": {"name": "TestApp"}})

        # Validar inicialización con tema dark por defecto
        app = ConfigApp(
            context=self.context,
            dev_mode=True,
            theme="dark"
        )
        self.assertEqual(app.theme, "dark")
        self.assertEqual(ctk.get_appearance_mode(), "Dark")
        app.destroy()

        # Validar inicialización con tema light
        app_light = ConfigApp(
            context=self.context,
            dev_mode=True,
            theme="light"
        )
        self.assertEqual(app_light.theme, "light")
        self.assertEqual(ctk.get_appearance_mode(), "Light")
        app_light.destroy()
    def test_lazy_decryption_and_valorpass_methods(self):
        """
        Verifica exhaustivamente:
        1. ConfigDict mantiene contraseñas encriptadas en memoria.
        2. valor / valor_profile / valor_parent retornan máscara <pass_key> para contraseñas.
        3. valorpass / valorpass_profile / valorpass_parent desencriptan JIT y soportan valor_compara.
        4. valorpass sobre variables comunes retorna la máscara <var_key>.
        5. Variables en SECURITY_SECTIONS con is_password=False se desencriptan en memoria al cargar.
        """
        custom_schema = {
            "seguridad": {
                "admin_user": {"default": "superadmin", "type": "str", "is_password": False},
                "admin_pass": {"default": "admin_secret_999", "type": "str", "is_password": True},
            },
            "app": {
                # SECURITY_SECTION (app): licencia is_password=False se desencripta al cargar; token is_password=True se mantiene cifrado
                "licencia": {"default": "LIC-ABCD-1234", "type": "str", "is_password": False},
                "token": {"default": "TOK-SECRET-9999", "type": "str", "is_password": True},
            },
            "@profiles": {
                "_template": {
                    "conexiones": {
                        "host": {"default": "127.0.0.1", "type": "str", "is_password": False},
                        "user": {"default": "sa", "type": "str", "is_password": False},
                        "password": {"default": "perfil_pwd_123", "type": "str", "is_password": True},
                    }
                },
                "01": {
                    "conexiones": {
                        "user": "root",
                        "password": "clave_perfil_01"
                    }
                }
            }
        }

        meta_custom = extract_schema_metadata(custom_schema)
        def_vals, val_rules = meta_custom["default_config"], meta_custom["validation_rules"]
        self.context.password_fields = list(meta_custom["password_fields"])

        # 1. Guardar configuración
        save_config(
            self.context,
            def_vals,
            validation_rules=val_rules,
            default_config=def_vals,
            format_mode="plain"
        )

        # 2. Cargar configuración
        loaded = load_config(
            self.context,
            default_config=def_vals,
            validation_rules=val_rules
        )

        # 3. Validar enmascaramiento en valor() para contraseñas y variables
        self.assertEqual(loaded.valor("seguridad.admin_pass"), "<pass_seguridad.admin_pass>")
        self.assertEqual(loaded.valor("seguridad.admin_user"), "superadmin")

        # 4. Validar valorpass() para contraseñas
        self.assertEqual(loaded.valorpass("seguridad.admin_pass"), "admin_secret_999")
        self.assertTrue(loaded.valorpass("seguridad.admin_pass", valor_compara="admin_secret_999"))
        self.assertFalse(loaded.valorpass("seguridad.admin_pass", valor_compara="otra_clave"))

        # 5. Validar valorpass() sobre variable común -> máscara <var_key>
        self.assertEqual(loaded.valorpass("seguridad.admin_user"), "<var_seguridad.admin_user>")

        # 6. Validar SECURITY_SECTIONS (app):
        # 'app.licencia' (is_password=False) -> se desencriptó al cargar en memoria
        self.assertEqual(loaded.valor("app.licencia"), "LIC-ABCD-1234")
        self.assertEqual(loaded.valorpass("app.licencia"), "<var_app.licencia>")
        # 'app.token' (is_password=True) -> se mantuvo cifrado en memoria
        self.assertEqual(loaded.valor("app.token"), "<pass_app.token>")
        self.assertEqual(loaded.valorpass("app.token"), "TOK-SECRET-9999")
        self.assertTrue(loaded.valorpass("app.token", valor_compara="TOK-SECRET-9999"))

        # 7. Validar perfiles con valor_profile y valorpass_profile
        self.assertEqual(loaded.valor_profile("01", "conexiones.password"), "<pass_conexiones.password>")
        self.assertEqual(loaded.valor_profile("01", "conexiones.user"), "root")
        self.assertEqual(loaded.valorpass_profile("01", "conexiones.password"), "clave_perfil_01")
        self.assertTrue(loaded.valorpass_profile("01", "conexiones.password", valor_compara="clave_perfil_01"))
        self.assertEqual(loaded.valorpass_profile("01", "conexiones.user"), "<var_conexiones.user>")

        # 8. Validar herencia jerárquica con valor_parent y valorpass_parent
        self.assertEqual(loaded.valor_parent("conexiones.password", profile_code="01"), "<pass_conexiones.password>")
        self.assertEqual(loaded.valor_parent("conexiones.user", profile_code="01"), "root")
        self.assertEqual(loaded.valorpass_parent("conexiones.password", profile_code="01"), "clave_perfil_01")
        self.assertTrue(loaded.valorpass_parent("conexiones.password", profile_code="01", valor_compara="clave_perfil_01"))
        self.assertEqual(loaded.valorpass_parent("conexiones.user", profile_code="01"), "<var_conexiones.user>")

    def test_cryptography_startup_import_validation(self):
        """Verifica que la importación de Fernet y AEAD esté validada en asiscfg.crypto."""
        from asiscfg.crypto import Fernet as CryptoFernet
        from cryptography.fernet import Fernet as OrigFernet
        self.assertIs(CryptoFernet, OrigFernet)

    def test_get_key_raises_filenotfound_when_missing(self):
        """Verifica que get_key lance FileNotFoundError si no existe el archivo de clave."""
        missing_key_path = os.path.join(self.test_dir, "non_existent_secret.key")
        self.assertFalse(os.path.exists(missing_key_path))
        missing_ctx = create_app_context(config_file=self.config_path, key_file=missing_key_path)
        with self.assertRaises(FileNotFoundError):
            get_key(missing_ctx)

    def test_generate_key_file_explicit_creation_and_overwrite(self):
        """Verifica la creación explícita de clave y control de sobreescritura."""
        new_key_path = os.path.join(self.test_dir, "explicit_new_secret.key")
        new_ctx = create_app_context(config_file=self.config_path, key_file=new_key_path)
        key_bytes = generate_key_file(new_ctx)
        self.assertTrue(os.path.exists(new_key_path))
        self.assertEqual(len(key_bytes), 44)  # Clave Fernet base64 urlsafe de 32 bytes = 44 chars

        # Intentar generar de nuevo sin overwrite debe lanzar FileExistsError
        with self.assertRaises(FileExistsError):
            generate_key_file(new_ctx, overwrite=False)

        # Con overwrite=True se debe permitir regenerar
        new_key_bytes = generate_key_file(new_ctx, overwrite=True)
        self.assertEqual(len(new_key_bytes), 44)

    def test_get_key_caching_and_force_reload(self):
        """Verifica que get_key utilice caché en memoria para evitar lecturas de disco y responda a forzar=True."""
        key_path = os.path.join(self.test_dir, "cache_test.key")
        cache_ctx = create_app_context(config_file=self.config_path, key_file=key_path)
        initial_key = generate_key_file(cache_ctx)

        # 1. Primera lectura debe devolver la clave
        self.assertEqual(get_key(cache_ctx), initial_key)

        # 2. Modificamos el archivo físicamente en disco sin invalidar la caché
        modified_key = b"ANOTHER_MOCK_FERNET_KEY_IN_DISK_1234567890="
        with open(key_path, "wb") as f:
            f.write(modified_key)

        # 3. get_key() sin forzar debe devolver el valor en caché (initial_key), evitando la lectura de disco
        self.assertEqual(get_key(cache_ctx), initial_key)

        # 4. get_key(..., forzar=True) debe recargar desde disco
        self.assertEqual(get_key(cache_ctx, forzar=True), modified_key)

    def test_password_fields_centralized_registration_and_lookup(self):
        """Verifica la extracción de password_fields y la consulta directa en _is_password_field."""
        sample_schema = {
            "conexiones": {
                "user": {"default": "root", "type": "str", "is_password": False},
                "password": {"default": "secret123", "type": "str", "is_password": True}
            },
            "@profiles": {
                "_template": {
                    "conexiones": {
                        "password": {"default": "", "type": "str", "is_password": True},
                        "host": {"default": "localhost", "type": "str", "is_password": False}
                    }
                }
            }
        }
        meta = extract_schema_metadata(sample_schema)
        def_vals = meta["default_config"]
        rules = meta["validation_rules"]
        pwd_fields = meta["password_fields"]

        self.assertIn("conexiones.password", pwd_fields)
        self.assertIn("@profiles.conexiones.password", pwd_fields)
        self.assertNotIn("conexiones.user", pwd_fields)
        self.assertNotIn("@profiles.conexiones.host", pwd_fields)

        test_ctx = create_app_context(config_file=self.config_path, key_file=self.key_path)
        test_ctx.password_fields = pwd_fields
        cfg = ConfigDict(test_ctx, def_vals, validation_rules=rules)
        # Búsqueda directa en general
        self.assertTrue(cfg._is_password_field("conexiones.password"))
        self.assertFalse(cfg._is_password_field("conexiones.user"))

        # Búsqueda directa en perfil
        self.assertTrue(cfg._is_password_field("conexiones.password", profile_code="01"))
        self.assertFalse(cfg._is_password_field("conexiones.host", profile_code="01"))

    def test_valorpass_profile_jit_decryption_with_fernet_retention(self):
        """Verifica que valorpass_profile descifre correctamente en JIT preservando Fernet tras load_config y validación."""
        schema = {
            "@profiles": {
                "_template": {
                    "db": {
                        "password": {"default": "master_pwd_123", "type": "str", "is_password": True},
                        "user": {"default": "admin", "type": "str"}
                    }
                },
                "01": {
                    "db": {
                        "password": "perfil_pwd_999"
                    }
                }
            }
        }
        meta_prof = extract_schema_metadata(schema)
        def_vals, rules = meta_prof["default_config"], meta_prof["validation_rules"]
        cfg_file = os.path.join(self.test_dir, "test_prof_pwd.enc")
        prof_ctx = create_app_context(config_file=cfg_file, key_file=self.key_path, format_mode="plain")
        prof_ctx.password_fields = list(meta_prof["password_fields"])
        save_config(prof_ctx, def_vals, validation_rules=rules, default_config=def_vals, format_mode="plain")

        loaded = load_config(prof_ctx, default_config=def_vals, validation_rules=rules)
        self.assertEqual(loaded.valor_profile("01", "db.password"), "<pass_db.password>")
        self.assertEqual(loaded.valorpass_profile("01", "db.password"), "perfil_pwd_999")

    def test_app_config_context_creation_and_resolution(self):
        """Verifica la resolución canónica de rutas y creación de AppConfigContext."""
        ctx = create_app_context(
            config_file="custom_conf.enc",
            key_file="custom_key.key",
            schema_file="custom_schema.py",
            base_dir=self.test_dir,
            admin_pass_hash="hash_test_123",
            format_mode="fernet"
        )
        self.assertIsInstance(ctx, AppConfigContext)
        self.assertEqual(ctx.config_file_path, os.path.abspath(os.path.join(self.test_dir, "custom_conf.enc")))
        self.assertEqual(ctx.config_file_name, "custom_conf.enc")
        self.assertEqual(ctx.key_file_path, os.path.abspath(os.path.join(self.test_dir, "custom_key.key")))
        self.assertEqual(ctx.key_file_name, "custom_key.key")
        self.assertEqual(ctx.schema_file_path, os.path.abspath(os.path.join(self.test_dir, "custom_schema.py")))
        self.assertEqual(ctx.schema_file_name, "custom_schema.py")
        self.assertEqual(ctx.admin_pass_hash, "hash_test_123")
        self.assertEqual(ctx.format_mode, "fernet")

    def test_load_and_save_config_with_context(self):
        """Verifica que load_config y save_config usen el contexto unificado y lo vinculen al ConfigDict."""
        custom_cfg_path = os.path.join(self.test_dir, "context_test.enc")
        ctx = create_app_context(
            config_file=custom_cfg_path,
            key_file=self.key_path,
            format_mode="plain"
        )
        data = {"app": {"name": "AppConContexto"}}
        save_config(ctx, data)
        self.assertTrue(os.path.exists(custom_cfg_path))

        loaded = load_config(ctx)
        self.assertIsNotNone(loaded.context)
        self.assertEqual(loaded.context.config_file_path, custom_cfg_path)
        self.assertEqual(loaded.valor("app.name"), "AppConContexto")

        # Probar guardado automático usando el contexto interno del ConfigDict
        loaded["app"]["name"] = "AppConContextoModificada"
        save_config(loaded.context, loaded)
        reloaded = load_config(ctx)
        self.assertEqual(reloaded.valor("app.name"), "AppConContextoModificada")

    def test_multiple_parallel_configurations_isolation(self):
        """Verifica que dos instancias independientes con sus propios contextos operen en paralelo sin interferencia."""
        cfg1_path = os.path.join(self.test_dir, "sede_1.enc")
        cfg2_path = os.path.join(self.test_dir, "sede_2.enc")
        key1_path = os.path.join(self.test_dir, "key_1.key")
        key2_path = os.path.join(self.test_dir, "key_2.key")

        ctx1 = create_app_context(config_file=cfg1_path, key_file=key1_path, format_mode="plain")
        ctx2 = create_app_context(config_file=cfg2_path, key_file=key2_path, format_mode="plain")
        generate_key_file(ctx1)
        generate_key_file(ctx2)

        save_config(ctx1, {"db": {"host": "10.0.0.1"}})
        save_config(ctx2, {"db": {"host": "10.0.0.2"}})

        obj1 = load_config(ctx1)
        obj2 = load_config(ctx2)

        self.assertEqual(obj1.valor("db.host"), "10.0.0.1")
        self.assertEqual(obj2.valor("db.host"), "10.0.0.2")
        self.assertEqual(obj1.context.config_file_path, cfg1_path)
        self.assertEqual(obj2.context.config_file_path, cfg2_path)

    def test_verify_key_integrity_missing_key(self):
        """Verifica que verify_key_integrity detecte correctamente un archivo de clave faltante."""
        missing_key_path = os.path.join(self.test_dir, "nonexistent.key")
        ctx = create_app_context(config_file=self.config_path, key_file=missing_key_path)
        status, detail = verify_key_integrity(ctx)
        self.assertEqual(status, "missing")
        self.assertIn("nonexistent.key", detail)

    def test_verify_key_integrity_empty_key(self):
        """Verifica que verify_key_integrity detecte un archivo de clave vacío (0 bytes)."""
        empty_key_path = os.path.join(self.test_dir, "empty.key")
        with open(empty_key_path, "wb") as f:
            pass
        ctx = create_app_context(config_file=self.config_path, key_file=empty_key_path)
        status, detail = verify_key_integrity(ctx)
        self.assertEqual(status, "corrupted")
        self.assertIn("vacío", detail.lower())

    def test_verify_key_integrity_malformed_key(self):
        """Verifica que verify_key_integrity detecte un archivo de clave con bytes/formato corrupto."""
        bad_key_path = os.path.join(self.test_dir, "corrupted.key")
        with open(bad_key_path, "wb") as f:
            f.write(b"NOT_A_VALID_KEY_CONTENT_12345")
        ctx = create_app_context(config_file=self.config_path, key_file=bad_key_path, format_mode="fernet")
        status, detail = verify_key_integrity(ctx)
        self.assertEqual(status, "corrupted")

    def test_verify_key_integrity_mismatched_key_encrypted_format(self):
        """Verifica que verify_key_integrity detecte una clave alterada que no coincide con un archivo totalmente cifrado."""
        # 1. Guardar configuración cifrada con clave A
        ctx_a = create_app_context(config_file=self.config_path, key_file=self.key_path, format_mode="fernet")
        save_config(ctx_a, {"app": {"secret": "data123"}}, format_mode="fernet")

        # 2. Crear clave B válida estructuralmente pero distinta
        key_b_path = os.path.join(self.test_dir, "other.key")
        ctx_b = create_app_context(config_file=self.config_path, key_file=key_b_path, format_mode="fernet")
        generate_key_file(ctx_b)

        # 3. Probar contexto B contra el config_path cifrado con clave A
        status, detail = verify_key_integrity(ctx_b)
        self.assertEqual(status, "corrupted")
        self.assertTrue(len(detail) > 0)

    def test_verify_key_integrity_mismatched_key_plain_format(self):
        """Verifica que verify_key_integrity detecte una clave alterada en formato plain con campos cifrados."""
        # 1. Guardar configuración plain con campos protegidos usando clave A
        save_config(
            self.context,
            self.def_values,
            validation_rules=self.val_rules,
            default_config=self.def_values,
            format_mode="plain"
        )

        # 2. Crear clave B
        key_b_path = os.path.join(self.test_dir, "other_plain.key")
        ctx_b = create_app_context(config_file=self.config_path, key_file=key_b_path, format_mode="plain")
        generate_key_file(ctx_b)

        # 3. Validar integridad de ctx_b contra la configuración existente
        status, detail = verify_key_integrity(ctx_b)
        self.assertEqual(status, "corrupted")

    def test_verify_key_integrity_ok(self):
        """Verifica que verify_key_integrity retorne status 'ok' cuando la clave y la configuración son correctas."""
        save_config(
            self.context,
            self.def_values,
            validation_rules=self.val_rules,
            default_config=self.def_values,
            format_mode="plain"
        )
        status, detail = verify_key_integrity(self.context)
        self.assertEqual(status, "ok")
        self.assertEqual(detail, "")

    def test_password_failures_missing_keys(self):
        """Verifica la detección de claves de contraseña faltantes en archivo existente."""
        # 1. Guardar una configuración donde falta una clave de contraseña (ej. db.password en perfil 01)
        data_without_pwd = {
            "app": {
                "name": "TestApp",
                "port": 8080,
                "api_key": "ENC:valid_encrypted_token"
            },
            "@profiles": {
                "01": {
                    "info": {"name": "Perfil Uno"},
                    "db": {"host": "192.168.1.50"}  # Falta password
                }
            }
        }
        # Cifrar api_key con el motor
        from asiscfg.constants import get_format_engine
        engine = get_format_engine("plain")
        data_without_pwd["app"]["api_key"] = engine.encrypt_field("secret_key_123", self.context.key_bytes)

        with open(self.config_path, "w", encoding="utf-8") as f:
            f.write(f"{engine.header}\n" + json.dumps(data_without_pwd, indent=4))

        # 2. En modo producción (edit_mode=False), debe lanzar ValueError detallando la clave faltante
        with self.assertRaises(ValueError) as ctx_err:
            load_config(
                self.context,
                default_config=self.def_values,
                validation_rules=self.val_rules,
                edit_mode=False
            )
        self.assertIn("@profiles.01.db.password", str(ctx_err.exception))

        # 3. En modo edición (edit_mode=True), debe cargar sin fallar y registrar la falla
        loaded = load_config(
            self.context,
            default_config=self.def_values,
            validation_rules=self.val_rules,
            edit_mode=True
        )
        failures = loaded.get_password_failures()
        self.assertTrue(any(f["field_path"] == "@profiles.01.db.password" and f["reason"] == "missing" for f in failures))

    def test_password_failures_unencrypted_and_empty(self):
        """Verifica la detección de contraseñas no encriptadas y vacías."""
        from asiscfg.constants import get_format_engine
        engine = get_format_engine("plain")

        data_faulty = {
            "app": {
                "name": "TestApp",
                "port": 8080,
                "api_key": "clave_en_texto_claro_sin_enc"
            },
            "@profiles": {
                "01": {
                    "info": {"name": "Perfil Uno"},
                    "db": {
                        "host": "192.168.1.50",
                        "password": "ENC:"
                    }
                }
            }
        }
        with open(self.config_path, "w", encoding="utf-8") as f:
            f.write(f"{engine.header}\n" + json.dumps(data_faulty, indent=4))

        # En producción debe fallar
        with self.assertRaises(ValueError) as ctx_err:
            load_config(
                self.context,
                default_config=self.def_values,
                validation_rules=self.val_rules,
                edit_mode=False
            )
        err_msg = str(ctx_err.exception)
        self.assertIn("app.api_key", err_msg)
        self.assertIn("@profiles.01.db.password", err_msg)

        # En edición debe cargar y detallar ambas fallas
        loaded = load_config(
            self.context,
            default_config=self.def_values,
            validation_rules=self.val_rules,
            edit_mode=True
        )
        failures = loaded.get_password_failures()
        self.assertTrue(any(f["field_path"] == "app.api_key" and f["reason"] == "unencrypted" for f in failures))
        self.assertTrue(any(f["field_path"] == "@profiles.01.db.password" and f["reason"] == "empty" for f in failures))

    def test_password_failures_decryption_error(self):
        """Verifica la detección de error al desencriptar campos individuales."""
        from asiscfg.constants import get_format_engine
        engine = get_format_engine("plain")

        data_bad_crypto = {
            "app": {
                "name": "TestApp",
                "port": 8080,
                "api_key": "ENC:gAAAAABinvalidCorruptedPayloadTokenHere=="
            },
            "@profiles": {
                "01": {
                    "info": {"name": "Perfil Uno"},
                    "db": {
                        "host": "192.168.1.50",
                        "password": engine.encrypt_field("valid_pass", self.context.key_bytes)
                    }
                }
            }
        }
        with open(self.config_path, "w", encoding="utf-8") as f:
            f.write(f"{engine.header}\n" + json.dumps(data_bad_crypto, indent=4))

        # En producción debe fallar
        with self.assertRaises(ValueError) as ctx_err:
            load_config(
                self.context,
                default_config=self.def_values,
                validation_rules=self.val_rules,
                edit_mode=False
            )
        self.assertIn("app.api_key", str(ctx_err.exception))

        # En edición debe cargar registrando la falla
        loaded = load_config(
            self.context,
            default_config=self.def_values,
            validation_rules=self.val_rules,
            edit_mode=True
        )
        failures = loaded.get_password_failures()
        self.assertTrue(any(f["field_path"] == "app.api_key" and f["reason"] == "decrypt_error" for f in failures))

    def test_password_failures_empty_enc_prefix(self):
        """Verifica la detección de error cuando el campo inicia con ENC: pero no tiene payload (ej: 'ENC:')."""
        from asiscfg.constants import get_format_engine
        engine = get_format_engine("plain")

        data_empty_enc = {
            "app": {
                "name": "TestApp",
                "port": 8080,
                "api_key": "ENC:"
            },
            "@profiles": {
                "01": {
                    "info": {"name": "Perfil Uno"},
                    "db": {
                        "host": "192.168.1.50",
                        "password": engine.encrypt_field("valid_pass", self.context.key_bytes)
                    }
                }
            }
        }
        with open(self.config_path, "w", encoding="utf-8") as f:
            f.write(f"{engine.header}\n" + json.dumps(data_empty_enc, indent=4))

        # En producción debe fallar
        with self.assertRaises(ValueError) as ctx_err:
            load_config(
                self.context,
                default_config=self.def_values,
                validation_rules=self.val_rules,
                edit_mode=False
            )
        self.assertIn("app.api_key", str(ctx_err.exception))

        # En edición debe cargar registrando la falla de vacío
        loaded = load_config(
            self.context,
            default_config=self.def_values,
            validation_rules=self.val_rules,
            edit_mode=True
        )
        failures = loaded.get_password_failures()
        self.assertTrue(any(f["field_path"] == "app.api_key" and f["reason"] == "empty" for f in failures))

    def test_password_encrypted_null_sentinel_is_valid_and_returns_empty_string(self):
        """Verifica que si una clave protegida tiene token cifrado válido que desencripta a NULL_SENTINEL:
        1. No se detecta como falla de contraseña.
        2. Carga exitosamente en modo producción (edit_mode=False).
        3. valorpass y valorpass_profile retornan cadena vacía ('').
        4. Comparación con '' retorna True.
        """
        from asiscfg.constants import get_format_engine, NULL_SENTINEL
        engine = get_format_engine("plain")

        data_null_sentinel = {
            "app": {
                "name": "TestApp",
                "port": 8080,
                "api_key": ""
            },
            "@profiles": {
                "01": {
                    "info": {"name": "Perfil Uno"},
                    "db": {
                        "host": "192.168.1.50",
                        "password": ""
                    }
                }
            }
        }
        save_config(
            self.context,
            data_null_sentinel,
            validation_rules=self.val_rules,
            default_config=self.def_values,
            format_mode="plain"
        )

        # Cargar en modo producción (no debe fallar)
        loaded = load_config(
            self.context,
            default_config=self.def_values,
            validation_rules=self.val_rules,
            edit_mode=False
        )

        # No debe haber fallas de contraseña
        failures = loaded.get_password_failures()
        self.assertEqual(len(failures), 0)

        # Para el consumidor / UI debe entregarse como cadena vacía ""
        self.assertEqual(loaded.valorpass("app.api_key"), "")
        self.assertEqual(loaded.valorpass_profile("01", "db.password"), "")
        self.assertTrue(loaded.valorpass("app.api_key", valor_compara=""))
        self.assertTrue(loaded.valorpass_profile("01", "db.password", valor_compara=""))

    def test_schema_expects_profiles_but_physical_file_has_none_raises_error(self):
        """Verifica que si el esquema requiere @profiles y el archivo físico existe pero no contiene perfiles:
        - En modo producción (edit_mode=False) lanza ValueError y detiene la ejecución.
        - En modo edición (edit_mode=True) carga emitiendo advertencia.
        """
        from asiscfg.constants import get_format_engine
        engine = get_format_engine("plain")

        # Archivo físico que solo contiene la sección app pero ninguna sección de @profiles
        data_without_profiles = {
            "app": {
                "name": "AppSinPerfiles",
                "port": 8080,
                "api_key": engine.encrypt_field("secret_key", self.context.key_bytes)
            }
        }
        with open(self.config_path, "w", encoding="utf-8") as f:
            f.write(f"{engine.header}\n" + json.dumps(data_without_profiles, indent=4))

        # En modo producción debe fallar con ValueError indicando que falta @profiles
        with self.assertRaises(ValueError) as ctx_err:
            load_config(
                self.context,
                default_config=self.def_values,
                validation_rules=self.val_rules,
                edit_mode=False
            )
        self.assertIn("@profiles", str(ctx_err.exception))

        # En modo edición se permite la carga para corrección
        loaded = load_config(
            self.context,
            default_config=self.def_values,
            validation_rules=self.val_rules,
            edit_mode=True
        )
        self.assertEqual(loaded.get_profiles(), [])


if __name__ == "__main__":
    unittest.main()





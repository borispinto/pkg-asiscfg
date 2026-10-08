# -*- coding: utf-8 -*-
# SPDX-FileCopyrightText: 2026 Asisnet Computacion, CA <proyectos@asisnet.net>
# SPDX-License-Identifier: MIT
# Autor: Boris Pinto <borispinto@asisnet.net>
# File: tests/test_ui_profile_validation.py

"""
Pruebas de verificación de validación y controles de perfiles en la UI (asiscfg.ui.app).
"""

import os
import tempfile
import unittest
import customtkinter as ctk

from asiscfg.constants import SECTION_PROFILES
from asiscfg.models import create_app_context, AppConfigContext
from asiscfg.ui.app import ConfigApp


class TestUIProfileValidation(unittest.TestCase):

    def setUp(self):
        self.test_dir = tempfile.mkdtemp()
        self.config_path = os.path.join(self.test_dir, "test_ui_cfg.enc")
        self.key_path = os.path.join(self.test_dir, "test_ui_sec.key")
        self.schema_path = os.path.join(self.test_dir, "test_schema.py")

        schema_code = '''
DEFAULT_CONFIG = {
    "app": {"name": {"default": "TestApp"}},
    "general": {"timeout": {"default": 30, "type": "int"}},
    "@profiles": {
        "_template": {
            "conexiones": {
                "port": {"default": 1433, "type": "int", "min": 1, "max": 65535},
                "host": {"default": "127.0.0.1", "type": "str"}
            }
        },
        "01": {
            "conexiones": {
                "port": 1433,
                "host": "192.168.1.50"
            }
        }
    }
}
'''
        with open(self.schema_path, "w", encoding="utf-8") as f:
            f.write(schema_code)

        self.context = create_app_context(
            action="ui",
            config_file=self.config_path,
            key_file=self.key_path,
            schema_file=self.schema_path
        )

        from asiscfg.core import save_config, generate_key_file
        generate_key_file(self.context)
        self.initial_data = {
            "app": {"name": "TestApp"},
            "general": {"timeout": 30},
            "@profiles": {
                "_template": {
                    "conexiones": {
                        "port": {"default": 1433, "type": "int", "min": 1, "max": 65535},
                        "host": {"default": "127.0.0.1", "type": "str"}
                    }
                },
                "01": {
                    "conexiones": {
                        "port": 1433,
                        "host": "192.168.1.50"
                    }
                }
            }
        }

        save_config(self.context, self.initial_data)

    def test_profile_entries_validation_and_methods(self):
        app = ConfigApp(
            context=self.context,
            dev_mode=True
        )
        if hasattr(app, "login_frame") and app.login_frame:
            app.login_frame.destroy()
        app._build_main_ui()

        try:
            # 1. Verificar existencia de widgets de perfil y active_profile
            self.assertEqual(app.active_profile, "01")
            self.assertIn("conexiones", app.profile_entries)
            self.assertIn("port", app.profile_entries["conexiones"])

            # 2. Validar que la validación pase inicialmente
            valid, err = app.validate_all_entries()
            self.assertTrue(valid, f"La validación debería pasar pero retornó: {err}")

            # 3. Alterar el valor del puerto en profile_entries a un número fuera de rango
            port_widget = app.profile_entries["conexiones"]["port"]
            port_widget.delete(0, "end")
            port_widget.insert(0, "999999")  # Excede max=65535

            valid, err = app.validate_all_entries()
            self.assertFalse(valid)
            self.assertIn("conexiones.port", err)

            # 4. Alterar el valor del puerto a un string no numérico
            port_widget.delete(0, "end")
            port_widget.insert(0, "abc")
            valid, err = app.validate_all_entries()
            self.assertFalse(valid)
            self.assertIn("conexiones.port", err)

            # 5. Restablecer puerto con reset_param_to_default
            app.reset_param_to_default("conexiones", "port", "1433", port_widget, is_profile=True)
            self.assertEqual(port_widget.get(), "1433")
            valid, err = app.validate_all_entries()
            self.assertTrue(valid)

        finally:
            app.destroy()

    def test_ui_is_password_field_strict_handling(self):
        """Verifica que 'is_password: True' sea la única validación y que se descifre en UI."""
        pwd_schema_path = os.path.join(self.test_dir, "pwd_schema.py")
        pwd_config_path = os.path.join(self.test_dir, "pwd_cfg.enc")
        schema_code = '''
DEFAULT_CONFIG = {
    "security": {
        "api_token": {"default": "secret_token_123", "type": "str", "is_password": True},
        "bypass_code": {"default": "non_secret_pass", "type": "str", "is_password": False}
    },
    "@profiles": {
        "_template": {
            "auth": {
                "custom_key": {"default": "prof_secret_456", "type": "str", "is_password": True},
                "passenger_name": {"default": "John Doe", "type": "str", "is_password": False}
            }
        },
        "01": {
            "auth": {
                "custom_key": "prof_secret_456",
                "passenger_name": "John Doe"
            }
        }
    }
}
'''
        with open(pwd_schema_path, "w", encoding="utf-8") as f:
            f.write(schema_code)

        pwd_ctx = create_app_context(
            config_file=pwd_config_path,
            key_file=self.key_path,
            schema_file=pwd_schema_path
        )

        from asiscfg.core import save_config
        save_config(pwd_ctx, {
            "security": {
                "api_token": "secret_token_123",
                "bypass_code": "non_secret_pass"
            },
            "@profiles": {
                "01": {
                    "auth": {
                        "custom_key": "prof_secret_456",
                        "passenger_name": "John Doe"
                    }
                }
            }
        })

        app = ConfigApp(
            context=pwd_ctx,
            dev_mode=True
        )
        if hasattr(app, "login_frame") and app.login_frame:
            app.login_frame.destroy()
        app._build_main_ui()

        try:
            # 1. api_token tiene is_password: True -> show='*' y texto en claro en widget
            api_entry = app.business_entries["security"]["api_token"]
            self.assertEqual(api_entry.cget("show"), "*")
            self.assertEqual(api_entry.get(), "secret_token_123")

            # 2. bypass_code contiene 'pass' pero is_password: False -> show=''
            bypass_entry = app.business_entries["security"]["bypass_code"]
            self.assertEqual(bypass_entry.cget("show"), "")
            self.assertEqual(bypass_entry.get(), "non_secret_pass")

            # 3. custom_key en perfil tiene is_password: True -> show='*' y texto en claro
            custom_entry = app.profile_entries["auth"]["custom_key"]
            self.assertEqual(custom_entry.cget("show"), "*")
            self.assertEqual(custom_entry.get(), "prof_secret_456")

            # 4. passenger_name en perfil contiene 'pass' pero is_password: False -> show=''
            passenger_entry = app.profile_entries["auth"]["passenger_name"]
            self.assertEqual(passenger_entry.cget("show"), "")
            self.assertEqual(passenger_entry.get(), "John Doe")

            # 5. has_unsaved_changes no debe dar falso positivo con campos is_password=True
            self.assertFalse(app.has_unsaved_changes())

            # 6. Al modificar un campo is_password=True, has_unsaved_changes debe retornar True
            api_entry.delete(0, "end")
            api_entry.insert(0, "new_secret_789")
            self.assertTrue(app.has_unsaved_changes())

            # 7. Al restaurar el valor original, has_unsaved_changes debe volver a False
            api_entry.delete(0, "end")
            api_entry.insert(0, "secret_token_123")
            self.assertFalse(app.has_unsaved_changes())

            # 8. Al modificar un campo de perfil is_password=True, has_unsaved_changes debe retornar True
            custom_entry.delete(0, "end")
            custom_entry.insert(0, "prof_changed_999")
            self.assertTrue(app.has_unsaved_changes())

            # Restaurar valor
            custom_entry.delete(0, "end")
            custom_entry.insert(0, "prof_secret_456")
            self.assertFalse(app.has_unsaved_changes())

        finally:
            app.destroy()

    def test_add_profile_then_switch_profile_no_error(self):
        """Verifica que tras agregar un nuevo perfil se pueda alternar entre perfiles sin error de Tkinter."""
        app = ConfigApp(
            context=self.context,
            dev_mode=True
        )
        if hasattr(app, "login_frame") and app.login_frame:
            app.login_frame.destroy()
        app._build_main_ui()

        try:
            self.assertEqual(app.active_profile, "01")
            
            # Simular adición de un nuevo perfil '02'
            new_prof = {
                "conexiones": {
                    "port": 1500,
                    "host": "192.168.1.99"
                }
            }
            app.working_config[SECTION_PROFILES]["02"] = new_prof
            app.active_profile = "02"
            
            display_list = app._get_profile_display_list()
            app.combo_profile.configure(values=display_list)
            app.combo_profile.set("02")
            app.populate_tabs()
            
            self.assertEqual(app.active_profile, "02")
            self.assertEqual(app.profile_entries["conexiones"]["port"].get(), "1500")
            
            # Cambiar de vuelta al perfil '01' vía dropdown callback
            app._on_profile_selected("01")
            self.assertEqual(app.active_profile, "01")
            self.assertEqual(app.profile_entries["conexiones"]["port"].get(), "1433")
            self.assertEqual(app.profile_entries["conexiones"]["host"].get(), "192.168.1.50")
            
            # Cambiar nuevamente al perfil '02' vía dropdown callback
            app._on_profile_selected("02")
            self.assertEqual(app.active_profile, "02")
            self.assertEqual(app.profile_entries["conexiones"]["port"].get(), "1500")
            self.assertEqual(app.profile_entries["conexiones"]["host"].get(), "192.168.1.99")
            
        finally:
            app.destroy()

    def test_multiple_profiles_has_unsaved_changes_no_false_positive(self):
        """Verifica que al abrir una configuración con múltiples perfiles no se reporten falsos cambios sin guardar en los perfiles inactivos."""
        multi_schema_path = os.path.join(self.test_dir, "test_multi_pwd_schema.py")
        multi_config_path = os.path.join(self.test_dir, "test_multi_pwd_cfg.enc")
        schema_code = '''
DEFAULT_CONFIG = {
    "app": {"name": {"default": "TestApp"}},
    "security": {
        "api_token": {"default": "token_123", "type": "str", "is_password": True},
        "bypass_code": {"default": "bypass_123", "type": "str", "is_password": False}
    },
    "@profiles": {
        "_template": {
            "auth": {
                "custom_key": {"default": "pass_prof_1", "type": "str", "is_password": True},
                "passenger_name": {"default": "User 1", "type": "str", "is_password": False}
            },
            "conexiones": {
                "port": {"default": 1433, "type": "int"},
                "host": {"default": "127.0.0.1", "type": "str"}
            }
        },
        "01": {
            "auth": {
                "custom_key": "pass_prof_1",
                "passenger_name": "User 1"
            },
            "conexiones": {
                "port": 1433,
                "host": "192.168.1.50"
            }
        },
        "02": {
            "auth": {
                "custom_key": "pass_prof_2",
                "passenger_name": "User 2"
            },
            "conexiones": {
                "port": 1500,
                "host": "192.168.1.99"
            }
        }
    }
}
'''
        with open(multi_schema_path, "w", encoding="utf-8") as f:
            f.write(schema_code)

        multi_ctx = create_app_context(
            config_file=multi_config_path,
            key_file=self.key_path,
            schema_file=multi_schema_path,
            format_mode="plain"
        )

        from asiscfg.core import save_config
        multi_prof_cfg = {
            "app": {"name": "TestApp"},
            "security": {
                "api_token": "token_123",
                "bypass_code": "bypass_123"
            },
            SECTION_PROFILES: {
                "01": {
                    "auth": {
                        "custom_key": "pass_prof_1",
                        "passenger_name": "User 1"
                    },
                    "conexiones": {
                        "port": 1433,
                        "host": "192.168.1.50"
                    }
                },
                "02": {
                    "auth": {
                        "custom_key": "pass_prof_2",
                        "passenger_name": "User 2"
                    },
                    "conexiones": {
                        "port": 1500,
                        "host": "192.168.1.99"
                    }
                }
            }
        }
        save_config(
            multi_ctx,
            multi_prof_cfg,
            format_mode="plain"
        )

        app = ConfigApp(
            context=multi_ctx,
            dev_mode=True
        )
        if hasattr(app, "login_frame") and app.login_frame:
            app.login_frame.destroy()
        app._build_main_ui()

        try:
            # Al iniciar con perfil 01 activo, perfil 02 (inactivo) no debe dar falso positivo
            self.assertEqual(app.has_unsaved_changes(), [])

            # Al cambiar de perfil al 02 sin editar nada, tampoco debe haber cambios pendientes
            app._on_profile_selected("02")
            self.assertEqual(app.has_unsaved_changes(), [])

            # Al cambiar de vuelta al 01 sin editar nada, tampoco debe haber cambios pendientes
            app._on_profile_selected("01")
            self.assertEqual(app.has_unsaved_changes(), [])

            # Modificar la clave del perfil 01
            app.profile_entries["auth"]["custom_key"].delete(0, "end")
            app.profile_entries["auth"]["custom_key"].insert(0, "new_pass_1")
            changes = app.has_unsaved_changes()
            self.assertEqual(len(changes), 1)
            self.assertIn("@profiles.01.auth.custom_key", changes[0])

            # Restaurar la clave del perfil 01
            app.profile_entries["auth"]["custom_key"].delete(0, "end")
            app.profile_entries["auth"]["custom_key"].insert(0, "pass_prof_1")
            self.assertEqual(app.has_unsaved_changes(), [])

        finally:
            app.destroy()

    def test_profile_combo_alphabetical_sorting_and_update(self):
        """Valida que la lista del combo de perfiles se ordene alfabéticamente y se actualice."""
        app = ConfigApp(
            context=self.context,
            dev_mode=True
        )
        if hasattr(app, "login_frame") and app.login_frame:
            app.login_frame.destroy()
        app._build_main_ui()

        try:
            # Inyectar perfiles desordenados en working_config
            app.working_config[SECTION_PROFILES] = {
                "Z0": {"info": {"nombre": "Zulu Corp"}, "conexiones": {"port": 1433, "host": "10.0.0.1"}},
                "02": {"info": {"nombre": "Beta S.A."}, "conexiones": {"port": 1433, "host": "10.0.0.2"}},
                "01": {"info": {"nombre": "Alpha C.A."}, "conexiones": {"port": 1433, "host": "10.0.0.3"}}
            }
            display_list = app._get_profile_display_list()
            expected = ["01 - Alpha C.A.", "02 - Beta S.A.", "Z0 - Zulu Corp"]
            self.assertEqual(display_list, expected)

            # Probar _update_profile_combo
            app.active_profile = "02"
            app._update_profile_combo()
            self.assertEqual(app.combo_profile.cget("values"), expected)
            self.assertEqual(app.combo_profile.get(), "02 - Beta S.A.")

            # Cambiar nombre y actualizar
            app.working_config[SECTION_PROFILES]["02"]["info"]["nombre"] = "Bravo S.A."
            app._update_profile_combo(target_profile="02")
            new_expected = ["01 - Alpha C.A.", "02 - Bravo S.A.", "Z0 - Zulu Corp"]
            self.assertEqual(app.combo_profile.cget("values"), new_expected)
            self.assertEqual(app.combo_profile.get(), "02 - Bravo S.A.")

        finally:
            app.destroy()


if __name__ == "__main__":
    unittest.main()



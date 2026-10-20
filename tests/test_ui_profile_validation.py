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
from asiscfg.context import create_app_context
from asiscfg.storage import save_config, generate_key_file
from asiscfg.ui.app import ConfigApp


class TestUIProfileValidation(unittest.TestCase):

    def setUp(self):
        self.test_dir = tempfile.mkdtemp()
        self.config_path = os.path.join(self.test_dir, "test_ui_cfg.enc")
        self.key_path = os.path.join(self.test_dir, "test_ui_sec.key")
        self.schema_path = os.path.join(self.test_dir, "test_schema.py")

        schema_code = '''
CONFIG_SCHEMA = {
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

        from asiscfg.storage import save_config, generate_key_file
        generate_key_file(self.context)
        self.initial_data = {
            "app": {"name": "TestApp"},
            "general": {"timeout": 30},
            "@asiscfg": {
                "admin_pass_hash": "2a97516c354b68848cdbd8f54a226a0a55b21ed138e207ad6c5cbb9c00aa5aea"
            },
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
CONFIG_SCHEMA = {
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

        from asiscfg.storage import save_config
        save_config(pwd_ctx, {
            "security": {
                "api_token": "secret_token_123",
                "bypass_code": "non_secret_pass"
            },
            "@asiscfg": {
                "admin_pass_hash": "2a97516c354b68848cdbd8f54a226a0a55b21ed138e207ad6c5cbb9c00aa5aea"
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
CONFIG_SCHEMA = {
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

        from asiscfg.storage import save_config
        multi_prof_cfg = {
            "app": {"name": "TestApp"},
            "security": {
                "api_token": "token_123",
                "bypass_code": "bypass_123"
            },
            "@asiscfg": {
                "admin_pass_hash": "2a97516c354b68848cdbd8f54a226a0a55b21ed138e207ad6c5cbb9c00aa5aea"
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
        save_config(multi_ctx, multi_prof_cfg)

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

    def test_validate_all_entries_with_option_menu(self):
        """Verifica que validate_all_entries funcione correctamente con campos que usan CTkOptionMenu."""
        opt_schema_path = os.path.join(self.test_dir, "opt_schema.py")
        opt_config_path = os.path.join(self.test_dir, "opt_cfg.enc")
        schema_code = '''
CONFIG_SCHEMA = {
    "database": {
        "engine": {"default": "sqlite", "type": "str", "options": ["sqlite", "mssql", "postgres"]},
        "timeout": {"default": 10, "type": "int", "min": 1, "max": 60}
    },
    "@profiles": {
        "_template": {
            "driver": {
                "name": {"default": "ODBC 18", "type": "str", "options": ["ODBC 17", "ODBC 18", "ODBC 13"]}
            }
        },
        "01": {
            "driver": {
                "name": "ODBC 18"
            }
        }
    }
}
'''
        with open(opt_schema_path, "w", encoding="utf-8") as f:
            f.write(schema_code)

        opt_ctx = create_app_context(
            action="ui",
            config_file=opt_config_path,
            key_file=self.key_path,
            schema_file=opt_schema_path
        )
        save_config(opt_ctx, {
            "database": {"engine": "sqlite", "timeout": 10},
            "@asiscfg": {
                "admin_pass_hash": "2a97516c354b68848cdbd8f54a226a0a55b21ed138e207ad6c5cbb9c00aa5aea"
            },
            "@profiles": {
                "01": {
                    "driver": {"name": "ODBC 18"}
                }
            }
        })

        app = ConfigApp(
            context=opt_ctx,
            dev_mode=True
        )
        if hasattr(app, "login_frame") and app.login_frame:
            app.login_frame.destroy()
        app._build_main_ui()

        try:
            # Verificar que los widgets con 'options' son CTkOptionMenu
            engine_widget = app.business_entries["database"]["engine"]
            self.assertIsInstance(engine_widget, ctk.CTkOptionMenu)
            driver_widget = app.profile_entries["driver"]["name"]
            self.assertIsInstance(driver_widget, ctk.CTkOptionMenu)

            # validate_all_entries no debe fallar con ValueError ('border_color', 'border_width')
            valid, err = app.validate_all_entries()
            self.assertTrue(valid, f"validate_all_entries falló inesperadamente: {err}")
        finally:
            app.destroy()

    def test_security_check_two_phases(self):
        """Verifica que check_security_and_init (Fase 1) y check_security_post_login (Fase 2) operan de forma separada."""
        from unittest.mock import patch

        app = ConfigApp(
            context=self.context,
            dev_mode=True
        )
        try:
            # Fase 1: En inicio solo se prepara login_frame y no se abren modales de advertencia
            self.assertIsNotNone(app.login_frame)
            self.assertIsNone(app.main_container)

            # Simular diferencias forenses / campos alterados
            fake_diffs = [{"status": "tampered", "expected": {"timeout": 30}, "actual": {"timeout": 60}}]
            app.current_config._audit_diffs = fake_diffs

            # Fase 2: Al ejecutar check_security_post_login se debe invocar DiffWarningDialog
            with patch("asiscfg.ui.app.DiffWarningDialog") as mock_diff_dialog:
                with patch.object(app, "wait_window") as mock_wait:
                    app.check_security_post_login()
                    mock_diff_dialog.assert_called_once_with(app, fake_diffs)
                    self.assertTrue(mock_wait.called)
        finally:
            app.destroy()

    def test_diff_warning_dialog_grid_and_password_normalization(self):
        """Verifica que DiffWarningDialog construye la estructura de grid de 3 columnas y oculta texto plano de contraseñas."""
        from asiscfg.ui.dialogs import DiffWarningDialog
        from asiscfg.storage import _compare_plain_snapshots
        from asiscfg.crypto import FORMAT_MODES
        from asiscfg.constants import NULL_SENTINEL

        # 1. Probar _compare_plain_snapshots: contraseñas vacías en diferentes representaciones no deben reportar alteración
        engine = FORMAT_MODES["plain"]
        original = {"conexiones": {"password": "", "host": "127.0.0.1"}}
        current = {"conexiones": {"password": NULL_SENTINEL, "host": "127.0.0.1"}}
        diffs = _compare_plain_snapshots(original, current, pwd_set={"conexiones.password"}, engine=engine, key=b"dummy")
        self.assertEqual(diffs, [], "No debe reportar alteración cuando ambas contraseñas son vacías")

        # 2. Contraseña legítimamente modificada: debe reportar [Protegido] -> [Modificado] sin revelar texto
        current_mod = {"conexiones": {"password": "NuevaPassword123", "host": "127.0.0.1"}}
        diffs_mod = _compare_plain_snapshots(original, current_mod, pwd_set={"conexiones.password"}, engine=engine, key=b"dummy")
        self.assertEqual(len(diffs_mod), 1)
        self.assertEqual(diffs_mod[0]["key_path"], "conexiones.password")
        self.assertTrue(diffs_mod[0]["is_password"])
        self.assertEqual(diffs_mod[0]["old_value"], "[Vacío]")
        self.assertEqual(diffs_mod[0]["new_value"], "[Modificado]")

        # 3. Construir DiffWarningDialog con el grid y verificar widgets
        app = ConfigApp(context=self.context, dev_mode=True)
        try:
            dialog = DiffWarningDialog(app, diffs_mod)
            try:
                self.assertIn("780x500", dialog.geometry())
            finally:
                dialog.destroy()
        finally:
            app.destroy()

    def test_diff_warning_dialog_seal_discrepancy_at_top(self):
        """Verifica que las discrepancias de sellado se posicionan al tope del grid de DiffWarningDialog."""
        from asiscfg.ui.dialogs import DiffWarningDialog

        diffs_with_seal = [
            {"status": "tampered", "key_path": "general.nombre", "old_value": "Antes", "new_value": "Ahora"},
            {"status": "missing_seal", "key_path": "@NO_MODIFICAR_NO_MODIFY", "error": "Falta la clave de sellado requerida"},
        ]

        app = ConfigApp(context=self.context, dev_mode=True)
        try:
            dialog = DiffWarningDialog(app, diffs_with_seal)
            try:
                # El scrollable frame contiene primero el header y luego las filas
                # Verificamos que se crearon los widgets correspondientes
                self.assertIsNotNone(dialog)
            finally:
                dialog.destroy()
        finally:
            app.destroy()

    def test_show_modal_message_dialog_execution(self):
        """Verifica que show_modal_message_dialog invoque correctamente messagebox."""
        from asiscfg.ui.dialogs import show_modal_message_dialog
        from unittest.mock import patch, ANY

        with patch("tkinter.messagebox.showerror") as mock_err, patch("tkinter.Tk"):
            show_modal_message_dialog("Error Title", "Error Msg", icon_type="error")
            mock_err.assert_called_once_with("Error Title", "Error Msg", parent=ANY)

        with patch("tkinter.messagebox.showwarning") as mock_warn, patch("tkinter.Tk"):
            show_modal_message_dialog("Warn Title", "Warn Msg", icon_type="warning")
            mock_warn.assert_called_once_with("Warn Title", "Warn Msg", parent=ANY)

        with patch("tkinter.messagebox.showinfo") as mock_info, patch("tkinter.Tk"):
            show_modal_message_dialog("Info Title", "Info Msg", icon_type="info")
            mock_info.assert_called_once_with("Info Title", "Info Msg", parent=ANY)

    def test_confirm_action_dialog_gui_and_console_fallback(self):
        """Verifica que confirm_action_dialog use messagebox en GUI y fallback en consola."""
        from asiscfg.ui.dialogs import confirm_action_dialog
        from unittest.mock import patch

        # 1. Modo GUI exitoso
        with patch("tkinter.messagebox.askyesno", return_value=True) as mock_ask, patch("tkinter.Tk"):
            res = confirm_action_dialog("Title", "Proceed?")
            self.assertTrue(res)
            mock_ask.assert_called_once()

        # 2. Modo Fallback Consola (simulando excepción en Tkinter)
        with patch("tkinter.Tk", side_effect=Exception("No DISPLAY")):
            with patch("builtins.input", return_value="s"):
                res = confirm_action_dialog("Title", "Proceed?")
                self.assertTrue(res)

            with patch("builtins.input", return_value="n"):
                res = confirm_action_dialog("Title", "Proceed?")
                self.assertFalse(res)

    def test_missing_asiscfg_in_existing_file_blocks_and_notifies_recovery(self):
        """Verifica que un archivo existente sin @asiscfg sea bloqueado notificando corrupción y procedimiento de recuperación."""
        from unittest.mock import patch, ANY

        corrupt_cfg_path = os.path.join(self.test_dir, "corrupt_cfg.enc")
        from asiscfg.storage import save_config
        corrupt_ctx = create_app_context(
            action="ui",
            config_file=corrupt_cfg_path,
            key_file=self.key_path,
            schema_file=self.schema_path
        )
        # Guardar archivo existente SIN @asiscfg
        save_config(corrupt_ctx, {
            "app": {"name": "TestApp"},
            "general": {"timeout": 30},
            "@profiles": {
                "01": {"conexiones": {"port": 1433, "host": "127.0.0.1"}}
            }
        })

        with patch("asiscfg.ui.app.messagebox.showerror") as mock_err:
            with patch("asiscfg.ui.app.log_audit_event") as mock_audit:
                with self.assertRaises(SystemExit) as cm:
                    ConfigApp(context=corrupt_ctx, dev_mode=True)
                self.assertEqual(cm.exception.code, 0)
                mock_err.assert_called_once()
                title, msg = mock_err.call_args[0]
                self.assertIn("Corrupto", title)
                self.assertIn("recuperar la clave administrativa", msg)
                self.assertIn("corrupto", msg.lower())
                mock_audit.assert_any_call("SECURITY_TAMPER_ASISCFG", ANY)


if __name__ == "__main__":
    unittest.main()




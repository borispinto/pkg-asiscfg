# -*- coding: utf-8 -*-
# SPDX-FileCopyrightText: 2026 Asisnet Computacion, CA <proyectos@asisnet.net>
# SPDX-License-Identifier: MIT
# Autor: Boris Pinto <borispinto@asisnet.net>
# File: asiscfg/ui/app.py

"""
Aplicación Principal GUI de Configuración (ConfigApp) en CustomTkinter.
"""

import sys
import os
import hmac
import logging
from datetime import datetime
import json
import tkinter as tk
from tkinter import messagebox, filedialog
from typing import Tuple, Optional, Any, List
import customtkinter as ctk

from asiscfg.constants import (
    FORMAT_MODES,
    SECTION_PROFILES,
    SECURITY_SECTIONS,
    ENC_PREFIX,
    NULL_SENTINEL,
    is_security_section,
    is_schema_directive,
    is_business_section
)
from asiscfg.crypto import get_format_engine

from asiscfg.models import ConfigDict, AppConfigContext, create_app_context
from asiscfg.security import check_admin_password, set_admin_password, is_admin, log_audit_event
from asiscfg.core import load_config, save_config, verify_key_integrity
from asiscfg.ui.utils import apply_window_icon, PALETTE, CTkToolTip, get_i18n_instance, t18n
from asiscfg.ui.dialogs import (
    ChangeAdminPasswordDialog,
    PlaintextPasswordsWarningDialog,
    AddProfileDialog,
    RenameProfileDialog,
    AboutDialog,
    CurrentConfigDialog,
    SchemaModelDialog,
    ExplanatorySchemaDialog,
    KeyRecoveryDialog
)


class ConfigApp(ctk.CTk):
    """Aplicación GUI de Mantenimiento de Configuración Cifrada con Pestañas Dinámicas y Soporte Opcional Multiperfil."""
    def __init__(
        self,
        context: AppConfigContext,
        i18n_path: Optional[str] = None,
        dev_mode: bool = False,
        allow_app_edit: bool = False,
        theme: str = "dark"
    ):
        self.context = context
        self.config_file = self.context.config_file_path
        self.key_file = self.context.key_file_path
        self.schema_file = self.context.schema_file_path
        self.i18n_path = i18n_path
        self.dev_mode = dev_mode
        self.allow_app_edit = allow_app_edit
        self.theme = theme.lower().strip() if (theme and isinstance(theme, str)) else "dark"

        ctk.set_appearance_mode(self.theme)

        if self.i18n_path and os.path.exists(self.i18n_path):
            get_i18n_instance().set_external_languages_dir(self.i18n_path)

        self.default_config = self.context.default_config
        self.validation_rules = self.context.validation_rules
        super().__init__()

        apply_window_icon(self)

        # Registrar diccionarios por defecto (Capa 0) y obtener instancia de i18n
        i18n_inst = get_i18n_instance()
        i18n_inst.register_defaults(self.get_default_translations_dict())

        self.current_config = None
        self.working_config = None
        self.active_profile = None

        self.geometry("860x720")
        self.minsize(760, 560)

        self.login_attempts = 0
        self.max_login_attempts = 3
        self.entries = {}
        self.business_entries = {}
        self.profile_entries = {}
        self.initial_field_values = {}
        self.field_label_widgets = {}
        self.is_authenticated = False
        self.login_frame = None
        self.main_container = None
        self.master_tabview = None
        self.tabview_business = None
        self.tabview_profile = None
        self.combo_profile = None
        self.combo_format = None
        self.lbl_format_origin = None
        self.lbl_target_path = None
        self.status_label = None

        self.protocol("WM_DELETE_WINDOW", self.on_close)

        self.check_security_and_init()

    def _create_working_config(self, config_source: Any) -> dict:
        """Crea una copia de trabajo de la configuración con todos los valores protegidos descifrados en memoria."""
        raw_dict = json.loads(json.dumps(dict(config_source)))

        def _decrypt_tree(node):
            if isinstance(node, dict):
                return {k: _decrypt_tree(v) for k, v in node.items()}
            elif isinstance(node, list):
                return [_decrypt_tree(elem) for elem in node]
            elif node == NULL_SENTINEL or node is None:
                return ""
            elif isinstance(node, str) and node.startswith(ENC_PREFIX):
                return self.current_config._decrypt_value(node)
            return node

        return _decrypt_tree(raw_dict)

    def check_security_and_init(self):
        log_audit_event("APP_START", t18n("asiscfg.app_start", "Inicio de ejecución de asiscfg."))

        # Capa 1: Verificación de Privilegios UAC en Windows
        if self.dev_mode:
            print(t18n("asiscfg.msg_dev_mode", "[INFO] Modo desarrollo activo (--dev). Validación de permisos UAC omitida."))
            log_audit_event("DEV_MODE", t18n("asiscfg.dev_mode", "Validación UAC omitida por parámetro --dev."))
        else:
            if not is_admin():
                log_audit_event("UAC_REJECTED", "Intento de inicio sin privilegios de Administrador del SO.")
                messagebox.showerror(
                    t18n("asiscfg.title_admin_required", "Privilegios Requeridos"),
                    t18n("asiscfg.msg_admin_required", "Esta herramienta requiere ejecutarse con privilegios elevados de Administrador del sistema operativo.\n\nPor favor, cierre la aplicación y ejecútela como Administrador."),
                    parent=self
                )
                self.destroy()
                sys.exit(0)
            else:
                self.dev_mode = True
                print(t18n("asiscfg.msg_uac_elevated", "[INFO] Proceso ejecutado con privilegios elevados de Administrador."))
                log_audit_event("UAC_ELEVATED", t18n("asiscfg.uac_elevated", "Proceso ejecutado con privilegios elevados de Administrador."))

        # Capa 2: Verificación de Integridad de la Clave Criptográfica (.key)
        key_status, key_detail = verify_key_integrity(self.context)
        if key_status in ("missing", "corrupted"):
            log_audit_event("KEY_INTEGRITY_FAILED", f"Fallo de integridad de clave ({key_status}): {key_detail}")
            recovery_dialog = KeyRecoveryDialog(self, status=key_status, detail=key_detail)
            self.wait_window(recovery_dialog)
            if recovery_dialog.action_result not in ("restored", "generated"):
                self.destroy()
                sys.exit(0)

        # Capa 3: Carga de Configuración
        if os.path.exists(self.config_file):
            self.current_config = load_config(
                context=self.context,
                default_config=self.default_config,
                validation_rules=self.validation_rules,
                edit_mode=True
            )
        else:
            self.current_config = ConfigDict(self.context, self.default_config)
            self.current_config.set_default_config(self.default_config)

        self.working_config = self._create_working_config(self.current_config)

        profiles_list = self.current_config.get_profiles()
        if profiles_list:
            self.active_profile = profiles_list[0]
        else:
            self.active_profile = None

        app_name = self.current_config.valor("app.name",default="Sistema")
        self.title(t18n("asiscfg.title", "Mantenimiento de Configuración - {app_name}", app_name=app_name))

        # Capa 4: Mostrar Vista de Login de Administrador
        self._build_login_ui()

    def _register_field_tracker(self, sec: str, key: str, initial_val: str, lbl_widget: Any, entry_widget: Any, is_profile: bool = False, profile_code: Optional[str] = None):
        """Registra un control y vincula listeners dinámicos para cambiar el color de la etiqueta si el valor difiere del original o por defecto ante fallas."""
        prof_code = profile_code or (self.active_profile if is_profile else "")
        field_id = (sec, key, prof_code) if (is_profile and prof_code) else (sec, key)
        
        # Comprobar si este campo tuvo falla de carga (texto plano no cifrado, vacío, faltante o error de descifrado)
        unenc_list = self.current_config.get_unencrypted_passwords()
        pwd_failures = self.current_config.get_password_failures() if hasattr(self.current_config, "get_password_failures") else []
        failed_paths = [u[0] if isinstance(u, (tuple, list)) else str(u) for u in unenc_list] + [f.get("field_path", "") for f in pwd_failures if isinstance(f, dict)]

        is_failed = False
        for u_path in failed_paths:
            u_clean = u_path.lstrip("@")
            if not is_profile:
                if u_clean == f"{sec}.{key}" or u_path == f"{sec}.{key}":
                    is_failed = True
                    break
            else:
                target_a = f"{SECTION_PROFILES}.{prof_code}.{sec}.{key}"
                target_b = f"profiles.{prof_code}.{sec}.{key}"
                target_c = f"{prof_code}.{sec}.{key}"
                if u_path in (target_a, target_b, target_c) or u_clean in (target_a, target_b, target_c) or u_clean.endswith(f".{prof_code}.{sec}.{key}"):
                    is_failed = True
                    break

        if is_failed:
            # Si el campo falló, la línea base de referencia es el valor por defecto del esquema.
            # Si el valor por defecto es vacío (""), la línea base se establece en NULL_SENTINEL.
            if not is_profile:
                def_v = self.default_config.get(sec, {}).get(key, "") if isinstance(self.default_config.get(sec), dict) else ""
            else:
                def_profs = self.default_config.get(SECTION_PROFILES, {})
                def_v = ""
                if isinstance(def_profs, dict) and def_profs:
                    if "_template" in def_profs and isinstance(def_profs["_template"], dict):
                        def_v = def_profs["_template"].get(sec, {}).get(key, "") if isinstance(def_profs["_template"].get(sec), dict) else ""
                    if not def_v and prof_code in def_profs and isinstance(def_profs[prof_code], dict):
                        def_v = def_profs[prof_code].get(sec, {}).get(key, "") if isinstance(def_profs[prof_code], dict) else ""
                    if not def_v:
                        first_k = list(def_profs.keys())[0]
                        def_v = def_profs[first_k].get(sec, {}).get(key, "") if isinstance(def_profs[first_k].get(sec), dict) else ""
            
            base_str = str(def_v if def_v is not None else "").strip()
            if base_str == "":
                base_str = NULL_SENTINEL
            self.initial_field_values[field_id] = base_str
        elif field_id not in self.initial_field_values:
            # Línea base normal: valor cargado desde disco
            sec_rules = self.get_profile_rules(sec) if is_profile else self.get_business_rules(sec)
            val_rule = sec_rules.get(key, {}) if isinstance(sec_rules, dict) else {}
            is_pwd = bool(isinstance(val_rule, dict) and val_rule.get("is_password") is True)
            if is_pwd:
                if not is_profile:
                    orig = self.current_config.valorpass(f"{sec}.{key}", default="")
                else:
                    orig = self.current_config.valorpass_profile(prof_code, f"{sec}.{key}", default="")
            else:
                if not is_profile:
                    orig = self.current_config.valor(f"{sec}.{key}", default="")
                else:
                    orig = self.current_config.valor_profile(prof_code, f"{sec}.{key}", default="")
            self.initial_field_values[field_id] = str(orig if orig is not None else "")
        
        self.field_label_widgets[(sec, key, "profile") if is_profile else (sec, key)] = lbl_widget

        def check_field_modified(*args):
            current_raw = str(entry_widget.get()) if hasattr(entry_widget, "get") else ""
            f_id = (sec, key, self.active_profile) if (is_profile and self.active_profile) else (sec, key)
            init_val = self.initial_field_values.get(f_id, "")
            if current_raw.strip() != init_val.strip():
                lbl_widget.configure(text_color=PALETTE["Warning"]["text_color"])
            else:
                lbl_widget.configure(text_color=PALETTE["KeyLabel"]["text_color"])

        # Verificación inicial del estado
        check_field_modified()

        if isinstance(entry_widget, ctk.CTkEntry):
            entry_widget.bind("<KeyRelease>", check_field_modified, add="+")
            entry_widget.bind("<FocusOut>", check_field_modified, add="+")
        elif isinstance(entry_widget, ctk.CTkOptionMenu):
            orig_cmd = entry_widget.cget("command")
            def wrapped_opt_cmd(choice):
                if callable(orig_cmd):
                    orig_cmd(choice)
                check_field_modified()
            entry_widget.configure(command=wrapped_opt_cmd)

    def _build_login_ui(self):
        """Construye la vista de autenticación dentro de la ventana principal."""
        self.login_frame = ctk.CTkFrame(self, corner_radius=15, fg_color=PALETTE["Card"]["fg_color"])
        self.login_frame.place(relx=0.5, rely=0.5, anchor="center", relwidth=0.55, relheight=0.5)

        lbl_icon = ctk.CTkLabel(
            self.login_frame,
            text="🔐",
            font=ctk.CTkFont(size=42)
        )
        lbl_icon.pack(pady=(25, 5))

        lbl_title = ctk.CTkLabel(
            self.login_frame,
            text=t18n("asiscfg.login_title", "Acceso Restringido - Configuración"),
            font=ctk.CTkFont(size=17, weight="bold"),
            text_color=PALETTE["Header"]["text_color"]
        )
        lbl_title.pack(pady=4)

        lbl_sub = ctk.CTkLabel(
            self.login_frame,
            text=t18n("asiscfg.login_subtitle", "Ingrese la Clave Maestra de Administración para ingresar:"),
            font=ctk.CTkFont(size=12),
            text_color=PALETTE["Subtext"]["text_color"]
        )
        lbl_sub.pack(pady=(0, 15))

        self.entry_pass = ctk.CTkEntry(
            self.login_frame,
            show="*",
            width=280,
            height=38,
            placeholder_text=t18n("asiscfg.ph_master_pass", "Clave Maestra...")
        )
        self.entry_pass.pack(pady=5)
        self.entry_pass.focus_set()
        self.after(100, lambda: self.entry_pass.focus_set() if self.entry_pass.winfo_exists() else None)
        self.entry_pass.bind("<Return>", lambda e: self.verify_login())

        self.lbl_login_error = ctk.CTkLabel(
            self.login_frame,
            text="",
            font=ctk.CTkFont(size=12),
            text_color=PALETTE["Error"]["text_color"]
        )
        self.lbl_login_error.pack(pady=5)

        btn_login = ctk.CTkButton(
            self.login_frame,
            text=t18n("asiscfg.btn_login", "Ingresar"),
            font=ctk.CTkFont(size=14, weight="bold"),
            fg_color=PALETTE["MainButton"]["fg_color"],
            hover_color=PALETTE["MainButton"]["hover_color"],
            text_color=PALETTE["MainButton"]["text_color"],
            width=140,
            height=36,
            command=self.verify_login
        )
        btn_login.pack(pady=10)
        CTkToolTip(btn_login, t18n("asiscfg.tip_login", "Verificar clave maestra e ingresar al sistema"))

    def verify_login(self):
        pwd = self.entry_pass.get().strip()
        if check_admin_password(pwd, self.current_config):
            log_audit_event("LOGIN_SUCCESS", "Autenticación de administración exitosa.")
            self.lbl_login_error.configure(
                text=t18n("asiscfg.login_loading", "⏳ Cargando configuración..."),
                text_color=PALETTE["Success"]["text_color"]
            )
            self.update_idletasks()

            # Si el archivo de configuración no existe en disco, solicitar confirmación tras superar UAC y Login
            if not os.path.exists(self.config_file):
                title = t18n("asiscfg.title_confirm_create_config", "Crear Archivo de Configuración")
                msg = t18n("asiscfg.msg_confirm_create_config",
                    "El archivo de configuración no existe en la ruta:\n\n{path}\n\n¿Desea crearlo ahora con los valores predeterminados?",
                    path=self.config_file
                )
                if not messagebox.askyesno(title, msg, parent=self):
                    self.destroy()
                    sys.exit(0)

                # Persistir la configuración inicial en disco y recargar en modo edición
                save_config(
                    self.context,
                    self.working_config,
                    validation_rules=self.validation_rules,
                    default_config=self.default_config,
                    format_mode=self.context.format_mode
                )
                self.current_config = load_config(
                    self.context,
                    default_config=self.default_config,
                    validation_rules=self.validation_rules,
                    edit_mode=True
                )
                self.working_config = self._create_working_config(self.current_config)

                profiles_list = self.current_config.get_profiles()
                if profiles_list:
                    self.active_profile = profiles_list[0]
                else:
                    self.active_profile = None

                app_name = self.current_config.valor("app.name",default="Sistema")
                self.title(t18n("asiscfg.title", "Mantenimiento de Configuración - {app_name}", app_name=app_name))

            # Advertencia inicial si se detectaron parámetros protegidos en texto claro
            unencrypted_list = self.current_config.get_unencrypted_passwords()
            if unencrypted_list:
                log_audit_event("PLAINTEXT_PASSWORDS_DETECTED", f"Detectados {len(unencrypted_list)} parámetros con contraseñas en texto claro.")
                warn_dialog = PlaintextPasswordsWarningDialog(self, unencrypted_list)
                self.wait_window(warn_dialog)

            self._build_main_ui()
            if self.login_frame:
                self.login_frame.destroy()
                self.login_frame = None
            self.main_container.pack(fill="both", expand=True)
            self.update_idletasks()
        else:
            self.login_attempts += 1
            log_audit_event("LOGIN_FAILED", f"Intento fallido #{self.login_attempts}.")
            if self.login_attempts >= self.max_login_attempts:
                log_audit_event("LOGIN_BLOCKED", "Límite de intentos superado. Acceso bloqueado.")
                self.destroy()
                sys.exit(0)
            else:
                remaining = self.max_login_attempts - self.login_attempts
                self.lbl_login_error.configure(
                    text=t18n("asiscfg.err_wrong_pass",
                        "❌ Clave incorrecta. Intentos restantes: {remaining}",
                        remaining=remaining
                    ),
                    text_color=PALETTE["Error"]["text_color"]
                )

    def _get_profile_display_list(self) -> list:
        profiles_dict = self.working_config.get(SECTION_PROFILES, {})
        display_list = []
        if isinstance(profiles_dict, dict):
            for code, cdict in profiles_dict.items():
                if is_schema_directive(code):
                    continue
                info = cdict.get("info", {}) if isinstance(cdict, dict) else {}
                desc = ""
                if isinstance(info, dict) and info:
                    first_val = str(list(info.values())[0]).strip()
                    if first_val:
                        desc = first_val
                if desc and desc != code:
                    display_list.append(f"{code} - {desc}")
                else:
                    display_list.append(code)
        return display_list


    def _build_menu_bar(self):
        """Construye la barra de menú superior nativa de la aplicación."""
        self.option_add("*tearOff", False)
        menubar = tk.Menu(self)

        # Menú Archivo
        file_menu = tk.Menu(menubar, tearoff=0)
        file_menu.add_command(
            label=t18n("asiscfg.menu_change_pass", "🔑 Cambiar Clave Administrador"),
            command=self.change_admin_password
        )
        file_menu.add_command(
            label=t18n("asiscfg.menu_import", "📥 Importar Configuración..."),
            command=self.import_backup
        )
        file_menu.add_command(
            label=t18n("asiscfg.menu_export", "📤 Exportar Configuración..."),
            command=self.export_backup
        )
        file_menu.add_command(
            label=t18n("asiscfg.menu_export_schema", "📄 Exportar Esquema (config_schema.py)..."),
            command=self.export_schema_file
        )


        if self.dev_mode:
            file_menu.add_separator()
            file_menu.add_command(
                label=t18n("asiscfg.menu_current_config", "🛠️ Configuración Actual..."),
                command=self.show_current_config_dialog
            )

        file_menu.add_separator()
        file_menu.add_command(
            label=t18n("asiscfg.menu_exit", "❌ Salir"),
            command=self.on_close
        )
        menubar.add_cascade(label=t18n("asiscfg.menu_file", "Archivo"), menu=file_menu)

        # Menú Ayuda
        help_menu = tk.Menu(menubar, tearoff=0)
        help_menu.add_command(
            label=t18n("asiscfg.menu_schema_template", "📋 Plantilla..."),
            command=self.show_schema_template_dialog
        )
        help_menu.add_command(
            label=t18n("asiscfg.menu_explanatory_schema", "💡 Esquema Explicativo..."),
            command=self.show_explanatory_schema_dialog
        )
        help_menu.add_separator()
        help_menu.add_command(
            label=t18n("asiscfg.menu_about", "ℹ️ Acerca de..."),
            command=self.show_about_dialog
        )
        menubar.add_cascade(label=t18n("asiscfg.menu_help", "Ayuda"), menu=help_menu)

        self.config(menu=menubar)

    def show_current_config_dialog(self):
        """Muestra el diálogo modal con el diccionario de configuración actual (Modo Dev)."""
        self.flush_current_entries()
        dialog = CurrentConfigDialog(self, config_data=self.working_config, validation_rules=self.validation_rules)
        self.wait_window(dialog)

    def show_schema_template_dialog(self):
        """Muestra el diálogo modal con la plantilla de código del esquema de configuración."""
        dialog = SchemaModelDialog(self)
        self.wait_window(dialog)

    def show_schema_model_dialog(self):
        """Alias de compatibilidad para show_schema_template_dialog."""
        self.show_schema_template_dialog()

    def show_explanatory_schema_dialog(self):
        """Muestra el diálogo modal con el esquema explicativo de arquitectura y etiquetas."""
        dialog = ExplanatorySchemaDialog(self)
        self.wait_window(dialog)

    def show_about_dialog(self):
        """Muestra el diálogo modal Acerca De."""
        app_name = self.current_config.valor("app.name",default="Sistema")
        dialog = AboutDialog(self, app_name=app_name)
        self.wait_window(dialog)

    def _build_main_ui(self):
        """Construye la vista principal de mantenimiento dentro de self.main_container."""
        self.is_authenticated = True
        if self.main_container:
            self.main_container.destroy()

        self._build_menu_bar()

        self.main_container = ctk.CTkFrame(self, fg_color="transparent")

        # Frame del Encabezado
        self.header_frame = ctk.CTkFrame(self.main_container, corner_radius=10, fg_color=PALETTE["Card"]["fg_color"])
        self.header_frame.pack(fill="x", padx=15, pady=(6, 4))

        app_name = self.current_config.valor("app.name",default="Sistema")
        title_text = t18n("asiscfg.header_title_app", "Mantenimiento de Configuración ({app_name})", app_name=app_name)

        self.title_label = ctk.CTkLabel(
            self.header_frame,
            text=title_text,
            font=ctk.CTkFont(size=16, weight="bold"),
            text_color=PALETTE["Header"]["text_color"]
        )
        self.title_label.pack(pady=(6, 1))

        # Indicador de Origen de Lectura
        self.lbl_format_origin = ctk.CTkLabel(
            self.header_frame,
            text="",
            font=ctk.CTkFont(size=11, weight="bold")
        )
        self.lbl_format_origin.pack(pady=(0, 1))

        # Indicador de Ubicación Física del Archivo Destino
        self.lbl_target_path = ctk.CTkLabel(
            self.header_frame,
            text="",
            font=ctk.CTkFont(size=11),
            text_color=PALETTE["Subtext"]["text_color"]
        )
        self.lbl_target_path.pack(pady=(0, 6))
        self._update_format_indicator()

        has_profs = SECTION_PROFILES in self.working_config and isinstance(self.working_config[SECTION_PROFILES], dict) and len(self.working_config[SECTION_PROFILES]) > 0

        if has_profs:

            # Nivel 1: Pestañas Maestras (⚙️ Configuración General vs 👤 Configuración por Perfil)
            self.master_tabview = ctk.CTkTabview(self.main_container, corner_radius=10, command=self._on_tab_change)
            self.master_tabview.pack(fill="both", expand=True, padx=15, pady=4)

            tab_gen_title = t18n("asiscfg.tab_master_general", "⚙️ Configuración General")
            tab_prof_title = t18n("asiscfg.tab_master_profiles", "👤 Configuración por Perfil")

            tab_gen_master = self.master_tabview.add(tab_gen_title)
            tab_prof_master = self.master_tabview.add(tab_prof_title)

            # Nivel 2: Pestañas de Negocio
            self.tabview_business = ctk.CTkTabview(tab_gen_master, corner_radius=8, command=self._on_tab_change)
            self.tabview_business.pack(fill="both", expand=True, padx=5, pady=5)

            # Nivel 2: Pestañas por Perfil (con Barra de Selección)
            self.profile_bar_frame = ctk.CTkFrame(tab_prof_master, corner_radius=8, fg_color=PALETTE["Card"]["sub_fg_color"])
            self.profile_bar_frame.pack(fill="x", padx=5, pady=(5, 6))

            self.lbl_profile_sel = ctk.CTkLabel(
                self.profile_bar_frame,
                text=t18n("asiscfg.lbl_active_profile", "👤 Perfil Activo:"),
                font=ctk.CTkFont(size=13, weight="bold"),
                text_color=PALETTE["Header"]["text_color"]
            )
            self.lbl_profile_sel.pack(side="left", padx=(12, 6), pady=8)

            display_list = self._get_profile_display_list()
            self.combo_profile = ctk.CTkOptionMenu(
                self.profile_bar_frame,
                values=display_list if display_list else ["-"],
                command=self._on_profile_selected,
                width=240,
                height=32
            )
            self.combo_profile.pack(side="left", padx=6, pady=8)

            if self.active_profile:
                for item in display_list:
                    if item == self.active_profile or item.startswith(f"{self.active_profile} - "):
                        self.combo_profile.set(item)
                        break

            self.btn_add_prof = ctk.CTkButton(
                self.profile_bar_frame,
                text=t18n("asiscfg.btn_add_profile", "➕ Agregar"),
                font=ctk.CTkFont(size=12, weight="bold"),
                fg_color=PALETTE["SecondaryButton"]["fg_color"],
                hover_color=PALETTE["SecondaryButton"]["hover_color"],
                text_color=PALETTE["SecondaryButton"]["text_color"],
                width=85,
                height=32,
                command=self.add_profile
            )
            self.btn_add_prof.pack(side="left", padx=3, pady=8)
            CTkToolTip(self.btn_add_prof, t18n("asiscfg.tip_add_profile", "Registrar un nuevo perfil en el archivo de configuración"))

            self.btn_rename_prof = ctk.CTkButton(
                self.profile_bar_frame,
                text=t18n("asiscfg.btn_rename_profile", "✏️ Renombrar"),
                font=ctk.CTkFont(size=12, weight="bold"),
                fg_color=PALETTE["SecondaryButton"]["fg_color"],
                hover_color=PALETTE["SecondaryButton"]["hover_color"],
                text_color=PALETTE["SecondaryButton"]["text_color"],
                width=95,
                height=32,
                command=self.rename_profile
            )
            self.btn_rename_prof.pack(side="left", padx=3, pady=8)
            CTkToolTip(self.btn_rename_prof, t18n("asiscfg.tip_rename_profile", "Renombrar el código del perfil activo"))

            self.btn_del_prof = ctk.CTkButton(
                self.profile_bar_frame,
                text=t18n("asiscfg.btn_delete_profile", "🗑️ Eliminar"),
                font=ctk.CTkFont(size=12, weight="bold"),
                fg_color=PALETTE["DangerButton"]["fg_color"],
                hover_color=PALETTE["DangerButton"]["hover_color"],
                text_color=PALETTE["DangerButton"]["text_color"],
                width=85,
                height=32,
                command=self.delete_profile
            )
            self.btn_del_prof.pack(side="left", padx=3, pady=8)
            CTkToolTip(self.btn_del_prof, t18n("asiscfg.tip_delete_profile", "Eliminar el perfil activo de la configuración"))

            self.tabview_profile = ctk.CTkTabview(tab_prof_master, corner_radius=8, command=self._on_tab_change)
            self.tabview_profile.pack(fill="both", expand=True, padx=5, pady=5)
        else:
            self.master_tabview = None
            self.profile_bar_frame = None
            self.tabview_profile = None

            self.tabview_business = ctk.CTkTabview(self.main_container, corner_radius=10, command=self._on_tab_change)
            self.tabview_business.pack(fill="both", expand=True, padx=15, pady=4)

        self.populate_tabs()

        # Botones de Acción Generales
        self.btn_frame = ctk.CTkFrame(self.main_container, fg_color="transparent")
        self.btn_frame.pack(fill="x", padx=15, pady=10)

        self.btn_save = ctk.CTkButton(
            self.btn_frame,
            text=t18n("asiscfg.btn_save", "💾 Grabar"),
            font=ctk.CTkFont(size=12, weight="bold"),
            fg_color=PALETTE["MainButton"]["fg_color"],
            hover_color=PALETTE["MainButton"]["hover_color"],
            text_color=PALETTE["MainButton"]["text_color"],
            height=38,
            command=self.save_changes
        )
        self.btn_save.pack(side="right", padx=4)
        CTkToolTip(self.btn_save, t18n("asiscfg.tip_save", "Guardar la configuración en el formato seleccionado"))

        available_formats = list(FORMAT_MODES.keys())
        current_fmt = getattr(self.context, "format_mode", available_formats[0]) if self.context else available_formats[0]
        if current_fmt not in available_formats:
            current_fmt = available_formats[0]

        #fg_color=PALETTE["Card"]["fg_color"]
        self.combo_format = ctk.CTkOptionMenu(
            self.btn_frame,
            values=available_formats,
            font=ctk.CTkFont(size=12, weight="bold"),
            fg_color=PALETTE["MainButton"]["fg_color"],
            button_color=PALETTE["MainButton"]["fg_color"],
            button_hover_color=PALETTE["MainButton"]["hover_color"],
            text_color=PALETTE["MainButton"]["text_color"],
            width=110,
            height=38
        )
        self.combo_format.set(current_fmt)
        self.combo_format.pack(side="right", padx=4)
        CTkToolTip(self.combo_format, t18n("asiscfg.tip_format_select", "Seleccionar formato de almacenamiento para el archivo"))

        self.btn_reset = ctk.CTkButton(
            self.btn_frame,
            text=t18n("asiscfg.btn_defaults", "🔄 Defectos"),
            font=ctk.CTkFont(size=12),
            fg_color=PALETTE["DangerButton"]["fg_color"],
            hover_color=PALETTE["DangerButton"]["hover_color"],
            text_color=PALETTE["DangerButton"]["text_color"],
            height=38,
            command=self.reset_defaults
        )
        self.btn_reset.pack(side="right", padx=4)
        CTkToolTip(self.btn_reset, t18n("asiscfg.tip_reset_defaults", "Restablecer todos los campos a sus valores por defecto"))

        # Barra de Estado con envoltura dinámica automática
        self.status_label = ctk.CTkLabel(
            self.main_container,
            text=t18n("asiscfg.status_ready", "Listo - Sesión de administración autenticada."),
            font=ctk.CTkFont(size=12),
            text_color=PALETTE["Subtext"]["text_color"],
            anchor="w",
            justify="left"
        )
        self.status_label.pack(fill="x", padx=20, pady=(0, 10))

        def _update_status_wraplength(event):
            if event.widget == self and self.status_label is not None:
                wrap_w = max(200, event.width - 50)
                self.status_label.configure(wraplength=wrap_w)

        self.bind("<Configure>", _update_status_wraplength, add="+")

        # Inicializar estado del botón Probar Conexión según la pestaña inicial
        self._on_tab_change()

    def get_business_rules(self, sec: str) -> dict:
        """Retorna las reglas de validación para una sección estándar de negocio (ámbito raíz)."""
        if isinstance(self.validation_rules, dict):
            sec_rules = self.validation_rules.get(sec, {})
            if isinstance(sec_rules, dict):
                return sec_rules
        return {}

    def get_profile_rules(self, sec: str) -> dict:
        """Retorna las reglas de validación para una subsección de perfil (@profiles._template)."""
        if isinstance(self.validation_rules, dict):
            if SECTION_PROFILES in self.validation_rules and isinstance(self.validation_rules[SECTION_PROFILES], dict):
                tmpl = self.validation_rules[SECTION_PROFILES].get("_template", {})
                if isinstance(tmpl, dict) and sec in tmpl:
                    return tmpl[sec]
            if "_template" in self.validation_rules and isinstance(self.validation_rules["_template"], dict):
                if sec in self.validation_rules["_template"]:
                    return self.validation_rules["_template"][sec]
            return self.validation_rules.get(sec, {})
        return {}

    def _parse_entry_val(self, sec: str, key: str, raw_str: str, is_profile: bool = False) -> Any:
        """Convierte el texto ingresado en la GUI al tipo estricto definido en el schema."""
        sec_rules = self.get_profile_rules(sec) if is_profile else self.get_business_rules(sec)
        rule = sec_rules.get(key, {}) if isinstance(sec_rules, dict) else {}
        val_type = rule.get("type", "str") if isinstance(rule, dict) else "str"

        if raw_str == "":
            return ""

        if val_type == "int":
            try:
                return int(raw_str)
            except ValueError:
                return raw_str
        elif val_type == "float":
            try:
                return float(raw_str)
            except ValueError:
                return raw_str
        elif val_type == "bool":
            if str(raw_str).lower() in ("true", "1", "yes", "si"):
                return True
            if str(raw_str).lower() in ("false", "0", "no"):
                return False
            return False
        else:
            # "str", "enum" o cualquier otro: estrictamente cadena de texto
            return raw_str

    def flush_current_entries(self):
        """Guarda los valores actuales de las cajas de texto en self.working_config en memoria respetando el schema."""
        has_profs = SECTION_PROFILES in self.working_config and isinstance(self.working_config[SECTION_PROFILES], dict)

        # 1. Guardar entradas de secciones de negocio (raíz)
        for sec, keys_dict in self.business_entries.items():
            sec_dict = self.working_config.setdefault(sec, {})
            for key, entry in keys_dict.items():
                raw_val = entry.get().strip()
                sec_dict[key] = self._parse_entry_val(sec, key, raw_val, is_profile=False)

        # 2. Guardar entradas del perfil activo
        if has_profs and self.active_profile:
            prof_dict = self.working_config.setdefault(SECTION_PROFILES, {}).setdefault(self.active_profile, {})
            for sec, keys_dict in self.profile_entries.items():
                sec_dict = prof_dict.setdefault(sec, {})
                for key, entry in keys_dict.items():
                    raw_val = entry.get().strip()
                    sec_dict[key] = self._parse_entry_val(sec, key, raw_val, is_profile=True)

    def update_profile_values(self, profile_code: str):
        """Actualiza instantáneamente los valores en las pestañas de perfil sin destruir ni recrear widgets."""
        if not self.profile_entries:
            return

        prof_data = self.working_config.get(SECTION_PROFILES, {}).get(profile_code, {})
        if not isinstance(prof_data, dict):
            prof_data = {}

        for sec, keys_dict in self.profile_entries.items():
            sec_data = prof_data.get(sec, {}) if isinstance(prof_data, dict) else {}
            if not isinstance(sec_data, dict):
                sec_data = {}
            sec_rules = self.get_profile_rules(sec)
            for key, entry_widget in keys_dict.items():
                val = sec_data.get(key, "")
                val_rule = sec_rules.get(key, {}) if isinstance(sec_rules, dict) else {}
                is_sensitive = bool(isinstance(val_rule, dict) and val_rule.get("is_password") is True)
                if is_sensitive and isinstance(val, str) and val.startswith(ENC_PREFIX):
                    val_str = self.current_config._decrypt_value(val)
                else:
                    val_str = str(val if val is not None else "")

                if isinstance(entry_widget, ctk.CTkOptionMenu):
                    entry_widget.set(val_str)
                elif isinstance(entry_widget, ctk.CTkEntry):
                    orig_state = str(entry_widget.cget("state"))
                    if orig_state == "disabled":
                        entry_widget.configure(state="normal")
                    entry_widget.delete(0, "end")
                    entry_widget.insert(0, val_str)
                    if orig_state == "disabled":
                        entry_widget.configure(state="disabled")

                field_id = (sec, key, profile_code)
                if is_sensitive:
                    orig_prof_val = self.current_config.valorpass_profile(profile_code, f"{sec}.{key}", default="")
                else:
                    orig_prof_val = self.current_config.valor_profile(profile_code, f"{sec}.{key}", default="")
                if field_id not in self.initial_field_values:
                    unenc_list = self.current_config.get_unencrypted_passwords()
                    is_failed = any(
                        u[0] in (f"{SECTION_PROFILES}.{profile_code}.{sec}.{key}", f"profiles.{profile_code}.{sec}.{key}", f"{profile_code}.{sec}.{key}")
                        or u[0].lstrip("@").endswith(f".{profile_code}.{sec}.{key}")
                        for u in unenc_list
                    )
                    if is_failed:
                        def_profs = self.default_config.get(SECTION_PROFILES, {})
                        def_v = ""
                        if isinstance(def_profs, dict) and def_profs:
                            if "_template" in def_profs and isinstance(def_profs["_template"], dict):
                                def_v = def_profs["_template"].get(sec, {}).get(key, "") if isinstance(def_profs["_template"].get(sec), dict) else ""
                            if not def_v and profile_code in def_profs and isinstance(def_profs[profile_code], dict):
                                def_v = def_profs[profile_code].get(sec, {}).get(key, "") if isinstance(def_profs[profile_code], dict) else ""
                            if not def_v:
                                first_k = list(def_profs.keys())[0]
                                def_v = def_profs[first_k].get(sec, {}).get(key, "") if isinstance(def_profs[first_k].get(sec), dict) else ""
                        base_str = str(def_v if def_v is not None else "").strip()
                        if base_str == "":
                            base_str = NULL_SENTINEL
                        self.initial_field_values[field_id] = base_str
                    else:
                        self.initial_field_values[field_id] = str(orig_prof_val if orig_prof_val is not None else "")
                
                lbl_widget = self.field_label_widgets.get((sec, key, "profile")) or self.field_label_widgets.get(field_id) or self.field_label_widgets.get((sec, key, self.active_profile))
                if lbl_widget:
                    init_v = self.initial_field_values.get(field_id, "")
                    if val_str.strip() != init_v.strip():
                        lbl_widget.configure(text_color=PALETTE["Warning"]["text_color"])
                    else:
                        lbl_widget.configure(text_color=PALETTE["KeyLabel"]["text_color"])

    def _on_profile_selected(self, selected_text: str):
        self.flush_current_entries()
        code = selected_text.split(" - ")[0].strip() if " - " in selected_text else selected_text.strip()
        if code in self.working_config.get(SECTION_PROFILES, {}):
            self.active_profile = code
            self.update_profile_values(code)
            self._on_tab_change()

    def populate_tabs(self):
        """Construye abstractamente las pestañas de negocio y las pestañas por perfil si aplica."""
        self.entries = {}
        self.business_entries = {}
        self.profile_entries = {}
        self.field_label_widgets.clear()

        has_profs = SECTION_PROFILES in self.working_config and isinstance(self.working_config[SECTION_PROFILES], dict) and len(self.working_config[SECTION_PROFILES]) > 0

        business_secs = [k for k in self.working_config.keys() if is_business_section(k)]
        
        profile_secs = []
        active_prof_data = {}
        if has_profs and self.active_profile:
            active_prof_data = self.working_config.get(SECTION_PROFILES, {}).get(self.active_profile, {})
            if isinstance(active_prof_data, dict):
                profile_secs = [k for k in active_prof_data.keys() if not is_schema_directive(k)]


        # 1. Renderizar Pestañas de Negocio en tabview_business
        for sec in business_secs:
            tab_title = sec.capitalize()
            target_tv = self.tabview_business
            if tab_title not in target_tv._tab_dict:
                tab_widget = target_tv.add(tab_title)
            else:
                tab_widget = target_tv.tab(tab_title)

            for widget in tab_widget.winfo_children():
                widget.destroy()

            scroll = ctk.CTkScrollableFrame(tab_widget, corner_radius=6)
            scroll.pack(fill="both", expand=True, padx=5, pady=5)

            is_sec_sec = is_security_section(sec)
            is_ro = is_sec_sec and not self.allow_app_edit

            if is_sec_sec:
                if is_ro:
                    info_banner = ctk.CTkLabel(
                        scroll,
                        text=t18n("asiscfg.security_section_banner_ro", "🔒 Sección de Seguridad '{section}' (Solo Lectura. Use --app en CLI para modificar).", section=sec),
                        font=ctk.CTkFont(size=12, weight="bold"),
                        text_color=PALETTE["Warning"]["text_color"],
                        anchor="w"
                    )
                else:
                    info_banner = ctk.CTkLabel(
                        scroll,
                        text=t18n("asiscfg.security_section_banner_rw", "✏️ Sección de Seguridad '{section}' (Modo Edición Activo por --app).", section=sec),
                        font=ctk.CTkFont(size=12, weight="bold"),
                        text_color=PALETTE["Success"]["text_color"],
                        anchor="w"
                    )
                info_banner.pack(fill="x", pady=(5, 10), padx=5)

            # Encabezados de Columna para Pestañas de Negocio
            hdr_frame = ctk.CTkFrame(scroll, fg_color="transparent")
            hdr_frame.pack(fill="x", pady=(2, 6), padx=5)
            hdr_frame.grid_columnconfigure(0, weight=0, minsize=190)
            hdr_frame.grid_columnconfigure(1, weight=1, uniform="cols")
            hdr_frame.grid_columnconfigure(2, weight=0, minsize=22)
            hdr_frame.grid_columnconfigure(3, weight=1, uniform="cols")

            lbl_h_key = ctk.CTkLabel(
                hdr_frame,
                text=t18n("asiscfg.hdr_key", "Clave"),
                font=ctk.CTkFont(size=12, weight="bold"),
                anchor="w",
                text_color=PALETTE["Header"]["text_color"]
            )
            lbl_h_key.grid(row=0, column=0, sticky="ew", padx=5)

            lbl_h_val = ctk.CTkLabel(
                hdr_frame,
                text=t18n("asiscfg.hdr_current_val", "Valor Actual"),
                font=ctk.CTkFont(size=12, weight="bold"),
                anchor="w",
                text_color=PALETTE["Header"]["text_color"]
            )
            lbl_h_val.grid(row=0, column=1, sticky="ew", padx=5)

            lbl_h_spacer = ctk.CTkLabel(
                hdr_frame,
                text="",
                width=18
            )
            lbl_h_spacer.grid(row=0, column=2, padx=2)

            lbl_h_def = ctk.CTkLabel(
                hdr_frame,
                text=t18n("asiscfg.hdr_default_val", "Valor por Defecto"),
                font=ctk.CTkFont(size=12, weight="bold"),
                anchor="w",
                text_color=PALETTE["Header"]["text_color"]
            )
            lbl_h_def.grid(row=0, column=3, sticky="ew", padx=5)

            self.entries[sec] = ({}, False)
            self.business_entries[sec] = {}
            sec_data = self.working_config.get(sec, {}) if isinstance(self.working_config, dict) else {}
            if not isinstance(sec_data, dict):
                sec_data = {}

            sec_rules = self.get_business_rules(sec)

            all_keys = list(sec_rules.keys())
            for k in sec_data.keys():
                if k not in all_keys:
                    all_keys.append(k)

            for idx, key in enumerate(all_keys):
                if sec.lower() == "default" and key.lower() == "admin_pass_hash":
                    continue

                val = sec_data.get(key)
                val_rule = sec_rules.get(key, {})
                if not isinstance(val_rule, dict):
                    val_rule = {}

                description = str(val_rule.get("description", "")).strip()
                field_type = str(val_rule.get("type", "")).strip()

                row_bg = PALETTE["Table"]["row_main"] if idx % 2 == 0 else PALETTE["Table"]["row_alt"]
                row_frame = ctk.CTkFrame(scroll, fg_color=row_bg, corner_radius=4)
                row_frame.pack(fill="x", pady=2, padx=5)

                if field_type == "test_connection":
                    btn_text = description if description else t18n("asiscfg.btn_test_db", "🔌 Probar Conexión")
                    btn_test = ctk.CTkButton(
                        row_frame,
                        text=btn_text,
                        font=ctk.CTkFont(size=12, weight="bold"),
                        fg_color=PALETTE["SecondaryButton"]["fg_color"],
                        hover_color=PALETTE["SecondaryButton"]["hover_color"],
                        text_color=PALETTE["SecondaryButton"]["text_color"],
                        height=36,
                        command=lambda s=sec, k=key, vr=val_rule: self.run_test_connection_action(s, k, vr, is_profile=False)
                    )
                    btn_test.pack(anchor="center", pady=6, padx=10)
                    CTkToolTip(btn_test, t18n("asiscfg.tip_test_db", "Ejecutar prueba de conexión con los parámetros actuales"))
                    continue

                row_frame.grid_columnconfigure(0, weight=0, minsize=190)
                row_frame.grid_columnconfigure(1, weight=1, uniform="cols")
                row_frame.grid_columnconfigure(2, weight=0, minsize=22)
                row_frame.grid_columnconfigure(3, weight=1, uniform="cols")

                key_container = ctk.CTkFrame(row_frame, fg_color="transparent")
                key_container.grid(row=0, column=0, sticky="w", padx=5)

                lbl_key = ctk.CTkLabel(
                    key_container,
                    text=key,
                    font=ctk.CTkFont(size=13, weight="bold"),
                    anchor="w",
                    text_color=PALETTE["KeyLabel"]["text_color"]
                )
                lbl_key.pack(anchor="w")

                if description:
                    lbl_desc = ctk.CTkLabel(
                        key_container,
                        text=description,
                        font=ctk.CTkFont(size=10),
                        anchor="w",
                        justify="left",
                        wraplength=180,
                        text_color=PALETTE["Subtext"]["text_color"]
                    )
                    lbl_desc.pack(anchor="w")

                options_list = val_rule.get("options") if isinstance(val_rule, dict) else None
                is_sensitive = bool(isinstance(val_rule, dict) and val_rule.get("is_password") is True)
                if is_sensitive and isinstance(val, str) and val.startswith(ENC_PREFIX):
                    cur_val_str = self.current_config._decrypt_value(val)
                else:
                    cur_val_str = str(val if val is not None else "")

                val_container = ctk.CTkFrame(row_frame, fg_color="transparent")
                val_container.grid(row=0, column=1, sticky="ew", padx=5)

                if options_list and isinstance(options_list, (list, tuple)):
                    str_options = [str(opt) for opt in options_list]
                    if cur_val_str and cur_val_str not in str_options:
                        str_options.insert(0, cur_val_str)

                    entry_val = ctk.CTkOptionMenu(
                        val_container,
                        values=str_options,
                        font=ctk.CTkFont(size=12),
                        height=34
                    )
                    entry_val.pack(fill="x", expand=True)
                    if cur_val_str:
                        entry_val.set(cur_val_str)
                elif is_sensitive:
                    entry_val = ctk.CTkEntry(
                        val_container,
                        font=ctk.CTkFont(size=12),
                        height=34,
                        show="*"
                    )
                    entry_val.pack(side="left", fill="x", expand=True, padx=(0, 4))
                    entry_val.insert(0, cur_val_str)

                    if not is_ro:
                        btn_toggle = ctk.CTkButton(
                            val_container,
                            text="👁️",
                            width=34,
                            height=34,
                            fg_color=PALETTE["SecondaryButton"]["fg_color"],
                            hover_color=PALETTE["SecondaryButton"]["hover_color"],
                            text_color=PALETTE["SecondaryButton"]["text_color"],
                            command=lambda e=entry_val: e.configure(show="" if e.cget("show") == "*" else "*")
                        )
                        btn_toggle.pack(side="right")
                        CTkToolTip(btn_toggle, t18n("asiscfg.tip_toggle_pass", "Mostrar u ocultar contenido"))
                else:
                    entry_val = ctk.CTkEntry(
                        val_container,
                        font=ctk.CTkFont(size=12),
                        height=34
                    )
                    entry_val.pack(fill="x", expand=True)
                    entry_val.insert(0, cur_val_str)

                if is_ro:
                    entry_val.configure(state="disabled")

                # Valor por Defecto
                if is_sec_sec:
                    def_val_str = "N/A"
                else:
                    def_sec = self.default_config.get(sec, {})
                    def_val_str = str(def_sec.get(key, "N/A")) if isinstance(def_sec, dict) and key in def_sec else "N/A"

                # Botón individual para restaurar valor por defecto
                if def_val_str != "N/A" and not is_ro:
                    btn_reset_param = ctk.CTkButton(
                        row_frame,
                        text="↩",
                        width=18,
                        height=18,
                        corner_radius=4,
                        font=ctk.CTkFont(size=10, weight="bold"),
                        fg_color=PALETTE["SecondaryButton"]["fg_color"],
                        hover_color=PALETTE["SecondaryButton"]["hover_color"],
                        text_color=PALETTE["SecondaryButton"]["text_color"],
                        command=lambda s=sec, k=key, dv=def_val_str, ew=entry_val: self.reset_param_to_default(s, k, dv, ew, is_profile=False)
                    )
                    btn_reset_param.grid(row=0, column=2, padx=2)
                    CTkToolTip(btn_reset_param, t18n("asiscfg.tip_reset_param", "Restablecer al valor por defecto"))
                else:
                    spacer_param = ctk.CTkFrame(row_frame, width=18, height=18, fg_color="transparent")
                    spacer_param.grid(row=0, column=2, padx=2)

                entry_def = ctk.CTkEntry(
                    row_frame,
                    font=ctk.CTkFont(size=12),
                    height=34,
                    show="*" if is_sensitive else ""
                )
                entry_def.grid(row=0, column=3, sticky="ew", padx=5)
                entry_def.insert(0, def_val_str)
                entry_def.configure(state="disabled", fg_color=PALETTE["Disabled"]["fg_color"], text_color=PALETTE["Disabled"]["text_color"], border_color=PALETTE["Table"]["border_inactive"])

                self.entries[sec][0][key] = entry_val
                self.business_entries[sec][key] = entry_val
                self._register_field_tracker(sec, key, cur_val_str, lbl_key, entry_val, is_profile=False)

        # 2. Renderizar Pestañas por Perfil en tabview_profile (si aplica)
        if has_profs and self.tabview_profile:
            for sec in profile_secs:
                tab_title = sec.capitalize()
                target_tv = self.tabview_profile
                if tab_title not in target_tv._tab_dict:
                    tab_widget = target_tv.add(tab_title)
                else:
                    tab_widget = target_tv.tab(tab_title)

                for widget in tab_widget.winfo_children():
                    widget.destroy()

                scroll = ctk.CTkScrollableFrame(tab_widget, corner_radius=6)
                scroll.pack(fill="both", expand=True, padx=5, pady=5)

                # Encabezados de Columna para Pestañas de Perfil
                hdr_frame = ctk.CTkFrame(scroll, fg_color="transparent")
                hdr_frame.pack(fill="x", pady=(2, 6), padx=5)
                hdr_frame.grid_columnconfigure(0, weight=0, minsize=190)
                hdr_frame.grid_columnconfigure(1, weight=1, uniform="cols")
                hdr_frame.grid_columnconfigure(2, weight=0, minsize=22)
                hdr_frame.grid_columnconfigure(3, weight=1, uniform="cols")

                lbl_h_key = ctk.CTkLabel(
                    hdr_frame,
                    text=t18n("asiscfg.hdr_key", "Clave"),
                    font=ctk.CTkFont(size=12, weight="bold"),
                    anchor="w",
                    text_color=PALETTE["Header"]["text_color"]
                )
                lbl_h_key.grid(row=0, column=0, sticky="ew", padx=5)

                lbl_h_val = ctk.CTkLabel(
                    hdr_frame,
                    text=t18n("asiscfg.hdr_current_val", "Valor Actual"),
                    font=ctk.CTkFont(size=12, weight="bold"),
                    anchor="w",
                    text_color=PALETTE["Header"]["text_color"]
                )
                lbl_h_val.grid(row=0, column=1, sticky="ew", padx=5)

                lbl_h_spacer = ctk.CTkLabel(
                    hdr_frame,
                    text="",
                    width=18
                )
                lbl_h_spacer.grid(row=0, column=2, padx=2)

                lbl_h_def = ctk.CTkLabel(
                    hdr_frame,
                    text=t18n("asiscfg.hdr_default_val", "Valor por Defecto"),
                    font=ctk.CTkFont(size=12, weight="bold"),
                    anchor="w",
                    text_color=PALETTE["Header"]["text_color"]
                )
                lbl_h_def.grid(row=0, column=3, sticky="ew", padx=5)

                self.entries[sec] = ({}, True)
                self.profile_entries[sec] = {}
                sec_data = active_prof_data.get(sec, {}) if isinstance(active_prof_data, dict) else {}
                if not isinstance(sec_data, dict):
                    sec_data = {}

                sec_rules = self.get_profile_rules(sec)

                all_keys = list(sec_rules.keys())
                for k in sec_data.keys():
                    if k not in all_keys:
                        all_keys.append(k)

                def_profiles = self.default_config.get(SECTION_PROFILES, {})
                def_prof_data = {}
                if isinstance(def_profiles, dict) and def_profiles:
                    first_def_key = list(def_profiles.keys())[0]
                    def_prof_data = def_profiles.get(first_def_key, {})


                for idx, key in enumerate(all_keys):
                    val = sec_data.get(key)
                    val_rule = sec_rules.get(key, {})
                    if not isinstance(val_rule, dict):
                        val_rule = {}

                    description = str(val_rule.get("description", "")).strip()
                    field_type = str(val_rule.get("type", "")).strip()

                    row_bg = PALETTE["Table"]["row_main"] if idx % 2 == 0 else PALETTE["Table"]["row_alt"]
                    row_frame = ctk.CTkFrame(scroll, fg_color=row_bg, corner_radius=4)
                    row_frame.pack(fill="x", pady=2, padx=5)

                    if field_type == "test_connection":
                        btn_text = description if description else t18n("asiscfg.btn_test_db", "🔌 Probar Conexión")
                        btn_test = ctk.CTkButton(
                            row_frame,
                            text=btn_text,
                            font=ctk.CTkFont(size=12, weight="bold"),
                            fg_color=PALETTE["SecondaryButton"]["fg_color"],
                            hover_color=PALETTE["SecondaryButton"]["hover_color"],
                            text_color=PALETTE["SecondaryButton"]["text_color"],
                            height=36,
                            command=lambda s=sec, k=key, vr=val_rule: self.run_test_connection_action(s, k, vr, is_profile=True)
                        )
                        btn_test.pack(anchor="center", pady=6, padx=10)
                        CTkToolTip(btn_test, t18n("asiscfg.tip_test_db", "Ejecutar prueba de conexión con los parámetros actuales"))
                        continue

                    row_frame.grid_columnconfigure(0, weight=0, minsize=190)
                    row_frame.grid_columnconfigure(1, weight=1, uniform="cols")
                    row_frame.grid_columnconfigure(2, weight=0, minsize=22)
                    row_frame.grid_columnconfigure(3, weight=1, uniform="cols")

                    key_container = ctk.CTkFrame(row_frame, fg_color="transparent")
                    key_container.grid(row=0, column=0, sticky="w", padx=5)

                    lbl_key = ctk.CTkLabel(
                        key_container,
                        text=key,
                        font=ctk.CTkFont(size=13, weight="bold"),
                        anchor="w",
                        text_color=PALETTE["KeyLabel"]["text_color"]
                    )
                    lbl_key.pack(anchor="w")

                    if description:
                        lbl_desc = ctk.CTkLabel(
                            key_container,
                            text=description,
                            font=ctk.CTkFont(size=10),
                            anchor="w",
                            justify="left",
                            wraplength=180,
                            text_color=PALETTE["Subtext"]["text_color"]
                        )
                        lbl_desc.pack(anchor="w")

                    options_list = val_rule.get("options") if isinstance(val_rule, dict) else None
                    is_sensitive = bool(isinstance(val_rule, dict) and val_rule.get("is_password") is True)
                    if is_sensitive and isinstance(val, str) and val.startswith(ENC_PREFIX):
                        cur_val_str = self.current_config._decrypt_value(val)
                    else:
                        cur_val_str = str(val if val is not None else "")

                    val_container = ctk.CTkFrame(row_frame, fg_color="transparent")
                    val_container.grid(row=0, column=1, sticky="ew", padx=5)

                    if options_list and isinstance(options_list, (list, tuple)):
                        str_options = [str(opt) for opt in options_list]
                        if cur_val_str and cur_val_str not in str_options:
                            str_options.insert(0, cur_val_str)

                        entry_val = ctk.CTkOptionMenu(
                            val_container,
                            values=str_options,
                            font=ctk.CTkFont(size=12),
                            height=34
                        )
                        entry_val.pack(fill="x", expand=True)
                        if cur_val_str:
                            entry_val.set(cur_val_str)
                    elif is_sensitive:
                        entry_val = ctk.CTkEntry(
                            val_container,
                            font=ctk.CTkFont(size=12),
                            height=34,
                            show="*"
                        )
                        entry_val.pack(side="left", fill="x", expand=True, padx=(0, 4))
                        entry_val.insert(0, cur_val_str)

                        btn_toggle = ctk.CTkButton(
                            val_container,
                            text="👁️",
                            width=34,
                            height=34,
                            fg_color=PALETTE["SecondaryButton"]["fg_color"],
                            hover_color=PALETTE["SecondaryButton"]["hover_color"],
                            text_color=PALETTE["SecondaryButton"]["text_color"],
                            command=lambda e=entry_val: e.configure(show="" if e.cget("show") == "*" else "*")
                        )
                        btn_toggle.pack(side="right")
                        CTkToolTip(btn_toggle, t18n("asiscfg.tip_toggle_pass", "Mostrar u ocultar contenido"))
                    else:
                        entry_val = ctk.CTkEntry(
                            val_container,
                            font=ctk.CTkFont(size=12),
                            height=34
                        )
                        entry_val.pack(fill="x", expand=True)
                        entry_val.insert(0, cur_val_str)

                    # Valor por Defecto de Perfil
                    def_val_str = "N/A"
                    if isinstance(def_prof_data, dict):
                        def_sec = def_prof_data.get(sec, {})
                        if isinstance(def_sec, dict) and key in def_sec:
                            def_val_str = str(def_sec[key])
                        else:
                            def_gen = self.default_config.get(sec, {})
                            if isinstance(def_gen, dict) and key in def_gen:
                                def_val_str = str(def_gen[key])

                    # Botón individual para restaurar valor por defecto
                    if def_val_str != "N/A":
                        btn_reset_param = ctk.CTkButton(
                            row_frame,
                            text="↩",
                            width=18,
                            height=18,
                            corner_radius=4,
                            font=ctk.CTkFont(size=10, weight="bold"),
                            fg_color=PALETTE["SecondaryButton"]["fg_color"],
                            hover_color=PALETTE["SecondaryButton"]["hover_color"],
                            text_color=PALETTE["SecondaryButton"]["text_color"],
                            command=lambda s=sec, k=key, dv=def_val_str, ew=entry_val: self.reset_param_to_default(s, k, dv, ew, is_profile=True)
                        )
                        btn_reset_param.grid(row=0, column=2, padx=2)
                        CTkToolTip(btn_reset_param, t18n("asiscfg.tip_reset_param", "Restablecer al valor por defecto"))
                    else:
                        spacer_param = ctk.CTkFrame(row_frame, width=18, height=18, fg_color="transparent")
                        spacer_param.grid(row=0, column=2, padx=2)

                    entry_def = ctk.CTkEntry(
                        row_frame,
                        font=ctk.CTkFont(size=12),
                        height=34,
                        show="*" if is_sensitive else ""
                    )
                    entry_def.grid(row=0, column=3, sticky="ew", padx=5)
                    entry_def.insert(0, def_val_str)
                    entry_def.configure(state="disabled", fg_color=PALETTE["Disabled"]["fg_color"], text_color=PALETTE["Disabled"]["text_color"], border_color=PALETTE["Table"]["border_inactive"])

                    self.entries[sec][0][key] = entry_val
                    self.profile_entries[sec][key] = entry_val
                    self._register_field_tracker(sec, key, cur_val_str, lbl_key, entry_val, is_profile=True, profile_code=self.active_profile)

    def add_profile(self):
        self.flush_current_entries()
        existing = [k for k in self.working_config.get(SECTION_PROFILES, {}).keys() if not is_schema_directive(k)]

        def_profiles = self.default_config.get(SECTION_PROFILES, {})
        first_def_key = list(def_profiles.keys())[0] if def_profiles else None
        default_template_prof = def_profiles.get(first_def_key, {}) if first_def_key else {}
        default_info = default_template_prof.get("info", {})

        dialog = AddProfileDialog(
            self,
            existing_profiles=existing,
            working_profiles=self.working_config.get(SECTION_PROFILES, {}),
            default_info=default_info
        )
        self.wait_window(dialog)
        if dialog.result:
            code, info_dict, copy_from = dialog.result
            if copy_from and copy_from in self.working_config.get(SECTION_PROFILES, {}):
                new_prof = json.loads(json.dumps(self.working_config[SECTION_PROFILES][copy_from]))
            elif first_def_key:
                new_prof = self._create_working_config(def_profiles.get(first_def_key, {}))
            else:
                new_prof = {}

            new_prof["info"] = info_dict
            self.working_config.setdefault(SECTION_PROFILES, {})[code] = new_prof
            self.active_profile = code

            display_list = self._get_profile_display_list()
            self.combo_profile.configure(values=display_list)
            for item in display_list:
                if item == code or item.startswith(f"{code} - "):
                    self.combo_profile.set(item)
                    break

            self.populate_tabs()
            self._on_tab_change()
            log_audit_event("PROFILE_ADDED", f"Perfil '{code}' agregado a la configuración.")
            self.status_label.configure(
                text=t18n("asiscfg.msg_profile_added", "✅ Perfil '{code}' agregado correctamente.", code=code),
                text_color=PALETTE["Success"]["text_color"]
            )

    def rename_profile(self):
        if not self.active_profile:
            return
        self.flush_current_entries()
        current_code = self.active_profile
        existing = [k for k in self.working_config.get(SECTION_PROFILES, {}).keys() if not is_schema_directive(k)]
        dialog = RenameProfileDialog(self, current_code=current_code, existing_profiles=existing)
        self.wait_window(dialog)
        if dialog.result and dialog.result != current_code:
            old_code = current_code
            new_code = dialog.result
            prof_data = self.working_config[SECTION_PROFILES].pop(old_code)
            self.working_config[SECTION_PROFILES][new_code] = prof_data
            self.active_profile = new_code

            display_list = self._get_profile_display_list()
            self.combo_profile.configure(values=display_list)
            for item in display_list:
                if item == new_code or item.startswith(f"{new_code} - "):
                    self.combo_profile.set(item)
                    break

            self.update_profile_values(new_code)
            self._on_tab_change()
            log_audit_event("PROFILE_RENAMED", f"Perfil '{old_code}' renombrado a '{new_code}'.")
            self.status_label.configure(
                text=t18n("asiscfg.msg_profile_renamed", "✅ Código de perfil cambiado de '{old}' a '{new}'.", old=old_code, new=new_code),
                text_color=PALETTE["Success"]["text_color"]
            )

    def delete_profile(self):
        if not self.active_profile:
            return
        self.flush_current_entries()
        profiles_dict = self.working_config.get(SECTION_PROFILES, {})
        existing = [k for k in profiles_dict.keys() if not is_schema_directive(k)]
        if len(existing) <= 1:
            from tkinter import messagebox
            messagebox.showwarning(
                t18n("asiscfg.title_warn", "Advertencia"),
                t18n("asiscfg.err_cannot_delete_last_profile", "❌ No se puede eliminar el único perfil registrado. Debe existir al menos 1 perfil."),
                parent=self
            )
            return

        active_code = self.active_profile
        from tkinter import messagebox
        confirm = messagebox.askyesno(
            t18n("asiscfg.confirm_delete_title", "Confirmar Eliminación"),
            t18n("asiscfg.confirm_delete_profile", "¿Está seguro de eliminar el perfil '{code}'?", code=active_code),
            parent=self
        )
        if confirm:
            deleted_code = active_code
            del profiles_dict[deleted_code]
            remaining = [k for k in profiles_dict.keys() if not is_schema_directive(k)]
            self.active_profile = remaining[0]

            display_list = self._get_profile_display_list()
            self.combo_profile.configure(values=display_list)
            for item in display_list:
                if item == self.active_profile or item.startswith(f"{self.active_profile} - "):
                    self.combo_profile.set(item)
                    break


            self.update_profile_values(self.active_profile)
            self._on_tab_change()
            log_audit_event("PROFILE_DELETED", f"Perfil '{deleted_code}' eliminado.")
            self.status_label.configure(
                text=t18n("asiscfg.msg_profile_deleted", "ℹ️ Perfil '{code}' eliminado.", code=deleted_code),
                text_color=PALETTE["Warning"]["text_color"]
            )

    def change_admin_password(self):
        dialog = ChangeAdminPasswordDialog(self)
        self.wait_window(dialog)
        if dialog.success:
            self.status_label.configure(
                text=t18n("asiscfg.pass_updated_success", "✅ Clave de administración actualizada correctamente."),
                text_color=PALETTE["Success"]["text_color"]
            )

    def validate_all_entries(self) -> Tuple[bool, str]:
        """Valida tipos y rangos (min/max) de las entradas de la GUI contra las reglas del esquema."""
        def _validate_group(entries_group: dict, is_profile: bool) -> Tuple[bool, str]:
            for sec, keys_dict in entries_group.items():
                sec_rules = self.get_profile_rules(sec) if is_profile else self.get_business_rules(sec)
                for key, entry in keys_dict.items():
                    raw_val = entry.get().strip()
                    rule = sec_rules.get(key, {}) if isinstance(sec_rules, dict) else {}
                    if not isinstance(rule, dict):
                        rule = {}

                    val_type = rule.get("type", "str")
                    min_val = rule.get("min")
                    max_val = rule.get("max")

                    if val_type == "int" and raw_val != "":
                        try:
                            int(raw_val)
                        except ValueError:
                            if hasattr(entry, "configure"):
                                try:
                                    entry.configure(border_color=PALETTE["DangerButton"]["fg_color"], border_width=2)
                                except Exception:
                                    pass
                            return False, t18n("asiscfg.err_val_not_int", "❌ El parámetro '{sec}.{param_key}' debe ser un número entero.", sec=sec, param_key=key)

                    elif val_type == "float" and raw_val != "":
                        try:
                            float(raw_val)
                        except ValueError:
                            if hasattr(entry, "configure"):
                                try:
                                    entry.configure(border_color=PALETTE["DangerButton"]["fg_color"], border_width=2)
                                except Exception:
                                    pass
                            return False, t18n("asiscfg.err_val_not_number", "❌ El parámetro '{sec}.{param_key}' debe ser un valor numérico.", sec=sec, param_key=key)

                    if min_val is not None or max_val is not None:
                        try:
                            num_val = float(raw_val)
                            if min_val is not None and num_val < min_val:
                                if hasattr(entry, "configure"):
                                    try:
                                        entry.configure(border_color=PALETTE["DangerButton"]["fg_color"], border_width=2)
                                    except Exception:
                                        pass
                                return False, t18n("asiscfg.err_val_below_min", "❌ El parámetro '{sec}.{param_key}' ({val}) es menor al mínimo permitido ({min}).", sec=sec, param_key=key, val=num_val, min=min_val)
                            if max_val is not None and num_val > max_val:
                                if hasattr(entry, "configure"):
                                    try:
                                        entry.configure(border_color=PALETTE["DangerButton"]["fg_color"], border_width=2)
                                    except Exception:
                                        pass
                                return False, t18n("asiscfg.err_val_above_max", "❌ El parámetro '{sec}.{param_key}' ({val}) es mayor al máximo permitido ({max}).", sec=sec, param_key=key, val=num_val, max=max_val)
                        except ValueError:
                            if raw_val != "":
                                if hasattr(entry, "configure"):
                                    try:
                                        entry.configure(border_color=PALETTE["DangerButton"]["fg_color"], border_width=2)
                                    except Exception:
                                        pass
                                return False, t18n("asiscfg.err_val_not_number", "❌ El parámetro '{sec}.{param_key}' debe ser un valor numérico.", sec=sec, param_key=key)

                    if hasattr(entry, "configure"):
                        try:
                            entry.configure(border_color=PALETTE["Table"]["border_inactive"], border_width=1)
                        except Exception:
                            pass

        # 2. Validar entradas de perfil
        for sec, keys_dict in self.profile_entries.items():
                sec_rules = self.get_profile_rules(sec)
                for key, entry in keys_dict.items():
                    if not hasattr(entry, "get"):
                        continue
                    raw_val = entry.get().strip()
                    rule = sec_rules.get(key, {}) if isinstance(sec_rules, dict) else {}
                    if not isinstance(rule, dict):
                        rule = {}

                    val_type = rule.get("type", "str")
                    min_val = rule.get("min")
                    max_val = rule.get("max")

                    if val_type == "int" and raw_val != "":
                        try:
                            int(raw_val)
                        except ValueError:
                            if hasattr(entry, "configure"):
                                try:
                                    entry.configure(border_color=PALETTE["DangerButton"]["fg_color"], border_width=2)
                                except Exception:
                                    pass
                            return False, t18n("asiscfg.err_val_not_int", "❌ El parámetro '{sec}.{param_key}' debe ser un número entero.", sec=sec, param_key=key)

                    elif val_type == "float" and raw_val != "":
                        try:
                            float(raw_val)
                        except ValueError:
                            if hasattr(entry, "configure"):
                                try:
                                    entry.configure(border_color=PALETTE["DangerButton"]["fg_color"], border_width=2)
                                except Exception:
                                    pass
                            return False, t18n("asiscfg.err_val_not_number", "❌ El parámetro '{sec}.{param_key}' debe ser un valor numérico.", sec=sec, param_key=key)

                    if min_val is not None or max_val is not None:
                        try:
                            num_val = float(raw_val)
                            if min_val is not None and num_val < min_val:
                                if hasattr(entry, "configure"):
                                    try:
                                        entry.configure(border_color=PALETTE["DangerButton"]["fg_color"], border_width=2)
                                    except Exception:
                                        pass
                                return False, t18n("asiscfg.err_val_below_min", "❌ El parámetro '{sec}.{param_key}' ({val}) es menor al mínimo permitido ({min}).", sec=sec, param_key=key, val=num_val, min=min_val)
                            if max_val is not None and num_val > max_val:
                                if hasattr(entry, "configure"):
                                    try:
                                        entry.configure(border_color=PALETTE["DangerButton"]["fg_color"], border_width=2)
                                    except Exception:
                                        pass
                                return False, t18n("asiscfg.err_val_above_max", "❌ El parámetro '{sec}.{param_key}' ({val}) es mayor al máximo permitido ({max}).", sec=sec, param_key=key, val=num_val, max=max_val)
                        except ValueError:
                            if raw_val != "":
                                if hasattr(entry, "configure"):
                                    try:
                                        entry.configure(border_color=PALETTE["DangerButton"]["fg_color"], border_width=2)
                                    except Exception:
                                        pass
                                return False, t18n("asiscfg.err_val_not_number", "❌ El parámetro '{sec}.{param_key}' debe ser un valor numérico.", sec=sec, param_key=key)

                    if hasattr(entry, "configure"):
                        try:
                            entry.configure(border_color=PALETTE["Table"]["border_inactive"], border_width=1)
                        except Exception:
                            pass

        return True, ""

    def export_backup(self):
        """Exporta una copia de respaldo cifrada de la configuración activa."""
        self.flush_current_entries()
        valid, err_msg = self.validate_all_entries()
        if not valid:
            self.status_label.configure(text=err_msg, text_color=PALETTE["Error"]["text_color"])
            return

        from tkinter import filedialog, messagebox
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        dest_path = filedialog.asksaveasfilename(
            title=t18n("asiscfg.title_export_backup", "Exportar Respaldo Cifrado"),
            initialfile=f"config_export_{timestamp}.enc.bak",
            filetypes=[("Respaldo Cifrado (*.enc.bak)", "*.enc.bak"), ("Todos los archivos", "*.*")]
        )
        if dest_path:
            # Corregir duplicaci?n de extensiones en Windows FileDialog
            while dest_path.endswith(".enc.bak.enc.bak"):
                dest_path = dest_path[:-8]
            if not (dest_path.endswith(".enc.bak") or dest_path.endswith(".bak") or dest_path.endswith(".enc")):
                dest_path += ".enc.bak"
            try:
                save_config(self.context, self.working_config, config_path=dest_path)
                log_audit_event("EXPORT_BACKUP", f"Respaldo exportado a '{dest_path}'.")
                messagebox.showinfo(
                    t18n("asiscfg.title_export_success", "📤 Exportación Exitosa"),
                    t18n("asiscfg.msg_export_success", "Respaldo exportado correctamente a:\n{path}", path=dest_path),
                    parent=self
                )
            except Exception as e:
                messagebox.showerror(
                    t18n("asiscfg.title_export_error", "❌ Error al Exportar"),
                    t18n("asiscfg.msg_export_error", "No se pudo exportar el respaldo:\n{err}", err=str(e)),
                    parent=self
                )

    def export_schema_file(self):
        """Permite al usuario exportar el archivo config_schema.py mediante un diálogo interactivo."""
        from tkinter import filedialog, messagebox
        from asiscfg.core import export_config_schema

        initial_dir = os.path.dirname(os.path.abspath(self.config_file)) if self.config_file else os.getcwd()
        dest_path = filedialog.asksaveasfilename(
            title=t18n("asiscfg.title_export_schema", "Exportar Esquema de Configuración"),
            initialdir=initial_dir,
            initialfile="config_schema.py",
            filetypes=[("Archivo Python (*.py)", "*.py"), ("Todos los archivos", "*.*")]
        )
        if dest_path:
            if not dest_path.endswith(".py"):
                dest_path += ".py"
            try:
                code = export_config_schema(
                    source_path=self.schema_file,
                    target_path=dest_path
                )
                if code == 0:
                    log_audit_event("EXPORT_SCHEMA", f"Esquema exportado a '{dest_path}'.")
                    messagebox.showinfo(
                        t18n("asiscfg.title_export_schema_success", "📄 Exportación de Esquema Exitosa"),
                        t18n("asiscfg.msg_export_schema_success", "Esquema exportado correctamente a:\n{path}", path=dest_path),
                        parent=self
                    )
                else:
                    messagebox.showerror(
                        t18n("asiscfg.title_export_schema_error", "❌ Error al Exportar Esquema"),
                        t18n("asiscfg.msg_export_schema_error", "No se pudo generar el archivo de esquema en:\n{path}", path=dest_path),
                        parent=self
                    )
            except Exception as e:
                messagebox.showerror(
                    t18n("asiscfg.title_export_schema_error", "❌ Error al Exportar Esquema"),
                    t18n("asiscfg.msg_export_schema_error", "No se pudo generar el archivo de esquema:\n{err}", err=str(e)),
                    parent=self
                )


    def import_backup(self):
        """Importa y descifra una copia de respaldo en la sesión actual."""
        from tkinter import filedialog, messagebox
        src_path = filedialog.askopenfilename(
            title=t18n("asiscfg.title_import_backup", "Importar Respaldo Cifrado"),
            filetypes=[("Respaldo Cifrado (*.enc, *.enc.bak)", "*.enc;*.enc.bak"), ("Respaldo Plano (*.json, *.json.bak)", "*.json;*.json.bak"), ("Todos los archivos", "*.*")]
        )
        if src_path:
            confirm = messagebox.askyesno(
                t18n("asiscfg.confirm_import_title", "Confirmar Importación"),
                t18n("asiscfg.confirm_import_msg", "¿Está seguro de cargar la configuración desde este respaldo?\nSe reemplazarán los valores actuales en pantalla."),
                parent=self
            )
            if confirm:
                try:
                    imported_cfg = load_config(
                        src_path,
                        self.key_file,
                        default_config=self.default_config,
                        validation_rules=self.validation_rules
                    )
                    self.current_config = imported_cfg
                    self.working_config = self._create_working_config(imported_cfg)
                    self._update_format_indicator()
                    profiles_list = [k for k in self.working_config.get(SECTION_PROFILES, {}).keys() if not is_schema_directive(k)] if isinstance(self.working_config.get(SECTION_PROFILES), dict) else []
                    self.active_profile = profiles_list[0] if profiles_list else None

                    if self.combo_profile:
                        display_list = self._get_profile_display_list()
                        self.combo_profile.configure(values=display_list if display_list else ["-"])
                        if self.active_profile:
                            for item in display_list:
                                if item == self.active_profile or item.startswith(f"{self.active_profile} - "):
                                    self.combo_profile.set(item)
                                    break
                    self.populate_tabs()
                    self._on_tab_change()
                    log_audit_event("IMPORT_BACKUP", f"Respaldo importado desde '{src_path}'.")
                    self.status_label.configure(
                        text=t18n("asiscfg.msg_import_success", "📥 Respaldo importado exitosamente desde '{path}'.", path=os.path.basename(src_path)),
                        text_color=PALETTE["Success"]["text_color"]
                    )
                except Exception as e:
                    messagebox.showerror(
                        t18n("asiscfg.title_import_error", "❌ Error al Importar"),
                        t18n("asiscfg.msg_import_error", "No se pudo importar el respaldo:\n{err}", err=str(e)),
                        parent=self
                    )

    def _update_format_indicator(self):
        """Actualiza el indicador visual de formato de origen de lectura y ruta destino en el encabezado."""
        active_mode = self.current_config.format_mode if self.current_config else self.context.format_mode
        engine = get_format_engine(active_mode)
        icon = "🔒" if engine.is_full_encrypted else "📄"
        color = PALETTE["Warning"]["text_color"] if engine.is_full_encrypted else PALETTE["Link"]["text_color"]
        txt = t18n("asiscfg.badge_format_status", "{icon} Origen de lectura: {name}", icon=icon, name=engine.name)
        if self.lbl_format_origin is not None:
            self.lbl_format_origin.configure(text=txt, text_color=color)

        if self.combo_format is not None and active_mode in FORMAT_MODES:
            self.combo_format.set(active_mode)

        if self.lbl_target_path is not None:
            txt_path = t18n("asiscfg.lbl_target_path", "📁 Destino: {path}", path=self.config_file)
            self.lbl_target_path.configure(text=txt_path)

    def save_changes(self):
        """Guarda la configuración según el formato seleccionado en el selector."""
        target_mode = self.combo_format.get().strip().lower() if self.combo_format is not None else self.context.format_mode
        self._perform_save(format_mode=target_mode)

    def _perform_save(self, format_mode: Optional[str] = None):
        """Ejecuta el guardado validado en disco según el modo de formato seleccionado."""
        if format_mode is not None:
            target_mode = format_mode.strip().lower()
        elif self.combo_format is not None:
            target_mode = self.combo_format.get().strip().lower()
        else:
            target_mode = self.context.format_mode
        engine = get_format_engine(target_mode)

        title = t18n("asiscfg.confirm_save_title", "Confirmar Grabar ({name})", name=engine.name)
        msg = t18n(
            "asiscfg.confirm_save_msg",
            "¿Está seguro de que desea guardar la configuración en formato {name} en {path}?",
            name=engine.name,
            path=self.config_file
        )

        confirm = messagebox.askyesno(title, msg, parent=self)
        if not confirm:
            return

        self.flush_current_entries()
        valid, err_msg = self.validate_all_entries()
        if not valid:
            self.status_label.configure(text=err_msg, text_color=PALETTE["Error"]["text_color"])
            return

        try:
            backup_file = save_config(
                self.context,
                self.working_config,
                validation_rules=self.validation_rules,
                default_config=self.default_config,
                format_mode=engine.mode_id
            )
            self.current_config = load_config(
                self.context,
                default_config=self.default_config,
                validation_rules=self.validation_rules,
                edit_mode=True
            )
            self.working_config = self._create_working_config(self.current_config)
            self.initial_field_values.clear()
            self.populate_tabs()
            self._on_tab_change()
            self._update_format_indicator()

            log_audit_event("SAVE_CONFIG", f"Configuración guardada en modo '{engine.mode_id}' en {self.config_file} (Respaldo: {backup_file}).")
            msg = t18n(
                "asiscfg.save_success_msg",
                "✅ Configuración guardada en formato {name} en {path}.",
                name=engine.name,
                path=self.config_file
            )
            if backup_file:
                msg += f" (Respaldo: {backup_file})"

            self.status_label.configure(
                text=msg,
                text_color=PALETTE["Success"]["text_color"]
            )
            messagebox.showinfo(
                t18n("asiscfg.title_save_success", "✅ Guardado Exitoso"),
                msg,
                parent=self
            )
        except Exception as e:
            log_audit_event("SAVE_ERROR", f"Error al guardar configuración: {str(e)}")
            self.status_label.configure(
                text=t18n("asiscfg.save_error", "❌ Error al guardar la configuración: {err}", err=str(e)),
                text_color=PALETTE["Error"]["text_color"]
            )
            messagebox.showerror(
                t18n("asiscfg.title_save_error", "❌ Error al Guardar"),
                t18n("asiscfg.save_error", "❌ Error al guardar la configuración: {err}", err=str(e)),
                parent=self
            )

    def reset_defaults(self):
        from tkinter import messagebox
        confirm = messagebox.askyesno(
            t18n("asiscfg.confirm_reset_title", "Confirmar Valores por Defecto"),
            t18n("asiscfg.confirm_reset_msg", "¿Está seguro de que desea restablecer todos los parámetros a los valores por defecto?\nSe perderán los cambios no guardados en memoria."),
            parent=self
        )
        if not confirm:
            return

        preserved_security_sections = {}
        for sec_name in SECURITY_SECTIONS:
            if sec_name in self.working_config and isinstance(self.working_config.get(sec_name), dict):
                preserved_security_sections[sec_name] = json.loads(json.dumps(self.working_config[sec_name]))

        self.working_config = self._create_working_config(self.default_config)
        for sec_name, val in preserved_security_sections.items():
            self.working_config[sec_name] = val
        profiles_list = [k for k in self.working_config.get(SECTION_PROFILES, {}).keys() if not is_schema_directive(k)] if isinstance(self.working_config.get(SECTION_PROFILES), dict) else []
        self.active_profile = profiles_list[0] if profiles_list else None
        
        has_profs = SECTION_PROFILES in self.working_config and isinstance(self.working_config[SECTION_PROFILES], dict) and len(self.working_config[SECTION_PROFILES]) > 0
        if self.combo_profile:
            display_list = self._get_profile_display_list()
            self.combo_profile.configure(values=display_list if display_list else ["-"])
            if self.active_profile:
                for item in display_list:
                    if item == self.active_profile or item.startswith(f"{self.active_profile} - "):
                        self.combo_profile.set(item)
                        break

        self.populate_tabs()
        self._on_tab_change()
        log_audit_event("RESET_DEFAULTS", "Valores por defecto cargados en la interfaz GUI.")
        self.status_label.configure(
            text=t18n("asiscfg.defaults_loaded", "ℹ️ Valores por defecto cargados."),
            text_color=PALETTE["Warning"]["text_color"]
        )
        messagebox.showinfo(
            t18n("asiscfg.title_reset_success", "🔄 Valores por Defecto"),
            t18n("asiscfg.defaults_loaded", "ℹ️ Valores por defecto cargados."),
            parent=self
        )

    def reset_param_to_default(self, sec: str, key: str, def_val_str: str, entry_widget: Any, is_profile: bool = False):
        """Restaura el valor por defecto de un parámetro específico en la UI y memoria."""
        if def_val_str == "N/A":
            return

        if isinstance(entry_widget, ctk.CTkOptionMenu):
            entry_widget.set(def_val_str)
        elif isinstance(entry_widget, ctk.CTkEntry):
            orig_state = str(entry_widget.cget("state"))
            if orig_state == "disabled":
                return
            entry_widget.delete(0, "end")
            entry_widget.insert(0, def_val_str)
            entry_widget.configure(border_color=PALETTE["Table"]["border_inactive"], border_width=1)

        parsed_val = self._parse_entry_val(sec, key, def_val_str, is_profile=is_profile)
        if is_profile and self.active_profile:
            prof_dict = self.working_config.setdefault(SECTION_PROFILES, {}).setdefault(self.active_profile, {})
            sec_dict = prof_dict.setdefault(sec, {})
            sec_dict[key] = parsed_val
        else:
            sec_dict = self.working_config.setdefault(sec, {})
            sec_dict[key] = parsed_val

        field_id = (sec, key, self.active_profile) if (is_profile and self.active_profile) else (sec, key)
        lbl_widget = self.field_label_widgets.get((sec, key, "profile") if is_profile else (sec, key)) or self.field_label_widgets.get(field_id)
        if lbl_widget:
            init_v = self.initial_field_values.get(field_id, "")
            if def_val_str.strip() != init_v.strip():
                lbl_widget.configure(text_color=PALETTE["Warning"]["text_color"])
            else:
                lbl_widget.configure(text_color=PALETTE["KeyLabel"]["text_color"])

        self.status_label.configure(
            text=t18n("asiscfg.msg_param_restored", "ℹ️ Parámetro '{sec}.{param_key}' restaurado al valor por defecto.", sec=sec, param_key=key),
            text_color=PALETTE["Success"]["text_color"]
        )

    def _is_field_password(self, sec: str, key: str, is_profile: bool = False) -> bool:
        """Determina estrictamente desde el esquema si un campo tiene is_password == True."""
        rules = self.get_profile_rules(sec) if is_profile else self.get_business_rules(sec)
        rule = rules.get(key, {}) if isinstance(rules, dict) else {}
        return bool(isinstance(rule, dict) and rule.get("is_password") is True)

    def _compare_field_values(self, saved_val: Any, working_val: Any, is_password: bool) -> bool:
        """
        Compara un valor de current_config con working_config:
        - Si is_password es False: comparación directa normalizando NULL_SENTINEL / None a "".
        - Si is_password es True: descifrado JIT volátil de current_config y comparación en tiempo constante con working_config.
        """
        if not is_password:
            norm_saved = "" if (saved_val is None or saved_val == NULL_SENTINEL) else saved_val
            norm_working = "" if (working_val is None or working_val == NULL_SENTINEL) else working_val
            return norm_saved == norm_working

        # Campo contraseña: saved_val proviene de current_config (cifrado o NULL_SENTINEL) y working_val de working_config (texto en claro)
        if saved_val is None or saved_val == "" or saved_val == NULL_SENTINEL:
            dec_saved = ""
        else:
            dec_saved = self.current_config._decrypt_value(saved_val)

        working_str = "" if (working_val is None or working_val == NULL_SENTINEL) else str(working_val)
        return hmac.compare_digest(dec_saved, working_str)

    def _evaluate_field_diff(
        self,
        saved_val: Any,
        working_val: Any,
        sec: str,
        key: str,
        is_profile: bool,
        full_key_path: str
    ) -> Optional[str]:
        """Subrutina unificada para evaluar si un campo (de negocio o perfil) difiere entre disco y memoria."""
        is_pwd = self._is_field_password(sec, key, is_profile=is_profile)
        if not self._compare_field_values(saved_val, working_val, is_password=is_pwd):
            return full_key_path
        return None

    def _are_configs_equal(self, early_exit: bool = False) -> List[str]:
        """
        Compara working_config contra current_config guiado estrictamente por el esquema.
        - early_exit=True: Retorna la lista con la primera diferencia encontrada inmediatamente.
        - early_exit=False (Por defecto): Recorre todo el árbol, acumula las claves modificadas
          e imprime el detalle de los campos con cambios pendientes.
        Retorna la lista de claves modificadas (vacía si son idénticos).
        """
        saved = self.current_config
        working = self.working_config
        modified_keys: List[str] = []

        # 1. Secciones de Negocio (Raíz)
        for sec, sec_data in working.items():
            if not is_business_section(sec):
                continue
            if not isinstance(sec_data, dict):
                continue

            saved_sec = saved.get(sec, {}) if isinstance(saved.get(sec), dict) else {}
            for key, working_val in sec_data.items():
                if is_schema_directive(key):
                    continue
                saved_val = saved_sec.get(key)
                diff = self._evaluate_field_diff(
                    saved_val=saved_val,
                    working_val=working_val,
                    sec=sec,
                    key=key,
                    is_profile=False,
                    full_key_path=f"{sec}.{key}"
                )
                if diff:
                    modified_keys.append(diff)
                    if early_exit:
                        return modified_keys

        # 2. Secciones Multiperfil (@profiles)
        if SECTION_PROFILES in working and isinstance(working[SECTION_PROFILES], dict):
            working_profs = working[SECTION_PROFILES]
            saved_profs = saved.get(SECTION_PROFILES, {}) if isinstance(saved.get(SECTION_PROFILES), dict) else {}

            prof_keys_w = [p for p in working_profs.keys() if not is_schema_directive(p)]
            prof_keys_s = [p for p in saved_profs.keys() if not is_schema_directive(p)]

            added_profs = set(prof_keys_w) - set(prof_keys_s)
            deleted_profs = set(prof_keys_s) - set(prof_keys_w)

            for p in added_profs:
                modified_keys.append(f"{SECTION_PROFILES}.{p} (Perfil Agregado)")
            for p in deleted_profs:
                modified_keys.append(f"{SECTION_PROFILES}.{p} (Perfil Eliminado)")

            if (added_profs or deleted_profs) and early_exit:
                return modified_keys

            for prof_code, sub_secs in working_profs.items():
                if is_schema_directive(prof_code) or not isinstance(sub_secs, dict) or prof_code in added_profs:
                    continue
                saved_sub_secs = saved_profs.get(prof_code, {}) if isinstance(saved_profs.get(prof_code), dict) else {}

                for sub_sec, fields in sub_secs.items():
                    if is_schema_directive(sub_sec) or not isinstance(fields, dict):
                        continue
                    saved_fields = saved_sub_secs.get(sub_sec, {}) if isinstance(saved_sub_secs.get(sub_sec), dict) else {}

                    for key, working_val in fields.items():
                        if is_schema_directive(key):
                            continue
                        saved_val = saved_fields.get(key)
                        diff = self._evaluate_field_diff(
                            saved_val=saved_val,
                            working_val=working_val,
                            sec=sub_sec,
                            key=key,
                            is_profile=True,
                            full_key_path=f"{SECTION_PROFILES}.{prof_code}.{sub_sec}.{key}"
                        )
                        if diff:
                            modified_keys.append(diff)
                            if early_exit:
                                return modified_keys

        if modified_keys:
            keys_fmt = "\n  • ".join(modified_keys)
            logging.info(f"[CONFIG] Cambios pendientes de guardar ({len(modified_keys)}):\n  • {keys_fmt}")

        return modified_keys

    def has_unsaved_changes(self, early_exit: bool = False) -> List[str]:
        """
        Verifica si existen cambios en la interfaz o en memoria respecto a los datos guardados en disco.
        Retorna la lista de claves modificadas (lista vacía si no hay cambios).
        """
        if not self.is_authenticated:
            return []
        self.flush_current_entries()
        try:
            return self._are_configs_equal(early_exit=early_exit)
        except Exception:
            return []

    def on_close(self):
        """Maneja el evento de cierre de la ventana, solicitando confirmación si hay cambios sin guardar."""
        if not self.is_authenticated:
            self.destroy()
            return
        diferencias = self.has_unsaved_changes()
        if diferencias:
            title = t18n("asiscfg.confirm_exit_title", "Cambios sin Guardar")
            detalle = "\n".join(f"  • {k}" for k in diferencias)
            msg = t18n(
                "asiscfg.confirm_exit_msg_detail",
                "Hay modificaciones sin guardar en la configuración:\n\n{detalle}\n\n¿Está seguro de que desea salir sin guardar los cambios?",
                detalle=detalle
            )
            if not messagebox.askyesno(title, msg, parent=self):
                return
        self.destroy()

    def _on_tab_change(self):
        """Callback invocado al cambiar de pestaña."""
        pass

    def resolve_test_params(self, mapping: dict, current_section_values: dict, full_working_config: dict, context: Optional[dict] = None) -> dict:
        """
        Resuelve los parámetros mapeados normalizando a lista de candidatos (Fallback Chaining)
        e interpolando comodines de contexto ([profile], [empresa_destino], etc.).
        Soporta:
          - Constantes/Literales explícitos: LITERAL("valor"), {"literal": "valor"}, "literal:valor"
          - Variables de la sección activa: "nombre_campo"
          - Variables de otras secciones (con herencia perfil -> global): "seccion.nombre_campo"
          - Listas de prioridad de búsqueda: ["campo_local", "general.campo_global", LITERAL("default")]
        """
        resolved = {}
        if not isinstance(mapping, dict):
            return resolved

        from asisdb.engine import interpolate_placeholders

        ctx = dict(context or {})
        active_profile = str(ctx.get("profile") or "").strip()
        current_sec_name = str(ctx.get("section") or "").strip()

        # Fase 1: Resolver el valor crudo de cada parámetro según el mapping y la jerarquía de herencia
        for param_name, source in mapping.items():
            candidates = [source] if not isinstance(source, (list, tuple)) else list(source)
            resolved[param_name] = ""
            for item in candidates:
                val = None

                # 1. Caso Diccionario Literal: LITERAL("...") / {"literal": "..."}
                if isinstance(item, dict) and "literal" in item:
                    val = item.get("literal")

                # 2. Caso String con Prefijo Literal: "literal:..."
                elif isinstance(item, str) and item.lower().startswith("literal:"):
                    val = item.split(":", 1)[1]

                # 3. Caso Referencia con Punto a otra sección: "info.empresa_destino" / "conexiones.host"
                elif isinstance(item, str) and "." in item:
                    parts = item.split(".", 1)
                    sec_part, key_part = parts[0], parts[1]
                    # Si estamos en contexto de perfil, buscar primero en el perfil activo (herencia en cascada)
                    if active_profile and SECTION_PROFILES in full_working_config:
                        prof_dict = full_working_config.get(SECTION_PROFILES, {}).get(active_profile, {})
                        if isinstance(prof_dict, dict) and sec_part in prof_dict and isinstance(prof_dict[sec_part], dict):
                            val = prof_dict[sec_part].get(key_part)
                    # Si no existe o está vacío en el perfil, buscar en la raíz global
                    if val is None or str(val).strip() == "":
                        val = full_working_config.get(sec_part, {}).get(key_part)

                # 4. Caso Referencia Local sin punto en la sección activa o fallback a sección raíz
                elif isinstance(item, str):
                    val = current_section_values.get(item)
                    if (val is None or str(val).strip() == "") and current_sec_name and current_sec_name in full_working_config:
                        val = full_working_config[current_sec_name].get(item)

                if val is not None and str(val).strip() != "":
                    resolved[param_name] = val
                    break

        # Fase 2: Enriquecer el contexto de interpolación con los valores resueltos
        for k, v in resolved.items():
            if v is not None and str(v).strip() != "":
                ctx[k] = v

        # Fase 3: Interpolar comodines ([clave] / {clave}) en todos los valores resueltos de texto
        for param_name, val in resolved.items():
            if isinstance(val, str) and ("[" in val or "{" in val):
                resolved[param_name] = interpolate_placeholders(val, ctx)
        return resolved

    def run_test_connection_action(self, sec_key: str, field_name: str, field_info: dict, is_profile: Optional[bool] = None):
        """Ejecuta la prueba de conexión declarada en el campo type='test_connection'."""
        self.flush_current_entries()

        has_profs = SECTION_PROFILES in self.working_config and isinstance(self.working_config[SECTION_PROFILES], dict) and len(self.working_config[SECTION_PROFILES]) > 0
        if is_profile is None:
            is_profile = bool(has_profs and self.active_profile and sec_key in self.profile_entries)

        if is_profile and has_profs and self.active_profile:
            prof_data = self.working_config.get(SECTION_PROFILES, {}).get(self.active_profile, {})
            sec_vals = dict(prof_data.get(sec_key, {}))
            profile_label = self.active_profile
            context = {
                "profile": self.active_profile,
                "section": sec_key
            }
        else:
            sec_vals = dict(self.working_config.get(sec_key, {}))
            profile_label = t18n("asiscfg.general_scope", "General")
            context = {
                "profile": "",
                "section": sec_key
            }


        mapping = field_info.get("mapping", {})
        resolved_params = self.resolve_test_params(mapping, sec_vals, self.working_config, context=context)

        # Si el botón declara un 'driver' explícito en su definición y no se obtuvo por mapping, tomarlo
        if "driver" not in resolved_params or not str(resolved_params.get("driver", "")).strip():
            if "driver" in field_info and str(field_info["driver"]).strip():
                resolved_params["driver"] = field_info["driver"]

        try:
            from asisdb.engine import test_connection
            driver = resolved_params.get("driver", "")
            other_params = {k: v for k, v in resolved_params.items() if k != "driver"}
            #TODO: Ver como pasar la clave encriptada, quizas un string special como [clave_encriptada,[metodo:Fernet],[key segun metodo]] y asisdb resolver en caliente
            exito, mensaje, diagnostico = test_connection(driver=driver, **other_params)
        except Exception as e:
            exito = False
            mensaje = t18n("asiscfg.err_test_db_exec", "Error al ejecutar la prueba de conexión: {err}", err=str(e))
            diagnostico = {"used_params": {}, "unused_params": [], "target_url": ""}

        raw_used = diagnostico.get("used_params")
        used_params = raw_used if isinstance(raw_used, dict) else {}

        raw_unused = diagnostico.get("unused_params")
        unused_params = [str(x) for x in raw_unused] if isinstance(raw_unused, (list, tuple, set)) else []

        target_url = str(diagnostico.get("target_url") or "")

        used_lines = "\n".join([f"  • {k}: {v}" for k, v in used_params.items()]) if used_params else "  • (Ninguno)"
        unused_lines = ", ".join(unused_params) if unused_params else "(Ninguno)"

        report_body = (
            f"Ámbito: {profile_label} | Sección: [{sec_key}]\n\n"
            f"Resultado: {mensaje}\n\n"
            f"🔗 Destino / Conexión:\n  {target_url or 'N/A'}\n\n"
            f"✅ Parámetros Utilizados:\n{used_lines}\n\n"
            f"⚪ Parámetros No Utilizados / Vacíos:\n  {unused_lines}"
        )

        from tkinter import messagebox
        if exito:
            title = t18n("asiscfg.test_db_success_title", "🔌 Prueba de Conexión Exitosa")
            messagebox.showinfo(title, report_body, parent=self)
        else:
            title = t18n("asiscfg.test_db_error_title", "❌ Falló la Prueba de Conexión")
            messagebox.showerror(title, report_body, parent=self)

    def get_default_translations_dict(self):
        """Retorna un diccionario completo con todas las claves e idioma base (es) de la aplicación."""
        data = {
            "_language_name": "Español",
            "_default": {
                "btn_accept": "Aceptar",
                "btn_close": "Cerrar",
                "btn_continue": "Continuar"
            },
            "asiscfg": {
                "about_desc": "Herramienta administrativa de gestión y mantenimiento de parámetros cifrados.\nCifrado Multi-Formato (Fernet, AES-256-GCM, ChaCha20, Plain) y Hashing PBKDF2 / SHA-256.\n\nDesarrollado por ASISNET.",
                "about_title": "Acerca de - Mantenimiento de Configuración",
                "about_version": "Versión 1.0.0 (Build 2026.10)",
                "add_profile_header": "👤 Registrar Nuevo Perfil",
                "add_profile_title": "Agregar Nuevo Perfil",
                "app_start": "Inicio de ejecución de asiscfg.",
                "audit_admin_pass_reset": "Clave de administración restablecida al valor por defecto via CLI en {path}.",
                "badge_format_status": "{icon} Origen de lectura: {name}",
                "btn_add_profile": "➕ Agregar",
                "btn_add_profile_confirm": "Crear Perfil",
                "btn_browse_backup_key": "📂 Buscar Respaldo .key",
                "btn_cancel_exit": "❌ Salir",
                "btn_copied": "✅ ¡Copiado!",
                "btn_copy_clipboard": "📋 Copiar al Portapapeles",
                "btn_copy_explanation": "📋 Copiar Explicación",
                "btn_copy_template": "📋 Copiar Plantilla",
                "btn_defaults": "🔄 Defectos",
                "btn_delete_profile": "🗑️ Eliminar",
                "btn_generate_new_key": "🔑 Generar Nuevo .key",
                "btn_login": "Ingresar",
                "btn_rename_confirm": "Guardar Código",
                "btn_rename_profile": "✏️ Renombrar",
                "btn_save": "💾 Grabar",
                "btn_save_explanation": "💾 Guardar Explicación...",
                "btn_save_file": "💾 Guardar como archivo...",
                "btn_save_pass": "Guardar Nueva Clave",
                "btn_save_template_py": "💾 Guardar Plantilla (.py)...",
                "btn_test_db": "🔌 Probar Conexión",
                "change_pass_header": "🔑 Cambiar Clave de Administración",
                "change_pass_title": "Cambiar Clave de Administración",
                "config": {
                    "out_of_range": "[APPLICATION] Parámetro '{param_key}' ({val}) en sección '{section}' fuera de rango [{min} - {max}]. Tomando default ({def_val})."
                },
                "confirm_delete_profile": "¿Está seguro de eliminar el perfil '{code}'?",
                "confirm_delete_title": "Confirmar Eliminación",
                "confirm_exit_msg_detail": "Hay modificaciones sin guardar en la configuración:\n\n{detalle}\n\n¿Está seguro de que desea salir sin guardar los cambios?",
                "confirm_exit_title": "Cambios sin Guardar",
                "confirm_import_msg": "¿Está seguro de cargar la configuración desde este respaldo?\nSe reemplazarán los valores actuales en pantalla.",
                "confirm_import_title": "Confirmar Importación",
                "confirm_reset_msg": "¿Está seguro de que desea restablecer todos los parámetros a los valores por defecto?\nSe perderán los cambios no guardados en memoria.",
                "confirm_reset_title": "Confirmar Valores por Defecto",
                "confirm_save_msg": "¿Está seguro de que desea guardar la configuración en formato {name} en {path}?",
                "confirm_save_title": "Confirmar Grabar ({name})",
                "current_config_header": "🛠️ Configuración Actual en Memoria",
                "current_config_subtitle": "Representación JSON de los parámetros cargados (contraseñas como <pass>):",
                "current_config_title": "Configuración Actual (Modo Dev)",
                "defaults_loaded": "ℹ️ Valores por defecto cargados.",
                "desc_unencrypted_dialog": "El archivo de configuración contiene los siguientes campos clave en texto plano.\nPara mayor seguridad, serán cifrados automáticamente cuando guarde los cambios.",
                "dev_mode": "Validación UAC omitida por parámetro --dev.",
                "dlg_select_backup_key": "Seleccionar Archivo de Clave de Respaldo",
                "err_cannot_delete_last_profile": "❌ No se puede eliminar el único perfil registrado. Debe existir al menos 1 perfil.",
                "err_config_file_not_found": "El archivo de configuración no existe: {path}",
                "err_config_header_invalid": "El archivo de configuración no contiene una cabecera de formato válida reconocida: {err}",
                "err_config_json_invalid": "El archivo de configuración contiene un JSON inválido.",
                "err_config_read": "No se pudo leer el archivo de configuración: {err}",
                "err_curr_pass_invalid": "❌ La clave actual es incorrecta.",
                "err_invalid_header": "El archivo no contiene una cabecera de formato válida reconocida: {path}",
                "err_key_admin_warning": "[ERROR] El archivo de clave .key está alterado o faltante ({detail}). Debe buscar un respaldo del archivo .key o generar uno nuevo con --generate-key (perdiendo los valores encriptados previamente).",
                "err_key_empty": "El archivo de clave está vacío (0 bytes).",
                "err_key_file_exists": "El archivo de clave ya existe: {path}",
                "err_key_file_read": "Error al leer el archivo de clave {path}: {e}",
                "err_key_file_write": "Error al crear el archivo de clave {path}: {e}",
                "err_key_invalid_engine": "La clave no posee un formato válido para el motor '{name}'.",
                "err_key_invalid_format": "El formato del archivo de clave no es válido para el modo '{mode}'.",
                "err_key_mismatch_field": "La clave está alterada o no coincide con los campos protegidos cifrados.",
                "err_key_mismatch_payload": "La clave está alterada o no coincide con los datos cifrados del archivo de configuración.",
                "err_key_not_found": "El archivo de clave no existe en la ruta: {path}",
                "err_key_read": "No se pudo leer el archivo de clave: {err}",
                "err_key_stop_execution": "[ERROR] El archivo de clave .key está alterado o faltante. Deteniendo la ejecución.",
                "err_pass_min_length": "❌ La nueva clave debe tener al menos 4 caracteres.",
                "err_pass_mismatch": "❌ La confirmación no coincide con la nueva clave.",
                "err_password_integrity": "Falla de integridad en campos de contraseña de configuración:\n{details}",
                "err_profile_code_empty": "❌ El código no puede estar vacío o contener solo espacios.",
                "err_profile_code_exists": "❌ El código de perfil '{code}' ya existe.",
                "err_profiles_missing": "El archivo de configuración '{path}' no contiene ningún perfil registrado bajo '{section}', el cual es requerido por el esquema.",
                "err_pwd_decrypt": "Existe, inicia con '{prefix}' pero falla al desencriptar ({err}).",
                "err_pwd_empty": "Existe pero no tiene valor (nulo).",
                "err_pwd_empty_prefix": "Existe, inicia con '{prefix}' pero no tiene valor.",
                "err_pwd_missing": "No existe la clave en el archivo físico (faltante).",
                "err_pwd_no_prefix": "Existe pero no inicia con prefijo '{prefix}'.",
                "err_save_pass": "Error al guardar: {err}",
                "err_test_db_exec": "Error al ejecutar la prueba de conexión: {err}",
                "err_val_above_max": "❌ El parámetro '{sec}.{param_key}' ({val}) es mayor al máximo permitido ({max}).",
                "err_val_below_min": "❌ El parámetro '{sec}.{param_key}' ({val}) es menor al mínimo permitido ({min}).",
                "err_val_not_int": "❌ El parámetro '{sec}.{param_key}' debe ser un número entero.",
                "err_val_not_number": "❌ El parámetro '{sec}.{param_key}' debe ser un valor numérico.",
                "err_wrong_pass": "❌ Clave incorrecta. Intentos restantes: {remaining}",
                "explanatory_schema_header": "💡 Esquema Explicativo (Estructura y Reglas)",
                "explanatory_schema_subtitle": "Guía explicativa de las etiquetas funcionales obligatorias y atributos de configuración:",
                "explanatory_schema_title": "Esquema Explicativo de Configuración",
                "ft_all_files": "Todos los archivos (*.*)",
                "ft_key_files": "Archivos de Clave (*.key)",
                "general_scope": "General",
                "hdr_current_val": "Valor Actual",
                "hdr_default_val": "Valor por Defecto",
                "hdr_file_val": "Valor según el Archivo",
                "hdr_key": "Clave",
                "hdr_param_path": "Dirección Completa del Parámetro",
                "hdr_unencrypted_dialog": "⚠️ Parámetros Protegidos sin Cifrar Detectados",
                "header_title_app": "Mantenimiento de Configuración ({app_name})",
                "key_recovery_hdr_corrupted": "⚠️ Archivo de Clave Criptográfica Alterado o Dañado",
                "key_recovery_hdr_missing": "⚠️ Archivo de Clave Criptográfica Faltante",
                "key_recovery_msg_corrupted_body": "El archivo de clave existe pero está alterado, dañado o no coincide con los datos cifrados.\n\nDetalle técnico: {detail}\n\nDebe buscar un respaldo del archivo .key original o generar un nuevo archivo de clave (tenga en cuenta que al generar una nueva clave se perderán los valores encriptados previamente).",
                "key_recovery_msg_missing_body": "No se encontró el archivo de clave de cifrado (.key) en la ubicación especificada.\n\nPara continuar, debe buscar un respaldo del archivo .key original o generar un nuevo archivo de clave (tenga en cuenta que al generar una nueva clave se perderán los valores encriptados previamente).",
                "key_recovery_path_lbl": "📁 Ruta de la Clave: {path}",
                "key_recovery_title": "⚠️ Archivo de Clave Requerido o Alterado",
                "lbl_active_profile": "👤 Perfil Activo:",
                "lbl_copy_from": "Copiar parámetros de:",
                "lbl_info_fields": "📋 Datos del Perfil (Sección info):",
                "lbl_profile_code": "Código de Perfil:",
                "lbl_target_path": "📁 Destino: {path}",
                "login_loading": "⏳ Cargando configuración...",
                "login_subtitle": "Ingrese la Clave Maestra de Administración para ingresar:",
                "login_title": "Acceso Restringido - Configuración",
                "menu_about": "ℹ️ Acerca de...",
                "menu_change_pass": "🔑 Cambiar Clave Administrador",
                "menu_current_config": "🛠️ Configuración Actual...",
                "menu_exit": "❌ Salir",
                "menu_explanatory_schema": "💡 Esquema Explicativo...",
                "menu_export": "📤 Exportar Configuración...",
                "menu_export_schema": "📄 Exportar Esquema (config_schema.py)...",
                "menu_file": "Archivo",
                "menu_help": "Ayuda",
                "menu_import": "📥 Importar Configuración...",
                "menu_schema_template": "📋 Plantilla...",
                "msg_admin_pass_reset": "[INFO] La clave de administración ha sido restablecida exitosamente al valor por defecto ('admin').",
                "msg_admin_required": "Esta herramienta requiere ejecutarse con privilegios elevados de Administrador del sistema operativo.\n\nPor favor, cierre la aplicación y ejecútela como Administrador.",
                "msg_confirm_create_config": "El archivo de configuración no existe en la ruta:\n\n{path}\n\n¿Desea crearlo ahora con los valores predeterminados?",
                "msg_confirm_generate_key": "¿Está seguro de que desea generar un nuevo archivo de clave criptográfica?\n\nADVERTENCIA: Se sobrescribirá el archivo de clave y se perderán todos los valores encriptados previamente. Las contraseñas y datos protegidos se restablecerán a los valores predeterminados del esquema.",
                "msg_dev_mode": "[INFO] Modo desarrollo activo (--dev). Validación de permisos UAC omitida.",
                "msg_export_error": "No se pudo exportar el respaldo:\n{err}",
                "msg_export_schema_error": "No se pudo generar el archivo de esquema:\n{err}",
                "msg_export_schema_success": "Esquema exportado correctamente a:\n{path}",
                "msg_export_success": "Respaldo exportado correctamente a:\n{path}",
                "msg_generate_key_error": "No se pudo generar la nueva clave:\n{err}",
                "msg_import_error": "No se pudo importar el respaldo:\n{err}",
                "msg_import_success": "📥 Respaldo importado exitosamente desde '{path}'.",
                "msg_invalid_key_backup": "El archivo de respaldo seleccionado no es válido o no coincide con la configuración:\n\n{detail}",
                "msg_key_generated": "[INFO] Archivo de clave Fernet generado exitosamente en: {path}",
                "msg_key_generated_reset": "Se ha generado una nueva clave criptográfica exitosamente y la configuración ha sido inicializada.",
                "msg_key_restored": "El archivo de clave criptográfica se ha restaurado exitosamente desde el respaldo.",
                "msg_param_restored": "ℹ️ Parámetro '{sec}.{param_key}' restaurado al valor por defecto.",
                "msg_profile_added": "✅ Perfil '{code}' agregado correctamente.",
                "msg_profile_deleted": "ℹ️ Perfil '{code}' eliminado.",
                "msg_profile_renamed": "✅ Código de perfil cambiado de '{old}' a '{new}'.",
                "msg_restore_error": "No se pudo copiar el archivo de clave de respaldo:\n{err}",
                "msg_save_error": "No se pudo guardar el archivo:\n{err}",
                "msg_save_success": "Archivo guardado correctamente en:\n{path}",
                "msg_uac_elevated": "[INFO] Proceso ejecutado con privilegios elevados de Administrador.",
                "opt_default_schema": "[ Esquema por Defecto ]",
                "pass_updated_success": "✅ Clave de administración actualizada correctamente.",
                "ph_confirm_pass": "Confirmar Nueva Clave...",
                "ph_curr_pass": "Clave Actual...",
                "ph_master_pass": "Clave Maestra...",
                "ph_new_pass": "Nueva Clave (mín. 4 caracteres)...",
                "ph_profile_code": "Código de Perfil...",
                "ph_rename_profile_code": "Nuevo Código de Perfil...",
                "rename_profile_header": "✏️ Renombrar Código de Perfil",
                "rename_profile_title": "Renombrar Perfil - {code}",
                "save_error": "❌ Error al guardar la configuración: {err}",
                "save_success_msg": "✅ Configuración guardada en formato {name} en {path}.",
                "schema_template_header": "📋 Plantilla de Esquema (config_schema.py)",
                "schema_template_subtitle": "Plantilla de referencia Python para la definición de esquemas y reglas de validación:",
                "schema_template_title": "Plantilla de Esquema de Configuración",
                "security_section_banner_ro": "🔒 Sección de Seguridad '{section}' (Solo Lectura. Use --app en CLI para modificar).",
                "security_section_banner_rw": "✏️ Sección de Seguridad '{section}' (Modo Edición Activo por --app).",
                "status_ready": "Listo - Sesión de administración autenticada.",
                "tab_master_general": "⚙️ Configuración General",
                "tab_master_profiles": "👤 Configuración por Perfil",
                "test_db_error_title": "❌ Falló la Prueba de Conexión",
                "test_db_success_title": "🔌 Prueba de Conexión Exitosa",
                "tip_add_profile": "Registrar un nuevo perfil en el archivo de configuración",
                "tip_copy_clipboard": "Copiar el contenido JSON al portapapeles",
                "tip_copy_explanation": "Copiar la explicación al portapapeles",
                "tip_copy_schema_py": "Copiar la plantilla de esquema al portapapeles",
                "tip_delete_profile": "Eliminar el perfil activo de la configuración",
                "tip_format_select": "Seleccionar formato de almacenamiento para el archivo",
                "tip_login": "Verificar clave maestra e ingresar al sistema",
                "tip_rename_profile": "Renombrar el código del perfil activo",
                "tip_reset_defaults": "Restablecer todos los campos a sus valores por defecto",
                "tip_reset_param": "Restablecer al valor por defecto",
                "tip_save": "Guardar la configuración en el formato seleccionado",
                "tip_save_explanation": "Guardar la explicación en un archivo de texto",
                "tip_save_file": "Guardar la configuración actual en un archivo JSON",
                "tip_save_schema_py": "Guardar la plantilla como archivo Python (.py)",
                "tip_test_db": "Ejecutar prueba de conexión con los parámetros actuales",
                "tip_toggle_pass": "Mostrar u ocultar contenido",
                "title": "Mantenimiento de Configuración - {app_name}",
                "title_admin_required": "Privilegios Requeridos",
                "title_confirm_create_config": "Crear Archivo de Configuración",
                "title_confirm_generate_key": "Confirmar Generación de Clave",
                "title_export_backup": "Exportar Respaldo Cifrado",
                "title_export_error": "❌ Error al Exportar",
                "title_export_schema": "Exportar Esquema de Configuración",
                "title_export_schema_error": "❌ Error al Exportar Esquema",
                "title_export_schema_success": "📄 Exportación de Esquema Exitosa",
                "title_export_success": "📤 Exportación Exitosa",
                "title_generate_key_error": "Error al Generar Clave",
                "title_import_backup": "Importar Respaldo Cifrado",
                "title_import_error": "❌ Error al Importar",
                "title_invalid_key_backup": "Clave de Respaldo Inválida",
                "title_key_generated": "Nueva Clave Generada",
                "title_key_restored": "Clave Restaurada",
                "title_reset_success": "🔄 Valores por Defecto",
                "title_restore_error": "Error al Restaurar Clave",
                "title_save_config_json": "Guardar Configuración Actual",
                "title_save_error": "❌ Error al Guardar",
                "title_save_explanation_txt": "Guardar Esquema Explicativo",
                "title_save_schema_py": "Guardar Plantilla de Esquema",
                "title_save_success": "💾 Guardado Exitoso",
                "title_unencrypted_dialog": "⚠️ Advertencia de Seguridad - Parámetros en Texto Claro",
                "title_warn": "Advertencia",
                "uac_elevated": "Proceso ejecutado con privilegios elevados de Administrador."
            }
        }        
        return data

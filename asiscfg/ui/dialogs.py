# -*- coding: utf-8 -*-
# SPDX-FileCopyrightText: 2026 Asisnet Computacion, CA <proyectos@asisnet.net>
# SPDX-License-Identifier: MIT
# Autor: Boris Pinto <borispinto@asisnet.net>
# File: asiscfg/ui/dialogs.py

"""
Diálogos modales CustomTkinter para la gestión de usuarios, perfiles y acerca de.
"""

import os
import shutil
import json
from tkinter import messagebox, filedialog
from typing import Optional, Dict, Any
import customtkinter as ctk

from asiscfg.ui.utils import t18n, apply_window_icon, PALETTE, CTkToolTip
from asiscfg.security import check_admin_password, set_admin_password, log_audit_event
from asiscfg.core import save_config
from asiscfg.constants import SECTION_PROFILES


class ChangeAdminPasswordDialog(ctk.CTkToplevel):
    """Diálogo modal para cambiar la Clave Maestra de Administración."""
    def __init__(self, parent):
        super().__init__(parent)
        self.parent = parent
        self.success = False

        self.title(t18n("asiscfg.change_pass_title", "Cambiar Clave de Administración"))
        self.geometry("440x330")
        self.resizable(False, False)
        self.transient(parent)
        self.grab_set()

        apply_window_icon(self)
        self._build_ui()

    def _build_ui(self):
        lbl_title = ctk.CTkLabel(
            self,
            text=t18n("asiscfg.change_pass_header", "🔑 Cambiar Clave de Administración"),
            font=ctk.CTkFont(size=16, weight="bold"),
            text_color=PALETTE["Header"]["text_color"]
        )
        lbl_title.pack(pady=(15, 10))

        self.entry_current = ctk.CTkEntry(
            self,
            show="*",
            width=280,
            height=34,
            placeholder_text=t18n("asiscfg.ph_curr_pass", "Clave Actual...")
        )
        self.entry_current.pack(pady=6)
        self.entry_current.focus_set()
        self.after(100, lambda: self.entry_current.focus_set() if self.entry_current.winfo_exists() else None)

        self.entry_new = ctk.CTkEntry(
            self,
            show="*",
            width=280,
            height=34,
            placeholder_text=t18n("asiscfg.ph_new_pass", "Nueva Clave (mín. 4 caracteres)...")
        )
        self.entry_new.pack(pady=6)

        self.entry_confirm = ctk.CTkEntry(
            self,
            show="*",
            width=280,
            height=34,
            placeholder_text=t18n("asiscfg.ph_confirm_pass", "Confirmar Nueva Clave...")
        )
        self.entry_confirm.pack(pady=6)
        self.entry_confirm.bind("<Return>", lambda e: self.process_change())

        self.lbl_error = ctk.CTkLabel(
            self,
            text="",
            font=ctk.CTkFont(size=11),
            text_color=PALETTE["Error"]["text_color"]
        )
        self.lbl_error.pack(pady=4)

        btn_save = ctk.CTkButton(
            self,
            text=t18n("asiscfg.btn_save_pass", "Guardar Nueva Clave"),
            font=ctk.CTkFont(size=13, weight="bold"),
            fg_color=PALETTE["MainButton"]["fg_color"],
            hover_color=PALETTE["MainButton"]["hover_color"],
            text_color=PALETTE["MainButton"]["text_color"],
            width=160,
            height=36,
            command=self.process_change
        )
        btn_save.pack(pady=10)

    def process_change(self):
        curr = self.entry_current.get().strip()
        new_pass = self.entry_new.get().strip()
        confirm_pass = self.entry_confirm.get().strip()

        if not check_admin_password(curr, getattr(self.parent, "current_config", None)):
            self.lbl_error.configure(
                text=t18n("asiscfg.err_curr_pass_invalid", "❌ La clave actual es incorrecta."),
                text_color=PALETTE["Error"]["text_color"]
            )
            return

        if len(new_pass) < 4:
            self.lbl_error.configure(
                text=t18n("asiscfg.err_pass_min_length", "❌ La nueva clave debe tener al menos 4 caracteres."),
                text_color=PALETTE["Error"]["text_color"]
            )
            return

        if new_pass != confirm_pass:
            self.lbl_error.configure(
                text=t18n("asiscfg.err_pass_mismatch", "❌ La confirmación no coincide con la nueva clave."),
                text_color=PALETTE["Error"]["text_color"]
            )
            return

        try:
            set_admin_password(self.parent, new_pass)
            if hasattr(self.parent, "context") and hasattr(self.parent, "working_config"):
                save_config(self.parent.context, self.parent.working_config)
            self.success = True
            cfg_file = getattr(self.parent, "config_file", "")
            log_audit_event("ADMIN_PASS_CHANGED", f"Clave de administración modificada exitosamente en {cfg_file}." if cfg_file else "Clave de administración modificada exitosamente en la configuración.")
            self.destroy()
        except Exception as e:
            self.lbl_error.configure(
                text=t18n("asiscfg.err_save_pass", "Error al guardar: {err}", err=str(e)),
                text_color=PALETTE["Error"]["text_color"]
            )


class AddProfileDialog(ctk.CTkToplevel):
    """Diálogo modal dinámico para registrar un nuevo perfil basándose en las claves de 'info'."""
    def __init__(self, parent, existing_profiles: list, working_profiles: dict, default_info: dict):
        super().__init__(parent)
        self.parent = parent
        self.existing_profiles = existing_profiles
        self.working_profiles = working_profiles
        self.default_info = default_info
        self.result = None  # (code, info_dict, copy_from)

        self.title(t18n("asiscfg.add_profile_title", "Agregar Nuevo Perfil"))
        self.geometry("480x540")
        self.resizable(False, False)
        self.transient(parent)
        self.grab_set()

        apply_window_icon(self)
        self.info_entries = {}
        self._build_ui()

    def _build_ui(self):
        lbl_title = ctk.CTkLabel(
            self,
            text=t18n("asiscfg.add_profile_header", "👤 Registrar Nuevo Perfil"),
            font=ctk.CTkFont(size=15, weight="bold"),
            text_color=PALETTE["Header"]["text_color"]
        )
        lbl_title.pack(pady=(12, 6))

        # Campo Código de Perfil (Obligatorio)
        row_code = ctk.CTkFrame(self, fg_color="transparent")
        row_code.pack(fill="x", padx=20, pady=4)
        
        lbl_code = ctk.CTkLabel(
            row_code,
            text=t18n("asiscfg.lbl_profile_code", "Código de Perfil:"),
            font=ctk.CTkFont(size=12, weight="bold"),
            width=150,
            anchor="w"
        )
        lbl_code.pack(side="left", padx=5)

        self.entry_code = ctk.CTkEntry(
            row_code,
            height=32,
            placeholder_text=t18n("asiscfg.ph_profile_code", "Código de Perfil...")
        )
        self.entry_code.pack(side="left", fill="x", expand=True, padx=5)
        self.entry_code.focus_set()

        # Selector de Copiar Parámetros desde
        row_copy = ctk.CTkFrame(self, fg_color="transparent")
        row_copy.pack(fill="x", padx=20, pady=4)

        lbl_copy = ctk.CTkLabel(
            row_copy,
            text=t18n("asiscfg.lbl_copy_from", "Copiar parámetros de:"),
            font=ctk.CTkFont(size=12, weight="bold"),
            width=150,
            anchor="w"
        )
        lbl_copy.pack(side="left", padx=5)

        copy_options = [t18n("asiscfg.opt_default_schema", "[ Esquema por Defecto ]")]
        self.code_map = {}
        for code, cdict in self.working_profiles.items():
            info = cdict.get("info", {}) if isinstance(cdict, dict) else {}
            desc = list(info.values())[0] if (isinstance(info, dict) and info) else code
            display_str = f"{code} - {desc}" if desc and desc != code else str(code)
            copy_options.append(display_str)
            self.code_map[display_str] = code

        self.combo_copy = ctk.CTkOptionMenu(
            row_copy,
            values=copy_options,
            height=32,
            command=self._on_copy_source_changed
        )
        self.combo_copy.pack(side="left", fill="x", expand=True, padx=5)

        # Scrollable frame para campos dinámicos de 'info'
        lbl_info_sec = ctk.CTkLabel(
            self,
            text=t18n("asiscfg.lbl_info_fields", "📋 Datos del Perfil (Sección info):"),
            font=ctk.CTkFont(size=12, weight="bold"),
            text_color=PALETTE["Header"]["text_color"],
            anchor="w"
        )
        lbl_info_sec.pack(fill="x", padx=25, pady=(8, 2))

        self.scroll_info = ctk.CTkScrollableFrame(self, corner_radius=6, height=150)
        self.scroll_info.pack(fill="both", expand=True, padx=20, pady=4)

        self.lbl_error = ctk.CTkLabel(
            self,
            text="",
            font=ctk.CTkFont(size=11),
            text_color=PALETTE["Error"]["text_color"]
        )
        self.lbl_error.pack(pady=2)

        btn_save = ctk.CTkButton(
            self,
            text=t18n("asiscfg.btn_add_profile_confirm", "Crear Perfil"),
            font=ctk.CTkFont(size=13, weight="bold"),
            fg_color=PALETTE["MainButton"]["fg_color"],
            hover_color=PALETTE["MainButton"]["hover_color"],
            text_color=PALETTE["MainButton"]["text_color"],
            width=160,
            height=36,
            command=self.process_add
        )
        btn_save.pack(pady=10)

        # Cargar campos iniciales desde la fuente seleccionada
        self._on_copy_source_changed(self.combo_copy.get())

    def _on_copy_source_changed(self, selected_display: str):
        for widget in self.scroll_info.winfo_children():
            widget.destroy()
        self.info_entries = {}

        source_code = self.code_map.get(selected_display)
        if source_code and source_code in self.working_profiles:
            prof_data = self.working_profiles[source_code]
            info_dict = prof_data.get("info", {}) if isinstance(prof_data, dict) else {}
        else:
            info_dict = self.default_info

        for key, val in info_dict.items():
            row = ctk.CTkFrame(self.scroll_info, fg_color="transparent")
            row.pack(fill="x", pady=3, padx=2)

            lbl_key = ctk.CTkLabel(
                row,
                text=f"{key}:",
                font=ctk.CTkFont(size=12),
                width=130,
                anchor="w"
            )
            lbl_key.pack(side="left", padx=4)

            entry_val = ctk.CTkEntry(
                row,
                height=30
            )
            entry_val.pack(side="left", fill="x", expand=True, padx=4)
            entry_val.insert(0, str(val if val is not None else ""))
            self.info_entries[key] = entry_val

    def process_add(self):
        raw_code = self.entry_code.get()
        code = raw_code.lstrip()

        if not code:
            self.lbl_error.configure(text=t18n("asiscfg.err_profile_code_empty", "❌ El código no puede estar vacío o contener solo espacios."))
            return

        if code in self.existing_profiles:
            self.lbl_error.configure(text=t18n("asiscfg.err_profile_code_exists", "❌ El código de perfil '{code}' ya existe.", code=code))
            return

        selected_copy = self.combo_copy.get()
        copy_from = self.code_map.get(selected_copy)

        new_info = {}
        for key, entry in self.info_entries.items():
            new_info[key] = entry.get().strip()

        self.result = (code, new_info, copy_from)
        self.destroy()


class RenameProfileDialog(ctk.CTkToplevel):
    """Diálogo modal para renombrar el código del perfil activo."""
    def __init__(self, parent, current_code: str, existing_profiles: list):
        super().__init__(parent)
        self.parent = parent
        self.current_code = current_code
        self.existing_profiles = existing_profiles
        self.result = None

        self.title(t18n("asiscfg.rename_profile_title", "Renombrar Perfil - {code}", code=current_code))
        self.geometry("420x240")
        self.resizable(False, False)
        self.transient(parent)
        self.grab_set()

        apply_window_icon(self)
        self._build_ui()

    def _build_ui(self):
        lbl_title = ctk.CTkLabel(
            self,
            text=t18n("asiscfg.rename_profile_header", "✏️ Renombrar Código de Perfil"),
            font=ctk.CTkFont(size=15, weight="bold"),
            text_color=PALETTE["Header"]["text_color"]
        )
        lbl_title.pack(pady=(15, 10))

        self.entry_code = ctk.CTkEntry(
            self,
            width=280,
            height=34,
            placeholder_text=t18n("asiscfg.ph_rename_profile_code", "Nuevo Código de Perfil...")
        )
        self.entry_code.pack(pady=5)
        self.entry_code.insert(0, self.current_code)
        self.entry_code.focus_set()

        self.lbl_error = ctk.CTkLabel(
            self,
            text="",
            font=ctk.CTkFont(size=11),
            text_color=PALETTE["Error"]["text_color"]
        )
        self.lbl_error.pack(pady=2)

        btn_save = ctk.CTkButton(
            self,
            text=t18n("asiscfg.btn_rename_confirm", "Guardar Código"),
            font=ctk.CTkFont(size=13, weight="bold"),
            fg_color=PALETTE["MainButton"]["fg_color"],
            hover_color=PALETTE["MainButton"]["hover_color"],
            text_color=PALETTE["MainButton"]["text_color"],
            width=160,
            height=36,
            command=self.process_rename
        )
        btn_save.pack(pady=10)

    def process_rename(self):
        raw_code = self.entry_code.get()
        new_code = raw_code.lstrip()

        if not new_code:
            self.lbl_error.configure(text=t18n("asiscfg.err_profile_code_empty", "❌ El código no puede estar vacío o contener solo espacios."))
            return

        if new_code != self.current_code and new_code in self.existing_profiles:
            self.lbl_error.configure(text=t18n("asiscfg.err_profile_code_exists", "❌ El código de perfil '{code}' ya existe.", code=new_code))
            return

        self.result = new_code
        self.destroy()


class AboutDialog(ctk.CTkToplevel):
    """Diálogo modal para mostrar información acerca de la aplicación."""
    def __init__(self, parent, app_name: str = "Sistema"):
        super().__init__(parent)
        self.parent = parent
        self.app_name = app_name

        self.title(t18n("asiscfg.about_title", "Acerca de - Mantenimiento de Configuración"))
        self.geometry("460x340")
        self.resizable(False, False)
        self.transient(parent)
        self.grab_set()

        apply_window_icon(self)
        self._build_ui()

    def _build_ui(self):
        lbl_icon = ctk.CTkLabel(
            self,
            text="⚙️",
            font=ctk.CTkFont(size=42)
        )
        lbl_icon.pack(pady=(20, 5))

        lbl_app = ctk.CTkLabel(
            self,
            text=f"Mantenimiento de Configuración Cifrada\n({self.app_name})",
            font=ctk.CTkFont(size=16, weight="bold"),
            text_color=PALETTE["Header"]["text_color"],
            justify="center"
        )
        lbl_app.pack(pady=4)

        lbl_ver = ctk.CTkLabel(
            self,
            text=t18n("asiscfg.about_version", "Versión 1.0.0 (Build 2026.10)"),
            font=ctk.CTkFont(size=12, weight="bold"),
            text_color=PALETTE["MainButton"]["fg_color"]
        )
        lbl_ver.pack(pady=2)

        lbl_desc = ctk.CTkLabel(
            self,
            text=t18n("asiscfg.about_desc",
                "Herramienta administrativa de gestión y mantenimiento de parámetros cifrados.\n"
                "Cifrado Multi-Formato (Fernet, AES-256-GCM, ChaCha20, Plain) y Hashing PBKDF2 / SHA-256.\n\n"
                "Desarrollado por ASISNET."
            ),
            font=ctk.CTkFont(size=11),
            text_color=PALETTE["Subtext"]["text_color"],
            justify="center"
        )
        lbl_desc.pack(pady=10)

        btn_close = ctk.CTkButton(
            self,
            text=t18n("btn_accept", "Aceptar"),
            font=ctk.CTkFont(size=12, weight="bold"),
            fg_color=PALETTE["MainButton"]["fg_color"],
            hover_color=PALETTE["MainButton"]["hover_color"],
            text_color=PALETTE["MainButton"]["text_color"],
            width=120,
            height=34,
            command=self.destroy
        )
        btn_close.pack(pady=(5, 15))


def mask_config_passwords(data: Any, validation_rules: Optional[Dict[str, Any]] = None, current_path: str = "") -> Any:
    """
    Recorre recursivamente la estructura de configuración y reemplaza valores por '<pass>'
    únicamente si la regla de validación del campo tiene is_password == True.
    """
    if isinstance(data, dict):
        masked_dict = {}
        for key, val in data.items():
            path_key = f"{current_path}.{key}" if current_path else key
            
            is_pass = False
            if validation_rules and isinstance(validation_rules, dict):
                sec_name = current_path.split(".")[-1] if current_path else ""
                rule = None
                if current_path.startswith(f"{SECTION_PROFILES}.") and sec_name:
                    tmpl = validation_rules.get(SECTION_PROFILES, {}).get("_template", {})
                    if isinstance(tmpl, dict) and sec_name in tmpl:
                        rule = tmpl[sec_name].get(key)

                if not rule:
                    if sec_name:
                        rule = validation_rules.get(sec_name, {}).get(key)
                    else:
                        rule = validation_rules.get(key)
                
                if isinstance(rule, dict) and rule.get("is_password") is True:
                    is_pass = True

            if is_pass and not isinstance(val, (dict, list)):
                masked_dict[key] = "<pass>"
            else:
                masked_dict[key] = mask_config_passwords(val, validation_rules, path_key)
        return masked_dict
    elif isinstance(data, list):
        return [mask_config_passwords(item, validation_rules, current_path) for item in data]
    else:
        return data


class CurrentConfigDialog(ctk.CTkToplevel):
    """Diálogo modal para mostrar la configuración actual con valores enmascarados (<pass>)."""
    def __init__(self, parent, config_data: dict, validation_rules: Optional[dict] = None):
        super().__init__(parent)
        self.parent = parent
        self.config_data = config_data or {}
        self.validation_rules = validation_rules or {}

        self.title(t18n("asiscfg.current_config_title", "Configuración Actual (Modo Dev)"))
        self.geometry("680x540")
        self.minsize(580, 400)
        self.transient(parent)
        self.grab_set()

        apply_window_icon(self)
        self._build_ui()

    def _build_ui(self):
        lbl_header = ctk.CTkLabel(
            self,
            text=t18n("asiscfg.current_config_header", "🛠️ Configuración Actual en Memoria"),
            font=ctk.CTkFont(size=16, weight="bold"),
            text_color=PALETTE["Header"]["text_color"]
        )
        lbl_header.pack(pady=(15, 2))

        lbl_sub = ctk.CTkLabel(
            self,
            text=t18n("asiscfg.current_config_subtitle", "Representación JSON de los parámetros cargados (contraseñas como <pass>):"),
            font=ctk.CTkFont(size=11),
            text_color=PALETTE["Subtext"]["text_color"]
        )
        lbl_sub.pack(pady=(0, 8))

        masked_data = mask_config_passwords(self.config_data, self.validation_rules)
        self.json_text = json.dumps(masked_data, indent=4, ensure_ascii=False)

        self.textbox = ctk.CTkTextbox(
            self,
            font=ctk.CTkFont(family="Consolas", size=12),
            wrap="none",
            corner_radius=8
        )
        self.textbox.pack(fill="both", expand=True, padx=15, pady=5)
        self.textbox.insert("1.0", self.json_text)
        self.textbox.configure(state="disabled")

        btn_frame = ctk.CTkFrame(self, fg_color="transparent")
        btn_frame.pack(fill="x", padx=15, pady=(8, 15))

        btn_save = ctk.CTkButton(
            btn_frame,
            text=t18n("asiscfg.btn_save_file", "💾 Guardar como archivo..."),
            font=ctk.CTkFont(size=12, weight="bold"),
            fg_color=PALETTE["MainButton"]["fg_color"],
            hover_color=PALETTE["MainButton"]["hover_color"],
            text_color=PALETTE["MainButton"]["text_color"],
            height=34,
            command=self.save_to_file
        )
        btn_save.pack(side="left", padx=(0, 6))

        self.btn_copy = ctk.CTkButton(
            btn_frame,
            text=t18n("asiscfg.btn_copy_clipboard", "📋 Copiar al Portapapeles"),
            font=ctk.CTkFont(size=12, weight="bold"),
            fg_color=PALETTE["SecondaryButton"]["fg_color"],
            hover_color=PALETTE["SecondaryButton"]["hover_color"],
            text_color=PALETTE["SecondaryButton"]["text_color"],
            height=34,
            command=self.copy_to_clipboard
        )
        self.btn_copy.pack(side="left", padx=6)

        btn_close = ctk.CTkButton(
            btn_frame,
            text=t18n("btn_close", "Cerrar"),
            font=ctk.CTkFont(size=12, weight="bold"),
            fg_color=PALETTE["SecondaryButton"]["fg_color"],
            hover_color=PALETTE["SecondaryButton"]["hover_color"],
            text_color=PALETTE["SecondaryButton"]["text_color"],
            height=34,
            width=90,
            command=self.destroy
        )
        btn_close.pack(side="right")

        CTkToolTip(btn_save, t18n("asiscfg.tip_save_file", "Guardar la configuración actual en un archivo JSON"))
        CTkToolTip(self.btn_copy, t18n("asiscfg.tip_copy_clipboard", "Copiar el contenido JSON al portapapeles"))

    def save_to_file(self):
        dest_path = filedialog.asksaveasfilename(
            parent=self,
            title=t18n("asiscfg.title_save_config_json", "Guardar Configuración Actual"),
            initialfile="config_actual.json",
            filetypes=[("Archivos JSON (*.json)", "*.json"), ("Archivos de Texto (*.txt)", "*.txt"), ("Todos los archivos", "*.*")]
        )
        if dest_path:
            try:
                with open(dest_path, "w", encoding="utf-8") as f:
                    f.write(self.json_text)
                messagebox.showinfo(
                    t18n("asiscfg.title_save_success", "💾 Guardado Exitoso"),
                    t18n("asiscfg.msg_save_success", "Archivo guardado correctamente en:\n{path}", path=dest_path),
                    parent=self
                )
            except Exception as e:
                messagebox.showerror(
                    t18n("asiscfg.title_save_error", "❌ Error al Guardar"),
                    t18n("asiscfg.msg_save_error", "No se pudo guardar el archivo:\n{err}", err=str(e)),
                    parent=self
                )

    def copy_to_clipboard(self):
        self.clipboard_clear()
        self.clipboard_append(self.json_text)
        old_text = self.btn_copy.cget("text")
        self.btn_copy.configure(text=t18n("asiscfg.btn_copied", "✅ ¡Copiado!"))
        self.after(2000, lambda: self.btn_copy.configure(text=old_text) if self.btn_copy.winfo_exists() else None)


SCHEMA_MODEL_TEMPLATE_PYTHON = '''"""
Módulo de Esquema de Configuración Unificado (Modelo Estándar).
Define el diccionario por defecto, la plantilla multi-perfil y las reglas de validación.
"""

from typing import Dict, Any

try:
    from asisdb import get_supported_drivers, LITERAL
    SUPPORTED_DRIVERS = get_supported_drivers()
except ImportError:
    SUPPORTED_DRIVERS = ["mssql", "postgresql", "mysql", "sqlite", "foxpro"]
    def LITERAL(val): return {"literal": val}

try:
    from asiscfg import SCHEMA_KEY
except ImportError:
    def SCHEMA_KEY(key_path): return {"schema_key": key_path}


DEFAULT_CONFIG: Dict[str, Any] = {
    # ── 0. Política de Respaldos Automáticos (_backup) ──
    # Opcional: si se omite, toma los valores estándar {ROOT}/backups con rotación a 20 archivos.
    "_backup": {
        "enabled": True,
        "method": "timestamp",               # "timestamp" (histórico con fecha), "simple" (.bak fijo), "none"
        "target_dir": "{ROOT}/backups",      # Ruta fija con {ROOT} o clave dinámica: SCHEMA_KEY("paths.path_backup")
        "filename_pattern": "{TIMESTAMP}-{BASENAME}{EXT}.bak",
        "max_backups": 20                    # Máximo de respaldos históricos a conservar (0 = ilimitado)
    },

    # ── 1. Secciones Globales (Pestañas Generales) ──
    "app": {
        "name": {"default": "ASISNET - Connector", "description": "t18n#Nombre de la aplicación o sistema receptor."},
        "version": {"default": "v1.0.0", "description": "t18n#Versión del sistema conector."},
        "client": {"default": "ASISNET", "description": "t18n#Nombre del cliente."}
    },
    "paths": {
        "resources": {"default": "resources", "description": "t18n#Ruta relativa del directorio de recursos."},
        "languages": {"default": "resources/languages", "description": "t18n#Ruta relativa del directorio de idiomas e i18n."},
        "logs": {"default": "logs", "description": "t18n#Ruta relativa del directorio de archivos de log."},
        "fox_base_path": {"default": "C:\\\\ORBIS\\\\ORBISDAT\\\\[empresa_origen]", "description": "t18n#Plantilla de ruta base FoxPro (soporta comodines como [empresa_origen])."}
    },
    "general": {
        "active_language": {"default": "es", "description": "t18n#Código del idioma activo del sistema (ej. es)."},
        "log_filename_pattern": {"default": "%Y%m%d - Log.log", "description": "t18n#Patrón de formato de fecha para logs."},
        # ── Conexión SQL Global (Heredada por defecto por todos los perfiles) ──
        "sql_driver": {"default": "mssql", "description": "t18n#Motor de base de datos SQL global.", "type": "enum", "options": SUPPORTED_DRIVERS},
        "sql_host": {"default": "", "description": "t18n#Servidor SQL principal para todos los perfiles."},
        "sql_port": {"default": "", "description": "t18n#Puerto de escucha TCP/IP del servicio SQL."},
        "sql_user": {"default": "", "description": "t18n#Usuario SQL principal."},
        "sql_password": {"default": "", "description": "t18n#Contraseña SQL principal.", "is_password": True},
        "sql_database": {"default": "DAT[empresa_destino]SRVSQL", "description": "t18n#Plantilla de Base de Datos (usa comodines ejemplo: [empresa_destino])."},
        "sql_driver_autodetect": {"default": True, "description": "t18n#Autodetectar Driver ODBC instalado en Windows.", "type": "bool"}
    },

    # ── 2. Módulo Multi-Perfil ──
    "@profiles": {
        # Plantilla (_template) que define pestañas, campos y validaciones de TODOS los perfiles

        "_template": {
            "info": {
                "name": {"default": "", "description": "t18n#Nombre del perfil."},
                "empresa_origen": {"default": "01", "description": "t18n#Código de Empresa Origen (FoxPro / SA)."},
                "empresa_destino": {"default": "01", "description": "t18n#Código de Empresa Destino (SQL Server)."}
            },
            "db_sa": {
                "driver": {"default": "foxpro", "description": "t18n#Motor/Driver de base de datos administrativa.", "type": "enum", "options": SUPPORTED_DRIVERS},
                "path": {"default": "", "description": "t18n#Ruta FoxPro específica (dejar vacío para heredar plantilla de paths)."},
                "btn_test_sa": {
                    "type": "test_connection",
                    "description": "t18n#📁 Probar Conexión FoxPro/SA",
                    "mapping": {
                        "driver": "driver",
                        "path": ["path", "paths.fox_base_path"],
                        "empresa_origen": "info.empresa_origen",
                        "empresa_destino": "info.empresa_destino"
                    }
                }
            },
            "db_connector": {
                # Campos opcionales: si se dejan vacíos, heredan automáticamente de [general]
                "host": {"default": "", "description": "t18n#Servidor SQL específico (dejar vacío para usar general)."},
                "database": {"default": "", "description": "t18n#Base de datos específica (dejar vacío para usar plantilla general)."},
                "user": {"default": "", "description": "t18n#Usuario SQL específico (dejar vacío para usar general)."},
                "password": {"default": "", "description": "t18n#Contraseña específica (dejar vacío para usar general).", "is_password": True},
                "btn_test_connector": {
                    "type": "test_connection",
                    "description": "t18n#🔌 Probar Conexión Base de Datos",
                    "mapping": {
                        "driver": ["general.sql_driver", LITERAL("mssql")],
                        "host": ["host", "general.sql_host"],
                        "port": ["general.sql_port"],
                        "database": ["database", "general.sql_database"],
                        "user": ["user", "general.sql_user"],
                        "password": ["password", "general.sql_password"],
                        "empresa_destino": "info.empresa_destino",
                        "empresa_origen": "info.empresa_origen",
                        "sql_driver_autodetect": ["general.sql_driver_autodetect"]
                    }
                }
            },
            "api": {
                "system_name": {"default": "The Factory", "description": "t18n#Nombre del proveedor o servicio API."},
                "url": {"default": "https://dnv2.thefactory.com/", "description": "t18n#Endpoint o URL base del servicio web API."},
                "user": {"default": "demo_user", "description": "t18n#Usuario o identificador de acceso al API."},
                "password": {"default": "demo_password", "description": "t18n#Clave o contraseña de autenticación al API.", "is_password": True},
                "token": {"default": "", "description": "t18n#Token de seguridad o API Key para firmas.", "is_password": True},
                "retry_delay_seconds": {"default": 30, "description": "t18n#Segundos de espera entre reintentos.", "type": "int", "min": 5, "max": 300},
                "max_retry_attempts": {"default": 3, "description": "t18n#Número máximo de reintentos.", "type": "int", "min": 0, "max": 10},
                "tolerance_bs": {"default": 10.00, "description": "t18n#Tolerancia máxima de descuadre en Bs.", "type": "float", "min": 0, "max": 100},
                "tolerance_fx": {"default": 1.00, "description": "t18n#Tolerancia máxima de descuadre en Divisas.", "type": "float", "min": 0, "max": 100}
            }
        },

        # Perfil inicial concreto (solo define sus códigos o sobreescrituras particulares)
        "01": {
            "info": {
                "name": "Empresa Principal",
                "empresa_origen": "01",
                "empresa_destino": "01"
            },
            "db_sa": {
                "driver": "foxpro",
                "path": ""
            },
            "db_connector": {
                "host": "",
                "database": ""
            },
            "api": {
                "system_name": "The Factory",
                "url": "https://dnv2.thefactory.com/",
                "user": "demo_user"
            }
        }
    }
}
'''

class SchemaModelDialog(ctk.CTkToplevel):
    """Diálogo modal para mostrar la plantilla / código base del esquema de configuración."""
    def __init__(self, parent):
        super().__init__(parent)
        self.parent = parent

        self.title(t18n("asiscfg.schema_template_title", "Plantilla de Esquema de Configuración"))
        self.geometry("720x560")
        self.minsize(620, 420)
        self.transient(parent)
        self.grab_set()

        apply_window_icon(self)
        self._build_ui()

    def _build_ui(self):
        lbl_header = ctk.CTkLabel(
            self,
            text=t18n("asiscfg.schema_template_header", "📋 Plantilla de Esquema (config_schema.py)"),
            font=ctk.CTkFont(size=16, weight="bold"),
            text_color=PALETTE["Header"]["text_color"]
        )
        lbl_header.pack(pady=(15, 2))

        lbl_sub = ctk.CTkLabel(
            self,
            text=t18n("asiscfg.schema_template_subtitle", "Plantilla de referencia Python para la definición de esquemas y reglas de validación:"),
            font=ctk.CTkFont(size=11),
            text_color=PALETTE["Subtext"]["text_color"]
        )
        lbl_sub.pack(pady=(0, 8))

        self.python_code = SCHEMA_MODEL_TEMPLATE_PYTHON.strip()

        self.textbox = ctk.CTkTextbox(
            self,
            font=ctk.CTkFont(family="Consolas", size=12),
            wrap="none",
            corner_radius=8
        )
        self.textbox.pack(fill="both", expand=True, padx=15, pady=5)
        self.textbox.insert("1.0", self.python_code)
        self.textbox.configure(state="disabled")

        btn_frame = ctk.CTkFrame(self, fg_color="transparent")
        btn_frame.pack(fill="x", padx=15, pady=(8, 15))

        btn_save = ctk.CTkButton(
            btn_frame,
            text=t18n("asiscfg.btn_save_template_py", "💾 Guardar Plantilla (.py)..."),
            font=ctk.CTkFont(size=12, weight="bold"),
            fg_color=PALETTE["MainButton"]["fg_color"],
            hover_color=PALETTE["MainButton"]["hover_color"],
            text_color=PALETTE["MainButton"]["text_color"],
            height=34,
            command=self.save_to_file
        )
        btn_save.pack(side="left", padx=(0, 6))

        self.btn_copy = ctk.CTkButton(
            btn_frame,
            text=t18n("asiscfg.btn_copy_template", "📋 Copiar Plantilla"),
            font=ctk.CTkFont(size=12, weight="bold"),
            fg_color=PALETTE["SecondaryButton"]["fg_color"],
            hover_color=PALETTE["SecondaryButton"]["hover_color"],
            text_color=PALETTE["SecondaryButton"]["text_color"],
            height=34,
            command=self.copy_to_clipboard
        )
        self.btn_copy.pack(side="left", padx=6)

        btn_close = ctk.CTkButton(
            btn_frame,
            text=t18n("btn_close", "Cerrar"),
            font=ctk.CTkFont(size=12, weight="bold"),
            fg_color=PALETTE["SecondaryButton"]["fg_color"],
            hover_color=PALETTE["SecondaryButton"]["hover_color"],
            text_color=PALETTE["SecondaryButton"]["text_color"],
            height=34,
            width=90,
            command=self.destroy
        )
        btn_close.pack(side="right")

        CTkToolTip(btn_save, t18n("asiscfg.tip_save_schema_py", "Guardar la plantilla como archivo Python (.py)"))
        CTkToolTip(self.btn_copy, t18n("asiscfg.tip_copy_schema_py", "Copiar la plantilla de esquema al portapapeles"))

    def save_to_file(self):
        dest_path = filedialog.asksaveasfilename(
            parent=self,
            title=t18n("asiscfg.title_save_schema_py", "Guardar Plantilla de Esquema"),
            initialfile="config_schema.py",
            filetypes=[("Archivos Python (*.py)", "*.py"), ("Todos los archivos", "*.*")]
        )
        if dest_path:
            try:
                with open(dest_path, "w", encoding="utf-8") as f:
                    f.write(self.python_code)
                messagebox.showinfo(
                    t18n("asiscfg.title_save_success", "💾 Guardado Exitoso"),
                    t18n("asiscfg.msg_save_success", "Archivo guardado correctamente en:\n{path}", path=dest_path),
                    parent=self
                )
            except Exception as e:
                messagebox.showerror(
                    t18n("asiscfg.title_save_error", "❌ Error al Guardar"),
                    t18n("asiscfg.msg_save_error", "No se pudo guardar el archivo:\n{err}", err=str(e)),
                    parent=self
                )

    def copy_to_clipboard(self):
        self.clipboard_clear()
        self.clipboard_append(self.python_code)
        old_text = self.btn_copy.cget("text")
        self.btn_copy.configure(text=t18n("asiscfg.btn_copied", "✅ ¡Copiado!"))
        self.after(2000, lambda: self.btn_copy.configure(text=old_text) if self.btn_copy.winfo_exists() else None)


EXPLANATORY_SCHEMA_TEXT = '''===============================================================================
               ESTRUCTURA Y ARQUITECTURA DEL ESQUEMA (DEFAULT_CONFIG)
===============================================================================

1. ESTRUCTURA DE NIVELES Y ETIQUETAS FUNCIONALES
-------------------------------------------------------------------------------
DEFAULT_CONFIG = {
    # ── 0. DIRECTIVA RAÍZ: "_backup" (Política de Respaldos Automáticos) ──
    # Configuración opcional de resguardos automáticos antes de guardar cambios.
    "_backup": {
        "enabled": True,                           # Activar/desactivar respaldos
        "method": "timestamp",                     # "timestamp", "simple", "none"
        "target_dir": "{ROOT}/backups",            # Directorio ({ROOT} o SCHEMA_KEY)
        "filename_pattern": "{TIMESTAMP}-{BASENAME}{EXT}.bak",
        "max_backups": 20                          # Límite rotativo de retención
    },

    # ── 1. SECCIÓN DE SEGURIDAD PROTEGIDA: "app" ──
    # Define los metadatos globales del sistema o aplicación anfitriona.
    # Por defecto es de solo lectura salvo ejecución con flag CLI --app.
    "app": {
        "name": {"default": "Nombre Sistema", "description": "t18n#Nombre de la aplicación"},
        "version": {"default": "v1.0.0", "description": "t18n#Versión del sistema"}
    },

    # ── 2. SECCIONES GENERALES (Pestañas Globales: Seccion 1...N) ──
    # Cada clave superior (ej: "paths", "general", "Seccion_General_1") genera
    # automáticamente una pestaña en el panel general.
    "Seccion_General_1": {
        "Clave_1": {
            "default": "Valor por defecto",
            "description": "t18n#Texto descriptivo o ayuda contextual"
        },
        "Clave_2": {
            "default": 10,
            "type": "int",          # Tipos soportados: str, int, float, bool, enum, test_connection
            "min": 1,              # Límite mínimo para números
            "max": 100,            # Límite máximo para números
            "description": "Explicación del rango numérico"
        }
    },

    # ── 3. SECCIÓN ESPECIAL OBLIGATORIA: "@profiles" ──
    # Habilita el módulo Multi-Perfil con las siguientes subclaves:
    "@profiles": {
        # A. PLANTILLA MULTI-PERFIL ("_template"):
        # Define las pestañas y campos que tendrán TODOS los perfiles del sistema.
        "_template": {
            # Sub-sección obligatoria en cada perfil: "info"
            "info": {
                "name": {"default": "Nombre Perfil", "description": "t18n#Nombre o Descripción"},
                "empresa_destino": {"default": "01", "description": "t18n#Código destino"}
            },
            # Sub-secciones por perfil (Sección 1...N -> Pestañas por Perfil):
            "conexiones": {
                "database": {"default": "DAT[empresa_destino]SQL", "description": "Base de datos"},
                "btn_probar": {
                    "type": "test_connection",
                    "description": "t18n#🔌 Probar Conexión",
                    "mapping": {
                        "driver": "conexiones.driver",
                        "host": ["conexiones.host", "general.host"],
                        "database": "conexiones.database",
                        "user": ["conexiones.user", "general.user"],
                        "password": ["conexiones.password", "general.password"],
                        "empresa_destino": "info.empresa_destino"
                    }
                }
            }
        },

        # B. PERFIL INICIAL ("01"):
        # Valores por defecto para el primer perfil creado al inicializar.
        "01": {
            "info": {"name": "Perfil Principal", "empresa_destino": "01"},
            "conexiones": {"database": "DAT01SQL"}
        }
    }
}

===============================================================================
                     ATRIBUTOS SOPORTADOS POR CADA CAMPO
===============================================================================
- "default"         : [Cualquiera] Valor por defecto si el parámetro no existe.
- "description"     : [string] Texto descriptivo. Con prefijo "t18n#" se traduce automáticamente.
- "type"            : [string] "str" | "int" | "float" | "bool" | "enum" | "test_connection"
- "is_password"     : [bool] Si es True, enmascara el campo con asteriscos (***) y cifra en disco.
- "min" / "max"     : [int/float] Validadores numéricos automáticos de rango.
- "options"         : [list] Lista de opciones válidas para campos de tipo "enum".
- "mapping"         : [dict] Mapeo de parámetros para botones de tipo "test_connection".

===============================================================================
                  COMODINES DINÁMICOS Y HELPERS SOPORTADOS
===============================================================================
- [empresa_destino] / {empresa_destino} : Código de empresa destino activa (ej. '01', '02').
- [empresa_origen] / {empresa_origen}   : Código de empresa origen activa.
- [empresa] / {empresa}                 : Comodín genérico para interpolación de empresa.
- {ROOT}                                : Directorio base de la aplicación anfitriona.
- {TIMESTAMP}                           : Marca de tiempo en formato YYYYMMDD_HHMMSS para respaldos/logs.
- {BASENAME}                            : Nombre base del archivo sin extensión.
- {EXT}                                 : Extensión del archivo original.
- LITERAL(val)                          : Valor constante fijo dentro de un mapping de conexión.
- SCHEMA_KEY(key)                       : Referencia dinámica a otra clave de configuración por notación de puntos.
==============================================================================='''


class ExplanatorySchemaDialog(ctk.CTkToplevel):
    """Diálogo modal para mostrar el esquema explicativo de arquitectura y etiquetas."""
    def __init__(self, parent):
        super().__init__(parent)
        self.parent = parent

        self.title(t18n("asiscfg.explanatory_schema_title", "Esquema Explicativo de Configuración"))
        self.geometry("740x580")
        self.minsize(640, 440)
        self.transient(parent)
        self.grab_set()

        apply_window_icon(self)
        self._build_ui()

    def _build_ui(self):
        lbl_header = ctk.CTkLabel(
            self,
            text=t18n("asiscfg.explanatory_schema_header", "💡 Esquema Explicativo (Estructura y Reglas)"),
            font=ctk.CTkFont(size=16, weight="bold"),
            text_color=PALETTE["Header"]["text_color"]
        )
        lbl_header.pack(pady=(15, 2))

        lbl_sub = ctk.CTkLabel(
            self,
            text=t18n("asiscfg.explanatory_schema_subtitle", "Guía explicativa de las etiquetas funcionales obligatorias y atributos de configuración:"),
            font=ctk.CTkFont(size=11),
            text_color=PALETTE["Subtext"]["text_color"]
        )
        lbl_sub.pack(pady=(0, 8))

        self.explanatory_text = EXPLANATORY_SCHEMA_TEXT.strip()

        self.textbox = ctk.CTkTextbox(
            self,
            font=ctk.CTkFont(family="Consolas", size=12),
            wrap="none",
            corner_radius=8
        )
        self.textbox.pack(fill="both", expand=True, padx=15, pady=5)
        self.textbox.insert("1.0", self.explanatory_text)
        self.textbox.configure(state="disabled")

        btn_frame = ctk.CTkFrame(self, fg_color="transparent")
        btn_frame.pack(fill="x", padx=15, pady=(8, 15))

        btn_save = ctk.CTkButton(
            btn_frame,
            text=t18n("asiscfg.btn_save_explanation", "💾 Guardar Explicación..."),
            font=ctk.CTkFont(size=12, weight="bold"),
            fg_color=PALETTE["MainButton"]["fg_color"],
            hover_color=PALETTE["MainButton"]["hover_color"],
            text_color=PALETTE["MainButton"]["text_color"],
            height=34,
            command=self.save_to_file
        )
        btn_save.pack(side="left", padx=(0, 6))

        self.btn_copy = ctk.CTkButton(
            btn_frame,
            text=t18n("asiscfg.btn_copy_explanation", "📋 Copiar Explicación"),
            font=ctk.CTkFont(size=12, weight="bold"),
            fg_color=PALETTE["SecondaryButton"]["fg_color"],
            hover_color=PALETTE["SecondaryButton"]["hover_color"],
            text_color=PALETTE["SecondaryButton"]["text_color"],
            height=34,
            command=self.copy_to_clipboard
        )
        self.btn_copy.pack(side="left", padx=6)

        btn_close = ctk.CTkButton(
            btn_frame,
            text=t18n("btn_close", "Cerrar"),
            font=ctk.CTkFont(size=12, weight="bold"),
            fg_color=PALETTE["SecondaryButton"]["fg_color"],
            hover_color=PALETTE["SecondaryButton"]["hover_color"],
            text_color=PALETTE["SecondaryButton"]["text_color"],
            height=34,
            width=90,
            command=self.destroy
        )
        btn_close.pack(side="right")

        CTkToolTip(btn_save, t18n("asiscfg.tip_save_explanation", "Guardar la explicación en un archivo de texto"))
        CTkToolTip(self.btn_copy, t18n("asiscfg.tip_copy_explanation", "Copiar la explicación al portapapeles"))

    def save_to_file(self):
        dest_path = filedialog.asksaveasfilename(
            parent=self,
            title=t18n("asiscfg.title_save_explanation_txt", "Guardar Esquema Explicativo"),
            initialfile="esquema_explicativo.txt",
            filetypes=[("Archivos de Texto (*.txt)", "*.txt"), ("Todos los archivos", "*.*")]
        )
        if dest_path:
            try:
                with open(dest_path, "w", encoding="utf-8") as f:
                    f.write(self.explanatory_text)
                messagebox.showinfo(
                    t18n("asiscfg.title_save_success", "💾 Guardado Exitoso"),
                    t18n("asiscfg.msg_save_success", "Archivo guardado correctamente en:\n{path}", path=dest_path),
                    parent=self
                )
            except Exception as e:
                messagebox.showerror(
                    t18n("asiscfg.title_save_error", "❌ Error al Guardar"),
                    t18n("asiscfg.msg_save_error", "No se pudo guardar el archivo:\n{err}", err=str(e)),
                    parent=self
                )

    def copy_to_clipboard(self):
        self.clipboard_clear()
        self.clipboard_append(self.explanatory_text)
        old_text = self.btn_copy.cget("text")
        self.btn_copy.configure(text=t18n("asiscfg.btn_copied", "✅ ¡Copiado!"))
        self.after(2000, lambda: self.btn_copy.configure(text=old_text) if self.btn_copy.winfo_exists() else None)


class PlaintextPasswordsWarningDialog(ctk.CTkToplevel):
    """Diálogo modal de advertencia al detectar parámetros de clave/seguridad en texto claro."""
    def __init__(self, parent, unencrypted_params: list):
        super().__init__(parent)
        self.parent = parent
        self.unencrypted_params = unencrypted_params or []

        self.title(t18n("asiscfg.title_unencrypted_dialog", "⚠️ Advertencia de Seguridad - Parámetros en Texto Claro"))
        self.geometry("680x440")
        self.minsize(580, 360)
        self.transient(parent)
        self.grab_set()

        apply_window_icon(self)
        self._build_ui()

    def _build_ui(self):
        lbl_title = ctk.CTkLabel(
            self,
            text=t18n("asiscfg.hdr_unencrypted_dialog", "⚠️ Parámetros Protegidos sin Cifrar Detectados"),
            font=ctk.CTkFont(size=15, weight="bold"),
            text_color=PALETTE["Warning"]["text_color"]
        )
        lbl_title.pack(pady=(15, 4), padx=15, anchor="w")

        lbl_desc = ctk.CTkLabel(
            self,
            text=t18n("asiscfg.desc_unencrypted_dialog",
                "El archivo de configuración contiene los siguientes campos clave en texto plano.\n"
                "Para mayor seguridad, serán cifrados automáticamente cuando guarde los cambios."
            ),
            font=ctk.CTkFont(size=12),
            text_color=PALETTE["Subtext"]["text_color"],
            justify="left"
        )
        lbl_desc.pack(pady=(0, 10), padx=15, anchor="w")

        # Tabla / Contenedor desplazable
        scroll = ctk.CTkScrollableFrame(self, corner_radius=6)
        scroll.pack(fill="both", expand=True, padx=15, pady=5)

        # Encabezados
        hdr_frame = ctk.CTkFrame(scroll, fg_color="transparent")
        hdr_frame.pack(fill="x", pady=(2, 6), padx=5)
        hdr_frame.grid_columnconfigure(0, weight=1, uniform="warn_cols")
        hdr_frame.grid_columnconfigure(1, weight=1, uniform="warn_cols")

        lbl_h_path = ctk.CTkLabel(
            hdr_frame,
            text=t18n("asiscfg.hdr_param_path", "Dirección Completa del Parámetro"),
            font=ctk.CTkFont(size=12, weight="bold"),
            anchor="w",
            text_color=PALETTE["Header"]["text_color"]
        )
        lbl_h_path.grid(row=0, column=0, sticky="ew", padx=5)

        lbl_h_val = ctk.CTkLabel(
            hdr_frame,
            text=t18n("asiscfg.hdr_file_val", "Valor según el Archivo"),
            font=ctk.CTkFont(size=12, weight="bold"),
            anchor="w",
            text_color=PALETTE["Header"]["text_color"]
        )
        lbl_h_val.grid(row=0, column=1, sticky="ew", padx=5)

        for idx, (param_path, val) in enumerate(self.unencrypted_params):
            row_bg = PALETTE["Table"]["row_main"] if idx % 2 == 0 else PALETTE["Table"]["row_alt"]
            row_frame = ctk.CTkFrame(scroll, fg_color=row_bg, corner_radius=4)
            row_frame.pack(fill="x", pady=2, padx=5)
            row_frame.grid_columnconfigure(0, weight=1, uniform="warn_cols")
            row_frame.grid_columnconfigure(1, weight=1, uniform="warn_cols")

            lbl_p = ctk.CTkLabel(
                row_frame,
                text=str(param_path),
                font=ctk.CTkFont(size=12, weight="bold"),
                anchor="w",
                text_color=PALETTE["KeyLabel"]["text_color"]
            )
            lbl_p.grid(row=0, column=0, sticky="ew", padx=8, pady=4)

            val_str = str(val if val is not None else "")
            val_entry = ctk.CTkEntry(
                row_frame,
                font=ctk.CTkFont(size=12),
                height=30,
                text_color=PALETTE["Table"]["text_normal"],
                border_color=PALETTE["Table"]["border_inactive"]
            )
            val_entry.insert(0, val_str)
            val_entry.configure(state="readonly")
            val_entry.grid(row=0, column=1, sticky="ew", padx=8, pady=4)

        # Botonera inferior
        btn_frame = ctk.CTkFrame(self, fg_color="transparent")
        btn_frame.pack(fill="x", padx=15, pady=(8, 15))

        btn_continue = ctk.CTkButton(
            btn_frame,
            text=t18n("btn_continue", "Continuar"),
            font=ctk.CTkFont(size=13, weight="bold"),
            fg_color=PALETTE["MainButton"]["fg_color"],
            hover_color=PALETTE["MainButton"]["hover_color"],
            text_color=PALETTE["MainButton"]["text_color"],
            height=36,
            width=140,
            command=self.destroy
        )
        btn_continue.pack(side="right")


class KeyRecoveryDialog(ctk.CTkToplevel):
    """Diálogo modal para alertar y recuperar el archivo de clave criptográfica (.key) faltante o alterado."""
    def __init__(self, parent, status: str = "missing", detail: str = ""):
        super().__init__(parent)
        self.parent = parent
        self.status = status
        self.detail = detail
        self.action_result = "cancel"

        self.title(t18n("asiscfg.key_recovery_title", "⚠️ Archivo de Clave Requerido o Alterado"))
        self.geometry("580x430")
        self.minsize(540, 390)
        self.resizable(False, False)
        self.transient(parent)
        self.grab_set()

        apply_window_icon(self)
        self.protocol("WM_DELETE_WINDOW", self.on_cancel)
        self._build_ui()

    def _build_ui(self):
        header_text = (
            t18n("asiscfg.key_recovery_hdr_missing", "⚠️ Archivo de Clave Criptográfica Faltante")
            if self.status == "missing"
            else t18n("asiscfg.key_recovery_hdr_corrupted", "⚠️ Archivo de Clave Criptográfica Alterado o Dañado")
        )
        lbl_title = ctk.CTkLabel(
            self,
            text=header_text,
            font=ctk.CTkFont(size=16, weight="bold"),
            text_color=PALETTE["Warning"]["text_color"]
        )
        lbl_title.pack(pady=(18, 10), padx=20)

        card = ctk.CTkFrame(
            self,
            fg_color=PALETTE["Card"]["fg_color"],
            border_color=PALETTE["Card"]["border_color"],
            border_width=1,
            corner_radius=8
        )
        card.pack(fill="both", expand=True, padx=20, pady=10)

        key_path = getattr(self.parent, "key_file", "") or (self.parent.context.key_file_path if hasattr(self.parent, "context") else "")

        lbl_path = ctk.CTkLabel(
            card,
            text=t18n("asiscfg.key_recovery_path_lbl", "📁 Ruta de la Clave: {path}", path=key_path),
            font=ctk.CTkFont(size=12, weight="bold"),
            text_color=PALETTE["KeyLabel"]["text_color"],
            wraplength=490,
            justify="left"
        )
        lbl_path.pack(anchor="w", padx=16, pady=(14, 8))

        if self.status == "missing":
            msg_body = t18n(
                "asiscfg.key_recovery_msg_missing_body",
                "No se encontró el archivo de clave de cifrado (.key) en la ubicación especificada.\n\n"
                "Para continuar, debe buscar un respaldo del archivo .key original o generar un nuevo archivo de clave "
                "(tenga en cuenta que al generar una nueva clave se perderán los valores encriptados previamente)."
            )
        else:
            msg_body = t18n(
                "asiscfg.key_recovery_msg_corrupted_body",
                "El archivo de clave existe pero está alterado, dañado o no coincide con los datos cifrados.\n\n"
                "Detalle técnico: {detail}\n\n"
                "Debe buscar un respaldo del archivo .key original o generar un nuevo archivo de clave "
                "(tenga en cuenta que al generar una nueva clave se perderán los valores encriptados previamente).",
                detail=self.detail or "Clave no utilizable"
            )

        lbl_msg = ctk.CTkLabel(
            card,
            text=msg_body,
            font=ctk.CTkFont(size=12),
            text_color=PALETTE["TitleText"]["text_color"],
            wraplength=490,
            justify="left"
        )
        lbl_msg.pack(anchor="w", padx=16, pady=(0, 14))

        # Botonera de acciones
        btn_frame = ctk.CTkFrame(self, fg_color="transparent")
        btn_frame.pack(fill="x", padx=20, pady=(10, 18))

        btn_browse = ctk.CTkButton(
            btn_frame,
            text=t18n("asiscfg.btn_browse_backup_key", "📂 Buscar Respaldo .key"),
            font=ctk.CTkFont(size=12, weight="bold"),
            fg_color=PALETTE["MainButton"]["fg_color"],
            hover_color=PALETTE["MainButton"]["hover_color"],
            text_color=PALETTE["MainButton"]["text_color"],
            height=36,
            command=self.on_browse_backup
        )
        btn_browse.pack(side="left", padx=(0, 6), expand=True, fill="x")

        btn_generate = ctk.CTkButton(
            btn_frame,
            text=t18n("asiscfg.btn_generate_new_key", "🔑 Generar Nuevo .key"),
            font=ctk.CTkFont(size=12, weight="bold"),
            fg_color=PALETTE["DangerButton"]["fg_color"],
            hover_color=PALETTE["DangerButton"]["hover_color"],
            text_color=PALETTE["DangerButton"]["text_color"],
            height=36,
            command=self.on_generate_new_key
        )
        btn_generate.pack(side="left", padx=6, expand=True, fill="x")

        btn_cancel = ctk.CTkButton(
            btn_frame,
            text=t18n("asiscfg.btn_cancel_exit", "❌ Salir"),
            font=ctk.CTkFont(size=12, weight="bold"),
            fg_color=PALETTE["SecondaryButton"]["fg_color"],
            hover_color=PALETTE["SecondaryButton"]["hover_color"],
            text_color=PALETTE["SecondaryButton"]["text_color"],
            height=36,
            command=self.on_cancel
        )
        btn_cancel.pack(side="left", padx=(6, 0), expand=True, fill="x")

    def on_browse_backup(self):
        chosen_path = filedialog.askopenfilename(
            title=t18n("asiscfg.dlg_select_backup_key", "Seleccionar Archivo de Clave de Respaldo"),
            filetypes=[
                (t18n("asiscfg.ft_key_files", "Archivos de Clave (*.key)"), "*.key"),
                (t18n("asiscfg.ft_all_files", "Todos los archivos (*.*)"), "*.*")
            ],
            parent=self
        )
        if not chosen_path:
            return

        from asiscfg.core import verify_key_integrity, get_key
        # Probar la integridad de la clave seleccionada
        candidate_status, candidate_detail = verify_key_integrity(
            self.parent.context,
            config_path=self.parent.config_file,
            key_path=chosen_path
        )

        if candidate_status != "ok":
            messagebox.showerror(
                t18n("asiscfg.title_invalid_key_backup", "Clave de Respaldo Inválida"),
                t18n("asiscfg.msg_invalid_key_backup", "El archivo de respaldo seleccionado no es válido o no coincide con la configuración:\n\n{detail}", detail=candidate_detail),
                parent=self
            )
            return

        # Copiar el respaldo a la ruta canónica de la clave
        try:
            target_key_path = self.parent.key_file
            os.makedirs(os.path.dirname(os.path.abspath(target_key_path)), exist_ok=True)
            shutil.copy2(chosen_path, target_key_path)
            get_key(self.parent.context, forzar=True, key_path=target_key_path)
            log_audit_event("KEY_RESTORED_FROM_BACKUP", f"Clave restaurada desde {chosen_path} a {target_key_path}")
            messagebox.showinfo(
                t18n("asiscfg.title_key_restored", "Clave Restaurada"),
                t18n("asiscfg.msg_key_restored", "El archivo de clave criptográfica se ha restaurado exitosamente desde el respaldo."),
                parent=self
            )
            self.action_result = "restored"
            self.destroy()
        except Exception as e:
            messagebox.showerror(
                t18n("asiscfg.title_restore_error", "Error al Restaurar Clave"),
                t18n("asiscfg.msg_restore_error", "No se pudo copiar el archivo de clave de respaldo:\n{err}", err=e),
                parent=self
            )

    def on_generate_new_key(self):
        confirm = messagebox.askyesno(
            t18n("asiscfg.title_confirm_generate_key", "Confirmar Generación de Clave"),
            t18n("asiscfg.msg_confirm_generate_key",
                "¿Está seguro de que desea generar un nuevo archivo de clave criptográfica?\n\n"
                "ADVERTENCIA: Se sobrescribirá el archivo de clave y se perderán todos los valores encriptados previamente. "
                "Las contraseñas y datos protegidos se restablecerán a los valores predeterminados del esquema."
            ),
            parent=self
        )
        if not confirm:
            return

        from asiscfg.core import generate_key_file, save_config, get_key
        try:
            generate_key_file(self.parent.context, overwrite=True)
            get_key(self.parent.context, forzar=True)
            
            # Si el archivo de configuración existe, reescribir/reinicializar con la nueva clave
            if os.path.exists(self.parent.config_file):
                save_config(
                    self.parent.context,
                    self.parent.default_config,
                    validation_rules=self.parent.validation_rules,
                    default_config=self.parent.default_config,
                    format_mode=self.parent.context.format_mode
                )
            log_audit_event("KEY_REGENERATED", f"Nueva clave generada en {self.parent.key_file}")
            messagebox.showinfo(
                t18n("asiscfg.title_key_generated", "Nueva Clave Generada"),
                t18n("asiscfg.msg_key_generated_reset", "Se ha generado una nueva clave criptográfica exitosamente y la configuración ha sido inicializada."),
                parent=self
            )
            self.action_result = "generated"
            self.destroy()
        except Exception as e:
            messagebox.showerror(
                t18n("asiscfg.title_generate_key_error", "Error al Generar Clave"),
                t18n("asiscfg.msg_generate_key_error", "No se pudo generar la nueva clave:\n{err}", err=e),
                parent=self
            )

    def on_cancel(self):
        self.action_result = "exit"
        self.destroy()






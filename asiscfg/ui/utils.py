# -*- coding: utf-8 -*-
# SPDX-FileCopyrightText: 2026 Asisnet Computacion, CA <proyectos@asisnet.net>
# SPDX-License-Identifier: MIT
# Autor: Boris Pinto <borispinto@asisnet.net>
# File: asiscfg/ui/utils.py

"""
Utilidades auxiliares de UI, gestión de iconos e i18n para asiscfg.ui.
"""

import sys
import os
import ctypes
import logging
from typing import Optional

ASISCFG_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))


def setup_i18n_import() -> None:
    """
    Resuelve dinámicamente la ubicación del módulo i18n desde:
    1. Parámetros CLI (--i18n-path)
    2. Variable de entorno I18N_DIR
    3. Auto-descubrimiento en la jerarquía de carpetas superiores (hasta 4 niveles)
    4. Directorio de trabajo actual (CWD)
    """
    candidates = []

    for i, arg in enumerate(sys.argv):
        if arg in ("--i18n-path") and i + 1 < len(sys.argv):
            candidates.append(os.path.abspath(sys.argv[i + 1]))
        elif arg.startswith("--i18n-path="):
            candidates.append(os.path.abspath(arg.split("=", 1)[1]))

    if os.environ.get("I18N_DIR"):
        candidates.append(os.path.abspath(os.environ["I18N_DIR"]))

    curr = ASISCFG_DIR
    for _ in range(5):
        candidates.append(curr)
        parent = os.path.abspath(os.path.join(curr, ".."))
        if parent == curr:
            break
        curr = parent

    cwd = os.getcwd()
    candidates.append(cwd)
    candidates.append(os.path.abspath(os.path.join(cwd, "..")))

    for cand in candidates:
        if not cand or not os.path.exists(cand):
            continue

        if os.path.basename(cand).lower() in ("i18n", "i18n") or (os.path.isfile(cand) and cand.endswith(".py")):
            parent_dir = os.path.dirname(cand)
            if parent_dir not in sys.path:
                sys.path.insert(0, parent_dir)
        else:
            if cand not in sys.path:
                sys.path.insert(0, cand)


from i18n import t18n, get_i18n_instance
I18N_AVAILABLE = True


def find_asiscfg_lang_dir() -> Optional[str]:
    """Localiza el directorio interno de idiomas propio de asiscfg."""
    if hasattr(sys, "_MEIPASS"):
        p1 = os.path.join(sys._MEIPASS, "asiscfg", "resources", "languages")
        if os.path.exists(p1):
            return p1
        p1_res = os.path.join(sys._MEIPASS, "resources", "languages")
        if os.path.exists(p1_res):
            return p1_res

    p2 = os.path.join(ASISCFG_DIR, "asiscfg", "resources", "languages")
    if os.path.exists(p2):
        return p2

    p2_res = os.path.join(ASISCFG_DIR, "resources", "languages")
    if os.path.exists(p2_res):
        return p2_res

    return None


def find_logo_icon_path() -> Optional[str]:
    """Busca el archivo de icono logo.ico en las rutas estándar de desarrollo o PyInstaller."""
    candidates = []

    # 1. Rutas en entorno empaquetado (PyInstaller _MEIPASS)
    if hasattr(sys, "_MEIPASS"):
        candidates.extend([
            os.path.join(sys._MEIPASS, "resources", "logo.ico"),
            os.path.join(sys._MEIPASS, "asiscfg", "resources", "logo.ico"),
            os.path.join(sys._MEIPASS, "logo.ico")
        ])

    # 2. Rutas relativas al ejecutable o directorio de ejecución
    if getattr(sys, "frozen", False):
        exe_dir = os.path.dirname(sys.executable)
        candidates.extend([
            os.path.join(exe_dir, "resources", "logo.ico"),
            os.path.join(exe_dir, "logo.ico")
        ])

    # 3. Rutas en entorno de desarrollo
    candidates.extend([
        os.path.join(ASISCFG_DIR, "resources", "logo.ico"),
        os.path.join(ASISCFG_DIR, "asiscfg", "resources", "logo.ico"),
        os.path.join(os.path.dirname(__file__), "..", "..", "resources", "logo.ico"),
        os.path.join(os.path.dirname(__file__), "..", "resources", "logo.ico"),
        os.path.join(os.getcwd(), "resources", "logo.ico"),
        os.path.join(os.getcwd(), "logo.ico")
    ])

    for p in candidates:
        if p and os.path.exists(p):
            return os.path.abspath(p)

    return None


def apply_window_icon(root_window) -> bool:
    """Aplica el icono institucional a la ventana Tkinter/CustomTkinter."""
    icon_path = find_logo_icon_path()
    if not icon_path or not os.path.exists(icon_path):
        return False

    try:
        if sys.platform.startswith("win"):
            try:
                app_id = "comsisa.asiscfg.app.1.0"
                ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID(app_id)
            except Exception:
                pass

        root_window.iconbitmap(icon_path)
        return True
    except Exception as e:
        logging.warning(f"No se pudo aplicar el icono de la ventana: {e}")
        return False


import tkinter as tk

PALETTE = {
    # 1. Botones de Acción Principal (Guardar, Aceptar, Procesar)
    "MainButton": {
        "fg_color": ("#2FA572", "#2FA572"),
        "hover_color": ("#248259", "#248259"),
        "text_color": ("#FFFFFF", "#FFFFFF")
    },
    # 2. Botones Secundarios / Auxiliares
    "SecondaryButton": {
        "fg_color": ("#E0E0E0", "#3B3E45"),
        "hover_color": ("#D0D0D0", "#4A4D56"),
        "text_color": ("#1A1A1A", "#FFFFFF")
    },
    # 3. Botones de Peligro / Reset (Restablecer, Cancelar/Eliminar)
    "DangerButton": {
        "fg_color": ("#C0392B", "#C0392B"),
        "hover_color": ("#922B21", "#922B21"),
        "text_color": ("#FFFFFF", "#FFFFFF")
    },
    # 4. Encabezados y Títulos
    "Header": {
#        "text_color": ("#2FA572", "#2FA572")
        "text_color": ("#000000", "#FFFFFF")
    },
    "TitleText": {
        "text_color": ("#1A1A1A", "#E6E6E6")
    },
    "Subtext": {
        "text_color": ("#555555", "#9A9FA8")
    },
    # 5. Estados y Retroalimentación Visual
    "Error": {
        "text_color": ("#FF3333", "#FF3333")
    },
    "Success": {
        "text_color": ("#2FA572", "#2FA572")
    },
    "Warning": {
        "text_color": ("#D97706", "#E67E22")
    },
    "KeyLabel": {
        "text_color": ("#0284C7", "#38BDF8")
    },
    # 6. Enlaces, Separadores y Textos Secundarios
    "Link": {
        "text_color": ("#1F6AA5", "#3B8ED0")
    },
    "Separator": {
        "fg_color": ("#CCCCCC", "#555555")
    },
    "Disabled": {
        "text_color": "gray",
        "fg_color": ("#F2F2F2", "#25262B")
    },
    # 7. Contenedores y Tarjetas
    "Card": {
        "fg_color": ("#F8F9FA", "#1E1E22"),
        "sub_fg_color": ("#EAEAEA", "#25262B"),
        "border_color": ("#CCCCCC", "#3A3A3A")
    },
    # 8. Tablas / Listas / Listbox (Efecto Cebra y Selección)
    "Table": {
        "row_main": ("#FFFFFF", "#1D1E22"),
        "row_alt": ("#F2F2F2", "#2E3038"),
        "text_normal": ("#1A1A1A", "#E6E6E6"),
        "selection_bg": ("#3B8ED0", "#1F6AA5"),
        "selection_text": ("#FFFFFF", "#FFFFFF"),
        "border_inactive": ("#CCCCCC", "#3A3A3A"),
        "error_text": "#FF3333"
    },
    # 9. Tooltips / Mensajes Flotantes
    "Tooltip": {
        "bg_color": ("#FFFFE0", "#82F19A"),
        "text_color": ("#000000", "#0C0B0B"),
        "border_color": ("#CCCCCC", "#2E3038")
    }
}


class CTkToolTip:
    """Tooltip flotante para widgets CustomTkinter con soporte adaptativo para Modo Claro y Modo Oscuro."""
    def __init__(self, widget, text: str, delay: int = 400):
        self.widget = widget
        self.text = text
        self.delay = delay
        self.tip_window = None
        self.id = None
        if self.widget:
            self.widget.bind("<Enter>", self.schedule_tip, add="+")
            self.widget.bind("<Leave>", self.hide_tip, add="+")
            self.widget.bind("<ButtonPress>", self.hide_tip, add="+")

    def schedule_tip(self, event=None):
        self.unschedule()
        if self.text:
            self.id = self.widget.after(self.delay, self.show_tip)

    def unschedule(self):
        id_ = self.id
        self.id = None
        if id_ and hasattr(self.widget, "after_cancel"):
            try:
                self.widget.after_cancel(id_)
            except Exception:
                pass

    def show_tip(self, event=None):
        if self.tip_window or not self.text or not self.widget.winfo_exists():
            return
        try:
            x = self.widget.winfo_rootx() + 10
            y = self.widget.winfo_rooty() + self.widget.winfo_height() + 4
            self.tip_window = tw = tk.Toplevel(self.widget)
            tw.wm_overrideredirect(True)
            tw.wm_geometry(f"+{x}+{y}")

            try:
                mode = ctk.get_appearance_mode()
            except Exception:
                mode = "Dark"
            is_dark = (str(mode).lower() == "dark")
            bg = PALETTE["Tooltip"]["bg_color"][1] if is_dark else PALETTE["Tooltip"]["bg_color"][0]
            fg = PALETTE["Tooltip"]["text_color"][1] if is_dark else PALETTE["Tooltip"]["text_color"][0]
            border = PALETTE["Tooltip"]["border_color"][1] if is_dark else PALETTE["Tooltip"]["border_color"][0]

            frame = tk.Frame(tw, background=border, borderwidth=1)
            frame.pack(fill="both", expand=True)
            label = tk.Label(
                frame,
                text=self.text,
                justify="left",
                background=bg,
                foreground=fg,
                relief="flat",
                padx=6,
                pady=3,
                font=("Segoe UI", 9)
            )
            label.pack(fill="both", expand=True, padx=1, pady=1)
        except Exception:
            self.hide_tip()

    def hide_tip(self, event=None):
        self.unschedule()
        tw = self.tip_window
        self.tip_window = None
        if tw:
            try:
                tw.destroy()
            except Exception:
                pass


try:
    import customtkinter as ctk
    ctk.set_default_color_theme("blue")
except Exception:
    pass

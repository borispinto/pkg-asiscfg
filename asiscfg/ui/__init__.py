# -*- coding: utf-8 -*-
# SPDX-FileCopyrightText: 2026 Asisnet Computacion, CA <proyectos@asisnet.net>
# SPDX-License-Identifier: MIT
# Autor: Boris Pinto <borispinto@asisnet.net>
# File: asiscfg/ui/__init__.py

"""
Subpaquete UI de asiscfg (Interfaz Gráfica en CustomTkinter).
"""

from .app import ConfigApp
from .dialogs import (
    ChangeAdminPasswordDialog,
    PlaintextPasswordsWarningDialog,
    AddProfileDialog,
    RenameProfileDialog,
    AboutDialog
)
from .utils import (
    apply_window_icon,
    PALETTE,
    CTkToolTip,
    find_logo_icon_path,
    find_asiscfg_lang_dir,
    setup_i18n_import,
    t18n
)

__all__ = [
    "ConfigApp",
    "ChangeAdminPasswordDialog",
    "PlaintextPasswordsWarningDialog",
    "AddProfileDialog",
    "RenameProfileDialog",
    "AboutDialog",
    "apply_window_icon",
    "PALETTE",
    "CTkToolTip",
    "find_logo_icon_path",
    "find_asiscfg_lang_dir",
    "setup_i18n_import",
    "t18n"
]

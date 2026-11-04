# -*- coding: utf-8 -*-
# SPDX-FileCopyrightText: 2026 ASISNET Computación, CA <proyectos@asisnet.net>
# SPDX-FileCopyrightText: 2026 Boris Pinto <borispinto@gmail.com>
# SPDX-License-Identifier: MIT
# Autor: Boris Pinto <borispinto@gmail.com>
# Contacto Institucional: ASISNET Computación, CA <proyectos@asisnet.net>
# File: tests/test_ui_help_texts.py

import ast
import unittest
from asiscfg.ui.dialogs import SCHEMA_MODEL_TEMPLATE_PYTHON, EXPLANATORY_SCHEMA_TEXT
from asiscfg.ui.app import ConfigApp


class TestUIHelpTextsAndTemplates(unittest.TestCase):
    """Verifica que los textos de ayuda, plantilla y esquema explicativo cumplan con los estándares actuales."""

    def test_schema_model_template_syntax_and_directives(self):
        """Verifica que SCHEMA_MODEL_TEMPLATE_PYTHON sea código Python válido con las directivas requeridas."""
        # Validación de sintaxis
        tree = ast.parse(SCHEMA_MODEL_TEMPLATE_PYTHON)
        self.assertIsNotNone(tree)

        # Verificación de presencia de directivas canónicas y atributos
        self.assertIn('"_security_level": 1', SCHEMA_MODEL_TEMPLATE_PYTHON)
        self.assertIn('"_backup":', SCHEMA_MODEL_TEMPLATE_PYTHON)
        self.assertIn('"public": True', SCHEMA_MODEL_TEMPLATE_PYTHON)
        self.assertIn('from asiscfg import SCHEMA_KEY, LITERAL', SCHEMA_MODEL_TEMPLATE_PYTHON)
        self.assertIn('CONFIG_SCHEMA', SCHEMA_MODEL_TEMPLATE_PYTHON)
        self.assertIn('@profiles', SCHEMA_MODEL_TEMPLATE_PYTHON)
        self.assertIn('_template', SCHEMA_MODEL_TEMPLATE_PYTHON)

    def test_explanatory_schema_text_contents(self):
        """Verifica que EXPLANATORY_SCHEMA_TEXT documente todas las secciones, directivas y flags canónicos."""
        # Directivas de nivel 0
        self.assertIn('"_security_level"', EXPLANATORY_SCHEMA_TEXT)
        self.assertIn('"_backup"', EXPLANATORY_SCHEMA_TEXT)
        self.assertIn('"target_dir"', EXPLANATORY_SCHEMA_TEXT)
        self.assertIn('"max_backups"', EXPLANATORY_SCHEMA_TEXT)

        # Atributos soportados
        self.assertIn('"public"', EXPLANATORY_SCHEMA_TEXT)
        self.assertIn('"is_password"', EXPLANATORY_SCHEMA_TEXT)

        # Sustitución de flag legado --app por --edit
        self.assertIn('--edit', EXPLANATORY_SCHEMA_TEXT)
        self.assertNotIn('--app', EXPLANATORY_SCHEMA_TEXT)

    def test_no_unauthorized_shim_in_config_app(self):
        """Verifica que ConfigApp no contenga el alias shim 'show_schema_model_dialog'."""
        self.assertFalse(hasattr(ConfigApp, "show_schema_model_dialog"))
        self.assertTrue(hasattr(ConfigApp, "show_schema_template_dialog"))

    def test_security_section_banners_use_canonical_edit_flag(self):
        """Verifica que los textos de las secciones de seguridad usen --edit y no el legado --app."""
        i18n_data = ConfigApp.get_default_translations_dict(None)
        asiscfg_dict = i18n_data.get("asiscfg", {})

        banner_ro = asiscfg_dict.get("security_section_banner_ro", "")
        banner_rw = asiscfg_dict.get("security_section_banner_rw", "")

        self.assertIn("--edit", banner_ro)
        self.assertNotIn("--app", banner_ro)

        self.assertIn("--edit", banner_rw)
        self.assertNotIn("--app", banner_rw)


if __name__ == "__main__":
    unittest.main()

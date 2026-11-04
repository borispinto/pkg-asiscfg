# SPDX-License-Identifier: MIT
# SPDX-FileCopyrightText: 2026 ASISNET Computación, CA <proyectos@asisnet.net>
# SPDX-FileCopyrightText: 2026 Boris Pinto <borispinto@gmail.com>
# Autor: Boris Pinto <borispinto@gmail.com>
# Contacto Institucional: ASISNET Computación, CA <proyectos@asisnet.net>
# File: asiscfg/__main__.py

"""Punto de entrada canónico para ejecución modular vía python -m asiscfg (PEP 338)."""

import sys
from asiscfg.cli import main

if __name__ == "__main__":
    sys.exit(main())

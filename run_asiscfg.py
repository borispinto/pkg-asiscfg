# -*- coding: utf-8 -*-
# SPDX-FileCopyrightText: 2026 ASISNET Computación, CA <proyectos@asisnet.net>
# SPDX-FileCopyrightText: 2026 Boris Pinto <borispinto@gmail.com>
# SPDX-License-Identifier: MIT
# Autor: Boris Pinto <borispinto@gmail.com>
# Contacto Institucional: ASISNET Computación, CA <proyectos@asisnet.net>
# File: run_asiscfg.py

"""Lanzador raíz anticolisión para CLI y compilación PyInstaller."""

import sys
from asiscfg.cli import main

if __name__ == "__main__":
    sys.exit(main())

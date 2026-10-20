# -*- coding: utf-8 -*-
# SPDX-FileCopyrightText: 2026 ASISNET Computación, CA <proyectos@asisnet.net>
# SPDX-FileCopyrightText: 2026 Boris Pinto <borispinto@gmail.com>
# SPDX-License-Identifier: MIT
# Autor: Boris Pinto <borispinto@gmail.com>
# Contacto Institucional: ASISNET Computación, CA <proyectos@asisnet.net>
# File: demo/demo.py

"""
Programa demostrativo portable para pkg-asiscfg.
Muestra:
  1. Inicialización en una sola llamada con init_app_config y argumentos CLI declarativos (app_help).
  2. Consultas globales con valor() y valorpass().
  3. Consultas directas de perfil con valor_profile() y valorpass_profile().
  4. Consultas con herencia en cascada (Perfil -> Global -> Default) con valor_parent() y valorpass_parent().
  5. Consulta de parámetros CLI validados (param) y preservación de argumentos externos (remaining_args).
  6. Modificación y persistencia directa con bootstrap.save().
  7. Ejecución en modo consola y modo interfaz gráfica (--ui).
"""

import os
import sys

# Asegurar que la librería pkg-asiscfg sea importable si se ejecuta directamente desde el repo
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
PROJECT_ROOT = os.path.dirname(SCRIPT_DIR)
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

# Si se ejecuta desde fuera de la carpeta demo/, situar el contexto en demo/
if not os.path.exists("demo.cfg") and os.path.exists(os.path.join(SCRIPT_DIR, "demo.cfg")):
    os.chdir(SCRIPT_DIR)

from asiscfg import init_app_config


def main():
    # -------------------------------------------------------------------------
    # Paso 0: Inicialización Canónica de Configuración
    # -------------------------------------------------------------------------
    # init_app_config resuelve automáticamente demo.cfg, demo.key y core/config_schema.py.
    # Si el usuario pasa flags como --ui, abre la interfaz gráfica y retorna bootstrap.exit_code.
    bootstrap = init_app_config(
        args=sys.argv[1:],
        app_title="Demo Conector Empresarial (pkg-asiscfg)",
        app_files="demo",
        app_schema="core/config_schema.py",
        app_help={
            "description": "Sistema Demostrativo Portable SQLite & Multi-Perfil",
            "params": {
                "periodo": {"type": int, "help": "Año fiscal o período de ejecución"},
                "recalcular": {"type": bool, "help": "Fuerza recálculo de saldos"}
            }
        }
    )

    # Si se ejecutó una acción terminal de asiscfg (ej: --ui, --help, --export-schema)
    if bootstrap.exit_code is not None:
        return bootstrap.exit_code

    print("=" * 70)
    print("  DEMO PORTABLE PKG-ASISCFG: SQLITE, MULTI-PERFIL Y HERENCIA EN CASCADA")
    print("=" * 70)

    # -------------------------------------------------------------------------
    # 1. Acceso a Valores Globales (valor / valorpass) en O(1)
    # -------------------------------------------------------------------------
    app_nombre = bootstrap.valor("app.nombre", default="Sin Nombre")
    app_version = bootstrap.valor("app.version", default="0.0.0")
    app_debug = bootstrap.valor("app.debug", default=False)
    gen_idioma = bootstrap.valor("general.idioma", default="es")
    gen_empresa = bootstrap.valor("general.empresa", default="Empresa")

    print("\n[1. Parámetros Globales de la Aplicación y Negocio]")
    print(f"  • Nombre de la App:  {app_nombre}")
    print(f"  • Versión:           {app_version}")
    print(f"  • Modo Debug:        {app_debug}")
    print(f"  • Idioma Activo:     {gen_idioma}")
    print(f"  • Empresa General:   {gen_empresa}")

    # Valores de la sección database global
    db_global_driver = bootstrap.valor("database.driver")
    db_global_file = bootstrap.valor("database.database")
    db_global_user = bootstrap.valor("database.user")
    db_global_pass = bootstrap.valorpass("database.password")

    print("\n[2. Sección Base de Datos Global / Padre]")
    print(f"  • Motor Global:      {db_global_driver}")
    print(f"  • Archivo Global:    {db_global_file}")
    print(f"  • Usuario Global:    {db_global_user}")
    print(f"  • Contraseña Global: {'*** (Desencriptada JIT: ' + db_global_pass + ')' if db_global_pass else '(Vacía)'}")

    # -------------------------------------------------------------------------
    # 2. Acceso Específico por Perfil (valor_profile / valorpass_profile)
    # -------------------------------------------------------------------------
    print("\n[3. Acceso Estricto por Perfil (valor_profile / valorpass_profile)]")
    print("  Nota: Consulta exactamente lo registrado en el perfil sin heredar del padre.")
    for perfil in ["01", "02"]:
        info_nom = bootstrap.valor_profile("info.nombre", perfil, default="(Sin asignar)")
        db_raw = bootstrap.valor_profile("database.database", perfil, default="(No definido)")
        user_raw = bootstrap.valor_profile("database.user", perfil, default="(No definido)")
        print(f"  • Perfil {perfil} [{info_nom}] -> BD: '{db_raw}' | Usuario: '{user_raw}'")

    # -------------------------------------------------------------------------
    # 3. Acceso con Herencia en Cascada (valor_parent / valorpass_parent)
    # Regla: Si el perfil tiene valor -> usa el del perfil.
    #        Si el perfil está vacío o no lo define -> hereda del padre global.
    # -------------------------------------------------------------------------
    print("\n[4. Acceso con Herencia en Cascada (valor_parent / valorpass_parent)]")
    print("  Regla jerárquica: Perfil -> Sección Global (Padre) -> Default")

    for perfil in ["01", "02"]:
        info_nom = bootstrap.valor_profile("info.nombre", perfil, default=f"Perfil {perfil}")
        print(f"\n  Sucursal / Perfil [{perfil}] - {info_nom}:")

        # driver: Ambos perfiles lo tienen vacío -> Heredan 'sqlite' del padre
        driver = bootstrap.valor_parent("database.driver", profile_code=perfil)
        print(f"    • Motor BD:          {driver} (Heredado de database.driver global)")

        # database: Perfil 01 define demo_01.db; Perfil 02 hereda la plantilla global demo_{profile}.db
        db_file = bootstrap.valor_parent("database.database", profile_code=perfil)
        print(f"    • Archivo BD:        {db_file}")

        # user: Perfil 01 hereda admin_general; Perfil 02 sobrescribe con supervisor_sucursal_02
        user = bootstrap.valor_parent("database.user", profile_code=perfil)
        origen_user = "Sobrescrito propio" if perfil == "02" else "Heredado de database.user global"
        print(f"    • Usuario:           {user} ({origen_user})")

        # password: Ambos heredan y desencriptan la contraseña global
        password = bootstrap.valorpass_parent("database.password", profile_code=perfil)
        print(f"    • Contraseña:        *** (Heredada y desencriptada JIT: '{password}')")

    # -------------------------------------------------------------------------
    # 4. Parámetros CLI Declarativos y Argumentos Externos Preservados
    # -------------------------------------------------------------------------
    periodo = bootstrap.param("periodo")
    recalcular = bootstrap.param("recalcular")
    print("\n[5. Parámetros CLI Declarativos y Externos]")
    print(f"  • Período (--periodo):     {periodo}")
    print(f"  • Recalcular (--recalcular): {recalcular}")
    print(f"  • Argumentos Externos (FoxPro / anfitrión): {bootstrap.remaining_args}")

    # -------------------------------------------------------------------------
    # 5. Modificación y Persistencia Directa
    # -------------------------------------------------------------------------
    bootstrap.config["general"]["empresa"] = "Corporación Demo C.A."
    bootstrap.save()
    print("\n[6. Persistencia Directa]")
    print("  • Configuración verificada y guardada con bootstrap.save().")

    print("\n" + "=" * 70)
    print("  Para abrir la interfaz gráfica con selector de perfiles y botones de prueba:")
    print("  > python demo/demo.py --ui --dev")
    print("=" * 70)

    return 0


if __name__ == "__main__":
    sys.exit(main())

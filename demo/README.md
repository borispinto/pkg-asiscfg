# Demo Portable: Multi-Perfil, Herencia y SQLite (`pkg-asiscfg`)

Este directorio contiene un ejemplo completo, autónomo y de **cero configuración externa**, diseñado para ejecutarse inmediatamente tras clonar o descargar el repositorio.

---

## 📁 Archivos Incluidos

- [config_schema.py](file:///d:/COMSISA%20Proyectos/pkg-asiscfg/demo/config_schema.py): Esquema declarativo unificado (`CONFIG_SCHEMA`). Declara:
  - Sección global `app` (nombre, versión, debug).
  - Sección global padre `database` (motor SQLite, usuario general, contraseña protegida y botón de prueba).
  - Sección multi-perfil `@profiles` con plantilla `_template` y perfiles preconfigurados `01` y `02`.
- [demo.cfg](file:///d:/COMSISA%20Proyectos/pkg-asiscfg/demo/demo.cfg): Archivo de configuración en formato canónico `# ASISCFG_PLAIN` con metadatos públicos en cabecera y contraseñas protegidas con cifrado simétrico.
- [demo.key](file:///d:/COMSISA%20Proyectos/pkg-asiscfg/demo/demo.key): Clave criptográfica para descifrar los campos protegidos.
- [demo.py](file:///d:/COMSISA%20Proyectos/pkg-asiscfg/demo/demo.py): Programa ejecutable que demuestra el consumo de parámetros en tiempo de ejecución.

---

## 🚀 Cómo Ejecutarlo

### 1. Modo Consumo (Consola)
Ejecuta el script directamente para observar cómo se consultan los parámetros globales, los valores directos de cada perfil y la resolución jerárquica en cascada:

```bash
python demo/demo.py
```
*(O desde la carpeta `demo`)*:
```bash
cd demo
python demo.py
```

### 2. Modo Interfaz Gráfica (`--ui`)
Abre la interfaz visual con selector de perfiles ordenado alfabéticamente y botones de prueba de conectividad:

```bash
python demo/demo.py --ui --dev
```

En la ventana visual podrás:
1. Probar la conexión a la base de datos global en la pestaña principal.
2. Alternar entre el **Perfil 01** y el **Perfil 02**.
3. Presionar el botón **"🔌 Probar Conexión Perfil"** en cada uno para verificar cómo SQLite conecta a `demo_01.db` y `demo_02.db` heredando automáticamente los parámetros no definidos desde la sección global.

---

## 💡 Mecánica de Herencia (`valor_parent` y `valorpass_parent`)

| Parámetro | Perfil 01 | Perfil 02 | Regla de Resolución |
|---|---|---|---|
| `database.driver` | `sqlite` | `sqlite` | Heredado de la sección global |
| `database.database` | `demo_01.db` | `demo_02.db` | Propio de cada perfil |
| `database.user` | `admin_general` | `supervisor_sucursal_02` | `01` hereda del padre, `02` sobrescribe |
| `database.password` | `ClaveGlobal123` | `ClaveGlobal123` | Heredada y desencriptada JIT |

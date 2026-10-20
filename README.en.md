# ⚙️ pkg-asiscfg

[🇪🇸 Español](README.md) | [🇺🇸 English](README.en.md)

[![License: MIT](https://img.shields.io/badge/License-MIT-blue.svg)](LICENSE) [![Python Version](https://img.shields.io/badge/python-3.8%2B-brightgreen.svg)](https://www.python.org/) [![Architecture: 5-Layer Fail-Fast](https://img.shields.io/badge/architecture-5--layer%20fail--fast-orange.svg)](#️-architecture-and-design-principles-5-layer-fail-fast) [![Security: Deterministic](https://img.shields.io/badge/security-100%25%20deterministic-red.svg)](#-security-and-cryptography)

This package provides a comprehensive, centralized, decoupled, ultra-high-performance, and runtime overhead-free **configuration management, strict schema validation, and cryptographic security** solution for any Python project (desktop applications such as PyQt/CustomTkinter, CLI tools, background services, or web servers).

**pkg-asiscfg** serves as the end-to-end infrastructure for configuration management, schema validation, and cryptographic security across the **Asisnet** application suite.

--------------------------------------------------------------------------------

#### 📋 Table of Contents

1. [🎯 Why pkg-asiscfg? (Purpose and Motivation)](#-why-pkg-asiscfg-purpose-and-motivation)
2. [🚀 Key Features and Capabilities](#-key-features-and-capabilities)
3. [🖥️ Administrative Interface Visual Tour](#️-administrative-interface-visual-tour)
   - [1. General System Configuration](#1-general-system-configuration)
   - [2. Global Connection Management](#2-global-connection-management)
   - [3. Real-Time Connectivity Testing (Integration with pkg-asisdb)](#3-real-time-connectivity-testing-integration-with-pkg-asisdb)
   - [4. Profile Selector and Management](#4-profile-selector-and-management)
   - [5. Detailed Configuration by Profile](#5-detailed-configuration-by-profile)
   - [6. Application Parameters and Administrative Security](#6-application-parameters-and-administrative-security)
4. [📦 Installation](#-installation)
   - [1. Direct Installation from GitHub (Recommended)](#1-direct-installation-from-github-recommended)
   - [2. Installation from Local Source Code](#2-installation-from-local-source-code)
   - [3. Immediate Portable Demo Execution (demo/)](#3-immediate-portable-demo-execution-demo)
5. [🏗️ Architecture and Design Principles (5-Layer Fail-Fast)](#️-architecture-and-design-principles-5-layer-fail-fast)
6. [🔒 Security and Cryptography](#-security-and-cryptography)
   - [1. Supported Cryptographic Engines (FORMAT_MODES)](#1-supported-cryptographic-engines-format_modes)
   - [2. Forensic Tamper Sealing in PLAIN Mode (security_level: 1)](#2-forensic-tamper-sealing-in-plain-mode-security_level-1)
   - [3. Canonical Password Invariant (NULL_SENTINEL)](#3-canonical-password-invariant-null_sentinel)
   - [4. Key Integrity and Recovery (KeyRecoveryDialog)](#4-key-integrity-and-recovery-keyrecoverydialog)
7. [📁 Recommended Consumer Project Structure](#-recommended-consumer-project-structure)
8. [🛠️ Quick Start Guide for Developers](#️-quick-start-guide-for-developers)
   - [1. Schema Definition (config_schema.py)](#1-schema-definition-config_schemapy)
   - [2. Anatomy and Physical Structure of the Configuration File (.cfg)](#2-anatomy-and-physical-structure-of-the-configuration-file-cfg)
   - [3. Host Application Bootstrap (Step 0)](#3-host-application-bootstrap-step-0)
9. [💻 Console and Administrative Operations (CLI)](#-console-and-administrative-operations-cli)
   - [Canonical CLI Parameter Reference](#canonical-cli-parameter-reference)
10. [👥 Contact and Support](#-contact-and-support)
11. [📄 License](#-license)

--------------------------------------------------------------------------------

#### 🎯 Why pkg-asiscfg? (Purpose and Motivation)

In enterprise and mission-critical application development, configuration management often degenerates into a **repetitive, tedious, and highly vulnerable chore**:
*   **Constant wheel reinvention**: Every new project writes its own ad-hoc routines to parse and serialize configuration files on disk.
*   **Exposed plain-text credentials**: Database and API passwords remain exposed in plain text or weakly protected with fragile, easily reversible obfuscations.
*   **Scattered validations and late failures**: Type, range, and presence checks get dispersed across business logic, causing unexpected runtime crashes in production.
*   **Costly refactoring for multiple profiles**: Introducing multi-branch, multi-tenant, or multi-environment workflows forces heavy application rewrites.
*   **Manual tampering and silent corruption**: File edits by technicians or end-users corrupt critical parameters without traceability or forensic audit trails.

**`pkg-asiscfg` was engineered to eliminate these pitfalls entirely**, delivering a **turnkey, modular, resilient, and ultra-high-performance** solution:
1.  **Step 0 in a Single Line (`init_app_config`)**: Resolves file paths, validates schemas, decrypts keys, and yields an immutable, structured configuration object ready for instant consumption.
2.  **100% Deterministic Security**: Zero plain-text credentials, canonical invariant for empty passwords, fail-fast tampering detection, and industry-grade cryptographic engines (AES-256-GCM, ChaCha20, Fernet).
3.  **Maximum Performance ($O(1)$)**: Ultra-lightweight memory footprint using `__slots__` classes, zero CPU overhead, and zero unnecessary runtime dependencies.
4.  **Decoupled Graphical Administration (*Cold Path*)**: A modern desktop graphical UI for administrators and operators that never penalizes client memory or startup latency.

--------------------------------------------------------------------------------

#### 🚀 Key Features and Capabilities

*   **Unified "Step 0" Initialization (`init_app_config`)**: Bootstraps host applications in a single typed call returning an immutable structured container (`ConfigBootstrap`).
*   **Radical UI Isolation (*Cold Path*)**: The graphical UI (`customtkinter`) lives strictly on a cold execution path; in consumption mode (`consume`), GUI libraries are never imported into `sys.modules`, guaranteeing zero RAM waste and instant startup.
*   **Direct Constant-Time Lookups ($O(1)$)**: High-frequency query methods (`valor`, `valorpass`, `valor_profile`, `valorpass_profile`, `valor_parent`, `valorpass_parent`) optimized with `__slots__` and direct memory lookups.
*   **Just-In-Time Decryption & Zero Clear-Text Passwords**: Passwords decrypt ephemerally in memory (*Just-In-Time*) only when calling `valorpass*()`.
*   **Canonical `NULL_SENTINEL` Invariant**: Empty passwords persist encrypted under the `<%null$>` token and return to consumers as empty string `""`. A password is never written to disk in plain text.
*   **Strict 4-Failure Password Detection**: Fails fast (`ValueError`) if a protected field is missing, lacks the `ENC:` prefix, has an empty token body, or fails decryption due to a bad key.
*   **Declarative CLI Parameter Management (`app_help`)**: Allows host applications to declare custom CLI flags with automatic type casting (`int`, `float`, `bool`, `str`), requirement enforcement (`required`), and option validation (`choices`), supporting symmetric `/`, `-`, and `--` prefixes.
*   **Zero Argument Leakage**: Host positional executable arguments (e.g., non-prefixed execution parameters) are preserved intact and isolated in `boot.remaining_args`.
*   **Forensic Tamper Sealing in PLAIN Mode (`security_level: 1`)**: Enables readable configuration files while locking an encrypted snapshot `@NO_MODIFICAR_NO_MODIFY`. Any unauthorized external modification is caught, audited (`[AUDIT-TAMPER]`), and reported via the `DiffWarningDialog` UI.
*   **Interactive Key Recovery (`KeyRecoveryDialog`)**: If the cryptographic key file (`.key`) is lost or corrupt, the engine halts execution in production or launches a guided recovery/regeneration wizard in elevated admin mode.
*   **Readable Public Metadata (`# public`)**: Fields flagged as public serialize at the top of physical files as human-readable comments `# <key>: <value>`, inspectable in plain text even when the file is fully encrypted.
*   **Integrated i18n Localization**: Native support for translatable schema descriptions and UI labels using the `t18n#` prefix in direct coordination with `pkg-i18n`.
*   **Automated Headless Deployment (`--install`)**: Built-in flag to generate default configuration and keys automatically during silent, unattended deployments.

--------------------------------------------------------------------------------

#### 🖥️ Administrative Interface Visual Tour

The `pkg-asiscfg` administrative suite provides a modern, intuitive desktop interface to manage all configuration facets safely:

##### 1. General System Configuration
Global company parameters, application workspace paths, and central operational preferences.
![General Configuration](README.IMG/img_general.jpg)

--------------------------------------------------------------------------------

##### 2. Global Connection Management
Centralized administration of database engines, network ports, instances, and credentials with hot live testing.
![Global Connections](README.IMG/img_conexiones.jpg)

--------------------------------------------------------------------------------

##### 3. Real-Time Connectivity Testing (Integration with `pkg-asisdb`)
Instant validation of credentials and network paths across relational engines (SQL Server, PostgreSQL, MySQL, Oracle, SQLite) and file-based data stores (FoxPro / DBF).

| SQL Server Verification | FoxPro / DBF Verification |
| :---: | :---: |
| ![SQL Connection OK](README.IMG/img_conection_sql_ok.jpg) | ![FoxPro Connection OK](README.IMG/img_conection_fox_ok.jpg) |

###### How Does the Connection Test Work?
When clicking the test button in the UI:
1.  **Hot In-Memory Collection**: The UI synchronizes current on-screen inputs without requiring the user to save to disk first.
2.  **Secure Just-In-Time Decryption**: Protected passwords (`is_password: True`) decrypt ephemerally in RAM exclusively for the test connection.
3.  **Wildcard & Variable Interpolation**: Resolves dynamic tokens (such as `[empresa_destino]` or `{ROOT}`) in database names and physical file paths.
4.  **Delegation to `pkg-asisdb`**: Calls `asisdb.engine.test_connection(driver=driver, **other_params)`, verifying network handshakes, authentication, and database access.
5.  **Diagnostic Report**: Displays a detailed modal window reporting the verdict (success or root-cause failure), parameters evaluated, omitted keys, and sanitized connection URLs.

###### How to Declare Connection Buttons in the Schema (`config_schema.py`)?
Test buttons are declared as schema fields with `"type": "test_connection"` and a `"mapping"` directive linking driver parameters with UI field paths:

```python
# Profile test button with cascade inheritance (Profile -> Global)
"btn_test_db": {
    "type": "test_connection",
    "description": "t18n#🔌 Test Profile Connection",
    "mapping": {
        "driver": ["driver", "database.driver"],       # Cascade: Profile -> Global (sqlite)
        "database": ["database", "database.database"], # Cascade: demo_01.db -> demo_{profile}.db
        "user": ["user", "database.user"],             # Cascade: Profile -> Global (admin_general)
        "password": ["password", "database.password"]  # Cascade: Profile -> Global (JIT decrypted)
    }
},

# Global test button with immutable fixed literal
"btn_test_db_global": {
    "type": "test_connection",
    "description": "t18n#🔌 Test Global Connection",
    "mapping": {
        "driver": "database.driver",
        "database": LITERAL("demo_global.db"),         # Fixed immutable literal
        "user": "database.user",
        "password": "database.password"
    }
}
```

**Parameter Resolution Rules in `mapping`**:
*   **Cascade Resolution (List)**: `["driver", "database.driver"]` or `["password", "database.password"]`. Evaluates the list sequentially: searches the active profile first; if blank or missing, falls back to the parent global section.
*   **Fixed Literals**: `LITERAL("demo_global.db")` or `"literal:sqlite"`. Binds a hardcoded parameter without needing a UI input widget.
*   **Dynamic Wildcards**: Allows templates such as `demo_{profile}.db` or `DAT[empresa_destino]SQL` that resolve dynamically based on the active profile.
*   **Supported Drivers**: `sqlite`, `mssql` (SQL Server), `postgres` (PostgreSQL), `mysql` (MySQL / MariaDB), `oracle`, and `foxpro` (Visual FoxPro / DBF tables).

--------------------------------------------------------------------------------

##### 4. Profile Selector and Management
Native support for multiple profiles (branches, companies, environments, or independent workspaces) with automatic synchronization and alphabetical sorting.
![Profile Selector](README.IMG/img_perfil_combo.jpg)

--------------------------------------------------------------------------------

##### 5. Detailed Configuration by Profile
Each profile maintains its own identity attributes and dedicated database connection definitions:

| Profile Identification Details | Profile Database Connections |
| :---: | :---: |
| ![Profile Information](README.IMG/img_perfil_info.jpg) | ![Profile Connections](README.IMG/img_perfil_conexiones.jpg) |

--------------------------------------------------------------------------------

##### 6. Application Parameters and Administrative Security
Protected administrative section requiring UAC elevation and master password authentication to modify application identity and critical core parameters.
![Application Parameters](README.IMG/img_app.jpg)

--------------------------------------------------------------------------------

#### 📦 Installation

##### 1. Direct Installation from GitHub (Recommended)
Install directly into your active virtual environment via `pip`:
```powershell
pip install git+https://github.com/borispinto/pkg-asiscfg.git
```

Or declare it in your `requirements.txt`:
```text
pkg-asiscfg @ git+https://github.com/borispinto/pkg-asiscfg.git
```

Or in your `pyproject.toml`:
```toml
[project]
dependencies = [
    "pkg-asiscfg>=1.0.0",
]
```

--------------------------------------------------------------------------------

##### 2. Installation from Local Source Code
Standard clone and install:
```powershell
git clone https://github.com/borispinto/pkg-asiscfg.git
cd pkg-asiscfg
pip install .
```

Or in editable development mode:
```powershell
pip install -e .
```

--------------------------------------------------------------------------------

##### 3. Immediate Portable Demo Execution (`demo/`)
The repository includes a complete, self-contained, pre-configured SQLite demo with multi-profile support (`01` and `02`) under the `demo/` directory, ready to run without installing external database servers:

```powershell
# 1. Clone the repository and enter the directory
git clone https://github.com/borispinto/pkg-asiscfg.git
cd pkg-asiscfg

# 2. Install the package in editable mode
pip install -e .

# 3. Launch the interactive administrative UI in development mode
python demo/demo.py --ui --dev
```

>[!TIP]
>**Console Mode**: To inspect how configuration initializes in the terminal, how global parameters are queried, and how cascade inheritance operates (`valor_parent` and `valorpass_parent`), run directly:
>```powershell
>python demo/demo.py
>```

>[!NOTE]
>**Environment and Ecosystem Requirements**:
>*   **Consumption Mode (Services / Production)**: Requires only `cryptography>=3.0` (included in package dependencies). The graphical UI is never imported into memory.
>*   **Visual Administrative Mode (`--ui`)**: Requires desktop GUI support (`customtkinter` and `Pillow`).
>*   **Full 100% Capabilities**:
>    *   **`pkg-asisdb`**: Infrastructure library required to execute live database connectivity tests (`test_connection`) in the UI.
>    *   **`pkg-i18n`**: Library required for dynamic localization of schema descriptions and UI labels carrying the `t18n#` prefix.

--------------------------------------------------------------------------------

#### 🏗️ Architecture and Design Principles (5-Layer Fail-Fast)

The package is engineered around a strict 5-layer sequential hierarchy where each tier guarantees 100% of its contract, eliminating redundant defensive code between boundaries:

| Layer | Component / Tier | Responsibility and Fail-Fast Principle |
| :---: | :--- | :--- |
| **1** | **CLI & Parsing** (`asiscfg.cli`) | Deterministic syntax validation, type casting, and strict isolation of host positional arguments (`remaining_args`). |
| **2** | **Context & Cryptography** (`asiscfg.context`, `asiscfg.crypto`) | Deterministic path resolution, physical key verification in RAM, and constant-time ($O(1)$) cryptographic engine selection. |
| **3** | **Persistence & Schema** (`asiscfg.schema`, `asiscfg.storage`) | Structural validation against `CONFIG_SCHEMA`, public metadata serialization (`# public`), forensic tamper sealing, and detection of the 4 canonical password failures. |
| **4** | **In-Memory Models** (`asiscfg.models`) | `ConfigDict` and `ConfigBootstrap` containers optimized with `__slots__ = True` for minimal memory consumption and zero overhead. |
| **5** | **Data Delivery** (`ConfigDict.valor*`) | Direct constant-time ($O(1)$) queries and Just-In-Time (JIT) password decryption solely upon calling `valorpass*`. |

##### Guiding Design Principles
1.  **Deterministic Security**: Zero tolerance for silent failures. If a protected field is corrupted or tampered with, execution terminates immediately in production (*Fail-Fast*).
2.  **Architectural Duality (*Cold Path*)**: The administrative GUI (`asiscfg.ui`) loads purely on demand; during consumption (`consume`), UI packages (`tkinter`, `customtkinter`) never enter `sys.modules`.
3.  **Inviolability of Production Efficiency**: Production code never implements sluggish fallbacks or redundant defensive checks to appease tests; unit test suites rigorously adapt to optimal production contracts.

--------------------------------------------------------------------------------

#### 🔒 Security and Cryptography

Security in `pkg-asiscfg` is **100% deterministic** and enforces the *Fail-Fast* paradigm: on any tampering, inconsistency, or invalid credential, the engine halts immediately in production to safeguard business assets.

##### 1. Supported Cryptographic Engines (`FORMAT_MODES`)

| Engine | Identifier | Cryptographic Characteristics | Recommended Scenario |
| :--- | :--- | :--- | :--- |
| **Plain** | `plain` | Legible JSON layout with per-field encryption for passwords. Supports forensic sealing. | Development, debugging, and direct text inspection. |
| **Fernet** | `fernet` | Full symmetric authenticated encryption (AES-128-CBC + HMAC-SHA256). | Standard cross-platform production deployments. |
| **AES-256-GCM** | `aes256_gcm` | Military-grade 256-bit authenticated hardware-accelerated encryption (AES-NI). | High-volume, mission-critical production environments. |
| **ChaCha20** | `chacha20` | 256-bit Poly1305 authenticated stream cipher. Ultra-efficient on non-AES-NI CPUs. | Embedded systems, virtualized appliances, or mobile cores. |

##### 2. Forensic Tamper Sealing in PLAIN Mode (`security_level: 1`)
Under the `plain` format, setting `_security_level: 1` creates an encrypted forensic snapshot under the `@NO_MODIFICAR_NO_MODIFY` directive. If a user or operator manually modifies settings in the physical file:
*   In **production**, the discrepancy is recorded immediately in the audit log (`[AUDIT-TAMPER]`).
*   In the **administrative UI (`--ui`)**, the `DiffWarningDialog` modal window opens, displaying the exact modified keys, their sealed baseline values, and current values on disk.

##### 3. Canonical Password Invariant (`NULL_SENTINEL`)
*   Empty passwords are **never written in plain text** nor assumed implicitly.
*   They persist encrypted under the canonical token `NULL_SENTINEL` (`"<%null$>"`). When decrypted via `valorpass*()`, they return to consumers as empty string `""`.
*   **4 Canonical Password Failure States**: If a field with `is_password: True` (1) is missing, (2) lacks the `ENC:` prefix, (3) has an empty token body, or (4) fails decryption due to a bad key, execution aborts immediately in production (`ValueError`).

##### 4. Key Integrity and Recovery (`KeyRecoveryDialog`)
At startup, the engine exhaustively validates the presence and cryptographic compatibility of the `.key` file. If the key file is missing or replaced by an alien key:
*   In **production**, execution halts immediately.
*   In **elevated administrative mode (`--dev` or Administrator)**, the interactive recovery dialog assists the operator to:
    1.  Locate and restore a valid backup copy of the `.key` file.
    2.  Regenerate a clean key with safe reset to schema default values.

--------------------------------------------------------------------------------

#### 📁 Recommended Consumer Project Structure

```text
my_project/
├── pyproject.toml / requirements.txt  # Declares pkg-asiscfg dependency
├── demo.cfg                           # Physical configuration file (encrypted or plain)
├── demo.key                           # Physical cryptographic key (production)
└── demo/
    ├── core/
    │   └── config_schema.py           # Canonical schema definition and validations
    └── demo.py                        # Step 0 Bootstrap: init_app_config(...)
```

>[!NOTE]
>`pkg-asiscfg` resolves physical paths deterministically: checking the current working directory first or alongside the executable (`sys.executable` when frozen with PyInstaller). The `.cfg` and `.key` files always live on the host filesystem.

--------------------------------------------------------------------------------

#### 🛠️ Quick Start Guide for Developers

##### 1. Schema Definition (`config_schema.py`)
Create a `config_schema.py` module in your project defining structure, data types, validation rules, and profiles:

```python
  1 # demo/core/config_schema.py
  2 from asiscfg import LITERAL
  3 
  4 CONFIG_SCHEMA = {
  5     # ── Configuration Policies ──
  6     "_security_level": 1,
  7     "_backup": {
  8         "enabled": True,
  9         "method": "timestamp",
 10         "target_dir": "{ROOT}/backups",
 11         "filename_pattern": "{TIMESTAMP}-{BASENAME}{EXT}.bak",
 12         "max_backups": 20
 13     },
 14 
 15     # ── 1. Application & Security Section ──
 16     "app": {
 17         "nombre": {
 18             "type": "str",
 19             "default": "Demo Conector Empresarial",
 20             "description": "Nombre de la Aplicación",
 21             "public": True
 22         },
 23         "version": {
 24             "type": "str",
 25             "default": "1.0.0",
 26             "description": "Versión del Software",
 27             "public": True
 28         },
 29         "debug": {
 30             "type": "bool",
 31             "default": False,
 32             "description": "Habilitar Modo Depuración"
 33         }
 34     },
 35 
 36     # ── 2. General Business Section ──
 37     "general": {
 38         "idioma": {
 39             "type": "str",
 40             "default": "es",
 41             "description": "Código de Idioma Activo",
 42             "public": True
 43         },
 44         "empresa": {
 45             "type": "str",
 46             "default": "Corporación Demo C.A.",
 47             "description": "Nombre de la Empresa",
 48             "public": True
 49         }
 50     },
 51 
 52     # ── 3. Global (Parent) Section: Shared Database ──
 53     "database": {
 54         "driver": {
 55             "type": "str",
 56             "default": "sqlite",
 57             "description": "Motor de Base de Datos Global",
 58             "public": True
 59         },
 60         "database": {
 61             "type": "str",
 62             "default": "demo_{profile}.db",
 63             "description": "Archivo de BD Global"
 64         },
 65         "user": {
 66             "type": "str",
 67             "default": "admin_general",
 68             "description": "Usuario Global por Defecto"
 69         },
 70         "password": {
 71             "type": "str",
 72             "default": "ClaveGlobal123",
 73             "is_password": True,
 74             "description": "Contraseña Global por Defecto"
 75         },
 76         "btn_test_db_global": {
 77             "type": "test_connection",
 78             "description": "🔌 Probar Conexión Global",
 79             "mapping": {
 80                 "driver": "database.driver",
 81                 "database": LITERAL("demo_global.db"),
 82                 "user": "database.user",
 83                 "password": "database.password"
 84             }
 85         }
 86     },
 87 
 88     # ── 4. Multi-Profile Section (@profiles): Profiles & Inheritance ──
 89     "@profiles": {
 90         "_template": {
 91             "info": {
 92                 "nombre": {
 93                     "type": "str",
 94                     "default": "",
 95                     "description": "Nombre de la Sucursal",
 96                     "public": True
 97                 },
 98                 "codigo": {
 99                     "type": "str",
100                     "default": "01",
101                     "description": "Código de Sucursal"
102                 }
103             },
104             "database": {
105                 "driver": {
106                     "type": "str",
107                     "default": "",
108                     "description": "Motor (vacío = hereda del padre global)"
109                 },
110                 "database": {
111                     "type": "str",
112                     "default": "",
113                     "description": "Archivo de BD del Perfil (vacío = hereda)"
114                 },
115                 "user": {
116                     "type": "str",
117                     "default": "",
118                     "description": "Usuario (vacío = hereda del padre global)"
119                 },
120                 "password": {
121                     "type": "str",
122                     "default": "",
123                     "is_password": True,
124                     "description": "Contraseña (vacía = hereda del padre global)"
125                 },
126                 "btn_test_db": {
127                     "type": "test_connection",
128                     "description": "🔌 Probar Conexión Perfil",
129                     "mapping": {
130                         "driver": ["driver", "database.driver"],
131                         "database": ["database", "database.database"],
132                         "user": ["user", "database.user"],
133                         "password": ["password", "database.password"]
134                     }
135                 }
136             }
137         },
138         # Profile 01: Main Branch in Caracas
139         "01": {
140             "info": {
141                 "nombre": "Sucursal Principal",
142                 "codigo": "01"
143             },
144             "database": {
145                 "database": "demo_01.db"
146             }
147         },
148         # Profile 02: Secondary Branch with dedicated user
149         "02": {
150             "info": {
151                 "nombre": "Sucursal Secundaria",
152                 "codigo": "02"
153             },
154             "database": {
155                 "user": "supervisor_sucursal_02"
156             }
157         }
158     }
159 }
```

##### Schema Line-by-Line Breakdown and Declaration Rules:

The declarative schema serves as the master contract for validation, UI widget rendering, and physical persistence. Below is the itemized breakdown of lines, directives, and operational rules:

| Element / Directive | Schema Type / Role | Purpose and Declaration Rules |
| :--- | :--- | :--- |
| **`LITERAL`**<br>*(Line 2)* | Import Helper | Canonical helper imported from `asiscfg` to bind immutable static string literals in `mapping` directives (such as `LITERAL("demo_global.db")` in line 81) without exposing editable UI input widgets. |
| **`CONFIG_SCHEMA`**<br>*(Line 4)* | Root Dictionary | Root contract defining all system aspects: operational policies, custom scalar sections, administrative security sections, and multi-profile modules. |
| **`_security_level`**<br>*(Line 6)* | Root Sealing Directive | File integrity enforcement. Setting `1` in `PLAIN` mode directs the engine to calculate and persist an encrypted forensic snapshot under `@NO_MODIFICAR_NO_MODIFY`. Any unauthorized external modification outside the UI triggers `[AUDIT-TAMPER]` logging and the `DiffWarningDialog` visual alert. |
| **`_backup`**<br>*(Lines 7 to 13)* | Root Backup Policy | Pre-save backup policy. Configures automated backup execution (`enabled: True`), rotation strategy (`method: "timestamp"`), wildcard-interpolated target folder (`target_dir: "{ROOT}/backups"`), naming pattern, and version retention (`max_backups: 20`). |
| **`"app"`**<br>*(Lines 16 to 34)* | Canonical Security Section | Houses application branding and identity parameters (`nombre`, `version`, `debug`). Persists on disk encrypted with Fernet (`ENC:`) and presents as read-only in the administrative UI (unless launched with `--edit`). |
| **`public: True`**<br>*(Lines 21, 27, 42, 49, 58, 96)* | Public Visibility Attribute | Serializes field values as `# public` comments in the physical header of the `.cfg` file. Enables technicians and monitoring agents to inspect critical keys using any plain text editor (Notepad) without decrypting the file. Mutually exclusive with `is_password`. |
| **`"general"`**<br>*(Lines 37 to 50)* | Custom Open Section | Business section defined for this demo to categorize parameters based on project needs (`idioma`, `empresa`). In `asiscfg`, custom section names and contents are completely open; their keys participate in cascade inheritance if and only if host applications invoke `valor_parent*`. |
| **`"database"`**<br>*(Lines 53 to 86)* | Custom Open Section | Another custom section defined freely for this example to structure shared connection attributes (`driver`, `database`, `user`, `password`). Like `"general"`, its keys serve as the parent fallback during cascade inheritance if queried via `valor_parent*`, or as standalone global values if queried via `valor*`. |
| **`is_password: True`**<br>*(Lines 73 and 123)* | Cryptographic Protection Attribute | Flags sensitive parameters that must be Fernet-encrypted under the `ENC:` prefix. Masked in UI widgets (`••••••`) and never exposed in clear text. When empty, stored as `NULL_SENTINEL`. |
| **`btn_test_db_global`**<br>*(Lines 76 to 85)* | Global Test Button | Field of `"type": "test_connection"`. Renders an interactive button in the UI to validate connection settings. Its `mapping` directive links required driver parameters to schema keys and `LITERAL` values. |
| **`"@profiles"`**<br>*(Lines 89 a 158)* | Canonical Multi-Profile Module | Container for independent profiles or contextual variants (e.g., branches, companies, execution environments, connections, or POS terminals). Declares the mandatory `_template` and default pre-seeded profile instances (`"01"` and `"02"`). |
| **`"_template"`**<br>*(Lines 90 to 136)* | Mandatory Profile Template | Defines the required internal hierarchy of each profile (`info` and `database`). Declaring empty defaults (`""`) does not trigger automatic inheritance; it enables cascade inheritance if and only if client code calls `valor_parent()` or `valorpass_parent()`. By default, fallback resolves against the identical key path in the root (`key_path_parent = key_path`), but can be redirected to **any arbitrary section or key** via the optional `key_path_parent` parameter. |
| **`btn_test_db` in Profile**<br>*(Lines 126 to 135)* | Profile Fallback Test Button | Connection test button whose `mapping` directive uses fallback resolution lists (e.g., `["driver", "database.driver"]`). Evaluates the profile key first; if empty, automatically falls back to the parent global section. |
| **Concrete Profiles `"01"` and `"02"`**<br>*(Lines 138 to 157)* | Profile Instances (100% Optional) | **100% Optional**: Declared in the schema only if the developer desires to pre-seed default profile instances when generating the file for the first time. If omitted, files can initialize without profiles (added dynamically later via UI or API). In this demo, `"01"` overrides `database: "demo_01.db"` and `"02"` overrides `user: "supervisor_sucursal_02"`, leaving other keys to inherit from the parent when queried with `valor_parent*`. |

--------------------------------------------------------------------------------

##### 2. Anatomy and Physical Structure of the Configuration File (`.cfg`)

Below is the actual content of a configuration file generated by `pkg-asiscfg` ([`demo/demo.cfg`](demo/demo.cfg)) in `PLAIN` mode with forensic tamper sealing and protected fields:

```ini
 1 # ASISCFG_PLAIN
 2 # app.nombre: Demo Conector Empresarial
 3 # app.version: 1.0.0
 4 # general.idioma: es
 5 # general.empresa: Corporación Demo C.A.
 6 # database.driver: sqlite
 7 # @profiles.01.info.nombre: Sucursal Principal
 8 # @profiles.02.info.nombre: Sucursal Secundaria
 9 {
10     "app": {
11         "nombre": "ENC:gAAAAABq1rBTc9T3yzBo90eBWuFHfUc844-HqcPZkl6ngjR-iLEuVBYUfrv-zlO8_VG-3W7HPJJCMSeZxw2RjlLyqce-U0oB-L2RAytNAqIabtdkvYLwU9U=",
12         "version": "ENC:gAAAAABq1rBTYqjn5V3AwhpkboWBlrJWt9UHRL61sYvQ1Qif1z9vZu1UcE9VSYDsPKyAMEdA780aXS1xXHa0FRklYuSMuQ0Vkg==",
13         "debug": "ENC:gAAAAABq1rBT5JOyHV9-MaZL9aT-nv6SEV7M-TUudkleQ0Yg_OLpvwd2EN2RAr3DqxN-Yo9WLYPkOFJ45JoZ3ADXedSiz1_s5g=="
14     },
15     "general": {
16         "idioma": "es",
17         "empresa": "Corporación Demo C.A."
18     },
19     "database": {
20         "driver": "sqlite",
21         "database": "demo_{profile}.db",
22         "user": "admin_general",
23         "password": "ENC:gAAAAABq1rAX2IrvJuYS0mSPX3eiLj2a9IuTq8UpZUNOVwelCY_vPXbk9P3YUREkbdiooeSPh8EBsM1gGFKKpegP9IFB24BXLA=="
24     },
25     "@profiles": {
26         "01": {
27             "info": {
28                 "nombre": "Sucursal Principal",
29                 "codigo": "01"
30             },
31             "database": {
32                 "driver": "",
33                 "database": "demo_01.db",
34                 "user": "",
35                 "password": "ENC:gAAAAABq1rBTifBoK1JtpMYhPcWWI5_i08ek_6uZtj9lfFn5eueRxJLmpkDiClEv86r5KdEDNeb3yo6IwtzJjQTruJQjVuThCw=="
36             }
37         },
38         "02": {
39             "info": {
40                 "nombre": "Sucursal Secundaria",
41                 "codigo": "02"
42             },
43             "database": {
44                 "driver": "",
45                 "database": "",
46                 "user": "supervisor_sucursal_02",
47                 "password": "ENC:gAAAAABq1rBTMDEwsiBIl9EoyoVrxq-kpZfKfKtuxVtumu4ViRePJiMHsSDcDuzAEHdI4crflEuPvMGxbO6xG8-HisNjlXA5DQ=="
48             }
49         }
50     },
51     "@asiscfg": {
52         "admin_pass_hash": "2a97516c354b68848cdbd8f54a226a0a55b21ed138e207ad6c5cbb9c00aa5aea"
53     },
54     "@NO_MODIFICAR_NO_MODIFY": "gAAAAABq1rBTnfJ2w7oEx5QlYD9ba3tgOP6Beuzxv0W6SlxY0MIpPxi2wi97JrhsvuMyoAWY1K6DmkoCtWJJ6P75RwkBSd1nGogiB4d3jd3c-zFgXVCgbhDrC_mwaGweiRVlmxoQ1Z6U74ZdRPn0kwFH9QWnC3uZU8EUqebOzW98tnPZVG_x_eBK2xnxQ_mpbtsNaaPBjTqzUWH0TwiZ5Piv8kWF1aogqEstrSw0HpaxS3NoA5aDMbUp4FTzzsIFGkcCdQjVzAYHKb9PAeFzqcCBUl9xkw5CoFD1w4qhwUo-KzR01pcpV_Jbur75rvvxBDazot1u6Lj1LbOlAAqRbqCOGfSYsyFHWhLM0i-KTqbC_7Mq-ggsG3-g_RO31Js1Tx8KXdzIZ2hjhggZqxtbsTHZLgCiPypCo4z0_aMV8N55d0QiV_OS7NvmKcDOxuLi3AfSBM_CqjJ7Q0V52jIILKHxC0UXfLF6CSDSiXcBHutEqhVdnNUZbXdka9n5J-bp-6DlLtBoN_OC6DuSfgSXxXAOfEvwS_HRPdhO7S2ErNs1dD1txSk-25Xp1IXGgcEsm0uymY0VIkDT4oq1FSwshJH1e81NvyKu50kqlCfesaD-J5Cmq1auK3eAfaN3v9lIfrHLXCzo28rU55t91OkSNbCjZEvh3bJ1lLgXf88fAcbjYfGu-0DOKFGnbRW4aMsBg8ecAzFqL61xVRPkWgWhC3g8ly7QacWx3ZSJiNdz7hOAawXzdHf8s5k2_2LDlK6ygb66qc-wCQ0dRkGQqaUiGhXEODnUCrwq2R01gSPmNI0Y-OoMbDm-dRvdxr12XgKio8X7hqeDaddHgxZTNE1rN2xT92cT5thFXesIlOAASvjDsTyjIYzY-UR7bq2pQDCj3_ajMdGefUEJWueuh-_5FGiToOE1QAl7Q6EtzcaV6Zm11bhi8GJgbZ3mkYm6umU_jGDo58oWm7XsL-uYz65FZ9WN19dThL8jnoILImcqU6BNIieTCmaTNR-Wit2NO3WIiULTRGsmSkwswSU6r0IggLJE_q_P0lvcXQapL7MWFhaYUcWqyJG5E2K0JwE4ifNgOGvlXeXXgiSqW1o0aHys94w-bP2h6g3P3rCi_nTQLsi_joKIGD_3Yq5zvXLxJ5nvweKkj2-88gqzZP2vmLQzNnCQyKKGPtd5YLioZug2_seacGnyc2IsVWM5FNoBfDdXmyb-FTwMpKulebxZK7dZP_cECBWOOsRPiX9obQ6ecpyQrz-QpjA0j7lZMfhnqhwK5sRyYLLbgNPqcsvPxo25lOKFjbq5tvSyxKixy-DmYhfdmynjVgBV4YDxwVKJmQirccaTb7DHbG1MgiHWlFFs-CkisaV-OufESAmNg6fT0AyT2XhI-1-pcPqcGTqjJWPOf3-7kkSjp1UushwE8_uEXd3E6bu6D9-3Pox1olIANfSxNHLAZ8s4quosJVi-Hy5bvntuiLmfy7YE9hoh7cE71u1i-mSrxpi8-C5dKp8EPGmvywsg4pCFbMJJhQOEAZCeSQysMLCdtHH8_N_TYovnoFiU2vGYy6-yclr3hqDVK6ODxLJR3iZ0keOmWc8riCuQMmEW_FsjIOuHa0qMywKp-BkArDhV6bbQMFMXhYqfmJ7C4eM-1-rJFIynKBN4KVNJ9VZqYkcE4SU5BOZvCuLIWISw7y2gTmrZgKRQOyJkrJaeJpN_5tttvbJhNDGlRMeKAVcMVrluKi_-IWSbcyUVyuBTwZzhvf8YYEOZk9aYx6POgThWHLarVlh8WBZ5Tl0TMETTwjVzqM_m"
55 }
```

##### Canonical Sections Breakdown and Field Manipulation Rules:

The physical file merges engine directives with declared schema parameters. The table below outlines canonical sections and plain-text field behavior (`PLAIN` mode):

| Element / Field | Type and Format | Plain-Text Behavior and Manipulation Rules |
| :--- | :--- | :--- |
| **`# ASISCFG_PLAIN`**<br>*(Line 1)* | Engine Header | **Immutable**: Identifies in constant time ($O(1)$) the file cryptographic algorithm (`plain`, `fernet`, `aes256_gcm`, `chacha20`). Modifying this header corrupts file loading. |
| **`# public`**<br>*(Lines 2 to 8)* | Public Comments | **Read-Only / Informational**: Generated automatically from schema fields flagged with `"public": True`. Allows technicians and monitoring services to inspect key parameters in plain text (Notepad) without decrypting files or exposing passwords (passwords are never published). |
| **`"app"`**<br>*(Lines 10 to 14)* | Canonical Security Section | **Protected / Encrypted with `ENC:`**: Stores branding and software identity parameters (`nombre`, `version`, `debug`). Values persist Fernet-encrypted with the `ENC:` prefix to prevent manual tampering. Read-only in the UI unless launched with `--edit`. Manual modification in text editors corrupts deterministic decryption. |
| **Business Fields in Plain Text**<br>*(Lines 15 to 22, 27 to 30, 39 to 42)* | Native types (`str`, `int`, `bool`, etc.) | **Editable in Plain Text**: Standard scalar values (e.g., `idioma`, `empresa`, `driver`, `database`, `user`). Directly readable and editable in any text editor. If `_security_level: 1` is configured, external disk edits are caught by forensic sealing, generating an `[AUDIT-TAMPER]` log and prompting the `DiffWarningDialog` in the UI with exact discrepancies. |
| **Password Fields** (`is_password: True`)<br>*(Lines 23, 35, and 47)* | Fernet Token with `ENC:` prefix | **Strictly Immutable in Plain Text**: Passwords **never persist in plain text**. Entering a plain password directly in the `.cfg` file (omitting encryption or the `ENC:` prefix) causes the engine to abort immediately (*Fail-Fast*) with `ValueError`. Empty passwords persist under the canonical token `NULL_SENTINEL` (`"<%null$>"`). All password updates must occur via the UI (`--ui`) or programmatic API. |
| **`"@profiles"`**<br>*(Lines 25 to 50)* | Canonical Multi-Profile Module | **Profile Structure**: Encapsulates independent profile instances (`"01"` in lines 26 to 37, `"02"` in lines 38 to 49). Although multi-company or multi-branch architectures are typical, `@profiles` adapts to any profile scenario (dev/staging/prod environments, connections, or POS terminals). Each profile owns isolated local sections (`info`, `database`, etc.). |
| **Profile Fields & Inheritance Rule**<br>*(Lines 31 to 36 and 43 to 48)* | On-Demand Inheritance (`valor_parent*`) | **Editable in Plain Text / Non-Automatic Inheritance**: Leaving a profile field blank (`""`) (such as `driver` in line 32 or `database` in line 45) **does not inherit automatically by default**. Calling `valor_profile()` or `valorpass_profile()` yields strictly the local profile value (`""`) without checking the parent. **Cascade inheritance (`Profile -> Parent Global Section -> Schema Default`) executes exclusively when client code calls `valor_parent()` or `valorpass_parent()`**. By default, it resolves against the **identical key path in the root** (`key_path_parent = key_path`), but can be redirected to **any arbitrary section or key** by providing `key_path_parent="other_section.key"`. If the profile defines an explicit value (e.g., `database: "demo_01.db"` in line 33 or `user: "supervisor_sucursal_02"` in line 46), the profile value overrides the global section. |
| **`"@asiscfg"`**<br>*(Lines 51 to 53)* | Canonical Admin Section | **Immutable in Plain Text**: Stores the SHA-256 hash (`admin_pass_hash`) of the master administrative password. Altering or deleting this key locks administrative UI access to prevent authentication bypass. |
| **`"@NO_MODIFICAR_NO_MODIFY"`**<br>*(Line 54)* | Canonical Sealing Directive | **Immutable in Plain Text**: Present when `_security_level: 1` in `PLAIN` mode. Stores a Fernet-encrypted forensic snapshot of the baseline physical configuration. Discrepancies between current disk values and this sealed snapshot trigger tamper alerts (*Tamper Detection*). |

--------------------------------------------------------------------------------

##### 3. Host Application Bootstrap (Step 0)
At your application entry point, initialize configuration in a single call via `init_app_config`:

```python
import sys
from asiscfg import init_app_config

# Canonical Step 0 bootstrap with optional declarative CLI flags
boot = init_app_config(
    args=sys.argv[1:],
    app_title="Demo Conector Empresarial (pkg-asiscfg)",
    app_files="demo",                  # Resolves/generates demo.cfg and demo.key
    app_schema="core/config_schema.py", # Mandatory schema definition module
    app_help={
        "description": "Sistema Demostrativo Portable SQLite & Multi-Perfil",
        "params": {
            "periodo": {"type": int, "help": "Fiscal year or execution period"},
            "recalcular": {"type": bool, "help": "Force balance recalculation"}
        }
    }
)

# Exit control: terminates if invoked with --help, --ui, or on CLI validation failure
if boot.exit_code is not None:
    sys.exit(boot.exit_code)

# 1. Global scalar lookups in O(1)
app_nombre = boot.valor("app.nombre")
empresa = boot.valor("general.empresa")
db_driver = boot.valor("database.driver")
db_pass = boot.valorpass("database.password")  # Secure JIT decryption

# 2. Host declarative CLI arguments query
periodo_fiscal = boot.param("periodo")
recalcular = boot.param("recalcular")

# 3. Strict profile queries (valor_profile / valorpass_profile: DOES NOT inherit)
sucursal_01 = boot.valor_profile("info.nombre", profile_code="01")
db_01_raw = boot.valor_profile("database.database", profile_code="01")

# 4. On-demand cascade inheritance: Profile -> Global (Parent) -> Default
#    (Executes exclusively when calling valor_parent or valorpass_parent)
#
#    a) Default fallback: resolves against the SAME key path in root (key_path_parent = key_path)
db_driver_01 = boot.valor_parent("database.driver", profile_code="01")      # Inherits 'sqlite' from global database.driver
db_file_01 = boot.valor_parent("database.database", profile_code="01")     # Uses profile's own 'demo_01.db'
db_user_02 = boot.valor_parent("database.user", profile_code="02")         # Overridden by profile with 'supervisor_sucursal_02'
db_pass_01 = boot.valorpass_parent("database.password", profile_code="01") # Inherits and decrypts JIT

#    b) Explicit fallback redirection to ANY OTHER root section (key_path_parent):
#       If profile has no 'servidor', falls back to 'general.servidor_central'
servidor_01 = boot.valor_parent(
    key_path="servidor",
    profile_code="01",
    key_path_parent="general.servidor_central", # Redirects fallback to any section
    default="localhost"
)

# 5. External positional arguments preserved intact
argumentos_externos = boot.remaining_args

# 6. Direct mutation and persistence
boot.config["general"]["empresa"] = "Corporación Demo C.A."
boot.save()
```

> [!NOTE]
> **Mechanics of Cascade Inheritance (`valor_parent` and `valorpass_parent`):**
> 1. **Profile Resolution**: Evaluates first whether the specified profile defines an assigned value (non-null and non-empty string `""`). If present, returns it immediately.
> 2. **Fallback to Root Global**: If the profile field is empty or undefined:
>    - **By Default (`key_path_parent=""`)**: Inherits by querying the **same section and key path** in the root configuration (`key_path`). For example, `valor_parent("database.driver", profile_code="01")` inspects `"database.driver"` at the root.
>    - **Custom Redirection (`key_path_parent="section.key"`)**: You may explicitly target **any other arbitrary section or key** in the root. For example, `valor_parent("driver", profile_code="01", key_path_parent="database.driver")` searches `"driver"` within the profile and, if missing, falls back to `"database.driver"` in the root.
> 3. **Final Default**: If neither the profile nor the parent root section contains a value, returns the `default` argument.

--------------------------------------------------------------------------------

#### 💻 Console and Administrative Operations (CLI)

The `asiscfg` CLI command (or `python -m asiscfg`) accepts `/`, `-`, or `--` prefixes symmetrically:

```bash
# Launch the administrative graphical interface
python -m asiscfg --ui --config-file demo.cfg --key-file demo.key --schema-file core/config_schema.py

# Enable application protected parameters editing tab in the UI
python -m asiscfg --ui --edit --config-file demo.cfg

# Generate a new secure cryptographic key file
python -m asiscfg --generate-key --key-file demo.key

# Export the resolved configuration schema to the base directory
python -m asiscfg --export-schema --schema-file core/config_schema.py

# Automated deployment / Unattended setup (Install Mode)
python -m asiscfg --install --config-file demo.cfg --key-file demo.key --schema-file core/config_schema.py
```

##### Canonical CLI Parameter Reference

>[!NOTE]
>**Separators and Valid Syntax**:
>All CLI options accept interchangeably the canonical `-`, `--`, and `/` separators (e.g., `--config-file`, `-config-file`, and `/config-file` are fully equivalent).
>Values can be assigned using space (`--config-file path`), equal sign (`--config-file=path`), or colon (`--config-file:path`).

| Parameter | Type | Description |
| :--- | :--- | :--- |
| `--schema-file` | Value | Path to the schema definition module (`config_schema.py`). |
| `--config-file` | Value | Path to the physical configuration file (`.cfg` or `.enc`). |
| `--key-file` | Value | Path to the cryptographic key file (`.key`). |
| `--ui` | Flag | Launches the desktop administrative graphical interface. |
| `--install` | Flag | Initializes keys and default configuration if absent. |
| `--edit` | Flag | Enables application protected parameters editing tab in the UI. |
| `--dev` | Flag | Developer mode (bypasses Windows UAC administrator elevation checks). |
| `--generate-key` | Flag | Generates a new valid cryptographic key file. |
| `--overwrite-key` | Flag | Allows overwriting an existing key file when generating keys. |
| `--reset-admin-pass` | Flag | Resets the administrative master password to default (`admin`). |
| `--export-schema` | Flag | Exports the resolved schema file to the base directory. |
| `--format-mode` | Value | Cryptographic engine: `plain`, `fernet`, `aes256_gcm`, `chacha20`. |
| `--theme` | Value | Visual theme for the graphical UI (`dark` or `light`). |
| `--show` | Flag | Enables visual dialog modals on warnings and errors. |
| `--debug` | Flag | Activates detailed console debugging events and telemetry. |

--------------------------------------------------------------------------------

#### 👥 Contact and Support

This project is developed and maintained by **Boris Pinto**, in partnership with **Asisnet Computación, CA**.

##### 🛠️ Authorship and Personal Brand
To collaborate on open-source initiatives or connect professionally:
*   **Lead Developer:** Boris Pinto
*   **Personal Email:** [borispinto@gmail.com](mailto:borispinto@gmail.com)
*   **GitHub Profile:** [@borispinto](https://github.com/borispinto)

##### 🏢 Enterprise Solutions and Connectivity
Looking to adapt this tool to your infrastructure, require corporate technical support, or need custom technology solutions? At **Asisnet Computación, CA**, we integrate software and hardware to elevate enterprise operations.
*   **Services:**
    *   **Administrative Software:** Tailored enterprise software for workflow control and automation.
    *   **Networks & Telecommunications:** Design, installation, and support for enterprise infrastructure.
    *   **Hardware & IT Solutions:** Hardware procurement, maintenance, and diagnostics.
*   **Commercial Inquiries:** [proyectos@asisnet.net](mailto:proyectos@asisnet.net)

--------------------------------------------------------------------------------

#### 📄 License

This project is licensed under the [MIT License](LICENSE). It is free and open-source software, fully authorized for personal, academic, and commercial use.

Copyright (c) 2026 Boris Pinto. All rights reserved.

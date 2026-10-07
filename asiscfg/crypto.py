# -*- coding: utf-8 -*-
# SPDX-FileCopyrightText: 2026 Asisnet Computacion, CA <proyectos@asisnet.net>
# SPDX-License-Identifier: MIT
# Autor: Boris Pinto <borispinto@asisnet.net>
# File: asiscfg/crypto.py

"""
Módulo de motores criptográficos y formatos de almacenamiento para asiscfg.
Implementa el Patrón Estrategia (Strategy Pattern) para soportar múltiples algoritmos
(Plain híbrido, Fernet, AES-256-GCM, ChaCha20-Poly1305) con invocación directa y tipada.
"""

import abc
import base64
import os
from typing import Any, Dict, List, Optional, Tuple, Union

try:
    from cryptography.fernet import Fernet, InvalidToken
    from cryptography.hazmat.primitives.ciphers.aead import AESGCM, ChaCha20Poly1305
except ImportError as err:
    raise ImportError(
        "El paquete 'asiscfg' requiere la librería 'cryptography'. "
        "Instálela usando 'pip install cryptography'."
    ) from err

from asiscfg.constants import ENC_PREFIX, NULL_SENTINEL


def _extract_raw_key_32(key: Union[bytes, str, Any]) -> bytes:
    """Extrae 32 bytes crudos a partir de una clave en bytes, str o Fernet."""
    if hasattr(key, "_signing_key") and hasattr(key, "_encryption_key"):
        # Instancia de Fernet: _signing_key (16 bytes) + _encryption_key (16 bytes) = 32 bytes
        sig = getattr(key, "_signing_key")
        enc = getattr(key, "_encryption_key")
        combined = sig + enc
        if len(combined) == 32:
            return combined
        if len(enc) == 32:
            return enc
    if isinstance(key, str):
        key = key.encode("utf-8")
    if not isinstance(key, bytes):
        raise TypeError(f"Clave criptográfica inválida de tipo: {type(key)}")

    key = key.strip()
    if len(key) == 44:
        try:
            decoded = base64.urlsafe_b64decode(key)
            if len(decoded) == 32:
                return decoded
        except Exception:
            pass
    if len(key) == 32:
        return key
    raise ValueError(
        f"Longitud de clave inválida ({len(key)} bytes). Se requieren 32 bytes (o 44 caracteres Base64 urlsafe)."
    )


class BaseFormatEngine(abc.ABC):
    """Clase base abstracta para motores de formato de configuración y cifrado."""

    mode_id: str
    header: str
    name: str
    is_full_encrypted: bool

    @abc.abstractmethod
    def generate_key(self) -> bytes:
        """Genera una clave criptográficamente segura adecuada para el motor."""
        pass

    @abc.abstractmethod
    def validate_key(self, key: Any) -> bool:
        """Valida que la clave sea compatible y utilizable por el motor."""
        pass

    @abc.abstractmethod
    def encrypt_payload(self, data: bytes, key: Any) -> bytes:
        """Cifra o empaqueta el contenido completo del archivo de configuración."""
        pass

    @abc.abstractmethod
    def decrypt_payload(self, payload: bytes, key: Any) -> bytes:
        """Descifra o desempaqueta el contenido completo del archivo de configuración."""
        pass

    @abc.abstractmethod
    def encrypt_field(self, plain_value: Any, key: Any) -> str:
        """
        Cifra un valor individual de contraseña generando el token canónico ENC:<token>.
        Garantiza que cualquier valor vacío se normalice estrictamente a NULL_SENTINEL.
        """
        pass

    @abc.abstractmethod
    def decrypt_field(self, enc_value: str, key: Any) -> str:
        """
        Descifra un token individual ENC:<token> retornando el valor en claro
        o NULL_SENTINEL si corresponde.
        """
        pass


class PlainFormatEngine(BaseFormatEngine):
    """
    Motor de Texto Plano Híbrido:
    - Encabezado: # ASISCFG_PLAIN
    - Payload: Texto JSON en claro (UTF-8).
    - Contraseñas: Cifradas individualmente con token ENC:... preservando NULL_SENTINEL.
    """

    mode_id = "plain"
    header = "# ASISCFG_PLAIN"
    name = "Texto Plano Híbrido (plain)"
    is_full_encrypted = False

    def generate_key(self) -> bytes:
        return Fernet.generate_key()

    def validate_key(self, key: Any) -> bool:
        try:
            if isinstance(key, Fernet):
                return True
            if isinstance(key, str):
                key = key.encode("utf-8")
            Fernet(key)
            return True
        except Exception:
            return False

    def encrypt_payload(self, data: bytes, key: Any) -> bytes:
        return data

    def decrypt_payload(self, payload: bytes, key: Any) -> bytes:
        return payload

    def encrypt_field(self, plain_value: Any, key: Any) -> str:
        if plain_value is None or plain_value == "" or plain_value == NULL_SENTINEL:
            raw_to_enc = NULL_SENTINEL
        else:
            raw_to_enc = str(plain_value)

        if not key:
            return NULL_SENTINEL if raw_to_enc == NULL_SENTINEL else raw_to_enc

        fernet = key if isinstance(key, Fernet) else Fernet(key)
        token = fernet.encrypt(raw_to_enc.encode("utf-8")).decode("utf-8")
        return f"{ENC_PREFIX}{token}"

    def decrypt_field(self, enc_value: str, key: Any) -> str:
        if enc_value is None or enc_value == "" or enc_value == NULL_SENTINEL:
            return NULL_SENTINEL

        if not isinstance(enc_value, str):
            enc_value = str(enc_value)

        if not enc_value.startswith(ENC_PREFIX):
            return enc_value

        token = enc_value[len(ENC_PREFIX):]
        if not key:
            return enc_value

        fernet = key if isinstance(key, Fernet) else Fernet(key)
        dec_bytes = fernet.decrypt(token.encode("utf-8"))
        dec_str = dec_bytes.decode("utf-8")
        return NULL_SENTINEL if dec_str == NULL_SENTINEL else dec_str


class FernetFormatEngine(BaseFormatEngine):
    """
    Motor de Cifrado Total con Clave Fernet (AES-128-CBC + HMAC-SHA256):
    - Encabezado: # ASISCFG_FERNET
    - Payload: Blob binario cifrado completamente con Fernet.
    """

    mode_id = "fernet"
    header = "# ASISCFG_FERNET"
    name = "Cifrado con Clave Fernet (fernet)"
    is_full_encrypted = True

    def generate_key(self) -> bytes:
        return Fernet.generate_key()

    def validate_key(self, key: Any) -> bool:
        try:
            if isinstance(key, Fernet):
                return True
            if isinstance(key, str):
                key = key.encode("utf-8")
            Fernet(key)
            return True
        except Exception:
            return False

    def encrypt_payload(self, data: bytes, key: Any) -> bytes:
        fernet = key if isinstance(key, Fernet) else Fernet(key)
        return fernet.encrypt(data)

    def decrypt_payload(self, payload: bytes, key: Any) -> bytes:
        fernet = key if isinstance(key, Fernet) else Fernet(key)
        return fernet.decrypt(payload)

    def encrypt_field(self, plain_value: Any, key: Any) -> str:
        if plain_value is None or plain_value == "" or plain_value == NULL_SENTINEL:
            raw_to_enc = NULL_SENTINEL
        else:
            raw_to_enc = str(plain_value)

        if not key:
            return NULL_SENTINEL if raw_to_enc == NULL_SENTINEL else raw_to_enc

        fernet = key if isinstance(key, Fernet) else Fernet(key)
        token = fernet.encrypt(raw_to_enc.encode("utf-8")).decode("utf-8")
        return f"{ENC_PREFIX}{token}"

    def decrypt_field(self, enc_value: str, key: Any) -> str:
        if enc_value is None or enc_value == "" or enc_value == NULL_SENTINEL:
            return NULL_SENTINEL

        if not isinstance(enc_value, str):
            enc_value = str(enc_value)

        if not enc_value.startswith(ENC_PREFIX):
            return enc_value

        token = enc_value[len(ENC_PREFIX):]
        if not key:
            return enc_value

        fernet = key if isinstance(key, Fernet) else Fernet(key)
        dec_bytes = fernet.decrypt(token.encode("utf-8"))
        dec_str = dec_bytes.decode("utf-8")
        return NULL_SENTINEL if dec_str == NULL_SENTINEL else dec_str


class Aes256GcmFormatEngine(BaseFormatEngine):
    """
    Motor de Cifrado Total con AES-256-GCM (AEAD autenticado):
    - Encabezado: # ASISCFG_AES256GCM
    - Payload: Blob binario cifrado (Nonce 96-bit + Ciphertext + Tag 128-bit) codificado en Base64 urlsafe.
    """

    mode_id = "aes256_gcm"
    header = "# ASISCFG_AES256GCM"
    name = "Cifrado AES-256-GCM (aes256_gcm)"
    is_full_encrypted = True

    def generate_key(self) -> bytes:
        raw_key = AESGCM.generate_key(bit_length=256)
        return base64.urlsafe_b64encode(raw_key)

    def validate_key(self, key: Any) -> bool:
        try:
            raw_key = _extract_raw_key_32(key)
            AESGCM(raw_key)
            return True
        except Exception:
            return False

    def encrypt_payload(self, data: bytes, key: Any) -> bytes:
        raw_key = _extract_raw_key_32(key)
        aesgcm = AESGCM(raw_key)
        nonce = os.urandom(12)
        encrypted_raw = aesgcm.encrypt(nonce, data, None)
        return base64.urlsafe_b64encode(nonce + encrypted_raw)

    def decrypt_payload(self, payload: bytes, key: Any) -> bytes:
        raw_key = _extract_raw_key_32(key)
        aesgcm = AESGCM(raw_key)
        raw_blob = base64.urlsafe_b64decode(payload.strip())
        nonce = raw_blob[:12]
        ciphertext = raw_blob[12:]
        return aesgcm.decrypt(nonce, ciphertext, None)

    def encrypt_field(self, plain_value: Any, key: Any) -> str:
        if plain_value is None or plain_value == "" or plain_value == NULL_SENTINEL:
            raw_to_enc = NULL_SENTINEL
        else:
            raw_to_enc = str(plain_value)

        if not key:
            return NULL_SENTINEL if raw_to_enc == NULL_SENTINEL else raw_to_enc

        raw_key = _extract_raw_key_32(key)
        aesgcm = AESGCM(raw_key)
        nonce = os.urandom(12)
        enc_bytes = aesgcm.encrypt(nonce, raw_to_enc.encode("utf-8"), None)
        token = base64.urlsafe_b64encode(nonce + enc_bytes).decode("utf-8")
        return f"{ENC_PREFIX}{token}"

    def decrypt_field(self, enc_value: str, key: Any) -> str:
        if enc_value is None or enc_value == "" or enc_value == NULL_SENTINEL:
            return NULL_SENTINEL

        if not isinstance(enc_value, str):
            enc_value = str(enc_value)

        if not enc_value.startswith(ENC_PREFIX):
            return enc_value

        token = enc_value[len(ENC_PREFIX):]
        if not key:
            return enc_value

        raw_key = _extract_raw_key_32(key)
        aesgcm = AESGCM(raw_key)
        raw_blob = base64.urlsafe_b64decode(token.encode("utf-8"))
        nonce = raw_blob[:12]
        ciphertext = raw_blob[12:]
        dec_bytes = aesgcm.decrypt(nonce, ciphertext, None)
        dec_str = dec_bytes.decode("utf-8")
        return NULL_SENTINEL if dec_str == NULL_SENTINEL else dec_str


class ChaCha20FormatEngine(BaseFormatEngine):
    """
    Motor de Cifrado Total con ChaCha20-Poly1305 (AEAD autenticado):
    - Encabezado: # ASISCFG_CHACHA20
    - Payload: Blob binario cifrado (Nonce 96-bit + Ciphertext + Tag 128-bit) codificado en Base64 urlsafe.
    """

    mode_id = "chacha20"
    header = "# ASISCFG_CHACHA20"
    name = "Cifrado ChaCha20-Poly1305 (chacha20)"
    is_full_encrypted = True

    def generate_key(self) -> bytes:
        raw_key = ChaCha20Poly1305.generate_key()
        return base64.urlsafe_b64encode(raw_key)

    def validate_key(self, key: Any) -> bool:
        try:
            raw_key = _extract_raw_key_32(key)
            ChaCha20Poly1305(raw_key)
            return True
        except Exception:
            return False

    def encrypt_payload(self, data: bytes, key: Any) -> bytes:
        raw_key = _extract_raw_key_32(key)
        chacha = ChaCha20Poly1305(raw_key)
        nonce = os.urandom(12)
        encrypted_raw = chacha.encrypt(nonce, data, None)
        return base64.urlsafe_b64encode(nonce + encrypted_raw)

    def decrypt_payload(self, payload: bytes, key: Any) -> bytes:
        raw_key = _extract_raw_key_32(key)
        chacha = ChaCha20Poly1305(raw_key)
        raw_blob = base64.urlsafe_b64decode(payload.strip())
        nonce = raw_blob[:12]
        ciphertext = raw_blob[12:]
        return chacha.decrypt(nonce, ciphertext, None)

    def encrypt_field(self, plain_value: Any, key: Any) -> str:
        if plain_value is None or plain_value == "" or plain_value == NULL_SENTINEL:
            raw_to_enc = NULL_SENTINEL
        else:
            raw_to_enc = str(plain_value)

        if not key:
            return NULL_SENTINEL if raw_to_enc == NULL_SENTINEL else raw_to_enc

        raw_key = _extract_raw_key_32(key)
        chacha = ChaCha20Poly1305(raw_key)
        nonce = os.urandom(12)
        enc_bytes = chacha.encrypt(nonce, raw_to_enc.encode("utf-8"), None)
        token = base64.urlsafe_b64encode(nonce + enc_bytes).decode("utf-8")
        return f"{ENC_PREFIX}{token}"

    def decrypt_field(self, enc_value: str, key: Any) -> str:
        if enc_value is None or enc_value == "" or enc_value == NULL_SENTINEL:
            return NULL_SENTINEL

        if not isinstance(enc_value, str):
            enc_value = str(enc_value)

        if not enc_value.startswith(ENC_PREFIX):
            return enc_value

        token = enc_value[len(ENC_PREFIX):]
        if not key:
            return enc_value

        raw_key = _extract_raw_key_32(key)
        chacha = ChaCha20Poly1305(raw_key)
        raw_blob = base64.urlsafe_b64decode(token.encode("utf-8"))
        nonce = raw_blob[:12]
        ciphertext = raw_blob[12:]
        dec_bytes = chacha.decrypt(nonce, ciphertext, None)
        dec_str = dec_bytes.decode("utf-8")
        return NULL_SENTINEL if dec_str == NULL_SENTINEL else dec_str


# Instancias singleton canónicas de los motores
# ENGINE_PLAIN = PlainFormatEngine()
# ENGINE_FERNET = FernetFormatEngine()
# ENGINE_AES256GCM = Aes256GcmFormatEngine()
# ENGINE_CHACHA20 = ChaCha20FormatEngine()

# FORMAT_MODES: Dict[str, BaseFormatEngine] = {
#     "plain": ENGINE_PLAIN,
#     "fernet": ENGINE_FERNET,
#     "aes256_gcm": ENGINE_AES256GCM,
#     "chacha20": ENGINE_CHACHA20,
# }

FORMAT_MODES: Dict[str, BaseFormatEngine] = {}
engine_mode = PlainFormatEngine()
FORMAT_MODES["plain"] = engine_mode
engine_mode = FernetFormatEngine()
FORMAT_MODES["fernet"] = engine_mode
engine_mode = Aes256GcmFormatEngine()
FORMAT_MODES["aes256_gcm"] = engine_mode
engine_mode = ChaCha20FormatEngine()
FORMAT_MODES["chacha20"] = engine_mode

def get_format_engine(mode: Optional[str]) -> BaseFormatEngine:
    """
    Obtiene el motor de formato correspondiente al identificador canónico indicado.
    Lanza ValueError si el modo es nulo, vacío o no existe en FORMAT_MODES.
    """
    if not mode or not str(mode).strip():
        raise ValueError("Modo de formato no especificado o vacío.")
    canon_mode = str(mode).strip().lower()
    if canon_mode not in FORMAT_MODES:
        valid_modes = list(FORMAT_MODES.keys())
        raise ValueError(
            f"Modo de formato inválido o no soportado: '{canon_mode}'. Modos válidos: {valid_modes}"
        )
    return FORMAT_MODES[canon_mode]


def detect_format_engine(raw_bytes: bytes) -> Tuple[str, BaseFormatEngine]:
    """
    Detecta de forma estricta el formato inspeccionando la cabecera en los bytes iniciales.
    Retorna la tupla (mode_id, engine) o lanza ValueError si no se reconoce la firma.
    """
    stripped_raw = raw_bytes.strip()
    for mode_key, engine in FORMAT_MODES.items():
        header_bytes = engine.header.encode("utf-8")
        if stripped_raw.startswith(header_bytes):
            return mode_key, engine
    raise ValueError("El archivo no contiene una cabecera de formato válida reconocida.")

"""
e2ee.py — szyfrowanie end-to-end dla wiadomości prywatnych.

Schemat: szyfrowanie hybrydowe RSA-OAEP + AES-GCM
  - AES-256-GCM szyfruje treść wiadomości (szybkie, nieograniczona długość)
  - RSA-2048-OAEP szyfruje klucz AES (asymetryczne, klucz prywatny tylko lokalnie)

Format zaszyfrowanej wiadomości (base64 JSON):
  {
    "v": 1,
    "enc_key": "<base64 klucza AES zaszyfrowanego RSA>",
    "nonce":   "<base64 nonce AES-GCM, 12 bajtów>",
    "tag":     "<base64 tagu uwierzytelniającego AES-GCM, 16 bajtów>",
    "ct":      "<base64 zaszyfrowanej treści>"
  }
"""

import os
import json
import base64
from pathlib import Path

try:
    from cryptography.hazmat.primitives.asymmetric import rsa, padding
    from cryptography.hazmat.primitives import hashes, serialization
    from cryptography.hazmat.primitives.ciphers.aead import AESGCM
except ImportError:
    print("BŁĄD: pip install cryptography")
    exit()

KEY_DIR = Path.home() / ".czatroom"
PRIVATE_KEY_PATH = KEY_DIR / "private.pem"


# ---------------------------------------------------------------------------
# Generowanie i ładowanie kluczy
# ---------------------------------------------------------------------------

def load_or_generate_keypair() -> tuple:
    """
    Ładuje istniejącą parę kluczy z dysku lub generuje nową.
    Klucz prywatny zapisany w ~/.czatroom/private.pem (PEM, bez hasła).
    Zwraca (private_key, public_key_pem_str).
    """
    KEY_DIR.mkdir(mode=0o700, parents=True, exist_ok=True)

    if PRIVATE_KEY_PATH.exists():
        with open(PRIVATE_KEY_PATH, "rb") as f:
            private_key = serialization.load_pem_private_key(f.read(), password=None)
    else:
        private_key = rsa.generate_private_key(
            public_exponent=65537,
            key_size=2048,
        )
        pem_bytes = private_key.private_bytes(
            encoding=serialization.Encoding.PEM,
            format=serialization.PrivateFormat.PKCS8,
            encryption_algorithm=serialization.NoEncryption(),
        )
        PRIVATE_KEY_PATH.write_bytes(pem_bytes)
        os.chmod(PRIVATE_KEY_PATH, 0o600)  # tylko właściciel może czytać

    public_key_pem = private_key.public_key().public_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PublicFormat.SubjectPublicKeyInfo,
    ).decode('utf-8')

    return private_key, public_key_pem


def public_key_from_pem(pem: str):
    """Ładuje klucz publiczny z PEM (otrzymany od serwera)."""
    return serialization.load_pem_public_key(pem.encode('utf-8'))


# ---------------------------------------------------------------------------
# Szyfrowanie i deszyfrowanie
# ---------------------------------------------------------------------------

def encrypt(plaintext: str, recipient_public_key) -> str:
    """
    Szyfruje wiadomość dla odbiorcy.
    Zwraca base64-JSON gotowy do wysłania przez sieć.
    """
    # 1. Losowy klucz AES-256 i nonce
    aes_key = os.urandom(32)
    nonce = os.urandom(12)

    # 2. Szyfruj treść AES-GCM
    aesgcm = AESGCM(aes_key)
    ct_with_tag = aesgcm.encrypt(nonce, plaintext.encode('utf-8'), None)
    # AESGCM zwraca ciphertext + tag (ostatnie 16 bajtów) razem
    ct = ct_with_tag[:-16]
    tag = ct_with_tag[-16:]

    # 3. Szyfruj klucz AES kluczem publicznym RSA-OAEP
    enc_key = recipient_public_key.encrypt(
        aes_key,
        padding.OAEP(
            mgf=padding.MGF1(algorithm=hashes.SHA256()),
            algorithm=hashes.SHA256(),
            label=None,
        )
    )

    payload = {
        "v": 1,
        "enc_key": base64.b64encode(enc_key).decode(),
        "nonce":   base64.b64encode(nonce).decode(),
        "tag":     base64.b64encode(tag).decode(),
        "ct":      base64.b64encode(ct).decode(),
    }
    return base64.b64encode(json.dumps(payload).encode()).decode()


def decrypt(encrypted_blob: str, private_key) -> str:
    """
    Odszyfrowuje wiadomość własnym kluczem prywatnym.
    Rzuca ValueError jeśli blob jest nieprawidłowy lub klucz nie pasuje.
    """
    try:
        payload = json.loads(base64.b64decode(encrypted_blob))
        enc_key = base64.b64decode(payload["enc_key"])
        nonce   = base64.b64decode(payload["nonce"])
        tag     = base64.b64decode(payload["tag"])
        ct      = base64.b64decode(payload["ct"])
    except Exception:
        raise ValueError("Nieprawidłowy format zaszyfrowanej wiadomości.")

    # Odszyfruj klucz AES
    try:
        aes_key = private_key.decrypt(
            enc_key,
            padding.OAEP(
                mgf=padding.MGF1(algorithm=hashes.SHA256()),
                algorithm=hashes.SHA256(),
                label=None,
            )
        )
    except Exception:
        raise ValueError("Nie można odszyfrować — zły klucz prywatny?")

    # Odszyfruj treść
    try:
        aesgcm = AESGCM(aes_key)
        plaintext = aesgcm.decrypt(nonce, ct + tag, None)
        return plaintext.decode('utf-8')
    except Exception:
        raise ValueError("Błąd integralności wiadomości (AES-GCM tag mismatch).")


def is_e2ee_blob(text: str) -> bool:
    """Sprawdza czy tekst wygląda jak zaszyfrowany blob E2EE (nie Fernet)."""
    try:
        payload = json.loads(base64.b64decode(text))
        return payload.get("v") == 1 and "enc_key" in payload
    except Exception:
        return False
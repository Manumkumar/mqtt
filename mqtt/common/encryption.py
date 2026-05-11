"""
Fernet symmetric encryption helper.

Generates a key on first run and reuses it afterwards.  Both publisher and
subscriber call ``get_cipher()`` so they share the same key file.
"""

import os
from cryptography.fernet import Fernet
from common.config import KEY_FILE


def get_cipher() -> Fernet:
    """Return a Fernet cipher, creating the key file if it doesn't exist."""
    if not os.path.exists(KEY_FILE):
        with open(KEY_FILE, "wb") as f:
            f.write(Fernet.generate_key())

    with open(KEY_FILE, "rb") as f:
        return Fernet(f.read())

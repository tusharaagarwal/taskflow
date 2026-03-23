"""
Secrets loader: Tries multiple sources for sensitive configuration.
Priority order:
1. Environment variables (highest)
2. SQLite secrets database (if SECRETS_DB is set)
3. Fallback defaults (lowest, for development only)
"""

import os
from pathlib import Path
from typing import Optional
import sqlite3
from cryptography.fernet import Fernet, InvalidToken

class SecretsLoader:
    def __init__(self):
        self._fernet = None
        self._db_path = os.getenv('SECRETS_DB')
        self._init_fernet()

    def _init_fernet(self):
        """Initialize Fernet with key from env or file"""
        key = os.getenv('SECRETS_ENCRYPTION_KEY')
        if not key:
            key_file = os.getenv('SECRETS_KEY_FILE', '.secrets_key')
            if os.path.exists(key_file):
                with open(key_file, 'rb') as f:
                    key = f.read().strip()

        if key:
            self._fernet = Fernet(key)

    def _decrypt(self, encrypted_bytes: bytes) -> Optional[str]:
        """Decrypt value from DB"""
        if not self._fernet:
            return None
        try:
            return self._fernet.decrypt(encrypted_bytes).decode()
        except InvalidToken:
            return None

    def _from_db(self, key: str) -> Optional[str]:
        """Fetch and decrypt secret from SQLite"""
        if not self._db_path or not os.path.exists(self._db_path):
            return None
        try:
            conn = sqlite3.connect(self._db_path)
            cur = conn.execute("SELECT value FROM secrets WHERE key = ?", (key,))
            row = cur.fetchone()
            conn.close()
            if row:
                return self._decrypt(row[0])
        except Exception as e:
            print(f"[SecretsLoader] DB error: {e}")
        return None

    def get(self, key: str, default: Optional[str] = None) -> Optional[str]:
        """
        Get secret with fallback chain:
        1. os.getenv(key)
        2. SQLite DB (if configured)
        3. default
        """
        # 1. Environment variable
        val = os.getenv(key)
        if val:
            return val

        # 2. SQLite secrets store
        val = self._from_db(key)
        if val:
            return val

        # 3. Default
        return default

# Global loader instance
secrets = SecretsLoader()

def get_secret(key: str, default: Optional[str] = None) -> Optional[str]:
    """Convenience function"""
    return secrets.get(key, default)
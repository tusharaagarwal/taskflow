#!/usr/bin/env python3
"""
SQLite Secrets Manager for TaskFlow

Usage:
  python secrets_manager.py set <key> <value>   # Store a secret
  python secrets_manager.py get <key>          # Retrieve a secret
  python secrets_manager.py list               # List all keys (names only)
  python secrets_manager.py delete <key>       # Delete a secret
  python secrets_manager.py init               # Initialize DB

Secrets are stored encrypted using Fernet (AES-128).
"""

import sys
import os
from pathlib import Path
from cryptography.fernet import Fernet
import sqlite3
from datetime import datetime

DB_PATH = os.getenv('SECRETS_DB', 'secrets.db')
KEY_FILE = os.getenv('SECRETS_KEY_FILE', '.secrets_key')

def init_db():
    """Initialize the SQLite database and encryption key"""
    if not os.path.exists(DB_PATH):
        conn = sqlite3.connect(DB_PATH)
        conn.execute("""
            CREATE TABLE secrets (
                key TEXT PRIMARY KEY,
                value BLOB NOT NULL,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)
        conn.commit()
        conn.close()
        print(f"✅ Initialized secrets DB at {DB_PATH}")

    if not os.path.exists(KEY_FILE):
        key = Fernet.generate_key()
        with open(KEY_FILE, 'wb') as f:
            f.write(key)
        os.chmod(KEY_FILE, 0o600)  # Read/write only by owner
        print(f"✅ Generated encryption key at {KEY_FILE}")
    else:
        print(f"🔑 Using existing key from {KEY_FILE}")

def get_fernet():
    """Load or create encryption key"""
    if not os.path.exists(KEY_FILE):
        raise FileNotFoundError(f"Key file {KEY_FILE} not found. Run 'init' first.")
    with open(KEY_FILE, 'rb') as f:
        key = f.read().strip()
    return Fernet(key)

def set_secret(key: str, value: str):
    """Store a secret encrypted in SQLite"""
    f = get_fernet()
    encrypted = f.encrypt(value.encode())

    conn = sqlite3.connect(DB_PATH)
    conn.execute("""
        INSERT OR REPLACE INTO secrets (key, value, updated_at)
        VALUES (?, ?, CURRENT_TIMESTAMP)
    """, (key, encrypted))
    conn.commit()
    conn.close()
    print(f"✅ Stored secret: {key}")

def get_secret(key: str) -> str:
    """Retrieve and decrypt a secret"""
    f = get_fernet()
    conn = sqlite3.connect(DB_PATH)
    cur = conn.execute("SELECT value FROM secrets WHERE key = ?", (key,))
    row = cur.fetchone()
    conn.close()

    if not row:
        raise KeyError(f"Secret '{key}' not found")
    encrypted = row[0]
    decrypted = f.decrypt(encrypted).decode()
    return decrypted

def list_secrets():
    """List all secret keys (names only, not values)"""
    conn = sqlite3.connect(DB_PATH)
    cur = conn.execute("SELECT key FROM secrets ORDER BY key")
    keys = [row[0] for row in cur.fetchall()]
    conn.close()
    if keys:
        print("🔐 Stored secrets:")
        for k in keys:
            print(f"  - {k}")
    else:
        print("📭 No secrets stored")

def delete_secret(key: str):
    """Delete a secret by key"""
    conn = sqlite3.connect(DB_PATH)
    conn.execute("DELETE FROM secrets WHERE key = ?", (key,))
    conn.commit()
    deleted = conn.total_changes
    conn.close()
    if deleted > 0:
        print(f"🗑️ Deleted secret: {key}")
    else:
        print(f"⚠️ Secret '{key}' not found")

def main():
    if len(sys.argv) < 2:
        print(__doc__)
        sys.exit(1)

    command = sys.argv[1]

    try:
        if command == 'init':
            init_db()
        elif command == 'set' and len(sys.argv) == 4:
            set_secret(sys.argv[2], sys.argv[3])
        elif command == 'get' and len(sys.argv) == 3:
            value = get_secret(sys.argv[2])
            print(f"🔑 Value: {value}")
        elif command == 'list':
            list_secrets()
        elif command == 'delete' and len(sys.argv) == 3:
            delete_secret(sys.argv[2])
        else:
            print(__doc__)
            sys.exit(1)
    except Exception as e:
        print(f"❌ Error: {e}")
        sys.exit(1)

if __name__ == '__main__':
    main()
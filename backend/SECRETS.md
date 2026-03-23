# 🔐 SQLite Secrets Manager — Usage Guide

## Overview

TaskFlow supports storing sensitive configuration in an encrypted SQLite database instead of plaintext `.env` files.

**Benefits:**
- ✅ Secrets encrypted at rest using Fernet (AES-128)
- ✅ Separate from codebase (can be in `.gitignore`)
- ✅ Easy CLI to add/update/list secrets
- ✅ Production can still use environment variables

---

## Quick Start

### 1. Initialize Secrets Database

```bash
cd backend
python scripts/secrets_manager.py init
```

This creates:
- `secrets.db` — SQLite database (encrypted values)
- `.secrets_key` — Encryption key (keep this safe!)

**Add to `.gitignore` immediately:**
```
secrets.db
.secrets_key
.env
```

---

### 2. Set Your Secrets

```bash
# Store JWT secret
python scripts/secrets_manager.py set SECRET_KEY "your-jwt-secret-here"

# Store DATABASE_URL (for local dev)
python scripts/secrets_manager.py set DATABASE_URL "postgresql://..."

# Store any other sensitive config
python scripts/secrets_manager.py set SOME_API_KEY "sk-..."
```

---

### 3. List Your Secrets (names only)

```bash
python scripts/secrets_manager.py list
```

Output:
```
🔐 Stored secrets:
  - SECRET_KEY
  - DATABASE_URL
```

*Values are never printed for security.*

---

### 4. Retrieve a Secret

```bash
python scripts/secrets_manager.py get SECRET_KEY
# 🔑 Value: your-jwt-secret-here
```

---

### 5. Delete a Secret

```bash
python scripts/secrets_manager.py delete SECRET_KEY
```

---

## How It Works in the App

The `config.py` module automatically loads secrets from:

1. **Environment variables** (highest priority)
2. **SQLite secrets store** (if `SECRETS_DB` env var set or `secrets.db` exists)
3. **Fallback defaults** (development only)

### Deployment Options

**Local development (with SQLite secrets):**
```bash
# The app auto-detects secrets.db if present in working dir
uvicorn app.main:app --reload
```

**Production (Railway/Render) — use env vars:**
```bash
# Do NOT use SQLite in production
# Set env vars directly in Railway dashboard:
# SECRET_KEY, DATABASE_URL, etc.
```

---

## Security Notes

- 🔑 **Encryption key file (`.secrets_key`) must be kept secret** — add to `.gitignore`
- 🔒 **Never commit `secrets.db`** — it contains encrypted values but still sensitive
- 🔄 **Rotate keys** periodically by re-initializing: `secrets_manager.py init` and re-setting secrets
- 🚫 **Backup the `.secrets_key`** — without it, you cannot decrypt stored secrets

---

## Troubleshooting

**Error: "Key file not found"**
- Run `python scripts/secrets_manager.py init` first

**App can't read secret from DB**
- Ensure `secrets.db` exists in project root or set `SECRETS_DB` env var to its path
- Check file permissions on `.secrets_key` (should be readable by app user)

**Want to use custom DB location?**
```bash
export SECRETS_DB=/path/to/your/secrets.db
python scripts/secrets_manager.py set SECRET_KEY "value"
```

---

## Best Practices

1. **Local dev:** Use SQLite secrets + `.gitignore` to avoid leaking secrets
2. **Production:** Use platform env vars (Railway Variables, Render Environment)
3. **CI/CD:** Use GitHub Secrets or GitLab CI variables
4. **Team sharing:** Share `.secrets_key` securely (not in Git) or use env vars per developer

---

## Example Workflow

```bash
# Setup
python scripts/secrets_manager.py init

# Set JWT secret (generate one)
openssl rand -hex 32 | xargs python scripts/secrets_manager.py set SECRET_KEY

# Set database URL for local
python scripts/secrets_manager.py set DATABASE_URL "postgresql://..."

# Verify
python scripts/secrets_manager.py list

# Run app (auto-loads from DB)
uvicorn app.main:app --reload
```

---

**You now have full control over your secrets withoutEver exposing them in code!** 🎉
"""Platform auth: dashboard users (role-based) + per-client API keys.

Storage follows the project's JSON-file convention (single process, swap for a
real DB at scale):

  data/platform/users.json     {email: {name, role, password, client_ids, created}}
  data/platform/api_keys.json  [{key_id, secret_hash, publishable, client_id, label, ...}]
  data/platform/secret.key     random signing secret (generated on first boot)

Roles:
  admin      — everything: clients, users, keys, connectors, settings
  supervisor — monitoring: analytics, history, live calls, handoffs, queue
  agent      — operations: handoff inbox, live call view, history

API keys come in pairs per client:
  sk_...  secret key   — server-to-server REST API (stored hashed, shown once)
  pk_...  publishable  — embeds the widget on a public website (stored plain)

Session tokens are HMAC-signed (email|role|expiry|sig) — no server-side session
store needed, restarts don't log anyone out.
"""

import base64
import hashlib
import hmac
import json
import os
import secrets
import time
from pathlib import Path

from fastapi import HTTPException, Request
from loguru import logger

PLATFORM_DIR = Path(__file__).resolve().parent.parent.parent / "data" / "platform"
USERS_FILE = PLATFORM_DIR / "users.json"
KEYS_FILE = PLATFORM_DIR / "api_keys.json"
SECRET_FILE = PLATFORM_DIR / "secret.key"

ROLES = ("admin", "supervisor", "agent")
SESSION_TTL_S = 12 * 3600


def _load(path: Path, default):
    if path.exists():
        try:
            return json.loads(path.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            pass
    return default


def _save(path: Path, data):
    PLATFORM_DIR.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")


# ---------------------------------------------------------------- passwords


def hash_password(password: str, salt: bytes | None = None) -> str:
    salt = salt or secrets.token_bytes(16)
    digest = hashlib.pbkdf2_hmac("sha256", password.encode(), salt, 200_000)
    return base64.b64encode(salt).decode() + "$" + base64.b64encode(digest).decode()


def verify_password(password: str, stored: str) -> bool:
    try:
        salt_b64, _ = stored.split("$", 1)
        salt = base64.b64decode(salt_b64)
    except (ValueError, TypeError):
        return False
    return hmac.compare_digest(hash_password(password, salt), stored)


# ------------------------------------------------------------------- secret


def signing_secret() -> bytes:
    env = os.environ.get("PLATFORM_SECRET")
    if env:
        return env.encode()
    if SECRET_FILE.exists():
        return SECRET_FILE.read_text(encoding="utf-8").strip().encode()
    secret = secrets.token_hex(32)
    PLATFORM_DIR.mkdir(parents=True, exist_ok=True)
    SECRET_FILE.write_text(secret, encoding="utf-8")
    return secret.encode()


# -------------------------------------------------------------------- users


def list_users() -> dict:
    return _load(USERS_FILE, {})


def save_user(email: str, name: str, role: str, password: str | None = None,
              client_ids: list | None = None):
    if role not in ROLES:
        raise ValueError(f"Role must be one of {ROLES}")
    email = email.strip().lower()
    users = list_users()
    user = users.get(email, {})
    user.update(
        {
            "name": name,
            "role": role,
            "client_ids": client_ids if client_ids is not None else user.get("client_ids", ["*"]),
        }
    )
    if password:
        user["password"] = hash_password(password)
    user.setdefault("created", time.strftime("%Y-%m-%d %H:%M:%S"))
    if "password" not in user:
        raise ValueError("New users need a password")
    users[email] = user
    _save(USERS_FILE, users)


def delete_user(email: str):
    users = list_users()
    users.pop(email.strip().lower(), None)
    _save(USERS_FILE, users)


def ensure_bootstrap_admin():
    """First boot: create the admin account so the dashboard is reachable."""
    if list_users():
        return
    email = os.environ.get("PLATFORM_ADMIN_EMAIL", "admin@platform.local")
    password = os.environ.get("PLATFORM_ADMIN_PASSWORD") or secrets.token_urlsafe(10)
    save_user(email, "Platform Admin", "admin", password, ["*"])
    note = PLATFORM_DIR / "initial_admin.txt"
    note.write_text(
        f"Dashboard login (created on first boot)\nemail: {email}\npassword: {password}\n"
        "Change it after logging in. Delete this file once noted.\n",
        encoding="utf-8",
    )
    logger.info(f"Platform admin created: {email} (password in {note})")


# ----------------------------------------------------------------- sessions


def issue_token(email: str) -> str:
    users = list_users()
    user = users.get(email)
    if not user:
        raise ValueError("No such user")
    expiry = int(time.time()) + SESSION_TTL_S
    payload = f"{email}|{user['role']}|{expiry}"
    sig = hmac.new(signing_secret(), payload.encode(), hashlib.sha256).hexdigest()
    return base64.urlsafe_b64encode(f"{payload}|{sig}".encode()).decode()


def check_token(token: str) -> dict | None:
    """Return {email, role, name, client_ids} for a valid token, else None."""
    try:
        payload = base64.urlsafe_b64decode(token.encode()).decode()
        email, role, expiry, sig = payload.rsplit("|", 3)
    except (ValueError, TypeError, UnicodeDecodeError):
        return None
    expected = hmac.new(
        signing_secret(), f"{email}|{role}|{expiry}".encode(), hashlib.sha256
    ).hexdigest()
    if not hmac.compare_digest(sig, expected):
        return None
    if int(expiry) < time.time():
        return None
    user = list_users().get(email)
    if not user or user["role"] != role:
        return None
    return {
        "email": email,
        "role": user["role"],
        "name": user.get("name", email),
        "client_ids": user.get("client_ids", ["*"]),
    }


def login(email: str, password: str) -> str | None:
    user = list_users().get(email.strip().lower())
    if not user or not verify_password(password, user.get("password", "")):
        return None
    return issue_token(email.strip().lower())


# --------------------------------------------------- FastAPI auth dependency

ROLE_RANK = {"agent": 1, "supervisor": 2, "admin": 3}


def current_user(request: Request) -> dict:
    """Resolve the dashboard user from the Authorization header. 401 if absent."""
    header = request.headers.get("authorization", "")
    token = header[7:] if header.lower().startswith("bearer ") else ""
    user = check_token(token)
    if not user:
        raise HTTPException(401, "Not logged in")
    return user


def require_role(request: Request, minimum: str) -> dict:
    user = current_user(request)
    if ROLE_RANK[user["role"]] < ROLE_RANK[minimum]:
        raise HTTPException(403, f"Needs {minimum} access")
    return user


def user_can_see(user: dict, client_id: str) -> bool:
    scope = user.get("client_ids", ["*"])
    return "*" in scope or client_id in scope


# ----------------------------------------------------------------- API keys


def _list_keys() -> list:
    return _load(KEYS_FILE, [])


def list_api_keys(client_id: str | None = None) -> list[dict]:
    """Key metadata for the dashboard (never returns the secret)."""
    out = []
    for k in _list_keys():
        if client_id and k["client_id"] != client_id:
            continue
        out.append(
            {
                "key_id": k["key_id"],
                "client_id": k["client_id"],
                "label": k.get("label", ""),
                "publishable": k.get("publishable", ""),
                "secret_hint": "sk_..." + k.get("secret_hint", ""),
                "created": k.get("created", ""),
                "revoked": bool(k.get("revoked")),
            }
        )
    return out


def create_api_key(client_id: str, label: str = "") -> dict:
    """Mint an sk_/pk_ pair. The sk secret is returned ONCE and stored hashed."""
    secret = "sk_" + secrets.token_urlsafe(24)
    publishable = "pk_" + secrets.token_urlsafe(18)
    record = {
        "key_id": secrets.token_hex(4),
        "client_id": client_id,
        "label": label,
        "secret_hash": hashlib.sha256(secret.encode()).hexdigest(),
        "secret_hint": secret[-4:],
        "publishable": publishable,
        "created": time.strftime("%Y-%m-%d %H:%M:%S"),
        "revoked": False,
    }
    keys = _list_keys()
    keys.append(record)
    _save(KEYS_FILE, keys)
    return {"key_id": record["key_id"], "secret": secret, "publishable": publishable}


def revoke_api_key(key_id: str):
    keys = _list_keys()
    for k in keys:
        if k["key_id"] == key_id:
            k["revoked"] = True
    _save(KEYS_FILE, keys)


def client_for_secret_key(secret: str) -> str | None:
    """Resolve an sk_ Bearer key to its client_id (None = invalid/revoked)."""
    if not secret.startswith("sk_"):
        return None
    digest = hashlib.sha256(secret.encode()).hexdigest()
    for k in _list_keys():
        if not k.get("revoked") and hmac.compare_digest(k["secret_hash"], digest):
            return k["client_id"]
    return None


def client_for_publishable_key(publishable: str) -> str | None:
    """Resolve a pk_ widget key to its client_id (None = invalid/revoked)."""
    for k in _list_keys():
        if not k.get("revoked") and k.get("publishable") == publishable:
            return k["client_id"]
    return None


def api_client(request: Request) -> str:
    """FastAPI dependency for the public /v1 API: sk_ key -> client_id."""
    header = request.headers.get("authorization", "")
    key = header[7:] if header.lower().startswith("bearer ") else ""
    client_id = client_for_secret_key(key)
    if not client_id:
        raise HTTPException(401, "Invalid or missing API key (Authorization: Bearer sk_...)")
    return client_id

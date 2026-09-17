"""POC SQLite authentication service.

Authentication is isolated from authorization so Microsoft Entra OIDC can
replace this layer later without changing RBAC/page policies.
"""
from __future__ import annotations
import hashlib, hmac, os, sqlite3
from datetime import datetime
from typing import Optional
from config import DATABASE_PATH

ROLE_USER = "USER"
ROLE_ADMIN = "ADMIN"
ROLES = (ROLE_USER, ROLE_ADMIN)
_SCRYPT_N, _SCRYPT_R, _SCRYPT_P, _DKLEN = 2**14, 8, 1, 64


def _connect():
    connection = sqlite3.connect(DATABASE_PATH)
    connection.row_factory = sqlite3.Row
    return connection


def ensure_auth_table() -> None:
    with _connect() as conn:
        conn.execute("""CREATE TABLE IF NOT EXISTS app_users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            username TEXT NOT NULL UNIQUE,
            password_hash TEXT NOT NULL,
            display_name TEXT,
            role TEXT NOT NULL,
            personnel_id INTEGER,
            is_active INTEGER NOT NULL DEFAULT 1,
            created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
            last_login TEXT)""")
        conn.execute("CREATE INDEX IF NOT EXISTS ix_app_users_personnel_id ON app_users(personnel_id)")
        conn.commit()


def normalize_username(value: str) -> str:
    return str(value or "").strip().lower()


def hash_password(password: str) -> str:
    if not password or len(password) < 8:
        raise ValueError("Password must be at least 8 characters.")
    salt = os.urandom(16)
    digest = hashlib.scrypt(password.encode(), salt=salt, n=_SCRYPT_N, r=_SCRYPT_R, p=_SCRYPT_P, dklen=_DKLEN)
    return f"scrypt${_SCRYPT_N}${_SCRYPT_R}${_SCRYPT_P}${salt.hex()}${digest.hex()}"


def verify_password(password: str, encoded: str) -> bool:
    try:
        scheme, n, r, p, salt_hex, digest_hex = str(encoded).split("$")
        if scheme != "scrypt": return False
        expected = bytes.fromhex(digest_hex)
        actual = hashlib.scrypt(password.encode(), salt=bytes.fromhex(salt_hex), n=int(n), r=int(r), p=int(p), dklen=len(expected))
        return hmac.compare_digest(actual, expected)
    except (TypeError, ValueError, IndexError):
        return False


def authenticate(username: str, password: str) -> Optional[dict]:
    ensure_auth_table()
    with _connect() as conn:
        row = conn.execute("SELECT * FROM app_users WHERE username = ? AND is_active = 1", (normalize_username(username),)).fetchone()
        if row is None or not verify_password(password, row["password_hash"]): return None
        conn.execute("UPDATE app_users SET last_login = ? WHERE id = ?", (datetime.utcnow().isoformat(timespec="seconds"), row["id"]))
        conn.commit()
        return dict(row)


def create_user(username: str, password: str, role: str, personnel_id: int | None = None, display_name: str | None = None):
    ensure_auth_table(); username = normalize_username(username); role = str(role or "").upper().strip()
    if not username: return False, "Username is required.", None
    if role not in ROLES: return False, f"Unsupported role: {role}.", None
    if len(password or "") < 8: return False, "Password must be at least 8 characters.", None
    if role == ROLE_USER and personnel_id is None: return False, "USER accounts must be linked to a personnel record.", None
    if role == ROLE_ADMIN: personnel_id = None
    try:
        with _connect() as conn:
            if conn.execute("SELECT id FROM app_users WHERE username = ?", (username,)).fetchone():
                return False, f"Username '{username}' already exists.", None
            cur = conn.execute("INSERT INTO app_users (username,password_hash,display_name,role,personnel_id,is_active) VALUES (?,?,?,?,?,1)", (username, hash_password(password), (display_name or username).strip(), role, personnel_id))
            conn.commit(); return True, f"Created {role} account '{username}'.", int(cur.lastrowid)
    except Exception as exc:
        return False, str(exc), None


def bootstrap_admin_from_environment() -> bool:
    ensure_auth_table()
    with _connect() as conn:
        if conn.execute("SELECT 1 FROM app_users LIMIT 1").fetchone(): return False
    username, password = os.getenv("POC_ADMIN_USERNAME", "").strip(), os.getenv("POC_ADMIN_PASSWORD", "")
    if not username or not password: return False
    ok, _, _ = create_user(username, password, ROLE_ADMIN, display_name=os.getenv("POC_ADMIN_DISPLAY_NAME", "POC Administrator"))
    return ok


def list_users() -> list[dict]:
    ensure_auth_table()
    with _connect() as conn: rows = conn.execute("SELECT id,username,display_name,role,personnel_id,is_active,created_at,last_login FROM app_users ORDER BY role DESC,username").fetchall()
    return [dict(row) for row in rows]


def set_active(user_id: int, is_active: bool):
    with _connect() as conn:
        row = conn.execute("SELECT username FROM app_users WHERE id = ?", (int(user_id),)).fetchone()
        if row is None: return False, "User not found."
        conn.execute("UPDATE app_users SET is_active = ? WHERE id = ?", (1 if is_active else 0, int(user_id))); conn.commit()
        return True, f"{'Enabled' if is_active else 'Disabled'} {row['username']}."


def reset_password(user_id: int, password: str):
    try: encoded = hash_password(password)
    except ValueError as exc: return False, str(exc)
    with _connect() as conn:
        row = conn.execute("SELECT username FROM app_users WHERE id = ?", (int(user_id),)).fetchone()
        if row is None: return False, "User not found."
        conn.execute("UPDATE app_users SET password_hash = ? WHERE id = ?", (encoded, int(user_id))); conn.commit()
        return True, f"Password reset for {row['username']}."

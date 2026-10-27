"""POC SQLite authentication service.

Authentication is isolated from authorization so Microsoft Entra OIDC can
replace this layer later without changing RBAC/page policies.
"""
from __future__ import annotations
import hashlib, hmac, os, sqlite3
from datetime import datetime
from typing import Optional
from config import DATABASE_PATH

def _streamlit_admin_credentials() -> tuple[str, str, str]:
    """Read deployment credentials from Streamlit Secrets without exposing them in Git."""
    try:
        import streamlit as st
        admin = st.secrets.get("admin", {})
        username = str(admin.get("username", "")).strip()
        password = str(admin.get("password", ""))
        display_name = str(admin.get("display_name", "POC Administrator")).strip() or "POC Administrator"
        if username and password:
            return username, password, display_name
    except Exception:
        # Streamlit Secrets may be unavailable during local/unit-test execution.
        pass
    return "", "", ""


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
        # Keep a one-time marker for the configured administrator credentials.
        # Only a password hash is persisted here, never the plaintext secret.
        conn.execute("""CREATE TABLE IF NOT EXISTS auth_bootstrap_state (
            singleton INTEGER PRIMARY KEY CHECK (singleton = 1),
            username TEXT NOT NULL,
            display_name TEXT NOT NULL,
            password_hash TEXT NOT NULL,
            updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP)""")
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
    """Provision the configured ADMIN and apply each configured password once.

    Streamlit Secrets are the source of truth for the initial/configured ADMIN.
    A password hash in auth_bootstrap_state records which secret was last
    applied. This repairs stale or inactive pre-existing admin records on the
    first run after deployment, but does not overwrite a password that an
    administrator later changes manually. Other user accounts are untouched.
    """
    ensure_auth_table()

    username, password, display_name = _streamlit_admin_credentials()
    if not username or not password:
        username = os.getenv("POC_ADMIN_USERNAME", "").strip()
        password = os.getenv("POC_ADMIN_PASSWORD", "")
        display_name = os.getenv("POC_ADMIN_DISPLAY_NAME", "POC Administrator").strip() or "POC Administrator"

    username = normalize_username(username)
    display_name = str(display_name or username).strip() or username
    if not username or not password:
        return False

    with _connect() as conn:
        state = conn.execute(
            "SELECT username, display_name, password_hash FROM auth_bootstrap_state WHERE singleton = 1"
        ).fetchone()

        # The configured password has already been applied. Do not reset it
        # again on every Streamlit rerun, and do not undo an intentional
        # password reset performed later through Admin: User Access.
        if (
            state is not None
            and state["username"] == username
            and state["display_name"] == display_name
            and verify_password(password, state["password_hash"])
        ):
            existing = conn.execute(
                "SELECT id FROM app_users WHERE username = ?", (username,)
            ).fetchone()
            if existing is not None:
                return False

        encoded_password = hash_password(password)

        # If the configured admin username was changed, disable the prior
        # bootstrap-managed account instead of leaving an orphaned admin login.
        if state is not None and state["username"] != username:
            conn.execute(
                "UPDATE app_users SET is_active = 0 WHERE username = ?",
                (state["username"],),
            )

        existing = conn.execute(
            "SELECT id FROM app_users WHERE username = ?", (username,)
        ).fetchone()
        if existing is None:
            conn.execute(
                """INSERT INTO app_users
                   (username, password_hash, display_name, role, personnel_id, is_active)
                   VALUES (?, ?, ?, ?, NULL, 1)""",
                (username, encoded_password, display_name, ROLE_ADMIN),
            )
        else:
            conn.execute(
                """UPDATE app_users
                   SET password_hash = ?, display_name = ?, role = ?, personnel_id = NULL, is_active = 1
                   WHERE id = ?""",
                (encoded_password, display_name, ROLE_ADMIN, existing["id"]),
            )

        conn.execute(
            """INSERT INTO auth_bootstrap_state
               (singleton, username, display_name, password_hash, updated_at)
               VALUES (1, ?, ?, ?, CURRENT_TIMESTAMP)
               ON CONFLICT(singleton) DO UPDATE SET
                   username = excluded.username,
                   display_name = excluded.display_name,
                   password_hash = excluded.password_hash,
                   updated_at = CURRENT_TIMESTAMP""",
            (username, display_name, encoded_password),
        )
        conn.commit()
        return True


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

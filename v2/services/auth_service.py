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

def _admin_credentials_from_mapping(admins) -> list[tuple[str, str, str]]:
    """Convert a mapping of named TOML admin tables to credentials."""
    credentials = []
    if hasattr(admins, "items"):
        for _, settings in admins.items():
            if not hasattr(settings, "get"):
                continue
            username = str(settings.get("username", "")).strip()
            password = str(settings.get("password", ""))
            display_name = (
                str(settings.get("display_name", username or "POC Administrator")).strip()
                or username
                or "POC Administrator"
            )
            if username and password:
                credentials.append((username, password, display_name))
    return credentials


def _streamlit_admin_credentials_list() -> list[tuple[str, str, str]]:
    """Read multiple named admin tables, with legacy single-admin support.

    Preferred TOML structure:
        [admins.first]
        username = "admin"
        password = "..."
        display_name = "System Administrator"

    Each configured account is bootstrapped and tracked independently.
    """
    try:
        import streamlit as st

        credentials = _admin_credentials_from_mapping(st.secrets.get("admins", {}))
        if credentials:
            return credentials
    except Exception:
        # Secrets may be unavailable during local/unit-test execution.
        pass

    # Keep existing [admin] deployments and tests working during migration.
    username, password, display_name = _streamlit_admin_credentials()
    if username and password:
        return [(username, password, display_name)]
    return []


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
        # Multi-admin bootstrap state tracks each configured account separately.
        # This allows one administrator to rotate credentials without resetting
        # the other configured administrators.
        conn.execute("""CREATE TABLE IF NOT EXISTS auth_bootstrap_admins (
            username TEXT PRIMARY KEY,
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
    """Provision every configured ADMIN account without resetting on reruns.

    Streamlit Secrets may define multiple accounts under [admins.<key>].
    Existing single [admin] secrets and the POC_ADMIN_* environment variables
    remain supported for backward compatibility.

    Each account has an independent one-time password marker. Configured
    credentials are hashed with scrypt; a password manually changed after the
    initial bootstrap remains unchanged until that account's secret changes.
    """
    ensure_auth_table()

    credentials = _streamlit_admin_credentials_list()
    if not credentials:
        username = os.getenv("POC_ADMIN_USERNAME", "").strip()
        password = os.getenv("POC_ADMIN_PASSWORD", "")
        display_name = (
            os.getenv("POC_ADMIN_DISPLAY_NAME", "POC Administrator").strip()
            or "POC Administrator"
        )
        if username and password:
            credentials = [(username, password, display_name)]

    # Guard against duplicate usernames in the TOML file. The last entry wins,
    # which is deterministic and avoids attempting duplicate account updates.
    configured = {}
    for username, password, display_name in credentials:
        username = normalize_username(username)
        display_name = str(display_name or username).strip() or username
        if username and password:
            configured[username] = (password, display_name)

    if not configured:
        return False

    changed = False
    with _connect() as conn:
        # Migrate the former singleton marker into the per-account table. This
        # preserves password-change behaviour for existing [admin] deployments.
        legacy_state = conn.execute(
            "SELECT username, display_name, password_hash FROM auth_bootstrap_state WHERE singleton = 1"
        ).fetchone()
        if legacy_state is not None:
            conn.execute(
                """INSERT OR IGNORE INTO auth_bootstrap_admins
                   (username, display_name, password_hash, updated_at)
                   VALUES (?, ?, ?, CURRENT_TIMESTAMP)""",
                (
                    legacy_state["username"],
                    legacy_state["display_name"],
                    legacy_state["password_hash"],
                ),
            )

        for username, (password, display_name) in configured.items():
            state = conn.execute(
                """SELECT display_name, password_hash
                   FROM auth_bootstrap_admins WHERE username = ?""",
                (username,),
            ).fetchone()
            existing = conn.execute(
                "SELECT id FROM app_users WHERE username = ?", (username,)
            ).fetchone()

            # Do not overwrite a manual password reset when the configured
            # secret has not changed. Repair a missing user row if necessary.
            if (
                state is not None
                and state["display_name"] == display_name
                and verify_password(password, state["password_hash"])
                and existing is not None
            ):
                continue

            encoded_password = hash_password(password)
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
                       SET password_hash = ?, display_name = ?, role = ?,
                           personnel_id = NULL, is_active = 1
                       WHERE id = ?""",
                    (encoded_password, display_name, ROLE_ADMIN, existing["id"]),
                )

            conn.execute(
                """INSERT INTO auth_bootstrap_admins
                   (username, display_name, password_hash, updated_at)
                   VALUES (?, ?, ?, CURRENT_TIMESTAMP)
                   ON CONFLICT(username) DO UPDATE SET
                       display_name = excluded.display_name,
                       password_hash = excluded.password_hash,
                       updated_at = CURRENT_TIMESTAMP""",
                (username, display_name, encoded_password),
            )
            changed = True

        conn.commit()
    return changed


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

"""POC authentication service.

Authentication is intentionally isolated from authorization so Microsoft Entra
OIDC can replace this service later without changing page-level RBAC rules.
"""
from __future__ import annotations

import hashlib
import hmac
import os
from datetime import datetime
from typing import Optional

from sqlalchemy.orm import Session

from models import AppUser, Personnel

ROLE_USER = "USER"
ROLE_ADMIN = "ADMIN"
ROLES = (ROLE_USER, ROLE_ADMIN)

_SCRYPT_N = 2**14
_SCRYPT_R = 8
_SCRYPT_P = 1
_DKLEN = 64


def normalize_username(value: str) -> str:
    return str(value or "").strip().lower()


def hash_password(password: str) -> str:
    """Return a portable scrypt password hash."""
    if not password or len(password) < 8:
        raise ValueError("Password must be at least 8 characters.")
    salt = os.urandom(16)
    digest = hashlib.scrypt(
        password.encode("utf-8"),
        salt=salt,
        n=_SCRYPT_N,
        r=_SCRYPT_R,
        p=_SCRYPT_P,
        dklen=_DKLEN,
    )
    return (
        f"scrypt${_SCRYPT_N}${_SCRYPT_R}${_SCRYPT_P}$"
        f"{salt.hex()}${digest.hex()}"
    )


def verify_password(password: str, encoded: str) -> bool:
    try:
        scheme, n, r, p, salt_hex, digest_hex = str(encoded).split("$")
        if scheme != "scrypt":
            return False
        salt = bytes.fromhex(salt_hex)
        expected = bytes.fromhex(digest_hex)
        actual = hashlib.scrypt(
            password.encode("utf-8"),
            salt=salt,
            n=int(n),
            r=int(r),
            p=int(p),
            dklen=len(expected),
        )
        return hmac.compare_digest(actual, expected)
    except (TypeError, ValueError, IndexError):
        return False


def authenticate(session: Session, username: str, password: str) -> Optional[AppUser]:
    normalized = normalize_username(username)
    if not normalized or not password:
        return None
    user = (
        session.query(AppUser)
        .filter(AppUser.username == normalized, AppUser.is_active.is_(True))
        .first()
    )
    if user is None or not verify_password(password, user.password_hash):
        return None
    user.last_login = datetime.utcnow()
    session.commit()
    return user


def create_user(
    session: Session,
    username: str,
    password: str,
    role: str,
    personnel_id: int | None = None,
    display_name: str | None = None,
) -> tuple[bool, str, Optional[int]]:
    normalized = normalize_username(username)
    role = str(role or "").upper().strip()
    if not normalized:
        return False, "Username is required.", None
    if role not in ROLES:
        return False, f"Unsupported role: {role}.", None
    if role == ROLE_USER and personnel_id is None:
        return False, "USER accounts must be linked to a personnel record.", None
    if role == ROLE_ADMIN:
        personnel_id = None

    try:
        existing = session.query(AppUser).filter(AppUser.username == normalized).first()
        if existing:
            return False, f"Username '{normalized}' already exists.", None
        if personnel_id is not None:
            person = session.query(Personnel).filter(
                Personnel.id == int(personnel_id), Personnel.is_deleted.is_(False)
            ).first()
            if person is None:
                return False, "Selected personnel record was not found.", None

        user = AppUser(
            username=normalized,
            password_hash=hash_password(password),
            role=role,
            personnel_id=personnel_id,
            display_name=(display_name or normalized).strip(),
            is_active=True,
        )
        session.add(user)
        session.commit()
        return True, f"Created {role} account '{normalized}'.", int(user.id)
    except Exception as exc:
        session.rollback()
        return False, str(exc), None


def bootstrap_admin_from_environment(session: Session) -> bool:
    """Create the first POC admin from environment variables when configured."""
    if session.query(AppUser).count() > 0:
        return False
    username = os.getenv("POC_ADMIN_USERNAME", "").strip()
    password = os.getenv("POC_ADMIN_PASSWORD", "")
    if not username or not password:
        return False
    ok, _, _ = create_user(
        session,
        username=username,
        password=password,
        role=ROLE_ADMIN,
        display_name=os.getenv("POC_ADMIN_DISPLAY_NAME", "POC Administrator"),
    )
    return ok


def list_users(session: Session) -> list[dict]:
    rows = (
        session.query(AppUser)
        .order_by(AppUser.role.desc(), AppUser.username.asc())
        .all()
    )
    return [
        {
            "id": user.id,
            "username": user.username,
            "display_name": user.display_name,
            "role": user.role,
            "personnel_id": user.personnel_id,
            "is_active": bool(user.is_active),
            "last_login": user.last_login,
        }
        for user in rows
    ]


def set_active(session: Session, user_id: int, is_active: bool) -> tuple[bool, str]:
    user = session.query(AppUser).filter(AppUser.id == int(user_id)).first()
    if user is None:
        return False, "User not found."
    user.is_active = bool(is_active)
    session.commit()
    return True, f"{'Enabled' if is_active else 'Disabled'} {user.username}."


def reset_password(session: Session, user_id: int, password: str) -> tuple[bool, str]:
    user = session.query(AppUser).filter(AppUser.id == int(user_id)).first()
    if user is None:
        return False, "User not found."
    try:
        user.password_hash = hash_password(password)
        session.commit()
        return True, f"Password reset for {user.username}."
    except Exception as exc:
        session.rollback()
        return False, str(exc)

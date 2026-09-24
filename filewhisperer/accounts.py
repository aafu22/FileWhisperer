"""User accounts and per-user chat storage, backed by a local SQLite file.

Passwords are hashed with PBKDF2-HMAC-SHA256 (Python's built-in `hashlib`,
260,000 iterations, a random 16-byte salt per user) rather than a
third-party library like bcrypt — bcrypt needs a compiled C extension that
isn't always installable everywhere (this exact project has already hit
Windows pip install issues more than once), while this needs nothing beyond
the standard library and is still a secure, well-established approach.

This is deliberately simple: no email verification, no password reset flow,
no admin panel. For a small, self-hosted deployment where you already
control who gets the signup invite code, that's the right amount of system,
not a missing feature.
"""

from __future__ import annotations

import hashlib
import json
import os
import secrets
import sqlite3
import time
import uuid
from contextlib import contextmanager
from dataclasses import dataclass, field
from pathlib import Path

DB_PATH = Path(__file__).resolve().parent.parent / "data" / "documind.db"
PBKDF2_ITERATIONS = 260_000
REMEMBER_ME_DAYS = 30
REMEMBER_ME_SECONDS = REMEMBER_ME_DAYS * 24 * 60 * 60


class UsernameTaken(Exception):
    pass


class InvalidCredentials(Exception):
    pass


@dataclass
class ChatSummary:
    id: str
    name: str
    created_at: float
    updated_at: float


@dataclass
class Chat:
    id: str
    user_id: int
    name: str
    created_at: float
    updated_at: float
    messages: list[dict] = field(default_factory=list)


@dataclass
class ChatDocument:
    chat_id: str
    filename: str
    file_type: str
    size_bytes: int
    data: bytes
    created_at: float


@contextmanager
def _connect():
    """Use persistent Turso Cloud in deployment; local SQLite otherwise."""
    turso_url = os.getenv("TURSO_DATABASE_URL", "").strip()
    turso_token = os.getenv("TURSO_AUTH_TOKEN", "").strip()

    if turso_url and turso_token:
        try:
            import turso_serverless
        except ImportError as exc:
            raise RuntimeError(
                "Turso credentials are configured but turso_serverless is not installed. "
                "Add turso_serverless to requirements.txt."
            ) from exc
        conn = turso_serverless.connect(turso_url, auth_token=turso_token)
    else:
        DB_PATH.parent.mkdir(parents=True, exist_ok=True)
        conn = sqlite3.connect(DB_PATH)
        conn.execute("PRAGMA journal_mode=WAL")

    try:
        yield conn
        conn.commit()
    finally:
        conn.close()


def init_db() -> None:
    with _connect() as conn:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS users (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                username TEXT UNIQUE NOT NULL,
                salt BLOB NOT NULL,
                password_hash BLOB NOT NULL,
                created_at REAL NOT NULL
            )
            """
        )
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS chats (
                id TEXT PRIMARY KEY,
                user_id INTEGER NOT NULL,
                name TEXT NOT NULL,
                created_at REAL NOT NULL,
                updated_at REAL NOT NULL,
                messages TEXT NOT NULL,
                FOREIGN KEY (user_id) REFERENCES users(id)
            )
            """
        )
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS chat_documents (
                chat_id TEXT NOT NULL,
                filename TEXT NOT NULL,
                file_type TEXT NOT NULL,
                size_bytes INTEGER NOT NULL,
                data BLOB NOT NULL,
                created_at REAL NOT NULL,
                PRIMARY KEY (chat_id, filename),
                FOREIGN KEY (chat_id) REFERENCES chats(id)
            )
            """
        )

        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS remember_sessions (
                token_hash TEXT PRIMARY KEY,
                user_id INTEGER NOT NULL,
                created_at REAL NOT NULL,
                expires_at REAL NOT NULL,
                FOREIGN KEY (user_id) REFERENCES users(id)
            )
            """
        )


def _hash_password(password: str, salt: bytes) -> bytes:
    return hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt, PBKDF2_ITERATIONS)


# --- users -------------------------------------------------------------

def create_user(username: str, password: str) -> int:
    """Create a new account. Raises UsernameTaken if the name is in use."""
    username = username.strip()
    if not username or not password:
        raise ValueError("Username and password can't be empty.")

    salt = secrets.token_bytes(16)
    password_hash = _hash_password(password, salt)

    with _connect() as conn:
        try:
            cur = conn.execute(
                "INSERT INTO users (username, salt, password_hash, created_at) VALUES (?, ?, ?, ?)",
                (username, salt, password_hash, time.time()),
            )
        except Exception as e:
            # SQLite and Turso use different exception classes for UNIQUE violations.
            message = str(e).lower()
            if "unique" not in message and "constraint" not in message:
                raise
            raise UsernameTaken(f'The name "{username}" is already taken.') from e

        # Avoid driver-specific lastrowid behavior. Username is UNIQUE, so this is reliable.
        row = conn.execute("SELECT id FROM users WHERE username = ?", (username,)).fetchone()
        return int(row[0])


def authenticate(username: str, password: str) -> int:
    """Returns the user's id on success. Raises InvalidCredentials on a
    wrong username or password (deliberately the same error for both, so a
    failed attempt doesn't reveal whether the username exists)."""
    with _connect() as conn:
        row = conn.execute(
            "SELECT id, salt, password_hash FROM users WHERE username = ?", (username.strip(),)
        ).fetchone()

    if row is None:
        raise InvalidCredentials("Incorrect username or password.")

    candidate = _hash_password(password, row[1])
    if not secrets.compare_digest(candidate, row[2]):
        raise InvalidCredentials("Incorrect username or password.")

    return row[0]


# --- remember-me sessions ----------------------------------------------

def _hash_session_token(token: str) -> str:
    """Hash a browser session token before storing it in SQLite."""
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def create_remember_token(user_id: int) -> str:
    """Create a cryptographically random 30-day token. Only its hash is stored."""
    token = secrets.token_urlsafe(32)
    now = time.time()
    expires_at = now + REMEMBER_ME_SECONDS
    token_hash = _hash_session_token(token)

    with _connect() as conn:
        conn.execute(
            """
            INSERT INTO remember_sessions
                (token_hash, user_id, created_at, expires_at)
            VALUES (?, ?, ?, ?)
            """,
            (token_hash, user_id, now, expires_at),
        )
    return token


def authenticate_remember_token(token: str) -> tuple[int, str] | None:
    """Return (user_id, username) for a valid unexpired token, otherwise None."""
    if not token:
        return None

    token_hash = _hash_session_token(token)
    now = time.time()

    with _connect() as conn:
        row = conn.execute(
            """
            SELECT rs.user_id, u.username, rs.expires_at
            FROM remember_sessions rs
            JOIN users u ON u.id = rs.user_id
            WHERE rs.token_hash = ?
            """,
            (token_hash,),
        ).fetchone()

        if row is None:
            return None

        if row[2] <= now:
            conn.execute(
                "DELETE FROM remember_sessions WHERE token_hash = ?",
                (token_hash,),
            )
            return None

        return row[0], row[1]


def revoke_remember_token(token: str) -> None:
    """Revoke a persistent browser session token."""
    if not token:
        return
    token_hash = _hash_session_token(token)
    with _connect() as conn:
        conn.execute(
            "DELETE FROM remember_sessions WHERE token_hash = ?",
            (token_hash,),
        )


def cleanup_expired_tokens() -> None:
    """Delete expired persistent sessions."""
    with _connect() as conn:
        conn.execute(
            "DELETE FROM remember_sessions WHERE expires_at <= ?",
            (time.time(),),
        )


# --- chats ---------------------------------------------------------------

def save_chat(user_id: int, messages: list[dict], chat_id: str | None = None, name: str | None = None) -> str:
    """Create (if chat_id is None) or update an existing chat. Returns the
    chat id either way, so the caller can keep auto-saving to the same row
    as the conversation continues."""
    now = time.time()
    chat_id = chat_id or uuid.uuid4().hex[:12]

    with _connect() as conn:
        existing = conn.execute("SELECT created_at, name FROM chats WHERE id = ?", (chat_id,)).fetchone()

        if name is None:
            first_user_msg = next(
                (m["content"] for m in messages if m["role"] == "user"),
                "",
            )
            generated_name = (
                first_user_msg.strip().replace("\n", " ")[:60]
                or "Untitled chat"
            )

            if existing is not None:
                existing_name = existing[1]
                if existing_name in {"New chat", "Untitled chat"} and first_user_msg.strip():
                    name = generated_name
                else:
                    name = existing_name
            else:
                name = generated_name

        created_at = existing[0] if existing is not None else now

        conn.execute(
            """
            INSERT INTO chats (id, user_id, name, created_at, updated_at, messages)
            VALUES (?, ?, ?, ?, ?, ?)
            ON CONFLICT(id) DO UPDATE SET
                name = excluded.name,
                updated_at = excluded.updated_at,
                messages = excluded.messages
            """,
            (chat_id, user_id, name, created_at, now, json.dumps(messages, ensure_ascii=False)),
        )

    return chat_id


def list_chats(user_id: int) -> list[ChatSummary]:
    with _connect() as conn:
        rows = conn.execute(
            "SELECT id, name, created_at, updated_at FROM chats WHERE user_id = ? ORDER BY updated_at DESC",
            (user_id,),
        ).fetchall()
    return [ChatSummary(id=r[0], name=r[1], created_at=r[2], updated_at=r[3]) for r in rows]


def load_chat(chat_id: str, user_id: int) -> Chat | None:
    """Returns None if the chat doesn't exist or doesn't belong to this
    user - callers should treat both the same way (deny), not distinguish
    them, so one user can't probe for another's chat ids."""
    with _connect() as conn:
        row = conn.execute(
            "SELECT id, user_id, name, created_at, updated_at, messages FROM chats WHERE id = ? AND user_id = ?",
            (chat_id, user_id),
        ).fetchone()
    if row is None:
        return None
    return Chat(
        id=row[0],
        user_id=row[1],
        name=row[2],
        created_at=row[3],
        updated_at=row[4],
        messages=json.loads(row[5]),
    )


# --- chat documents -------------------------------------------------------

def save_chat_document(
    chat_id: str,
    user_id: int,
    filename: str,
    file_type: str,
    data: bytes,
) -> None:
    """Persist one uploaded document for a chat owned by this user."""
    filename = filename.strip()
    if not filename:
        raise ValueError("Document filename can't be empty.")

    with _connect() as conn:
        chat = conn.execute(
            "SELECT id FROM chats WHERE id = ? AND user_id = ?",
            (chat_id, user_id),
        ).fetchone()

        if chat is None:
            raise ValueError("Chat not found.")

        conn.execute(
            """
            INSERT INTO chat_documents
                (chat_id, filename, file_type, size_bytes, data, created_at)
            VALUES (?, ?, ?, ?, ?, ?)
            ON CONFLICT(chat_id, filename) DO UPDATE SET
                file_type = excluded.file_type,
                size_bytes = excluded.size_bytes,
                data = excluded.data,
                created_at = excluded.created_at
            """,
            (
                chat_id,
                filename,
                file_type or "",
                len(data),
                data,
                time.time(),
            ),
        )


def list_chat_documents(
    chat_id: str,
    user_id: int,
) -> list[ChatDocument]:
    """Return all documents belonging to a chat owned by this user."""
    with _connect() as conn:
        rows = conn.execute(
            """
            SELECT cd.chat_id, cd.filename, cd.file_type,
                   cd.size_bytes, cd.data, cd.created_at
            FROM chat_documents cd
            JOIN chats c ON c.id = cd.chat_id
            WHERE cd.chat_id = ? AND c.user_id = ?
            ORDER BY cd.created_at ASC
            """,
            (chat_id, user_id),
        ).fetchall()

    return [
        ChatDocument(
            chat_id=row[0],
            filename=row[1],
            file_type=row[2],
            size_bytes=row[3],
            data=bytes(row[4]),
            created_at=row[5],
        )
        for row in rows
    ]


def delete_chat_document(
    chat_id: str,
    user_id: int,
    filename: str,
) -> None:
    """Delete one document from a chat owned by this user."""
    with _connect() as conn:
        conn.execute(
            """
            DELETE FROM chat_documents
            WHERE chat_id = ?
              AND filename = ?
              AND EXISTS (
                  SELECT 1 FROM chats
                  WHERE chats.id = chat_documents.chat_id
                    AND chats.user_id = ?
              )
            """,
            (chat_id, filename, user_id),
        )


def rename_chat(chat_id: str, user_id: int, new_name: str) -> None:
    new_name = new_name.strip() or "Untitled chat"
    with _connect() as conn:
        conn.execute(
            "UPDATE chats SET name = ? WHERE id = ? AND user_id = ?", (new_name, chat_id, user_id)
        )


def delete_chat(chat_id: str, user_id: int) -> None:
    with _connect() as conn:
        conn.execute(
            "DELETE FROM chat_documents WHERE chat_id = ? AND EXISTS "
            "(SELECT 1 FROM chats WHERE chats.id = chat_documents.chat_id AND chats.user_id = ?)",
            (chat_id, user_id),
        )
        conn.execute(
            "DELETE FROM chats WHERE id = ? AND user_id = ?",
            (chat_id, user_id),
        )

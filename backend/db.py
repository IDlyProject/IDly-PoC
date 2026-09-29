"""IDly 계정·세션·연동 메일·조치 기록 저장소.

- DATABASE_URL이 있으면 PostgreSQL(Supabase)의 `idly` 스키마, 없으면 data/idly.db(SQLite, 개발·테스트용).
- IDly 계정 비밀번호는 scrypt 해시로만 저장한다.
- 메일 앱 비밀번호는 Fernet으로 암호화해 저장한다. 키는 IDLY_SECRET_KEY 환경변수,
  없으면 data/secret.key를 만들어 쓴다 (운영에서는 반드시 환경변수로 따로 관리).
- 메일 원문은 저장하지 않는다. 탐색 결과(계정 목록 JSON)만 저장한다.
"""

import hashlib
import hmac
import json
import os
import secrets
import sqlite3
import threading
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence

from cryptography.fernet import Fernet, InvalidToken

DATA_DIR = Path(os.getenv("IDLY_DATA_DIR") or Path(__file__).parent / "data")
DATABASE_URL = os.getenv("DATABASE_URL", "").strip()
KEY_PATH = DATA_DIR / "secret.key"
SESSION_DAYS = 30

_lock = threading.Lock()
_PG = DATABASE_URL.startswith("postgres")

_TABLES = """
CREATE TABLE IF NOT EXISTS users (
  id {pk},
  email TEXT NOT NULL UNIQUE,
  password_hash TEXT NOT NULL,
  created_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS sessions (
  token TEXT PRIMARY KEY,
  user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
  created_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS mailboxes (
  id {pk},
  user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
  email TEXT NOT NULL,
  provider TEXT NOT NULL,
  host TEXT NOT NULL,
  port INTEGER NOT NULL,
  username TEXT NOT NULL,
  auth TEXT NOT NULL,
  secret TEXT NOT NULL,
  report TEXT,
  scanned_at TEXT,
  consented_at TEXT,
  created_at TEXT NOT NULL,
  UNIQUE(user_id, email)
);
CREATE TABLE IF NOT EXISTS action_log (
  id {pk},
  user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
  service TEXT NOT NULL,
  account_email TEXT NOT NULL,
  action TEXT NOT NULL,
  event TEXT NOT NULL,
  detail TEXT,
  created_at TEXT NOT NULL
);
"""


def _now() -> str:
    return datetime.now().isoformat(timespec="seconds")


# --- 연결 (PostgreSQL / SQLite) ------------------------------------------------

def _open():
    if _PG:
        import psycopg
        from psycopg.rows import dict_row

        conn = psycopg.connect(DATABASE_URL, autocommit=True, row_factory=dict_row, connect_timeout=10)
        # Supabase의 다른 테이블과 섞이지 않게 전용 스키마를 쓴다
        conn.execute("CREATE SCHEMA IF NOT EXISTS idly")
        conn.execute("SET search_path TO idly")
        return conn
    DATA_DIR.mkdir(exist_ok=True)
    conn = sqlite3.connect(DATA_DIR / "idly.db", check_same_thread=False, isolation_level=None)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


_conn = _open()


def _sql(query: str) -> str:
    return query.replace("?", "%s") if _PG else query


def _run(query: str, params: Sequence[Any] = (), fetch: str = "") -> Any:
    """쿼리 실행. PostgreSQL 연결이 끊겼으면 한 번 다시 연결한다."""
    global _conn
    with _lock:
        for attempt in (1, 2):
            try:
                cur = _conn.execute(_sql(query), params)
                if fetch == "one":
                    row = cur.fetchone()
                    return dict(row) if row else None
                if fetch == "all":
                    return [dict(r) for r in cur.fetchall()]
                return cur
            except Exception as e:  # 연결 끊김만 재시도
                if not _PG or attempt == 2 or type(e).__name__ not in ("OperationalError", "InterfaceError"):
                    raise
                _conn = _open()


for _statement in _TABLES.format(pk="BIGSERIAL PRIMARY KEY" if _PG else "INTEGER PRIMARY KEY AUTOINCREMENT").split(";"):
    if _statement.strip():
        _run(_statement)

# 예전에 만든 DB에 나중에 생긴 열을 붙인다
_MIGRATIONS = [("mailboxes", "consented_at", "TEXT")]
for _table, _column, _type in _MIGRATIONS:
    if _PG:
        _run(f"ALTER TABLE {_table} ADD COLUMN IF NOT EXISTS {_column} {_type}")
    elif _column not in [r["name"] for r in _run(f"PRAGMA table_info({_table})", (), "all")]:
        _run(f"ALTER TABLE {_table} ADD COLUMN {_column} {_type}")


def backend_name() -> str:
    return "postgresql" if _PG else "sqlite"


# --- 암호화 ---------------------------------------------------------------------

def _fernet() -> Fernet:
    key = os.getenv("IDLY_SECRET_KEY", "").strip()
    if not key:
        print("[idly] 경고: IDLY_SECRET_KEY가 없어 data/secret.key를 씁니다. 운영에서는 환경변수로 설정하세요.")
        DATA_DIR.mkdir(exist_ok=True)
        if not KEY_PATH.exists():
            KEY_PATH.write_bytes(Fernet.generate_key())
        key = KEY_PATH.read_text().strip()
    return Fernet(key.encode())


_cipher = _fernet()


def encrypt(value: str) -> str:
    return _cipher.encrypt(value.encode()).decode()


def decrypt(value: str) -> Optional[str]:
    try:
        return _cipher.decrypt(value.encode()).decode()
    except InvalidToken:
        return None


# --- IDly 계정 --------------------------------------------------------------------

def _hash_password(password: str, salt: Optional[bytes] = None) -> str:
    salt = salt or secrets.token_bytes(16)
    digest = hashlib.scrypt(password.encode(), salt=salt, n=2 ** 14, r=8, p=1)
    return f"scrypt${salt.hex()}${digest.hex()}"


def _check_password(password: str, stored: str) -> bool:
    try:
        _, salt_hex, _ = stored.split("$")
    except ValueError:
        return False
    return hmac.compare_digest(_hash_password(password, bytes.fromhex(salt_hex)), stored)


def create_user(email: str, password: str) -> Optional[int]:
    """이미 있는 이메일이면 None."""
    if _run("SELECT id FROM users WHERE email = ?", (email.lower(),), "one"):
        return None
    row = _run(
        "INSERT INTO users(email, password_hash, created_at) VALUES (?, ?, ?) RETURNING id",
        (email.lower(), _hash_password(password), _now()), "one",
    )
    return row["id"]


def verify_user(email: str, password: str) -> Optional[int]:
    row = _run("SELECT id, password_hash FROM users WHERE email = ?", (email.lower(),), "one")
    if row and _check_password(password, row["password_hash"]):
        return row["id"]
    return None


def get_user(user_id: int) -> Optional[Dict[str, Any]]:
    return _run("SELECT id, email FROM users WHERE id = ?", (user_id,), "one")


def delete_user(user_id: int) -> None:
    """계정 탈퇴: 세션·메일함·결과·조치 기록까지 함께 지워진다 (ON DELETE CASCADE)."""
    _run("DELETE FROM users WHERE id = ?", (user_id,))


def create_session(user_id: int) -> str:
    token = secrets.token_urlsafe(32)
    _run("INSERT INTO sessions(token, user_id, created_at) VALUES (?, ?, ?)", (token, user_id, _now()))
    return token


def session_user(token: str) -> Optional[Dict[str, Any]]:
    if not token:
        return None
    row = _run(
        "SELECT u.id, u.email, s.created_at FROM sessions s JOIN users u ON u.id = s.user_id WHERE s.token = ?",
        (token,), "one",
    )
    if not row:
        return None
    # 만료된 세션은 지운다
    if datetime.fromisoformat(row["created_at"]) < datetime.now() - timedelta(days=SESSION_DAYS):
        delete_session(token)
        return None
    return {"id": row["id"], "email": row["email"]}


def delete_session(token: str) -> None:
    _run("DELETE FROM sessions WHERE token = ?", (token,))


def delete_all_sessions(user_id: int) -> None:
    _run("DELETE FROM sessions WHERE user_id = ?", (user_id,))


# --- 연동 메일 --------------------------------------------------------------------

def upsert_mailbox(user_id: int, email: str, provider: str, host: str, port: int, username: str,
                   secret: str, consented: bool) -> None:
    """같은 메일을 다시 연동하면 자격 증명만 바꾸고 탐색 결과는 둔다."""
    _run(
        """INSERT INTO mailboxes(user_id, email, provider, host, port, username, auth, secret, consented_at, created_at)
           VALUES (?, ?, ?, ?, ?, ?, 'password', ?, ?, ?)
           ON CONFLICT(user_id, email) DO UPDATE SET
             provider = excluded.provider, host = excluded.host, port = excluded.port,
             username = excluded.username, secret = excluded.secret, consented_at = excluded.consented_at""",
        (user_id, email.lower(), provider, host, port, username, encrypt(secret),
         _now() if consented else None, _now()),
    )


def list_mailboxes(user_id: int) -> List[Dict[str, Any]]:
    return _run(
        "SELECT email, provider, scanned_at FROM mailboxes WHERE user_id = ? ORDER BY created_at, id", (user_id,), "all"
    )


def get_mailbox(user_id: int, email: str) -> Optional[Dict[str, Any]]:
    mailbox = _run("SELECT * FROM mailboxes WHERE user_id = ? AND email = ?", (user_id, email.lower()), "one")
    if mailbox:
        mailbox["secret"] = decrypt(mailbox["secret"])
    return mailbox


def delete_mailbox(user_id: int, email: str) -> None:
    _run("DELETE FROM mailboxes WHERE user_id = ? AND email = ?", (user_id, email.lower()))


def save_report(user_id: int, email: str, report: Dict[str, Any]) -> None:
    _run(
        "UPDATE mailboxes SET report = ?, scanned_at = ? WHERE user_id = ? AND email = ?",
        (json.dumps(report, ensure_ascii=False), _now(), user_id, email.lower()),
    )


def get_report(user_id: int, email: str) -> Optional[Dict[str, Any]]:
    row = _run("SELECT report FROM mailboxes WHERE user_id = ? AND email = ?", (user_id, email.lower()), "one")
    return json.loads(row["report"]) if row and row["report"] else None


# --- 조치 기록 (감사 로그) -----------------------------------------------------------

def log_action(user_id: int, service: str, account_email: str, action: str, event: str, detail: str = "") -> None:
    _run(
        "INSERT INTO action_log(user_id, service, account_email, action, event, detail, created_at) VALUES (?, ?, ?, ?, ?, ?, ?)",
        (user_id, service, account_email, action, event, detail, _now()),
    )


def list_actions(user_id: int, limit: int = 100) -> List[Dict[str, Any]]:
    return _run(
        "SELECT service, account_email, action, event, detail, created_at FROM action_log WHERE user_id = ? ORDER BY id DESC LIMIT ?",
        (user_id, limit), "all",
    )

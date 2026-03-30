import sqlite3
import threading
import hashlib
from contextlib import contextmanager

try:
    import bcrypt
except ImportError:
    print("BŁĄD: Zainstaluj bibliotekę bcrypt: pip install bcrypt")
    exit()

DB_PATH = 'chat.db'
_local = threading.local()


@contextmanager
def get_conn():
    """Thread-local connection — jedna na wątek, nie otwieramy za każdym razem nowej."""
    if not hasattr(_local, 'conn') or _local.conn is None:
        _local.conn = sqlite3.connect(DB_PATH, check_same_thread=False)
        _local.conn.row_factory = sqlite3.Row
    try:
        yield _local.conn
    except Exception:
        _local.conn.rollback()
        raise


# ---------------------------------------------------------------------------
# Inicjalizacja
# ---------------------------------------------------------------------------

def init_db():
    with get_conn() as conn:
        conn.executescript('''
            CREATE TABLE IF NOT EXISTS users (
                id            INTEGER PRIMARY KEY AUTOINCREMENT,
                username      TEXT    UNIQUE NOT NULL,
                password_hash TEXT    NOT NULL,
                hash_type     TEXT    NOT NULL DEFAULT 'bcrypt',
                public_key    TEXT    DEFAULT NULL
            );

            CREATE INDEX IF NOT EXISTS idx_users_username
                ON users (username);

            CREATE TABLE IF NOT EXISTS messages (
                id        INTEGER  PRIMARY KEY AUTOINCREMENT,
                sender    TEXT     NOT NULL,
                recipient TEXT     NOT NULL,
                content   TEXT     NOT NULL,
                timestamp DATETIME DEFAULT CURRENT_TIMESTAMP
            );

            CREATE TABLE IF NOT EXISTS groups (
                id   INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT    UNIQUE NOT NULL
            );

            CREATE TABLE IF NOT EXISTS group_members (
                group_name TEXT NOT NULL,
                username   TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS group_requests (
                group_name   TEXT NOT NULL,
                username     TEXT NOT NULL,
                request_type TEXT NOT NULL,
                UNIQUE (group_name, username, request_type)
            );

            -- Indeksy przyspieszające typowe zapytania
            CREATE INDEX IF NOT EXISTS idx_messages_recipient
                ON messages (recipient);
            CREATE INDEX IF NOT EXISTS idx_messages_sender
                ON messages (sender);
            CREATE INDEX IF NOT EXISTS idx_group_members_group
                ON group_members (group_name);
            CREATE INDEX IF NOT EXISTS idx_group_members_user
                ON group_members (username);
            CREATE INDEX IF NOT EXISTS idx_group_requests_user
                ON group_requests (username);
        ''')
        # Migracja dla istniejących baz — dodaje kolumnę hash_type jeśli jej nie ma.
        # Stare konta dostaną 'sha256', nowe domyślnie 'bcrypt'.
        try:
            conn.execute("ALTER TABLE users ADD COLUMN hash_type TEXT NOT NULL DEFAULT 'sha256'")
            conn.commit()
        except sqlite3.OperationalError:
            pass  # Kolumna już istnieje — wszystko OK

        # Migracja: kolumna public_key dla E2EE
        try:
            conn.execute("ALTER TABLE users ADD COLUMN public_key TEXT DEFAULT NULL")
            conn.commit()
        except sqlite3.OperationalError:
            pass


# ---------------------------------------------------------------------------
# Walidacja
# ---------------------------------------------------------------------------

MAX_USERNAME_LEN = 32
MAX_PASSWORD_LEN = 128
MAX_GROUP_NAME_LEN = 40
MAX_MESSAGE_LEN = 4000


def _validate_username(username: str) -> str:
    """Rzuca ValueError przy nieprawidłowej nazwie, zwraca oczyszczoną."""
    if not username or not isinstance(username, str):
        raise ValueError("Nazwa użytkownika nie może być pusta.")
    username = username.strip()
    if len(username) > MAX_USERNAME_LEN:
        raise ValueError(f"Nazwa użytkownika max {MAX_USERNAME_LEN} znaków.")
    if not username.replace('_', '').replace('-', '').isalnum():
        raise ValueError("Nazwa może zawierać tylko litery, cyfry, _ i -.")
    return username


def _validate_password(password: str):
    if not password or not isinstance(password, str):
        raise ValueError("Hasło nie może być puste.")
    if len(password) < 4:
        raise ValueError("Hasło musi mieć co najmniej 4 znaki.")
    if len(password) > MAX_PASSWORD_LEN:
        raise ValueError(f"Hasło max {MAX_PASSWORD_LEN} znaków.")


def _validate_message(content: str):
    if not content or not isinstance(content, str):
        raise ValueError("Treść wiadomości nie może być pusta.")
    if len(content) > MAX_MESSAGE_LEN * 4:
        # *4 bo zaszyfrowana wiadomość jest dłuższa od oryginału
        raise ValueError("Wiadomość jest za długa.")


# ---------------------------------------------------------------------------
# Użytkownicy
# ---------------------------------------------------------------------------

def hash_password(password: str) -> str:
    return bcrypt.hashpw(password.encode('utf-8'), bcrypt.gensalt()).decode('utf-8')


def _sha256_hash(password: str) -> str:
    """Stary algorytm — używany tylko przy leniwej migracji."""
    return hashlib.sha256(password.encode('utf-8')).hexdigest()


def verify_password(password: str, hashed: str) -> bool:
    try:
        return bcrypt.checkpw(password.encode('utf-8'), hashed.encode('utf-8'))
    except Exception:
        return False


def register_user(username: str, password: str) -> tuple[bool, str]:
    """Zwraca (sukces, komunikat)."""
    try:
        username = _validate_username(username)
        _validate_password(password)
    except ValueError as e:
        return False, str(e)

    hashed = hash_password(password)
    try:
        with get_conn() as conn:
            conn.execute(
                'INSERT INTO users (username, password_hash) VALUES (?, ?)',
                (username, hashed)
            )
            conn.commit()
        return True, "Zarejestrowano pomyślnie!"
    except sqlite3.IntegrityError:
        return False, "Nazwa użytkownika jest zajęta."


def verify_user(username: str, password: str) -> bool:
    """
    Weryfikuje hasło z leniwą migracją SHA-256 → bcrypt.

    Przy pierwszym logowaniu po migracji:
      1. Sprawdza stary hash SHA-256.
      2. Jeśli pasuje — od razu nadpisuje bcryptem i ustawia hash_type='bcrypt'.
      3. Kolejne logowania trafiają już tylko do bcrypt.
    """
    try:
        username = _validate_username(username)
    except ValueError:
        return False

    with get_conn() as conn:
        row = conn.execute(
            'SELECT password_hash, hash_type FROM users WHERE username = ?',
            (username,)
        ).fetchone()

    if row is None:
        # Timing attack guard — wykonujemy kosztowną operację nawet gdy
        # użytkownik nie istnieje, żeby czas odpowiedzi był taki sam.
        bcrypt.checkpw(b'dummy', bcrypt.hashpw(b'dummy', bcrypt.gensalt()))
        return False

    stored_hash = row['password_hash']
    hash_type = row['hash_type'] if row['hash_type'] else 'sha256'

    if hash_type == 'bcrypt':
        # Nowa ścieżka — zwykła weryfikacja bcrypt
        return verify_password(password, stored_hash)

    # Stara ścieżka SHA-256
    if _sha256_hash(password) != stored_hash:
        return False

    # Hasło poprawne — migrujemy do bcrypt przy okazji tego logowania
    new_hash = hash_password(password)
    with get_conn() as conn:
        conn.execute(
            "UPDATE users SET password_hash = ?, hash_type = 'bcrypt' WHERE username = ?",
            (new_hash, username)
        )
        conn.commit()

    return True


def get_all_users() -> list[str]:
    with get_conn() as conn:
        rows = conn.execute(
            'SELECT username FROM users ORDER BY username ASC'
        ).fetchall()
    return [r['username'] for r in rows]


def store_public_key(username: str, public_key_pem: str):
    """Zapisuje klucz publiczny RSA użytkownika (PEM jako tekst)."""
    with get_conn() as conn:
        conn.execute(
            'UPDATE users SET public_key = ? WHERE username = ?',
            (public_key_pem, username)
        )
        conn.commit()


def get_public_key(username: str) -> str | None:
    """Zwraca klucz publiczny RSA użytkownika lub None jeśli brak."""
    with get_conn() as conn:
        row = conn.execute(
            'SELECT public_key FROM users WHERE username = ?', (username,)
        ).fetchone()
    return row['public_key'] if row else None


# ---------------------------------------------------------------------------
# Wiadomości
# ---------------------------------------------------------------------------

def save_message(sender: str, recipient: str, content: str):
    try:
        _validate_message(content)
    except ValueError:
        return  # Za długa — po cichu odrzucamy (serwer powinien sprawdzać wcześniej)

    with get_conn() as conn:
        conn.execute(
            'INSERT INTO messages (sender, recipient, content) VALUES (?, ?, ?)',
            (sender, recipient, content)
        )
        conn.commit()


def get_global_history(limit: int = 50) -> list[dict]:
    with get_conn() as conn:
        rows = conn.execute(
            '''SELECT sender, content, strftime("%H:%M", timestamp, "localtime")
               FROM messages
               WHERE recipient = "Globalny"
               ORDER BY id DESC LIMIT ?''',
            (limit,)
        ).fetchall()
    return [{"sender": r[0], "content": r[1], "timestamp": r[2]} for r in reversed(rows)]


def get_private_history(username: str, limit: int = 100) -> list[dict]:
    with get_conn() as conn:
        rows = conn.execute(
            '''SELECT sender, recipient, content, strftime("%H:%M", timestamp, "localtime")
               FROM messages
               WHERE recipient != "Globalny"
                 AND recipient NOT LIKE "#%%"
                 AND (sender = ? OR recipient = ?)
               ORDER BY id DESC LIMIT ?''',
            (username, username, limit)
        ).fetchall()
    return [
        {"sender": r[0], "recipient": r[1], "content": r[2], "timestamp": r[3]}
        for r in reversed(rows)
    ]


def get_group_history(group_name: str, limit: int = 50) -> list[dict]:
    with get_conn() as conn:
        rows = conn.execute(
            '''SELECT sender, content, strftime("%H:%M", timestamp, "localtime")
               FROM messages
               WHERE recipient = ?
               ORDER BY id DESC LIMIT ?''',
            (group_name, limit)
        ).fetchall()
    return [
        {"sender": r[0], "group": group_name, "content": r[1], "timestamp": r[2]}
        for r in reversed(rows)
    ]


# ---------------------------------------------------------------------------
# Grupy
# ---------------------------------------------------------------------------

def create_group(name: str, creator: str) -> bool:
    with get_conn() as conn:
        existing = conn.execute(
            'SELECT name FROM groups WHERE LOWER(name) = LOWER(?)', (name,)
        ).fetchone()
        if existing:
            return False
        try:
            conn.execute('INSERT INTO groups (name) VALUES (?)', (name,))
            conn.execute(
                'INSERT INTO group_members (group_name, username) VALUES (?, ?)',
                (name, creator)
            )
            conn.commit()
            return True
        except sqlite3.IntegrityError:
            return False


def join_group(name: str, username: str) -> str:
    with get_conn() as conn:
        if not conn.execute(
            'SELECT name FROM groups WHERE name = ?', (name,)
        ).fetchone():
            return "Grupa nie istnieje!"
        if conn.execute(
            'SELECT 1 FROM group_members WHERE group_name = ? AND username = ?',
            (name, username)
        ).fetchone():
            return "Już jesteś w tej grupie!"
        conn.execute(
            'INSERT INTO group_members (group_name, username) VALUES (?, ?)',
            (name, username)
        )
        conn.commit()
    return "OK"


def get_user_groups(username: str) -> list[str]:
    with get_conn() as conn:
        rows = conn.execute(
            'SELECT group_name FROM group_members WHERE username = ?', (username,)
        ).fetchall()
    return [r[0] for r in rows]


def get_group_members(name: str) -> list[str]:
    with get_conn() as conn:
        rows = conn.execute(
            'SELECT username FROM group_members WHERE group_name = ?', (name,)
        ).fetchall()
    return [r[0] for r in rows]


def leave_group(name: str, username: str) -> bool:
    with get_conn() as conn:
        conn.execute(
            'DELETE FROM group_members WHERE group_name = ? AND username = ?',
            (name, username)
        )
        conn.commit()
    return True


def get_group_creator(group_name: str) -> str | None:
    with get_conn() as conn:
        row = conn.execute(
            'SELECT username FROM group_members WHERE group_name = ? ORDER BY rowid ASC LIMIT 1',
            (group_name,)
        ).fetchone()
    return row[0] if row else None


def delete_group(group_name: str, current_user: str) -> bool:
    if get_group_creator(group_name) != current_user:
        return False
    with get_conn() as conn:
        conn.execute('DELETE FROM groups WHERE name = ?', (group_name,))
        conn.execute('DELETE FROM group_members WHERE group_name = ?', (group_name,))
        conn.commit()
    return True


# ---------------------------------------------------------------------------
# Zaproszenia i prośby o dołączenie
# ---------------------------------------------------------------------------

def add_group_request(group_name: str, username: str, req_type: str):
    with get_conn() as conn:
        try:
            conn.execute(
                'INSERT INTO group_requests (group_name, username, request_type) VALUES (?, ?, ?)',
                (group_name, username, req_type)
            )
            conn.commit()
        except sqlite3.IntegrityError:
            pass


def remove_group_request(group_name: str, username: str, req_type: str):
    with get_conn() as conn:
        conn.execute(
            'DELETE FROM group_requests WHERE group_name = ? AND username = ? AND request_type = ?',
            (group_name, username, req_type)
        )
        conn.commit()


def get_user_invites(username: str) -> list[str]:
    with get_conn() as conn:
        rows = conn.execute(
            'SELECT group_name FROM group_requests WHERE username = ? AND request_type = "invite"',
            (username,)
        ).fetchall()
    return [r[0] for r in rows]


def get_creator_join_requests(creator_username: str) -> list[dict]:
    with get_conn() as conn:
        rows = conn.execute(
            'SELECT group_name, username FROM group_requests WHERE request_type = "join"'
        ).fetchall()
    return [
        {"group": r[0], "user": r[1]}
        for r in rows
        if get_group_creator(r[0]) == creator_username
    ]


init_db()
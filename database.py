import sqlite3
import hashlib


def init_db():
    conn = sqlite3.connect('chat.db')
    cursor = conn.cursor()
    cursor.execute('''
                   CREATE TABLE IF NOT EXISTS users
                   (
                       id
                       INTEGER
                       PRIMARY
                       KEY
                       AUTOINCREMENT,
                       username
                       TEXT
                       UNIQUE
                       NOT
                       NULL,
                       password_hash
                       TEXT
                       NOT
                       NULL
                   )
                   ''')
    cursor.execute('''
                   CREATE TABLE IF NOT EXISTS messages
                   (
                       id
                       INTEGER
                       PRIMARY
                       KEY
                       AUTOINCREMENT,
                       sender
                       TEXT
                       NOT
                       NULL,
                       recipient
                       TEXT
                       NOT
                       NULL,
                       content
                       TEXT
                       NOT
                       NULL,
                       timestamp
                       DATETIME
                       DEFAULT
                       CURRENT_TIMESTAMP
                   )
                   ''')
    cursor.execute('''
                   CREATE TABLE IF NOT EXISTS groups
                   (
                       id
                       INTEGER
                       PRIMARY
                       KEY
                       AUTOINCREMENT,
                       name
                       TEXT
                       UNIQUE
                       NOT
                       NULL
                   )
                   ''')
    cursor.execute('''
                   CREATE TABLE IF NOT EXISTS group_members
                   (
                       group_name
                       TEXT
                       NOT
                       NULL,
                       username
                       TEXT
                       NOT
                       NULL
                   )
                   ''')
    cursor.execute('''
                   CREATE TABLE IF NOT EXISTS group_requests
                   (
                       group_name
                       TEXT
                       NOT
                       NULL,
                       username
                       TEXT
                       NOT
                       NULL,
                       request_type
                       TEXT
                       NOT
                       NULL,
                       UNIQUE
                   (
                       group_name,
                       username,
                       request_type
                   )
                       )
                   ''')
    conn.commit()
    conn.close()


def hash_password(password):
    return hashlib.sha256(password.encode('utf-8')).hexdigest()


def register_user(username, password):
    conn = sqlite3.connect('chat.db')
    cursor = conn.cursor()
    hashed = hash_password(password)
    try:
        cursor.execute('INSERT INTO users (username, password_hash) VALUES (?, ?)', (username, hashed))
        conn.commit()
        return True
    except sqlite3.IntegrityError:
        return False
    finally:
        conn.close()


def verify_user(username, password):
    conn = sqlite3.connect('chat.db')
    cursor = conn.cursor()
    hashed = hash_password(password)
    cursor.execute('SELECT id FROM users WHERE username = ? AND password_hash = ?', (username, hashed))
    user = cursor.fetchone()
    conn.close()
    return user is not None


def get_all_users():
    conn = sqlite3.connect('chat.db')
    cursor = conn.cursor()
    cursor.execute('SELECT username FROM users ORDER BY username ASC')
    rows = cursor.fetchall()
    conn.close()
    return [row[0] for row in rows]


def save_message(sender, recipient, content):
    conn = sqlite3.connect('chat.db')
    cursor = conn.cursor()
    cursor.execute('INSERT INTO messages (sender, recipient, content) VALUES (?, ?, ?)', (sender, recipient, content))
    conn.commit()
    conn.close()


def get_global_history(limit=50):
    conn = sqlite3.connect('chat.db')
    cursor = conn.cursor()
    cursor.execute(
        'SELECT sender, content, strftime("%H:%M", timestamp, "localtime") FROM messages WHERE recipient = "Globalny" ORDER BY id DESC LIMIT ?',
        (limit,))
    rows = cursor.fetchall()
    conn.close()
    return [{"sender": row[0], "content": row[1], "timestamp": row[2]} for row in reversed(rows)]


def get_private_history(username, limit=100):
    conn = sqlite3.connect('chat.db')
    cursor = conn.cursor()
    cursor.execute('''
                   SELECT sender, recipient, content, strftime("%H:%M", timestamp, "localtime")
                   FROM messages
                   WHERE recipient != "Globalny" AND recipient NOT LIKE "#%" AND (sender = ? OR recipient = ?)
                   ORDER BY id DESC LIMIT ?
                   ''', (username, username, limit))
    rows = cursor.fetchall()
    conn.close()
    return [{"sender": row[0], "recipient": row[1], "content": row[2], "timestamp": row[3]} for row in reversed(rows)]


def create_group(name, creator):
    conn = sqlite3.connect('chat.db')
    cursor = conn.cursor()

    # NOWOŚĆ: Sprawdzamy czy taka nazwa już istnieje w bazie (ignorując wielkość liter - LOWER)
    cursor.execute('SELECT name FROM groups WHERE LOWER(name) = LOWER(?)', (name,))
    if cursor.fetchone():
        conn.close()
        return False  # Grupa już istnieje (nawet jeśli ktoś wpisał ją z innej wielkości liter)

    try:
        cursor.execute('INSERT INTO groups (name) VALUES (?)', (name,))
        cursor.execute('INSERT INTO group_members (group_name, username) VALUES (?, ?)', (name, creator))
        conn.commit()
        return True
    except sqlite3.IntegrityError:
        return False
    finally:
        conn.close()


def join_group(name, username):
    conn = sqlite3.connect('chat.db')
    cursor = conn.cursor()
    cursor.execute('SELECT name FROM groups WHERE name = ?', (name,))
    if not cursor.fetchone():
        conn.close()
        return "Grupa nie istnieje!"

    cursor.execute('SELECT * FROM group_members WHERE group_name = ? AND username = ?', (name, username))
    if cursor.fetchone():
        conn.close()
        return "Już jesteś w tej grupie!"

    cursor.execute('INSERT INTO group_members (group_name, username) VALUES (?, ?)', (name, username))
    conn.commit()
    conn.close()
    return "OK"


def get_user_groups(username):
    conn = sqlite3.connect('chat.db')
    cursor = conn.cursor()
    cursor.execute('SELECT group_name FROM group_members WHERE username = ?', (username,))
    rows = cursor.fetchall()
    conn.close()
    return [row[0] for row in rows]


def get_group_members(name):
    conn = sqlite3.connect('chat.db')
    cursor = conn.cursor()
    cursor.execute('SELECT username FROM group_members WHERE group_name = ?', (name,))
    rows = cursor.fetchall()
    conn.close()
    return [row[0] for row in rows]


def get_group_history(group_name, limit=50):
    conn = sqlite3.connect('chat.db')
    cursor = conn.cursor()
    cursor.execute(
        'SELECT sender, content, strftime("%H:%M", timestamp, "localtime") FROM messages WHERE recipient = ? ORDER BY id DESC LIMIT ?',
        (group_name, limit))
    rows = cursor.fetchall()
    conn.close()
    return [{"sender": row[0], "group": group_name, "content": row[1], "timestamp": row[2]} for row in reversed(rows)]


def leave_group(name, username):
    conn = sqlite3.connect('chat.db')
    cursor = conn.cursor()
    cursor.execute('DELETE FROM group_members WHERE group_name = ? AND username = ?', (name, username))
    conn.commit()
    conn.close()
    return True


def get_group_creator(group_name):
    conn = sqlite3.connect('chat.db')
    cursor = conn.cursor()
    cursor.execute('SELECT username FROM group_members WHERE group_name = ? ORDER BY rowid ASC LIMIT 1', (group_name,))
    row = cursor.fetchone()
    conn.close()
    return row[0] if row else None


def delete_group(group_name, current_user):
    creator = get_group_creator(group_name)
    if creator != current_user:
        return False
    conn = sqlite3.connect('chat.db')
    cursor = conn.cursor()
    cursor.execute('DELETE FROM groups WHERE name = ?', (group_name,))
    cursor.execute('DELETE FROM group_members WHERE group_name = ?', (group_name,))
    conn.commit()
    conn.close()
    return True


def add_group_request(group_name, username, req_type):
    conn = sqlite3.connect('chat.db')
    cursor = conn.cursor()
    try:
        cursor.execute('INSERT INTO group_requests (group_name, username, request_type) VALUES (?, ?, ?)',
                       (group_name, username, req_type))
        conn.commit()
    except sqlite3.IntegrityError:
        pass
    conn.close()


def remove_group_request(group_name, username, req_type):
    conn = sqlite3.connect('chat.db')
    cursor = conn.cursor()
    cursor.execute('DELETE FROM group_requests WHERE group_name = ? AND username = ? AND request_type = ?',
                   (group_name, username, req_type))
    conn.commit()
    conn.close()


def get_user_invites(username):
    conn = sqlite3.connect('chat.db')
    cursor = conn.cursor()
    cursor.execute('SELECT group_name FROM group_requests WHERE username = ? AND request_type = "invite"', (username,))
    rows = cursor.fetchall()
    conn.close()
    return [r[0] for r in rows]


def get_creator_join_requests(creator_username):
    conn = sqlite3.connect('chat.db')
    cursor = conn.cursor()
    cursor.execute('SELECT group_name, username FROM group_requests WHERE request_type = "join"')
    rows = cursor.fetchall()
    conn.close()
    res = []
    for r in rows:
        if get_group_creator(r[0]) == creator_username:
            res.append({"group": r[0], "user": r[1]})
    return res


init_db()
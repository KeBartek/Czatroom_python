"""
chat_client.py — warstwa sieciowa i logika biznesowa.
Bez GUI — komunikuje się z ui.py przez callbacki.
"""

import socket
import json
import threading
import os
import base64
from datetime import datetime

try:
    from cryptography.fernet import Fernet
except ImportError:
    print("BŁĄD: pip install cryptography")
    exit()

import e2ee

CIPHER_KEY = b'MDEyMzQ1Njc4OTAxMjM0NTY3ODkwMTIzNDU2Nzg5MDE='
MAX_FILE_SIZE = 5 * 1024 * 1024


class ChatClient:
    """
    Obsługuje połączenie z serwerem, szyfrowanie i routing wiadomości.
    GUI rejestruje callbacki przez on() i wywołuje metody send_*().
    """

    def __init__(self):
        self._cipher = Fernet(CIPHER_KEY)
        self._sock: socket.socket | None = None
        self._sock_file = None
        self._lock = threading.Lock()

        self.username: str | None = None
        self.server_ip = "127.0.0.1"
        self.server_port = 9999

        # E2EE
        self._private_key, self.public_key_pem = e2ee.load_or_generate_keypair()
        self._peer_keys: dict = {}
        self._pending: dict[str, list[tuple[str, str]]] = {}

        # Callbacki rejestrowane przez UI
        self._handlers: dict[str, list] = {}

    # ------------------------------------------------------------------
    # Rejestracja callbacków
    # ------------------------------------------------------------------

    def on(self, event: str, fn):
        """Rejestruje callback na zdarzenie. Można rejestrować wiele na jedno zdarzenie."""
        self._handlers.setdefault(event, []).append(fn)

    def _emit(self, event: str, *args, **kwargs):
        for fn in self._handlers.get(event, []):
            try:
                fn(*args, **kwargs)
            except Exception as e:
                print(f"[CALLBACK ERROR] {event}: {e}")

    # ------------------------------------------------------------------
    # Połączenie
    # ------------------------------------------------------------------

    def connect(self, ip: str, port: int) -> bool:
        try:
            self._sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            self._sock.connect((ip, port))
            self._sock_file = self._sock.makefile('r', encoding='utf-8')
            self.server_ip = ip
            self.server_port = port
            return True
        except Exception as e:
            self._sock = None
            self._emit('connect_error', str(e))
            return False

    def disconnect(self):
        if self._sock:
            try:
                self._sock.close()
            except Exception:
                pass
            self._sock = None

    # ------------------------------------------------------------------
    # Auth
    # ------------------------------------------------------------------

    def login(self, username: str, password: str):
        self._send_raw({"action": "login", "username": username, "password": password})
        resp = self._read_one()
        if resp and resp.get("status") == "success":
            self.username = username
            self._send_raw({"action": "upload_public_key", "public_key": self.public_key_pem})
            threading.Thread(target=self._receive_loop, daemon=True).start()
            self._emit('login_success', username)
        else:
            msg = resp.get("message", "Błąd logowania.") if resp else "Brak odpowiedzi."
            self._emit('login_error', msg)

    def register(self, username: str, password: str):
        self._send_raw({"action": "register", "username": username, "password": password})
        resp = self._read_one()
        if resp and resp.get("status") == "success":
            self._emit('register_success', resp.get("message", ""))
        else:
            msg = resp.get("message", "Błąd rejestracji.") if resp else "Brak odpowiedzi."
            self._emit('register_error', msg)

    # ------------------------------------------------------------------
    # Wysyłanie wiadomości
    # ------------------------------------------------------------------

    def send_global(self, text: str):
        enc = self._cipher.encrypt(text.encode()).decode()
        self._send_raw({"action": "broadcast_message", "content": enc})

    def send_group(self, group: str, text: str):
        enc = self._cipher.encrypt(text.encode()).decode()
        self._send_raw({"action": "group_message", "group": group, "content": enc})

    def send_private(self, recipient: str, text: str) -> bool:
        """
        Szyfruje i wysyła wiadomość prywatną E2EE.
        Jeśli klucz publiczny odbiorcy jest nieznany — kolejkuje i pobiera.
        Zwraca True jeśli wysłano od razu, False jeśli zakolejkowano.
        """
        if recipient not in self._peer_keys:
            self._pending.setdefault(recipient, []).append(
                (text, datetime.now().strftime("%H:%M"))
            )
            self._send_raw({"action": "get_public_key", "username": recipient})
            return False
        enc = e2ee.encrypt(text, self._peer_keys[recipient])
        self._send_raw({"action": "private_message", "recipient": recipient, "content": enc})
        return True

    def send_file(self, target: str, filepath: str) -> bool:
        if os.path.getsize(filepath) > MAX_FILE_SIZE:
            self._emit('error', "Plik za duży (max 5 MB).")
            return False
        filename = os.path.basename(filepath)
        file_id = f"{int(datetime.now().timestamp())}_{self.username}_{filename}"
        with open(filepath, "rb") as f:
            encoded = base64.b64encode(f.read()).decode()
        self._send_raw({
            "action": "send_file", "target": target,
            "filename": filename, "file_id": file_id, "data": encoded
        })
        return True

    def request_download(self, file_id: str, filename: str):
        self._send_raw({"action": "download_request", "file_id": file_id, "filename": filename})

    def send_typing(self, target: str):
        self._send_raw({"action": "typing", "target": target})

    # ------------------------------------------------------------------
    # Grupy
    # ------------------------------------------------------------------

    def create_group(self, name: str):
        formatted = "#" + name.strip().replace(" ", "_").replace("#", "")
        self._send_raw({"action": "create_group", "name": formatted})

    def join_group(self, name: str):
        formatted = "#" + name.strip().replace(" ", "_").replace("#", "")
        self._send_raw({"action": "join_group", "name": formatted})

    def leave_group(self, name: str):
        self._send_raw({"action": "leave_group", "name": name})

    def delete_group(self, name: str):
        self._send_raw({"action": "delete_group", "group": name})

    def get_group_info(self, name: str):
        self._send_raw({"action": "get_group_info", "group": name})

    def invite_to_group(self, group: str, user: str):
        self._send_raw({"action": "add_user_to_group", "group": group, "user": user})

    def kick_from_group(self, group: str, user: str):
        self._send_raw({"action": "kick_user", "group": group, "user": user})

    def resolve_join(self, group: str, user: str, accept: bool):
        self._send_raw({"action": "resolve_join", "group": group, "user": user, "accept": accept})

    def resolve_invite(self, group: str, accept: bool):
        self._send_raw({"action": "resolve_invite", "group": group, "accept": accept})

    # ------------------------------------------------------------------
    # Pętla odbioru
    # ------------------------------------------------------------------

    def _receive_loop(self):
        try:
            for raw in self._sock_file:
                if not raw.strip():
                    continue
                try:
                    msg = json.loads(raw)
                except json.JSONDecodeError:
                    continue
                self._route(msg)
        except Exception as e:
            self._emit('disconnected', str(e))

    def _route(self, msg: dict):
        action = msg.get("action")
        status = msg.get("status")

        if action == "chat_message":
            sender = msg["sender"]
            content = self._dec_fernet(msg.get("content", ""))
            self._emit('global_message', sender, content, msg.get("timestamp", ""))

        elif action == "private_message":
            sender = msg["sender"]
            raw_content = msg.get("content", "")
            content = self._dec_e2ee(raw_content)
            is_e2ee = e2ee.is_e2ee_blob(raw_content)
            self._emit('private_message', sender, content, msg.get("timestamp", ""), is_e2ee)

        elif action == "group_message":
            sender = msg["sender"]
            group = msg["group"]
            content = self._dec_fernet(msg.get("content", ""))
            self._emit('group_message', sender, group, content, msg.get("timestamp", ""))

        elif action == "public_key_response":
            self._handle_public_key(msg)

        elif action == "chat_history":
            history = [
                {"sender": m["sender"],
                 "content": self._dec_fernet(m.get("content", "")),
                 "timestamp": m.get("timestamp", "")}
                for m in msg.get("history", [])
            ]
            self._emit('chat_history', history)

        elif action == "private_history":
            history = []
            for m in msg.get("history", []):
                raw = m.get("content", "")
                history.append({
                    "sender": m["sender"],
                    "recipient": m["recipient"],
                    "content": self._dec_e2ee(raw) if e2ee.is_e2ee_blob(raw) else self._dec_fernet(raw),
                    "timestamp": m.get("timestamp", ""),
                    "is_e2ee": e2ee.is_e2ee_blob(raw),
                })
            self._emit('private_history', history)

        elif action == "group_history":
            history = [
                {"sender": m["sender"],
                 "content": self._dec_fernet(m.get("content", "")),
                 "timestamp": m.get("timestamp", "")}
                for m in msg.get("history", [])
            ]
            self._emit('group_history', msg["group"], history)

        elif action == "user_list":
            self._emit('user_list', msg.get("all_users", []), msg.get("online_users", []))

        elif action == "your_groups":
            self._emit('groups_updated', msg.get("groups", []))

        elif action == "group_info":
            self._emit('group_info', msg["group"], msg.get("members", []), msg.get("creator"))

        elif action == "typing":
            self._emit('typing', msg.get("sender"), msg.get("target"))

        elif action == "receive_download":
            self._emit('file_received', msg["filename"], msg["data"])

        elif action == "kicked_from_group":
            self._emit('kicked', msg["group"])

        elif action == "group_deleted":
            self._emit('group_deleted', msg["group"])

        elif action == "join_request_received":
            self._emit('join_request', msg["group"], msg["user"])

        elif action == "invite_received":
            self._emit('invite_received', msg["group"], msg.get("admin", ""))

        elif action == "pending_requests":
            for inv in msg.get("invites", []):
                self._emit('invite_received', inv, "właściciela")
            for req in msg.get("join_reqs", []):
                self._emit('join_request', req["group"], req["user"])

        elif status == "error":
            self._emit('error', msg.get("message", "Nieznany błąd."))

        elif status == "success":
            self._emit('success', msg.get("message", ""))

    # ------------------------------------------------------------------
    # E2EE helpers
    # ------------------------------------------------------------------

    def _handle_public_key(self, msg: dict):
        user = msg.get("username", "")
        pem = msg.get("public_key")
        if not pem or not user:
            return
        try:
            self._peer_keys[user] = e2ee.public_key_from_pem(pem)
        except Exception:
            return
        pending = self._pending.pop(user, [])
        for text, timestamp in pending:
            enc = e2ee.encrypt(text, self._peer_keys[user])
            self._send_raw({"action": "private_message", "recipient": user, "content": enc})
            self._emit('pending_sent', user, text, timestamp)

    def _dec_fernet(self, text: str) -> str:
        try:
            return self._cipher.decrypt(text.encode()).decode()
        except Exception:
            return text

    def _dec_e2ee(self, text: str) -> str:
        try:
            return e2ee.decrypt(text, self._private_key)
        except Exception:
            return "🔒 [Nie można odszyfrować]"

    # ------------------------------------------------------------------
    # Transport
    # ------------------------------------------------------------------

    def _send_raw(self, packet: dict):
        if not self._sock:
            return
        with self._lock:
            try:
                self._sock.sendall((json.dumps(packet) + "\n").encode('utf-8'))
            except Exception:
                pass

    def _read_one(self) -> dict | None:
        try:
            line = self._sock_file.readline()
            return json.loads(line) if line.strip() else None
        except Exception:
            return None
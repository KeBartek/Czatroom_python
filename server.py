import customtkinter as ctk
import socket
import threading
import json
import database
import os
import base64
from datetime import datetime
from tkinter import messagebox

try:
    from cryptography.fernet import Fernet
except ImportError:
    print("BŁĄD: pip install cryptography")
    exit()

ctk.set_appearance_mode("dark")
ctk.set_default_color_theme("blue")

# Uwaga: w prawdziwym E2EE klucze są generowane po stronie klienta.
# Ten klucz służy tylko do szyfrowania wiadomości systemowych serwera.
CIPHER_KEY = b'MDEyMzQ1Njc4OTAxMjM0NTY3ODkwMTIzNDU2Nzg5MDE='
cipher = Fernet(CIPHER_KEY)

# ---------------------------------------------------------------------------
# Współdzielony stan — ZAWSZE przez _users_lock
# ---------------------------------------------------------------------------
active_users: dict[str, socket.socket] = {}
_users_lock = threading.Lock()

server_app_instance = None

MAX_FILE_SIZE = 5 * 1024 * 1024        # 5 MB
MAX_MESSAGE_LEN = database.MAX_MESSAGE_LEN


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def log_message(msg: str):
    print(msg)
    if server_app_instance:
        server_app_instance.add_log(msg)


def encrypt_system_msg(text: str) -> str:
    return cipher.encrypt(text.encode('utf-8')).decode('utf-8')


def send_to(conn: socket.socket, packet: dict):
    try:
        conn.sendall((json.dumps(packet) + "\n").encode('utf-8'))
    except Exception:
        pass


def broadcast(packet: dict):
    data = (json.dumps(packet) + "\n").encode('utf-8')
    with _users_lock:
        targets = list(active_users.values())
    for conn in targets:
        try:
            conn.sendall(data)
        except Exception:
            pass


def broadcast_to_group(group_name: str, packet: dict, exclude: str | None = None):
    members = database.get_group_members(group_name)
    with _users_lock:
        snapshot = dict(active_users)
    for m in members:
        if m != exclude and m in snapshot:
            send_to(snapshot[m], packet)


def broadcast_user_list():
    with _users_lock:
        online = list(active_users.keys())
    all_users = database.get_all_users()
    broadcast({"action": "user_list", "all_users": all_users, "online_users": online})


def get_user_conn(username: str) -> socket.socket | None:
    with _users_lock:
        return active_users.get(username)


def is_online(username: str) -> bool:
    with _users_lock:
        return username in active_users


# ---------------------------------------------------------------------------
# Handlery akcji (każda akcja = osobna funkcja)
# ---------------------------------------------------------------------------

def handle_register(conn, _current_user, msg):
    ok, text = database.register_user(
        msg.get('username', ''), msg.get('password', '')
    )
    send_to(conn, {"status": "success" if ok else "error", "message": text})
    if ok:
        broadcast_user_list()
        log_message(f"[REJESTRACJA] {msg.get('username')}")


def handle_login(conn, _current_user, msg, state: dict) -> str | None:
    """Zwraca zalogowaną nazwę użytkownika lub None przy błędzie."""
    username = msg.get('username', '').strip()
    password = msg.get('password', '')

    if not database.verify_user(username, password):
        send_to(conn, {"status": "error", "message": "Błędny login lub hasło."})
        return None

    with _users_lock:
        if username in active_users:
            send_to(conn, {"status": "error", "message": "Użytkownik jest już zalogowany!"})
            return None
        active_users[username] = conn

    send_to(conn, {"status": "success", "message": f"Witaj {username} na czacie!"})

    now = datetime.now().strftime("%H:%M")
    enc = encrypt_system_msg(f"{username} dołączył do czatu.")
    broadcast({"action": "chat_message", "sender": "SYSTEM", "content": enc, "timestamp": now})
    broadcast_user_list()
    log_message(f"[LOGOWANIE] {username}")

    # Historia
    send_to(conn, {"action": "chat_history", "history": database.get_global_history()})
    send_to(conn, {"action": "private_history", "history": database.get_private_history(username)})

    user_groups = database.get_user_groups(username)
    send_to(conn, {"action": "your_groups", "groups": user_groups})
    for g in user_groups:
        send_to(conn, {"action": "group_history", "group": g, "history": database.get_group_history(g)})

    invites = database.get_user_invites(username)
    join_reqs = database.get_creator_join_requests(username)
    if invites or join_reqs:
        send_to(conn, {"action": "pending_requests", "invites": invites, "join_reqs": join_reqs})

    return username


def handle_typing(conn, current_user, msg):
    if not current_user:
        return
    target = msg.get("target", "")
    packet = {"action": "typing", "sender": current_user, "target": target}
    with _users_lock:
        snapshot = dict(active_users)

    if target == "Globalny":
        for name, c in snapshot.items():
            if name != current_user:
                send_to(c, packet)
    elif target.startswith("#"):
        for m in database.get_group_members(target):
            if m in snapshot and m != current_user:
                send_to(snapshot[m], packet)
    else:
        if target in snapshot:
            send_to(snapshot[target], packet)


def handle_broadcast_message(conn, current_user, msg):
    if not current_user:
        return
    content = msg.get('content', '')
    if len(content) > MAX_MESSAGE_LEN * 4:
        send_to(conn, {"status": "error", "message": "Wiadomość jest za długa."})
        return
    database.save_message(current_user, "Globalny", content)
    now = datetime.now().strftime("%H:%M")
    broadcast({"action": "chat_message", "sender": current_user, "content": content, "timestamp": now})


def handle_private_message(conn, current_user, msg):
    if not current_user:
        return
    recipient = msg.get("recipient", "")
    content = msg.get("content", "")
    if len(content) > MAX_MESSAGE_LEN * 4:
        send_to(conn, {"status": "error", "message": "Wiadomość jest za długa."})
        return
    database.save_message(current_user, recipient, content)
    target_conn = get_user_conn(recipient)
    if target_conn:
        now = datetime.now().strftime("%H:%M")
        send_to(target_conn, {
            "action": "private_message", "sender": current_user,
            "content": content, "timestamp": now
        })


def handle_group_message(conn, current_user, msg):
    if not current_user:
        return
    group_name = msg.get("group", "")
    content = msg.get("content", "")
    if len(content) > MAX_MESSAGE_LEN * 4:
        send_to(conn, {"status": "error", "message": "Wiadomość jest za długa."})
        return
    database.save_message(current_user, group_name, content)
    now = datetime.now().strftime("%H:%M")
    packet = {
        "action": "group_message", "sender": current_user,
        "group": group_name, "content": content, "timestamp": now
    }
    broadcast_to_group(group_name, packet, exclude=current_user)


def handle_send_file(conn, current_user, msg):
    if not current_user:
        return
    target = msg.get("target", "")
    filename = msg.get("filename", "plik")
    file_id = msg.get("file_id", "")
    file_data = msg.get("data", "")

    # Walidacja rozmiaru
    try:
        raw = base64.b64decode(file_data)
    except Exception:
        send_to(conn, {"status": "error", "message": "Błąd danych pliku."})
        return
    if len(raw) > MAX_FILE_SIZE:
        send_to(conn, {"status": "error", "message": "Plik jest za duży (max 5 MB)."})
        return

    # Bezpieczna nazwa pliku (path traversal)
    safe_name = os.path.basename(file_id)
    os.makedirs("Serwer_Pliki", exist_ok=True)
    file_path = os.path.join("Serwer_Pliki", safe_name)
    with open(file_path, "wb") as f:
        f.write(raw)

    log_message(f"[PLIK] {current_user} → {target}: {filename}")

    info_text = f"[FILE:{safe_name}:{filename}]"
    enc_info = encrypt_system_msg(info_text)
    database.save_message(current_user, target, enc_info)
    now = datetime.now().strftime("%H:%M")

    if target == "Globalny":
        action = "chat_message"
    elif target.startswith("#"):
        action = "group_message"
    else:
        action = "private_message"

    packet = {"action": action, "sender": current_user, "content": enc_info, "timestamp": now}
    if target.startswith("#"):
        packet["group"] = target

    if target == "Globalny":
        with _users_lock:
            snapshot = dict(active_users)
        for name, c in snapshot.items():
            if name != current_user:
                send_to(c, packet)
    elif target.startswith("#"):
        broadcast_to_group(target, packet, exclude=current_user)
    else:
        target_conn = get_user_conn(target)
        if target_conn:
            send_to(target_conn, packet)


def handle_download_request(conn, current_user, msg):
    if not current_user:
        return
    file_id = os.path.basename(msg.get("file_id", ""))  # path traversal guard
    filename = msg.get("filename", "plik")
    file_path = os.path.join("Serwer_Pliki", file_id)

    if os.path.exists(file_path):
        with open(file_path, "rb") as f:
            data = base64.b64encode(f.read()).decode('utf-8')
        send_to(conn, {"action": "receive_download", "filename": filename, "data": data})
    else:
        send_to(conn, {"status": "error", "message": "Plik został usunięty z serwera."})


def handle_create_group(conn, current_user, msg):
    if not current_user:
        return
    name = msg.get("name", "")
    if len(name) > database.MAX_GROUP_NAME_LEN:
        send_to(conn, {"status": "error", "message": "Nazwa grupy jest za długa."})
        return
    if database.create_group(name, current_user):
        send_to(conn, {"status": "success", "message": f"Utworzono {name}!"})
        send_to(conn, {"action": "your_groups", "groups": database.get_user_groups(current_user)})
        log_message(f"[GRUPA] Utworzono: {name} przez {current_user}")
    else:
        send_to(conn, {"status": "error", "message": "Taka grupa już istnieje!"})


def handle_join_group(conn, current_user, msg):
    if not current_user:
        return
    group_name = msg.get("name", "")
    creator = database.get_group_creator(group_name)
    if not creator:
        send_to(conn, {"status": "error", "message": "Taka grupa nie istnieje!"})
        return
    if current_user in database.get_group_members(group_name):
        send_to(conn, {"status": "error", "message": "Już jesteś w tej grupie!"})
        return
    database.add_group_request(group_name, current_user, "join")
    send_to(conn, {"status": "success",
                   "message": f"Wysłano prośbę o dołączenie do {group_name}. Czekaj na akceptację."})
    creator_conn = get_user_conn(creator)
    if creator_conn:
        send_to(creator_conn, {"action": "join_request_received", "group": group_name, "user": current_user})


def handle_add_user_to_group(conn, current_user, msg):
    if not current_user:
        return
    group_name = msg.get("group", "")
    user_to_add = msg.get("user", "")
    if database.get_group_creator(group_name) != current_user:
        send_to(conn, {"status": "error", "message": "Tylko założyciel grupy może zapraszać!"})
        return
    if user_to_add not in database.get_all_users():
        send_to(conn, {"status": "error", "message": f"Użytkownik {user_to_add} nie istnieje!"})
        return
    if user_to_add in database.get_group_members(group_name):
        send_to(conn, {"status": "error", "message": f"{user_to_add} już jest w tej grupie!"})
        return
    database.add_group_request(group_name, user_to_add, "invite")
    send_to(conn, {"status": "success", "message": f"Wysłano zaproszenie do {user_to_add}!"})
    target_conn = get_user_conn(user_to_add)
    if target_conn:
        send_to(target_conn, {"action": "invite_received", "group": group_name, "admin": current_user})


def handle_resolve_join(conn, current_user, msg):
    if not current_user:
        return
    group_name = msg.get("group", "")
    user = msg.get("user", "")
    accept = msg.get("accept", False)
    database.remove_group_request(group_name, user, "join")

    if accept:
        database.join_group(group_name, user)
        send_to(conn, {"status": "success", "message": f"Zaakceptowano {user} w {group_name}!"})
        user_conn = get_user_conn(user)
        if user_conn:
            send_to(user_conn, {"status": "success",
                                "message": f"Twoja prośba o dołączenie do {group_name} została zaakceptowana!"})
            send_to(user_conn, {"action": "your_groups", "groups": database.get_user_groups(user)})
            send_to(user_conn, {"action": "group_history", "group": group_name,
                                "history": database.get_group_history(group_name)})

        enc = encrypt_system_msg(f"{user} dołączył do grupy.")
        database.save_message("SYSTEM", group_name, enc)
        now = datetime.now().strftime("%H:%M")
        members = database.get_group_members(group_name)
        packet = {"action": "group_message", "sender": "SYSTEM", "group": group_name, "content": enc, "timestamp": now}
        info = {"action": "group_info", "group": group_name, "members": members, "creator": current_user}
        with _users_lock:
            snapshot = dict(active_users)
        for m in members:
            if m in snapshot:
                send_to(snapshot[m], packet)
                send_to(snapshot[m], info)
    else:
        user_conn = get_user_conn(user)
        if user_conn:
            send_to(user_conn, {"status": "error",
                                "message": f"Twoja prośba o dołączenie do {group_name} została ODRZUCONA."})


def handle_resolve_invite(conn, current_user, msg):
    if not current_user:
        return
    group_name = msg.get("group", "")
    accept = msg.get("accept", False)
    database.remove_group_request(group_name, current_user, "invite")
    creator = database.get_group_creator(group_name)

    if accept:
        database.join_group(group_name, current_user)
        send_to(conn, {"status": "success", "message": f"Dołączyłeś do grupy {group_name}!"})
        send_to(conn, {"action": "your_groups", "groups": database.get_user_groups(current_user)})
        send_to(conn, {"action": "group_history", "group": group_name,
                       "history": database.get_group_history(group_name)})

        enc = encrypt_system_msg(f"{current_user} zaakceptował zaproszenie do grupy.")
        database.save_message("SYSTEM", group_name, enc)
        now = datetime.now().strftime("%H:%M")
        members = database.get_group_members(group_name)
        packet = {"action": "group_message", "sender": "SYSTEM", "group": group_name,
                  "content": enc, "timestamp": now}
        info = {"action": "group_info", "group": group_name, "members": members, "creator": creator}
        with _users_lock:
            snapshot = dict(active_users)
        for m in members:
            if m in snapshot:
                send_to(snapshot[m], packet)
                send_to(snapshot[m], info)
    else:
        creator_conn = get_user_conn(creator)
        if creator_conn:
            send_to(creator_conn, {"status": "error",
                                   "message": f"{current_user} ODRZUCIŁ zaproszenie do {group_name}."})


def handle_leave_group(conn, current_user, msg):
    if not current_user:
        return
    group_name = msg.get("name", "")
    database.leave_group(group_name, current_user)
    send_to(conn, {"status": "success", "message": f"Opuszczono grupę {group_name}."})
    send_to(conn, {"action": "your_groups", "groups": database.get_user_groups(current_user)})

    enc = encrypt_system_msg(f"{current_user} opuścił grupę.")
    database.save_message("SYSTEM", group_name, enc)
    now = datetime.now().strftime("%H:%M")
    members = database.get_group_members(group_name)
    creator = database.get_group_creator(group_name)
    packet = {"action": "group_message", "sender": "SYSTEM", "group": group_name, "content": enc, "timestamp": now}
    info = {"action": "group_info", "group": group_name, "members": members, "creator": creator}
    with _users_lock:
        snapshot = dict(active_users)
    for m in members:
        if m in snapshot:
            send_to(snapshot[m], packet)
            send_to(snapshot[m], info)


def handle_kick_user(conn, current_user, msg):
    if not current_user:
        return
    group_name = msg.get("group", "")
    user_to_kick = msg.get("user", "")
    creator = database.get_group_creator(group_name)

    if creator != current_user:
        send_to(conn, {"status": "error", "message": "Tylko założyciel może wyrzucać osoby!"})
        return
    if user_to_kick == current_user:
        send_to(conn, {"status": "error", "message": "Nie możesz wyrzucić samego siebie!"})
        return
    if user_to_kick not in database.get_group_members(group_name):
        send_to(conn, {"status": "error", "message": f"{user_to_kick} nie jest w tej grupie!"})
        return

    database.leave_group(group_name, user_to_kick)
    send_to(conn, {"status": "success", "message": f"Wyrzucono {user_to_kick} z grupy."})

    kicked_conn = get_user_conn(user_to_kick)
    if kicked_conn:
        send_to(kicked_conn, {"action": "kicked_from_group", "group": group_name})
        send_to(kicked_conn, {"action": "your_groups", "groups": database.get_user_groups(user_to_kick)})

    enc = encrypt_system_msg(f"{user_to_kick} został wyrzucony przez administratora.")
    database.save_message("SYSTEM", group_name, enc)
    now = datetime.now().strftime("%H:%M")
    members = database.get_group_members(group_name)
    packet = {"action": "group_message", "sender": "SYSTEM", "group": group_name, "content": enc, "timestamp": now}
    info = {"action": "group_info", "group": group_name, "members": members, "creator": creator}
    with _users_lock:
        snapshot = dict(active_users)
    for m in members:
        if m in snapshot:
            send_to(snapshot[m], packet)
            send_to(snapshot[m], info)


def handle_get_group_info(conn, current_user, msg):
    if not current_user:
        return
    group_name = msg.get("group", "")
    members = database.get_group_members(group_name)
    creator = database.get_group_creator(group_name)
    send_to(conn, {"action": "group_info", "group": group_name, "members": members, "creator": creator})


def handle_delete_group(conn, current_user, msg):
    if not current_user:
        return
    group_name = msg.get("group", "")
    members = database.get_group_members(group_name)
    if database.delete_group(group_name, current_user):
        packet = {"action": "group_deleted", "group": group_name}
        with _users_lock:
            snapshot = dict(active_users)
        for m in members:
            if m in snapshot:
                send_to(snapshot[m], packet)
                send_to(snapshot[m], {"action": "your_groups", "groups": database.get_user_groups(m)})


# ---------------------------------------------------------------------------
# Mapa akcji → handler
# ---------------------------------------------------------------------------

ACTION_HANDLERS = {
    'typing':           handle_typing,
    'broadcast_message': handle_broadcast_message,
    'private_message':  handle_private_message,
    'group_message':    handle_group_message,
    'send_file':        handle_send_file,
    'download_request': handle_download_request,
    'create_group':     handle_create_group,
    'join_group':       handle_join_group,
    'add_user_to_group': handle_add_user_to_group,
    'resolve_join':     handle_resolve_join,
    'resolve_invite':   handle_resolve_invite,
    'leave_group':      handle_leave_group,
    'kick_user':        handle_kick_user,
    'get_group_info':   handle_get_group_info,
    'delete_group':     handle_delete_group,
}


# ---------------------------------------------------------------------------
# Główna pętla klienta
# ---------------------------------------------------------------------------

def handle_client(conn: socket.socket, addr):
    log_message(f"[NOWE POŁĄCZENIE] {addr}")
    current_user: str | None = None
    file_obj = conn.makefile('r', encoding='utf-8')

    try:
        for raw_line in file_obj:
            if not raw_line.strip():
                continue

            try:
                message = json.loads(raw_line)
            except json.JSONDecodeError:
                log_message(f"[BŁĄD JSON] od {addr}: {raw_line[:80]}")
                continue

            action = message.get('action')

            # Akcje pre-auth
            if action == 'register':
                handle_register(conn, None, message)
                continue

            if action == 'login':
                if current_user is None:
                    current_user = handle_login(conn, None, message, {})
                else:
                    send_to(conn, {"status": "error", "message": "Już jesteś zalogowany."})
                continue

            # Wszystkie pozostałe wymagają zalogowania
            if current_user is None:
                send_to(conn, {"status": "error", "message": "Najpierw się zaloguj."})
                continue

            handler = ACTION_HANDLERS.get(action)
            if handler:
                try:
                    handler(conn, current_user, message)
                except Exception as e:
                    log_message(f"[BŁĄD] handler '{action}' dla {current_user}: {e}")
            else:
                log_message(f"[NIEZNANA AKCJA] '{action}' od {current_user}")

    except Exception as e:
        log_message(f"[BŁĄD POŁĄCZENIA] {addr}: {e}")
    finally:
        with _users_lock:
            was_logged_in = current_user in active_users if current_user else False
            if was_logged_in:
                del active_users[current_user]

        if was_logged_in:
            now = datetime.now().strftime("%H:%M")
            enc = encrypt_system_msg(f"{current_user} opuścił czat.")
            broadcast({"action": "chat_message", "sender": "SYSTEM", "content": enc, "timestamp": now})
            broadcast_user_list()
            log_message(f"[WYLOGOWANIE] {current_user}")

        try:
            conn.close()
        except Exception:
            pass
        log_message(f"[ROZŁĄCZONO] {addr}")


# ---------------------------------------------------------------------------
# GUI serwera
# ---------------------------------------------------------------------------

class ServerApp:
    def __init__(self):
        global server_app_instance
        server_app_instance = self

        self.root = ctk.CTk()
        self.root.title("Panel Kontrolny Serwera")
        self.root.geometry("450x450")
        self.root.resizable(False, False)

        self.server_socket = None
        self.is_running = False

        ctk.CTkLabel(self.root, text="Konfiguracja Serwera",
                     font=("Roboto", 20, "bold")).pack(pady=(15, 5))

        input_frame = ctk.CTkFrame(self.root, fg_color="transparent")
        input_frame.pack(pady=5)

        self.entry_ip = ctk.CTkEntry(input_frame, placeholder_text="Adres IP", width=150)
        self.entry_ip.insert(0, "127.0.0.1")
        self.entry_ip.pack(side="left", padx=5)

        self.entry_port = ctk.CTkEntry(input_frame, placeholder_text="Port", width=80)
        self.entry_port.insert(0, "9999")
        self.entry_port.pack(side="left", padx=5)

        self.btn_start = ctk.CTkButton(self.root, text="▶ Uruchom Serwer",
                                       fg_color="#2b7b4d", hover_color="#1e5c38",
                                       command=self.start_server)
        self.btn_start.pack(pady=10)

        self.btn_stop = ctk.CTkButton(self.root, text="🛑 Wyłącz Serwer",
                                      fg_color="#c0392b", hover_color="#922b21",
                                      command=self.stop_server)
        self.btn_stop.pack(pady=10)
        self.btn_stop.pack_forget()

        self.lbl_status = ctk.CTkLabel(self.root, text="Status: Wyłączony", text_color="gray")
        self.lbl_status.pack(pady=(0, 10))

        self.log_area = ctk.CTkTextbox(self.root, width=400, height=180,
                                       state="disabled", font=("Consolas", 11))
        self.log_area.pack(pady=5)

    def add_log(self, text: str):
        def update():
            self.log_area.configure(state="normal")
            self.log_area.insert("end", f"[{datetime.now().strftime('%H:%M:%S')}] {text}\n")
            self.log_area.configure(state="disabled")
            self.log_area.see("end")
        self.root.after(0, update)

    def start_server(self):
        ip = self.entry_ip.get().strip()
        port_str = self.entry_port.get().strip()
        if not ip or not port_str.isdigit():
            messagebox.showerror("Błąd", "Podaj prawidłowy adres IP i port.")
            return
        port = int(port_str)
        try:
            self.server_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            self.server_socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            self.server_socket.bind((ip, port))
            self.server_socket.listen()
            self.is_running = True
            self.entry_ip.configure(state="disabled")
            self.entry_port.configure(state="disabled")
            self.btn_start.pack_forget()
            self.btn_stop.pack(pady=10)
            self.lbl_status.configure(text=f"Status: Działa na {ip}:{port}", text_color="#2ecc71")
            self.add_log("--- SERWER URUCHOMIONY ---")
            threading.Thread(target=self._accept_loop, daemon=True).start()
        except Exception as e:
            messagebox.showerror("Błąd", f"Nie można uruchomić serwera:\n{e}")

    def _accept_loop(self):
        while self.is_running:
            try:
                conn, addr = self.server_socket.accept()
                threading.Thread(target=handle_client, args=(conn, addr), daemon=True).start()
            except OSError:
                break

    def stop_server(self):
        self.is_running = False
        if self.server_socket:
            try:
                self.server_socket.close()
            except Exception:
                pass
        with _users_lock:
            conns = list(active_users.values())
            active_users.clear()
        for c in conns:
            try:
                c.close()
            except Exception:
                pass
        self.entry_ip.configure(state="normal")
        self.entry_port.configure(state="normal")
        self.btn_stop.pack_forget()
        self.btn_start.pack(pady=10)
        self.lbl_status.configure(text="Status: Wyłączony", text_color="gray")
        self.add_log("--- SERWER ZATRZYMANY ---")

    def run(self):
        self.root.mainloop()


if __name__ == "__main__":
    database.init_db()
    app = ServerApp()
    app.run()
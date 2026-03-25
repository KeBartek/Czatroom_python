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
    print("BŁĄD: Musisz zainstalować bibliotekę cryptography! Wpisz w konsoli: pip install cryptography")
    exit()

ctk.set_appearance_mode("dark")
ctk.set_default_color_theme("blue")

# Nasz uniwersalny klucz szyfrujący (w prawdziwej aplikacji E2EE klucze są unikalne dla każdej pary, tu dla uproszczenia używamy jednego globalnego dla całej sieci)
CIPHER_KEY = b'MDEyMzQ1Njc4OTAxMjM0NTY3ODkwMTIzNDU2Nzg5MDE='
cipher = Fernet(CIPHER_KEY)

active_users = {}
database.init_db()
server_app_instance = None


def log_message(msg):
    print(msg)
    if server_app_instance:
        server_app_instance.add_log(msg)


def encrypt_system_msg(text):
    """Szyfruje wiadomości generowane przez serwer (żeby klient nie zwariował przy ich odczycie)"""
    return cipher.encrypt(text.encode('utf-8')).decode('utf-8')


def broadcast(message_dict):
    json_data = (json.dumps(message_dict) + "\n").encode('utf-8')
    for username, conn in list(active_users.items()):
        try:
            conn.sendall(json_data)
        except Exception as e:
            pass


def broadcast_user_list():
    online_users = list(active_users.keys())
    all_users = database.get_all_users()
    packet = {"action": "user_list", "all_users": all_users, "online_users": online_users}
    broadcast(packet)


def send_to_user(conn, packet):
    try:
        conn.sendall((json.dumps(packet) + "\n").encode('utf-8'))
    except:
        pass


def handle_client(conn, addr):
    log_message(f"[NOWE POŁĄCZENIE] Klient {addr} połączył się.")
    current_user = None
    file_obj = conn.makefile('r', encoding='utf-8')

    try:
        for line in file_obj:
            if not line.strip():
                continue

            message = json.loads(line)
            action = message.get('action')

            if action == 'register':
                username = message.get('username')
                password = message.get('password')
                if database.register_user(username, password):
                    send_to_user(conn, {"status": "success", "message": "Zarejestrowano pomyślnie!"})
                    broadcast_user_list()
                    log_message(f"[REJESTRACJA] Nowy użytkownik: {username}")
                else:
                    send_to_user(conn, {"status": "error", "message": "Nazwa użytkownika jest zajęta."})

            elif action == 'login':
                username = message.get('username')
                password = message.get('password')
                if database.verify_user(username, password):
                    if username in active_users:
                        send_to_user(conn, {"status": "error", "message": "Użytkownik jest już zalogowany!"})
                    else:
                        current_user = username
                        send_to_user(conn, {"status": "success", "message": f"Witaj {username} na czacie!"})

                        now = datetime.now().strftime("%H:%M")
                        # Szyfrujemy wiadomość systemową
                        enc_sys_msg = encrypt_system_msg(f"{username} dołączył do czatu.")
                        broadcast(
                            {"action": "chat_message", "sender": "SYSTEM", "content": enc_sys_msg, "timestamp": now})

                        active_users[username] = conn
                        broadcast_user_list()
                        log_message(f"[LOGOWANIE] Zalogowano: {username}")

                        send_to_user(conn, {"action": "chat_history", "history": database.get_global_history()})
                        send_to_user(conn,
                                     {"action": "private_history", "history": database.get_private_history(username)})

                        user_groups = database.get_user_groups(username)
                        send_to_user(conn, {"action": "your_groups", "groups": user_groups})

                        for g in user_groups:
                            send_to_user(conn, {"action": "group_history", "group": g,
                                                "history": database.get_group_history(g)})

                        invites = database.get_user_invites(username)
                        join_reqs = database.get_creator_join_requests(username)
                        if invites or join_reqs:
                            send_to_user(conn,
                                         {"action": "pending_requests", "invites": invites, "join_reqs": join_reqs})

                else:
                    send_to_user(conn, {"status": "error", "message": "Błędny login lub hasło."})

            # TYPING
            elif action == 'typing':
                if current_user:
                    target = message.get("target")
                    msg_packet = {"action": "typing", "sender": current_user, "target": target}
                    if target == "Globalny":
                        for m in active_users:
                            if m != current_user:
                                send_to_user(active_users[m], msg_packet)
                    elif target.startswith("#"):
                        members = database.get_group_members(target)
                        for m in members:
                            if m in active_users and m != current_user:
                                send_to_user(active_users[m], msg_packet)
                    else:
                        if target in active_users:
                            send_to_user(active_users[target], msg_packet)

            elif action == 'broadcast_message':
                if current_user:
                    tresc = message.get('content')  # <-- TO JEST JUŻ ZASZYFROWANE PRZEZ KLIENTA!
                    database.save_message(current_user, "Globalny", tresc)
                    now = datetime.now().strftime("%H:%M")
                    broadcast({"action": "chat_message", "sender": current_user, "content": tresc, "timestamp": now})

            elif action == 'private_message':
                if current_user:
                    odbiorca = message.get("recipient")
                    tresc = message.get("content")  # <-- ZASZYFROWANE
                    database.save_message(current_user, odbiorca, tresc)
                    if odbiorca in active_users:
                        now = datetime.now().strftime("%H:%M")
                        send_to_user(active_users[odbiorca],
                                     {"action": "private_message", "sender": current_user, "content": tresc,
                                      "timestamp": now})

            elif action == 'group_message':
                if current_user:
                    group_name = message.get("group")
                    tresc = message.get("content")  # <-- ZASZYFROWANE
                    database.save_message(current_user, group_name, tresc)
                    now = datetime.now().strftime("%H:%M")
                    msg_packet = {"action": "group_message", "sender": current_user, "group": group_name,
                                  "content": tresc, "timestamp": now}
                    members = database.get_group_members(group_name)
                    for m in members:
                        if m in active_users and m != current_user:
                            send_to_user(active_users[m], msg_packet)

            elif action == 'send_file':
                if current_user:
                    target = message.get("target")
                    filename = message.get("filename")
                    file_id = message.get("file_id")
                    file_data = message.get("data")

                    os.makedirs("Serwer_Pliki", exist_ok=True)
                    file_path = os.path.join("Serwer_Pliki", file_id)
                    with open(file_path, "wb") as f:
                        f.write(base64.b64decode(file_data))

                    info_text = f"[FILE:{file_id}:{filename}]"
                    enc_info = encrypt_system_msg(info_text)
                    database.save_message(current_user, target, enc_info)
                    now = datetime.now().strftime("%H:%M")
                    log_message(f"[PLIK] {current_user} wysłał: {filename}")

                    msg_packet = {"action": "chat_message" if target == "Globalny" else (
                        "group_message" if target.startswith("#") else "private_message"),
                                  "sender": current_user, "content": enc_info, "timestamp": now}

                    if target.startswith("#"): msg_packet["group"] = target

                    if target == "Globalny":
                        for m in active_users:
                            if m != current_user: send_to_user(active_users[m], msg_packet)
                    elif target.startswith("#"):
                        for m in database.get_group_members(target):
                            if m in active_users and m != current_user: send_to_user(active_users[m], msg_packet)
                    else:
                        if target in active_users: send_to_user(active_users[target], msg_packet)

            elif action == 'download_request':
                if current_user:
                    file_id = message.get("file_id")
                    filename = message.get("filename")
                    file_path = os.path.join("Serwer_Pliki", file_id)

                    if os.path.exists(file_path):
                        with open(file_path, "rb") as f:
                            data = base64.b64encode(f.read()).decode('utf-8')
                        send_to_user(conn, {"action": "receive_download", "filename": filename, "data": data})
                    else:
                        send_to_user(conn, {"status": "error", "message": "Plik został usunięty z serwera."})

            elif action == 'create_group':
                if current_user:
                    group_name = message.get("name")
                    if database.create_group(group_name, current_user):
                        send_to_user(conn, {"status": "success", "message": f"Utworzono {group_name}!"})
                        send_to_user(conn, {"action": "your_groups", "groups": database.get_user_groups(current_user)})
                        log_message(f"[GRUPA] Utworzono: {group_name} przez {current_user}")
                    else:
                        send_to_user(conn, {"status": "error", "message": "Taka grupa już istnieje!"})

            elif action == 'join_group':
                if current_user:
                    group_name = message.get("name")
                    creator = database.get_group_creator(group_name)
                    if not creator:
                        send_to_user(conn, {"status": "error", "message": "Taka grupa nie istnieje!"})
                    elif current_user in database.get_group_members(group_name):
                        send_to_user(conn, {"status": "error", "message": "Już jesteś w tej grupie!"})
                    else:
                        database.add_group_request(group_name, current_user, "join")
                        send_to_user(conn, {"status": "success",
                                            "message": f"Wysłano prośbę o dołączenie do {group_name}. Czekaj na akceptację administratora."})
                        if creator in active_users:
                            send_to_user(active_users[creator],
                                         {"action": "join_request_received", "group": group_name, "user": current_user})

            elif action == 'add_user_to_group':
                if current_user:
                    group_name = message.get("group")
                    user_to_add = message.get("user")
                    creator = database.get_group_creator(group_name)

                    if creator == current_user:
                        all_u = database.get_all_users()
                        if user_to_add not in all_u:
                            send_to_user(conn, {"status": "error",
                                                "message": f"Użytkownik {user_to_add} nie istnieje w bazie!"})
                        elif user_to_add in database.get_group_members(group_name):
                            send_to_user(conn, {"status": "error",
                                                "message": f"Użytkownik {user_to_add} już jest w tej grupie!"})
                        else:
                            database.add_group_request(group_name, user_to_add, "invite")
                            send_to_user(conn,
                                         {"status": "success", "message": f"Wysłano zaproszenie do {user_to_add}!"})
                            if user_to_add in active_users:
                                send_to_user(active_users[user_to_add],
                                             {"action": "invite_received", "group": group_name, "admin": current_user})
                    else:
                        send_to_user(conn, {"status": "error", "message": "Tylko założyciel grupy może zapraszać!"})

            elif action == 'resolve_join':
                if current_user:
                    group_name = message.get("group")
                    user = message.get("user")
                    accept = message.get("accept")

                    database.remove_group_request(group_name, user, "join")
                    if accept:
                        database.join_group(group_name, user)
                        send_to_user(conn, {"status": "success",
                                            "message": f"Zaakceptowano użytkownika {user} w grupie {group_name}!"})
                        if user in active_users:
                            u_conn = active_users[user]
                            send_to_user(u_conn, {"status": "success",
                                                  "message": f"Twoja prośba o dołączenie do {group_name} została zaakceptowana!"})
                            send_to_user(u_conn, {"action": "your_groups", "groups": database.get_user_groups(user)})
                            send_to_user(u_conn, {"action": "group_history", "group": group_name,
                                                  "history": database.get_group_history(group_name)})

                        enc_info = encrypt_system_msg(f"{user} dołączył do grupy.")
                        database.save_message("SYSTEM", group_name, enc_info)
                        msg_packet = {"action": "group_message", "sender": "SYSTEM", "group": group_name,
                                      "content": enc_info, "timestamp": datetime.now().strftime("%H:%M")}
                        for m in database.get_group_members(group_name):
                            if m in active_users:
                                send_to_user(active_users[m], msg_packet)
                                send_to_user(active_users[m], {"action": "group_info", "group": group_name,
                                                               "members": database.get_group_members(group_name),
                                                               "creator": current_user})
                    else:
                        if user in active_users:
                            send_to_user(active_users[user], {"status": "error",
                                                              "message": f"Twoja prośba o dołączenie do {group_name} została ODRZUCONA."})

            elif action == 'resolve_invite':
                if current_user:
                    group_name = message.get("group")
                    accept = message.get("accept")

                    database.remove_group_request(group_name, current_user, "invite")
                    creator = database.get_group_creator(group_name)

                    if accept:
                        database.join_group(group_name, current_user)
                        send_to_user(conn, {"status": "success", "message": f"Dołączyłeś do grupy {group_name}!"})
                        send_to_user(conn, {"action": "your_groups", "groups": database.get_user_groups(current_user)})
                        send_to_user(conn, {"action": "group_history", "group": group_name,
                                            "history": database.get_group_history(group_name)})

                        enc_info = encrypt_system_msg(f"{current_user} zaakceptował zaproszenie do grupy.")
                        database.save_message("SYSTEM", group_name, enc_info)
                        msg_packet = {"action": "group_message", "sender": "SYSTEM", "group": group_name,
                                      "content": enc_info, "timestamp": datetime.now().strftime("%H:%M")}
                        for m in database.get_group_members(group_name):
                            if m in active_users:
                                send_to_user(active_users[m], msg_packet)
                                send_to_user(active_users[m], {"action": "group_info", "group": group_name,
                                                               "members": database.get_group_members(group_name),
                                                               "creator": creator})
                    else:
                        if creator in active_users:
                            send_to_user(active_users[creator], {"status": "error",
                                                                 "message": f"Użytkownik {current_user} ODRZUCIŁ zaproszenie do {group_name}."})

            elif action == 'leave_group':
                if current_user:
                    group_name = message.get("name")
                    database.leave_group(group_name, current_user)
                    send_to_user(conn, {"status": "success", "message": f"Opuszczono grupę {group_name}."})
                    send_to_user(conn, {"action": "your_groups", "groups": database.get_user_groups(current_user)})

                    enc_info = encrypt_system_msg(f"{current_user} opuścił grupę.")
                    database.save_message("SYSTEM", group_name, enc_info)
                    msg_packet = {"action": "group_message", "sender": "SYSTEM", "group": group_name,
                                  "content": enc_info, "timestamp": datetime.now().strftime("%H:%M")}

                    members = database.get_group_members(group_name)
                    creator = database.get_group_creator(group_name)
                    for m in members:
                        if m in active_users:
                            send_to_user(active_users[m], msg_packet)
                            send_to_user(active_users[m],
                                         {"action": "group_info", "group": group_name, "members": members,
                                          "creator": creator})

            elif action == 'kick_user':
                if current_user:
                    group_name = message.get("group")
                    user_to_kick = message.get("user")
                    creator = database.get_group_creator(group_name)
                    if creator == current_user:
                        if user_to_kick == current_user:
                            send_to_user(conn, {"status": "error", "message": "Nie możesz wyrzucić samego siebie!"})
                        elif user_to_kick not in database.get_group_members(group_name):
                            send_to_user(conn, {"status": "error",
                                                "message": f"Użytkownik {user_to_kick} nie jest w tej grupie!"})
                        else:
                            database.leave_group(group_name, user_to_kick)
                            send_to_user(conn, {"status": "success", "message": f"Wyrzucono {user_to_kick} z grupy."})

                            enc_info = encrypt_system_msg(f"{user_to_kick} został wyrzucony przez administratora.")
                            database.save_message("SYSTEM", group_name, enc_info)
                            msg_packet = {"action": "group_message", "sender": "SYSTEM", "group": group_name,
                                          "content": enc_info, "timestamp": datetime.now().strftime("%H:%M")}

                            if user_to_kick in active_users:
                                kicked_conn = active_users[user_to_kick]
                                send_to_user(kicked_conn, {"action": "kicked_from_group", "group": group_name})
                                send_to_user(kicked_conn, {"action": "your_groups",
                                                           "groups": database.get_user_groups(user_to_kick)})

                            members = database.get_group_members(group_name)
                            for m in members:
                                if m in active_users:
                                    send_to_user(active_users[m], msg_packet)
                                    send_to_user(active_users[m],
                                                 {"action": "group_info", "group": group_name, "members": members,
                                                  "creator": creator})
                    else:
                        send_to_user(conn, {"status": "error", "message": "Tylko założyciel może wyrzucać osoby!"})

            elif action == 'get_group_info':
                if current_user:
                    group_name = message.get("group")
                    members = database.get_group_members(group_name)
                    creator = database.get_group_creator(group_name)
                    send_to_user(conn,
                                 {"action": "group_info", "group": group_name, "members": members, "creator": creator})

            elif action == 'delete_group':
                if current_user:
                    group_name = message.get("group")
                    members = database.get_group_members(group_name)

                    if database.delete_group(group_name, current_user):
                        packet = {"action": "group_deleted", "group": group_name}
                        for m in members:
                            if m in active_users:
                                send_to_user(active_users[m], packet)
                                send_to_user(active_users[m],
                                             {"action": "your_groups", "groups": database.get_user_groups(m)})

    except Exception as e:
        pass
    finally:
        if current_user in active_users:
            del active_users[current_user]
            now = datetime.now().strftime("%H:%M")
            enc_sys_msg = encrypt_system_msg(f"{current_user} opuścił czat.")
            broadcast({"action": "chat_message", "sender": "SYSTEM", "content": enc_sys_msg, "timestamp": now})
            broadcast_user_list()
            log_message(f"[WYLOGOWANIE] Wylogowano: {current_user}")
        conn.close()
        log_message(f"[ROZŁĄCZONO] Klient {addr} opuścił serwer.")


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

        self.lbl_title = ctk.CTkLabel(self.root, text="Konfiguracja Serwera", font=("Roboto", 20, "bold"))
        self.lbl_title.pack(pady=(15, 5))

        self.input_frame = ctk.CTkFrame(self.root, fg_color="transparent")
        self.input_frame.pack(pady=5)

        self.entry_ip = ctk.CTkEntry(self.input_frame, placeholder_text="Adres IP", width=150)
        self.entry_ip.insert(0, "127.0.0.1")
        self.entry_ip.pack(side="left", padx=5)

        self.entry_port = ctk.CTkEntry(self.input_frame, placeholder_text="Port", width=80)
        self.entry_port.insert(0, "9999")
        self.entry_port.pack(side="left", padx=5)

        self.btn_start = ctk.CTkButton(self.root, text="▶ Uruchom Serwer", fg_color="#2b7b4d", hover_color="#1e5c38",
                                       command=self.start_server)
        self.btn_start.pack(pady=10)

        self.btn_stop = ctk.CTkButton(self.root, text="🛑 Wyłącz Serwer", fg_color="#c0392b", hover_color="#922b21",
                                      command=self.stop_server)
        self.btn_stop.pack(pady=10)
        self.btn_stop.pack_forget()

        self.lbl_status = ctk.CTkLabel(self.root, text="Status: Wyłączony", text_color="gray")
        self.lbl_status.pack(pady=(0, 10))

        self.log_area = ctk.CTkTextbox(self.root, width=400, height=180, state="disabled", font=("Consolas", 11))
        self.log_area.pack(pady=5)

    def add_log(self, text):
        def update():
            self.log_area.configure(state="normal")
            time_str = datetime.now().strftime("%H:%M:%S")
            self.log_area.insert("end", f"[{time_str}] {text}\n")
            self.log_area.configure(state="disabled")
            self.log_area.see("end")

        self.root.after(0, update)

    def start_server(self):
        ip = self.entry_ip.get().strip()
        port_str = self.entry_port.get().strip()

        if not ip or not port_str.isdigit():
            messagebox.showerror("Błąd", "Podaj prawidłowy adres IP i port (tylko cyfry).")
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
            self.lbl_status.configure(text=f"Status: Działa na {ip}:{port} (E2EE Active)", text_color="#2ecc71")
            self.add_log("--- SERWER URUCHOMIONY ---")

            threading.Thread(target=self.accept_loop, daemon=True).start()

        except Exception as e:
            messagebox.showerror("Błąd", f"Nie można uruchomić serwera:\n{e}")

    def accept_loop(self):
        while self.is_running:
            try:
                conn, addr = self.server_socket.accept()
                thread = threading.Thread(target=handle_client, args=(conn, addr))
                thread.start()
            except OSError:
                break

    def stop_server(self):
        self.is_running = False

        if self.server_socket:
            try:
                self.server_socket.close()
            except:
                pass

        for user, conn in list(active_users.items()):
            try:
                conn.close()
            except:
                pass
        active_users.clear()

        self.entry_ip.configure(state="normal")
        self.entry_port.configure(state="normal")
        self.btn_stop.pack_forget()
        self.btn_start.pack(pady=10)
        self.lbl_status.configure(text="Status: Wyłączony", text_color="gray")
        self.add_log("--- SERWER ZATRZYMANY ---")

    def run(self):
        self.root.mainloop()


if __name__ == "__main__":
    app = ServerApp()
    app.run()
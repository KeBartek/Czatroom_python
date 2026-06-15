import socket
import threading
import json
import os
import base64
from datetime import datetime
from cryptography.fernet import Fernet

import database
from config import CIPHER_KEY


class ChatServer:
    def __init__(self, log_callback):
        self.log = log_callback
        self.is_running = False
        self.server_socket = None
        self.active_users = {}
        self.cipher = Fernet(CIPHER_KEY)
        database.init_db()
        self.routes = {
            'register': self.handle_register,
            'login': self.handle_login,
            'typing': self.handle_typing,
            'broadcast_message': self.handle_broadcast_message,
            'private_message': self.handle_private_message,
            'group_message': self.handle_group_message,
            'send_file': self.handle_send_file,
            'download_request': self.handle_download_request,
            'create_group': self.handle_create_group,
            'join_group': self.handle_join_group,
            'add_user_to_group': self.handle_add_user_to_group,
            'resolve_join': self.handle_resolve_join,
            'resolve_invite': self.handle_resolve_invite,
            'leave_group': self.handle_leave_group,
            'kick_user': self.handle_kick_user,
            'get_group_info': self.handle_get_group_info,
            'delete_group': self.handle_delete_group,
            'update_public_key': self.handle_update_public_key
        }

    def start(self, ip, port):
        try:
            self.server_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            self.server_socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            self.server_socket.bind((ip, port))
            self.server_socket.listen()
            self.is_running = True

            threading.Thread(target=self._accept_loop, daemon=True).start()
            return True
        except Exception as e:
            self.log(f"Błąd uruchamiania serwera: {e}")
            return False

    def stop(self):
        self.is_running = False
        if self.server_socket:
            try:
                self.server_socket.close()
            except Exception:
                pass
        for conn in list(self.active_users.values()):
            try:
                conn.close()
            except Exception:
                pass
        self.active_users.clear()

    def _accept_loop(self):
        while self.is_running:
            try:
                conn, addr = self.server_socket.accept()
                threading.Thread(target=self._handle_client, args=(conn, addr), daemon=True).start()
            except OSError:
                break

    def encrypt_sys(self, text):
        return self.cipher.encrypt(text.encode('utf-8')).decode('utf-8')

    def send_to(self, conn, packet):
        try:
            conn.sendall((json.dumps(packet) + "\n").encode('utf-8'))
        except Exception:
            pass

    def broadcast(self, packet, exclude=None):
        json_data = (json.dumps(packet) + "\n").encode('utf-8')
        for username, conn in list(self.active_users.items()):
            if username != exclude:
                try:
                    conn.sendall(json_data)
                except Exception:
                    pass

    def broadcast_user_list(self):
        packet = {
            "action": "user_list",
            "all_users": database.get_all_users(),
            "online_users": list(self.active_users.keys()),
            "public_keys": database.get_all_users_with_keys()
        }
        self.broadcast(packet)

    def _handle_client(self, conn, addr):
        self.log(f"[POŁĄCZENIE] Nowy klient {addr}")
        current_user = None
        file_obj = conn.makefile('r', encoding='utf-8')

        try:
            for line in file_obj:
                if not line.strip():
                    continue
                message = json.loads(line)
                action = message.get('action')

                if action in self.routes:
                    result = self.routes[action](conn, message, current_user)
                    if result:
                        current_user = result
        except Exception as e:
            self.log(f"[BŁĄD] {addr}: {e}")
        finally:
            if current_user and current_user in self.active_users:
                del self.active_users[current_user]
                now = datetime.now().strftime("%H:%M")
                sys_msg = self.encrypt_sys(f"{current_user} opuścił czat.")
                self.broadcast({"action": "chat_message", "sender": "SYSTEM", "content": sys_msg, "timestamp": now})
                self.broadcast_user_list()
                self.log(f"[WYLOGOWANIE] Wylogowano: {current_user}")
            conn.close()
            self.log(f"[ROZŁĄCZONO] Klient {addr} opuścił serwer.")

    def handle_register(self, conn, msg, current_user):
        user, pwd = msg.get('username'), msg.get('password')
        if database.register_user(user, pwd):
            self.send_to(conn, {"status": "success", "message": "Zarejestrowano pomyślnie!"})
            self.broadcast_user_list()
            self.log(f"[REJESTRACJA] Nowy użytkownik: {user}")
        else:
            self.send_to(conn, {"status": "error", "message": "Nazwa użytkownika jest zajęta."})

    def handle_login(self, conn, msg, current_user):
        user, pwd = msg.get('username'), msg.get('password')
        if database.verify_user(user, pwd):
            if user in self.active_users:
                self.send_to(conn, {"status": "error", "message": "Użytkownik już zalogowany!"})
            else:
                self.send_to(conn, {"status": "success", "message": f"Witaj {user} na czacie!"})
                self.active_users[user] = conn
                self.broadcast_user_list()

                now = datetime.now().strftime("%H:%M")
                sys_msg = self.encrypt_sys(f"{user} dołączył do czatu.")
                self.broadcast({"action": "chat_message", "sender": "SYSTEM", "content": sys_msg, "timestamp": now},
                               exclude=user)

                self.send_to(conn, {"action": "chat_history", "history": database.get_global_history()})
                self.send_to(conn, {"action": "private_history", "history": database.get_private_history(user)})

                groups = database.get_user_groups(user)
                self.send_to(conn, {"action": "your_groups", "groups": groups})
                for g in groups:
                    self.send_to(conn,
                                 {"action": "group_history", "group": g, "history": database.get_group_history(g)})

                invites = database.get_user_invites(user)
                join_reqs = database.get_creator_join_requests(user)
                if invites or join_reqs:
                    self.send_to(conn, {"action": "pending_requests", "invites": invites, "join_reqs": join_reqs})

                self.log(f"[LOGOWANIE] Zalogowano: {user}")
                return user
        else:
            self.send_to(conn, {"status": "error", "message": "Błędny login lub hasło."})

    def handle_update_public_key(self, conn, msg, current_user):
        if not current_user:
            return
        pub_key = msg.get("public_key")
        if pub_key:
            database.update_user_public_key(current_user, pub_key)
            self.log(f"[KLUCZ] Zaktualizowano klucz publiczny dla {current_user}")
            self.broadcast_user_list()

    def handle_typing(self, conn, msg, current_user):
        if not current_user:
            return
        target = msg.get("target")
        packet = {"action": "typing", "sender": current_user, "target": target}

        if target == "Globalny":
            self.broadcast(packet, exclude=current_user)
        elif target.startswith("#"):
            for m in database.get_group_members(target):
                if m in self.active_users and m != current_user:
                    self.send_to(self.active_users[m], packet)
        elif target in self.active_users:
            self.send_to(self.active_users[target], packet)

    def handle_broadcast_message(self, conn, msg, current_user):
        if not current_user:
            return
        content = msg.get('content')
        database.save_message(current_user, "Globalny", content)

        self.broadcast({
            "action": "chat_message",
            "sender": current_user,
            "content": content,
            "timestamp": datetime.now().strftime("%H:%M")
        }, exclude=current_user)

    def handle_private_message(self, conn, msg, current_user):
        if not current_user:
            return
        recipient, content = msg.get("recipient"), msg.get("content")
        database.save_message(current_user, recipient, content)
        if recipient in self.active_users:
            self.send_to(self.active_users[recipient],
                         {"action": "private_message", "sender": current_user, "content": content,
                          "timestamp": datetime.now().strftime("%H:%M")})

    def handle_group_message(self, conn, msg, current_user):
        if not current_user:
            return
        group, content = msg.get("group"), msg.get("content")
        database.save_message(current_user, group, content)
        packet = {"action": "group_message", "sender": current_user, "group": group, "content": content,
                  "timestamp": datetime.now().strftime("%H:%M")}
        for m in database.get_group_members(group):
            if m in self.active_users and m != current_user:
                self.send_to(self.active_users[m], packet)

    def handle_send_file(self, conn, msg, current_user):
        if not current_user:
            return
        target, filename, file_id, file_data = msg.get("target"), msg.get("filename"), msg.get("file_id"), msg.get(
            "data")

        os.makedirs("Serwer_Pliki", exist_ok=True)
        with open(os.path.join("Serwer_Pliki", file_id), "wb") as f:
            f.write(base64.b64decode(file_data))

        enc_info = self.encrypt_sys(f"[FILE:{file_id}:{filename}]")
        database.save_message(current_user, target, enc_info)
        self.log(f"[PLIK] {current_user} wysłał: {filename}")

        packet = {
            "action": "chat_message" if target == "Globalny" else (
                "group_message" if target.startswith("#") else "private_message"),
            "sender": current_user,
            "content": enc_info,
            "timestamp": datetime.now().strftime("%H:%M")
        }
        if target.startswith("#"):
            packet["group"] = target

        if target == "Globalny":
            self.broadcast(packet, exclude=current_user)
        elif target.startswith("#"):
            for m in database.get_group_members(target):
                if m in self.active_users and m != current_user:
                    self.send_to(self.active_users[m], packet)
        elif target in self.active_users:
            self.send_to(self.active_users[target], packet)

    def handle_download_request(self, conn, msg, current_user):
        if not current_user:
            return
        file_id, filename = msg.get("file_id"), msg.get("filename")
        path = os.path.join("Serwer_Pliki", file_id)
        if os.path.exists(path):
            with open(path, "rb") as f:
                data = base64.b64encode(f.read()).decode('utf-8')
            self.send_to(conn, {"action": "receive_download", "filename": filename, "data": data})
        else:
            self.send_to(conn, {"status": "error", "message": "Plik został usunięty z serwera."})

    def handle_create_group(self, conn, msg, current_user):
        if not current_user:
            return
        name = msg.get("name")
        if database.create_group(name, current_user):
            self.send_to(conn, {"status": "success", "message": f"Utworzono {name}!"})
            self.send_to(conn, {"action": "your_groups", "groups": database.get_user_groups(current_user)})
            self.log(f"[GRUPA] Utworzono: {name} przez {current_user}")
        else:
            self.send_to(conn, {"status": "error", "message": "Taka grupa już istnieje!"})

    def handle_join_group(self, conn, msg, current_user):
        if not current_user:
            return
        name = msg.get("name")
        creator = database.get_group_creator(name)
        if not creator:
            self.send_to(conn, {"status": "error", "message": "Taka grupa nie istnieje!"})
        elif current_user in database.get_group_members(name):
            self.send_to(conn, {"status": "error", "message": "Już jesteś w tej grupie!"})
        else:
            database.add_group_request(name, current_user, "join")
            self.send_to(conn, {"status": "success", "message": f"Wysłano prośbę o dołączenie do {name}."})
            if creator in self.active_users:
                self.send_to(self.active_users[creator],
                             {"action": "join_request_received", "group": name, "user": current_user})

    def handle_add_user_to_group(self, conn, msg, current_user):
        if not current_user:
            return
        group, user_to_add = msg.get("group"), msg.get("user")
        if database.get_group_creator(group) == current_user:
            if user_to_add not in database.get_all_users():
                self.send_to(conn, {"status": "error", "message": f"Użytkownik {user_to_add} nie istnieje!"})
            elif user_to_add in database.get_group_members(group):
                self.send_to(conn, {"status": "error", "message": f"{user_to_add} już jest w grupie!"})
            else:
                database.add_group_request(group, user_to_add, "invite")
                self.send_to(conn, {"status": "success", "message": f"Wysłano zaproszenie do {user_to_add}!"})
                if user_to_add in self.active_users:
                    self.send_to(self.active_users[user_to_add],
                                 {"action": "invite_received", "group": group, "admin": current_user})
        else:
            self.send_to(conn, {"status": "error", "message": "Tylko założyciel może zapraszać!"})

    def handle_resolve_join(self, conn, msg, current_user):
        if not current_user:
            return
        group, user, accept = msg.get("group"), msg.get("user"), msg.get("accept")
        database.remove_group_request(group, user, "join")

        if accept:
            database.join_group(group, user)
            self.send_to(conn, {"status": "success", "message": f"Zaakceptowano {user} w {group}!"})
            if user in self.active_users:
                u_conn = self.active_users[user]
                self.send_to(u_conn, {"status": "success", "message": f"Dołączyłeś do {group}!"})
                self.send_to(u_conn, {"action": "your_groups", "groups": database.get_user_groups(user)})
                self.send_to(u_conn,
                             {"action": "group_history", "group": group, "history": database.get_group_history(group)})

            enc = self.encrypt_sys(f"{user} dołączył do grupy.")
            database.save_message("SYSTEM", group, enc)
            pkt = {"action": "group_message", "sender": "SYSTEM", "group": group, "content": enc,
                   "timestamp": datetime.now().strftime("%H:%M")}
            for m in database.get_group_members(group):
                if m in self.active_users:
                    self.send_to(self.active_users[m], pkt)
                    self.send_to(self.active_users[m],
                                 {"action": "group_info", "group": group, "members": database.get_group_members(group),
                                  "creator": current_user})
        else:
            if user in self.active_users:
                self.send_to(self.active_users[user],
                             {"status": "error", "message": f"Prośba o dołączenie do {group} ODRZUCONA."})

    def handle_resolve_invite(self, conn, msg, current_user):
        if not current_user:
            return
        group, accept = msg.get("group"), msg.get("accept")
        database.remove_group_request(group, current_user, "invite")
        creator = database.get_group_creator(group)

        if accept:
            database.join_group(group, current_user)
            self.send_to(conn, {"status": "success", "message": f"Dołączyłeś do {group}!"})
            self.send_to(conn, {"action": "your_groups", "groups": database.get_user_groups(current_user)})
            self.send_to(conn,
                         {"action": "group_history", "group": group, "history": database.get_group_history(group)})

            enc = self.encrypt_sys(f"{current_user} dołączył do grupy.")
            database.save_message("SYSTEM", group, enc)
            pkt = {"action": "group_message", "sender": "SYSTEM", "group": group, "content": enc,
                   "timestamp": datetime.now().strftime("%H:%M")}
            for m in database.get_group_members(group):
                if m in self.active_users:
                    self.send_to(self.active_users[m], pkt)
                    self.send_to(self.active_users[m],
                                 {"action": "group_info", "group": group, "members": database.get_group_members(group),
                                  "creator": creator})
        else:
            if creator in self.active_users:
                self.send_to(self.active_users[creator],
                             {"status": "error", "message": f"{current_user} ODRZUCIŁ zaproszenie do {group}."})

    def handle_leave_group(self, conn, msg, current_user):
        if not current_user:
            return
        group = msg.get("name")
        database.leave_group(group, current_user)
        self.send_to(conn, {"status": "success", "message": f"Opuszczono {group}."})
        self.send_to(conn, {"action": "your_groups", "groups": database.get_user_groups(current_user)})

        enc = self.encrypt_sys(f"{current_user} opuścił grupę.")
        database.save_message("SYSTEM", group, enc)
        pkt = {"action": "group_message", "sender": "SYSTEM", "group": group, "content": enc,
               "timestamp": datetime.now().strftime("%H:%M")}
        for m in database.get_group_members(group):
            if m in self.active_users:
                self.send_to(self.active_users[m], pkt)
                self.send_to(self.active_users[m],
                             {"action": "group_info", "group": group, "members": database.get_group_members(group),
                              "creator": database.get_group_creator(group)})

    def handle_kick_user(self, conn, msg, current_user):
        if not current_user:
            return
        group, user_to_kick = msg.get("group"), msg.get("user")
        creator = database.get_group_creator(group)
        if creator == current_user:
            database.leave_group(group, user_to_kick)
            self.send_to(conn, {"status": "success", "message": f"Wyrzucono {user_to_kick} z grupy."})

            enc = self.encrypt_sys(f"{user_to_kick} został wyrzucony przez administratora.")
            database.save_message("SYSTEM", group, enc)
            pkt = {"action": "group_message", "sender": "SYSTEM", "group": group, "content": enc,
                   "timestamp": datetime.now().strftime("%H:%M")}

            if user_to_kick in self.active_users:
                self.send_to(self.active_users[user_to_kick], {"action": "kicked_from_group", "group": group})
                self.send_to(self.active_users[user_to_kick],
                             {"action": "your_groups", "groups": database.get_user_groups(user_to_kick)})

            members = database.get_group_members(group)
            for m in members:
                if m in self.active_users:
                    self.send_to(self.active_users[m], pkt)
                    self.send_to(self.active_users[m],
                                 {"action": "group_info", "group": group, "members": members, "creator": creator})

    def handle_get_group_info(self, conn, msg, current_user):
        if not current_user:
            return
        group = msg.get("group")
        self.send_to(conn, {"action": "group_info", "group": group, "members": database.get_group_members(group),
                            "creator": database.get_group_creator(group)})

    def handle_delete_group(self, conn, msg, current_user):
        if not current_user:
            return
        group = msg.get("group")
        members = database.get_group_members(group)
        if database.delete_group(group, current_user):
            for m in members:
                if m in self.active_users:
                    self.send_to(self.active_users[m], {"action": "group_deleted", "group": group})
                    self.send_to(self.active_users[m], {"action": "your_groups", "groups": database.get_user_groups(m)})
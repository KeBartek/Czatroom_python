import customtkinter as ctk
import socket
import json
import threading
import os
import base64
import re
import platform
import subprocess
import requests
from PIL import Image
from tkinter import messagebox, filedialog
from datetime import datetime

try:
    from cryptography.fernet import Fernet
except ImportError:
    print("BŁĄD: Musisz zainstalować bibliotekę cryptography!")
    exit()

try:
    from plyer import notification
except ImportError:
    notification = None

ctk.set_appearance_mode("dark")
ctk.set_default_color_theme("blue")

CIPHER_KEY = b'MDEyMzQ1Njc4OTAxMjM0NTY3ODkwMTIzNDU2Nzg5MDE='

EMOTES_DB = {
    ":pepe:": "https://cdn.frankerfacez.com/emoticon/28087/1",
    ":pog:": "https://cdn.frankerfacez.com/emoticon/210748/1",
    ":kekw:": "https://cdn.frankerfacez.com/emoticon/381875/1",
    ":catjam:": "https://cdn.frankerfacez.com/emoticon/520322/1",
    ":sadge:": "https://cdn.frankerfacez.com/emoticon/425196/1",
    ":monkas:": "https://cdn.frankerfacez.com/emoticon/130762/1",
    ":ez:": "https://cdn.frankerfacez.com/emoticon/108566/1",
    ":ayaya:": "https://cdn.frankerfacez.com/emoticon/162146/1",
    ":5head:": "https://cdn.frankerfacez.com/emoticon/239504/1",
    ":pepehands:": "https://cdn.frankerfacez.com/emoticon/231552/1",
    ":copium:": "https://cdn.frankerfacez.com/emoticon/564259/1",
    ":poggers:": "https://cdn.frankerfacez.com/emoticon/214129/1",
    ":monkaw:": "https://cdn.frankerfacez.com/emoticon/214681/1",
    ":weirdchamp:": "https://cdn.frankerfacez.com/emoticon/322196/1",
    ":peeposhyness:": "https://cdn.frankerfacez.com/emoticon/316264/1",
    ":feelsbadman:": "https://cdn.frankerfacez.com/emoticon/33355/1",
    ":feelsgoodman:": "https://cdn.frankerfacez.com/emoticon/109777/1",
    ":omegadance:": "https://cdn.frankerfacez.com/emoticon/405106/1",
    ":smadge:": "https://cdn.frankerfacez.com/emoticon/494286/1"
}


class ChatClient:
    def __init__(self):
        self.root = ctk.CTk()
        self.root.title("Czatroom - Konfiguracja Połączenia")
        self.root.geometry("400x450")
        self.root.resizable(False, False)

        self.cipher = Fernet(CIPHER_KEY)
        self.client_socket = None
        self.socket_file = None
        self.username = None

        self.server_ip = "127.0.0.1"
        self.server_port = 9999

        self.current_chat = "Globalny"
        self.chat_histories = {"Globalny": ""}

        self.unread_counts = {}
        self.cached_all_users = []
        self.cached_online_users = []
        self.cached_groups = []

        self.current_group_members = []
        self.current_group_creator = None

        self.last_typing_time = 0
        self.typing_timer = None

        self.loaded_emotes = {}

        self.emote_panel = None
        self.emote_panel_visible = False

        # --- NOWOŚĆ: Uruchamiamy pobieranie emotek w tle przy starcie aplikacji ---
        threading.Thread(target=self.preload_emotes, daemon=True).start()

        self.build_connect_screen()

    # --- NOWOŚĆ: Pobiera pliki obrazków z neta, żeby nie spowalniać UI ---
    def preload_emotes(self):
        os.makedirs("Cache_Emotki", exist_ok=True)
        for code, url in EMOTES_DB.items():
            name = code.strip(":")
            filepath = os.path.join("Cache_Emotki", f"{name}.png")
            if not os.path.exists(filepath):
                try:
                    response = requests.get(url, timeout=3)
                    if response.status_code == 200:
                        with open(filepath, "wb") as f:
                            f.write(response.content)
                except:
                    pass

    def decrypt_msg(self, enc_text):
        try:
            return self.cipher.decrypt(enc_text.encode('utf-8')).decode('utf-8')
        except:
            return "🔒 [Nieczytelna wiadomość]"

    def get_emote_image(self, emote_code):
        if emote_code not in EMOTES_DB: return None
        if emote_code in self.loaded_emotes: return self.loaded_emotes[emote_code]

        name = emote_code.strip(":")
        filepath = os.path.join("Cache_Emotki", f"{name}.png")

        if not os.path.exists(filepath):
            return None

        try:
            img = ctk.CTkImage(Image.open(filepath), size=(24, 24))
            self.loaded_emotes[emote_code] = img
            return img
        except:
            return None

    def build_connect_screen(self):
        self.frame = ctk.CTkFrame(master=self.root)
        self.frame.pack(pady=20, padx=40, fill="both", expand=True)

        self.label_title = ctk.CTkLabel(master=self.frame, text="Ustawienia Serwera", font=("Roboto", 24, "bold"))
        self.label_title.pack(pady=30, padx=10)

        self.entry_ip = ctk.CTkEntry(master=self.frame, placeholder_text="Adres IP", width=250)
        self.entry_ip.insert(0, "127.0.0.1")
        self.entry_ip.pack(pady=12, padx=10)

        self.entry_port = ctk.CTkEntry(master=self.frame, placeholder_text="Port", width=250)
        self.entry_port.insert(0, "9999")
        self.entry_port.pack(pady=12, padx=10)

        self.entry_ip.bind("<Return>", lambda event: self.try_connect())
        self.entry_port.bind("<Return>", lambda event: self.try_connect())

        self.btn_connect = ctk.CTkButton(master=self.frame, text="Połącz z Serwerem", command=self.try_connect)
        self.btn_connect.pack(pady=20, padx=10)

    def try_connect(self):
        ip = self.entry_ip.get().strip()
        port_str = self.entry_port.get().strip()
        if not ip or not port_str.isdigit():
            messagebox.showerror("Błąd", "Podaj prawidłowy adres IP i port (tylko cyfry).")
            return

        self.server_ip = ip
        self.server_port = int(port_str)

        if self.connect_to_server():
            self.frame.destroy()
            self.build_login_screen()

    def connect_to_server(self):
        if self.client_socket is None:
            try:
                self.client_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
                self.client_socket.connect((self.server_ip, self.server_port))
                self.socket_file = self.client_socket.makefile('r', encoding='utf-8')
                return True
            except:
                messagebox.showerror("Błąd",
                                     f"Nie można połączyć się z serwerem pod adresem\n{self.server_ip}:{self.server_port}")
                self.client_socket = None
                return False
        return True

    def build_login_screen(self):
        self.root.title("Czatroom - Logowanie 🔒 E2EE")
        self.frame = ctk.CTkFrame(master=self.root)
        self.frame.pack(pady=20, padx=40, fill="both", expand=True)

        self.label_title = ctk.CTkLabel(master=self.frame, text="Witaj w Czatroomie", font=("Roboto", 24, "bold"))
        self.label_title.pack(pady=30, padx=10)

        self.entry_username = ctk.CTkEntry(master=self.frame, placeholder_text="Nazwa użytkownika", width=250)
        self.entry_username.pack(pady=12, padx=10)

        self.entry_password = ctk.CTkEntry(master=self.frame, placeholder_text="Hasło", width=250, show="*")
        self.entry_password.pack(pady=12, padx=10)

        self.entry_username.bind("<Return>", lambda event: self.login())
        self.entry_password.bind("<Return>", lambda event: self.login())

        self.btn_login = ctk.CTkButton(master=self.frame, text="Zaloguj się", command=self.login)
        self.btn_login.pack(pady=12, padx=10)

        self.btn_register = ctk.CTkButton(master=self.frame, text="Zarejestruj się", fg_color="transparent",
                                          border_width=2, text_color=("gray10", "#DCE4EE"), command=self.register)
        self.btn_register.pack(pady=12, padx=10)

    def send_auth_request(self, action):
        username = self.entry_username.get().strip()
        password = self.entry_password.get().strip()
        if not username or not password:
            messagebox.showwarning("Uwaga", "Wprowadź nazwę użytkownika i hasło.")
            return

        if not self.connect_to_server(): return

        request = {"action": action, "username": username, "password": password}
        try:
            self.client_socket.sendall((json.dumps(request) + "\n").encode('utf-8'))
            response_line = self.socket_file.readline()
            if not response_line: return
            response = json.loads(response_line)

            if response['status'] == 'success':
                messagebox.showinfo("Sukces", response['message'])
                if action == 'login':
                    self.username = username
                    self.open_chat_window()
            else:
                messagebox.showerror("Błąd", response['message'])
        except Exception as e:
            messagebox.showerror("Błąd krytyczny", f"Utracono połączenie: {e}")
            self.client_socket = None

    def login(self):
        self.send_auth_request("login")

    def register(self):
        self.send_auth_request("register")

    def open_chat_window(self):
        self.frame.destroy()
        self.root.geometry("1100x650")
        self.root.title(f"Czatroom - {self.username} (🔒 Zabezpieczono)")
        self.root.resizable(True, True)

        self.main_container = ctk.CTkFrame(master=self.root, fg_color="transparent")
        self.main_container.pack(fill="both", expand=True, padx=10, pady=10)

        self.sidebar_frame = ctk.CTkFrame(master=self.main_container, width=220)
        self.sidebar_frame.pack(side="left", fill="y", padx=(0, 10))

        self.btn_global_chat = ctk.CTkButton(master=self.sidebar_frame, text="🌐 Czat Globalny",
                                             font=("Roboto", 14, "bold"), command=lambda: self.switch_chat("Globalny"))
        self.btn_global_chat.pack(pady=10, padx=10, fill="x")

        self.btn_new_group = ctk.CTkButton(master=self.sidebar_frame, text="➕ Utwórz grupę", fg_color="#2b7b4d",
                                           hover_color="#1e5c38", command=self.ui_create_group)
        self.btn_new_group.pack(pady=(0, 5), padx=10, fill="x")
        self.btn_join_group = ctk.CTkButton(master=self.sidebar_frame, text="🤝 Dołącz do grupy", fg_color="#85531b",
                                            hover_color="#633d13", command=self.ui_join_group)
        self.btn_join_group.pack(pady=(0, 10), padx=10, fill="x")

        self.btn_leave_group = ctk.CTkButton(master=self.sidebar_frame, text="🚪 Opuść grupę", fg_color="#c0392b",
                                             hover_color="#922b21", command=self.ui_leave_group)
        self.btn_leave_group.pack(pady=(0, 10), padx=10, fill="x")

        self.lbl_groups = ctk.CTkLabel(master=self.sidebar_frame, text="📁 Twoje Grupy i Czaty:",
                                       font=("Roboto", 14, "bold"))
        self.lbl_groups.pack(pady=(0, 0), padx=10)
        self.groups_scrollable = ctk.CTkScrollableFrame(master=self.sidebar_frame, width=200)
        self.groups_scrollable.pack(fill="both", expand=True, padx=5, pady=5)

        self.right_panel = ctk.CTkFrame(master=self.main_container, width=220)
        self.right_panel.pack(side="right", fill="y", padx=(10, 0))

        self.lbl_right_title = ctk.CTkLabel(master=self.right_panel, text="👥 Użytkownicy:", font=("Roboto", 14, "bold"))
        self.lbl_right_title.pack(pady=(10, 0), padx=10)

        self.users_scrollable = ctk.CTkScrollableFrame(master=self.right_panel, width=200)
        self.users_scrollable.pack(fill="both", expand=True, padx=5, pady=5)

        self.btn_delete_group = ctk.CTkButton(master=self.right_panel, text="🗑️ Usuń Grupę (Admin)", fg_color="#c0392b",
                                              hover_color="#922b21", command=self.delete_current_group)

        self.chat_frame = ctk.CTkFrame(master=self.main_container)
        self.chat_frame.pack(side="left", fill="both", expand=True)

        self.lbl_current_chat = ctk.CTkLabel(master=self.chat_frame, text="Rozmowa: Globalny",
                                             font=("Roboto", 18, "bold"))
        self.lbl_current_chat.pack(pady=(10, 0))

        self.text_area = ctk.CTkTextbox(master=self.chat_frame, state="disabled", wrap="word", font=("Roboto", 14))
        self.text_area.pack(pady=10, padx=10, fill="both", expand=True)

        self.lbl_typing = ctk.CTkLabel(master=self.chat_frame, text="", font=("Roboto", 12, "italic"),
                                       text_color="gray")
        self.lbl_typing.pack(pady=(0, 5), padx=15, anchor="w")

        self.bottom_frame = ctk.CTkFrame(master=self.chat_frame, fg_color="transparent")
        self.bottom_frame.pack(pady=(0, 10), padx=10, fill="x")

        self.btn_attach = ctk.CTkButton(master=self.bottom_frame, text="📎", width=40, command=self.send_file)
        self.btn_attach.pack(side="left", padx=(0, 10))

        # --- NOWOŚĆ: Przycisk otwierający menu emotek ---
        self.btn_emotes = ctk.CTkButton(master=self.bottom_frame, text="😀", width=40, fg_color="#f39c12",
                                        hover_color="#e67e22", command=self.toggle_emote_panel)
        self.btn_emotes.pack(side="left", padx=(0, 10))

        self.entry_message = ctk.CTkEntry(master=self.bottom_frame, placeholder_text="Wpisz wiadomość...", width=600)
        self.entry_message.pack(side="left", padx=(0, 10), fill="x", expand=True)
        self.entry_message.bind("<KeyRelease>", self.on_key_release)
        self.entry_message.bind("<Return>", lambda event: self.send_message())

        self.btn_send = ctk.CTkButton(master=self.bottom_frame, text="Wyślij", width=100, command=self.send_message)
        self.btn_send.pack(side="right")

        threading.Thread(target=self.receive_messages, daemon=True).start()

    # --- NOWOŚĆ: Funkcje obsługujące wysuwany panel z emotkami ---
    def toggle_emote_panel(self):
        if self.emote_panel is None:
            self.emote_panel = ctk.CTkScrollableFrame(master=self.chat_frame, height=55, orientation="horizontal",
                                                      fg_color="#2b2b2b")

        if self.emote_panel_visible:
            self.emote_panel.pack_forget()
            self.emote_panel_visible = False
        else:
            self.emote_panel.pack(before=self.bottom_frame, fill="x", padx=10, pady=(0, 5))
            self.emote_panel_visible = True
            self.populate_emote_panel()

    def populate_emote_panel(self):
        for widget in self.emote_panel.winfo_children():
            widget.destroy()

        for code in EMOTES_DB.keys():
            img = self.get_emote_image(code)
            if img:
                btn = ctk.CTkButton(self.emote_panel, text="", image=img, width=40, height=40, fg_color="transparent",
                                    hover_color="#444444", command=lambda c=code: self.insert_emote_code(c))
                btn.pack(side="left", padx=5)
            else:
                # Fallback, jeśli emotka się jeszcze nie pobrała
                btn = ctk.CTkButton(self.emote_panel, text=code, width=50, height=40,
                                    command=lambda c=code: self.insert_emote_code(c))
                btn.pack(side="left", padx=5)

    def insert_emote_code(self, code):
        self.entry_message.insert("end", code + " ")
        self.entry_message.focus()

    def on_key_release(self, event):
        if event.keysym == "Return": return
        if len(self.entry_message.get().strip()) > 0:
            now = datetime.now().timestamp()
            if now - self.last_typing_time > 2:
                self.last_typing_time = now
                try:
                    req = {"action": "typing", "target": self.current_chat}
                    self.client_socket.sendall((json.dumps(req) + "\n").encode('utf-8'))
                except:
                    pass

    def show_typing_indicator(self, sender):
        self.lbl_typing.configure(text=f"{sender} pisze...")
        if self.typing_timer: self.root.after_cancel(self.typing_timer)
        self.typing_timer = self.root.after(3000, self.clear_typing_indicator)

    def clear_typing_indicator(self):
        self.lbl_typing.configure(text="")

    def refresh_ui(self):
        def refresh():
            unread_gl = self.unread_counts.get("Globalny", 0)
            gl_text = f"🌐 Czat Globalny ({unread_gl})" if unread_gl > 0 else "🌐 Czat Globalny"
            self.btn_global_chat.configure(text_color="#f39c12" if unread_gl > 0 else ("gray10", "#DCE4EE"))
            self.btn_global_chat.configure(text=gl_text)

            for widget in self.groups_scrollable.winfo_children(): widget.destroy()

            private_chats = [c for c in self.chat_histories.keys() if c != "Globalny" and not c.startswith("#")]

            for group in self.cached_groups:
                unread = self.unread_counts.get(group, 0)
                g_text = f"{group} ({unread})" if unread > 0 else group
                g_color = "#f39c12" if unread > 0 else "#2b7b4d"
                lbl = ctk.CTkLabel(master=self.groups_scrollable, text=g_text, font=("Roboto", 13, "bold"),
                                   text_color=g_color, cursor="hand2")
                lbl.bind("<Button-1>", lambda event, g=group: self.switch_chat(g))
                lbl.pack(anchor="w", pady=2, padx=10)

            for priv in private_chats:
                unread = self.unread_counts.get(priv, 0)
                p_text = f"👤 {priv} ({unread})" if unread > 0 else f"👤 {priv}"
                p_color = "#f39c12" if unread > 0 else ("gray10", "#DCE4EE")
                lbl = ctk.CTkLabel(master=self.groups_scrollable, text=p_text, font=("Roboto", 13), text_color=p_color,
                                   cursor="hand2")
                lbl.bind("<Button-1>", lambda event, p=priv: self.switch_chat(p))
                lbl.pack(anchor="w", pady=2, padx=10)

            for widget in self.users_scrollable.winfo_children(): widget.destroy()

            if self.current_chat.startswith("#"):
                self.lbl_right_title.configure(text=f"👥 Członkowie {self.current_chat}:")

                if self.username == self.current_group_creator:
                    btn_invite = ctk.CTkButton(master=self.users_scrollable, text="➕ Zaproś osobę", fg_color="#27ae60",
                                               hover_color="#219a52", command=self.ui_invite_to_group)
                    btn_invite.pack(pady=(0, 5), padx=10, fill="x")

                    btn_kick = ctk.CTkButton(master=self.users_scrollable, text="👢 Wyrzuć osobę", fg_color="#d35400",
                                             hover_color="#b83b00", command=self.ui_kick_from_group)
                    btn_kick.pack(pady=(0, 10), padx=10, fill="x")

                    self.btn_delete_group.pack(pady=(5, 0), padx=10, fill="x", side="bottom")
                else:
                    self.btn_delete_group.pack_forget()

                for user in self.current_group_members:
                    if user == self.username:
                        lbl_me = ctk.CTkLabel(master=self.users_scrollable, text=f"🔵 {self.username} (Ty)",
                                              font=("Roboto", 13, "bold"), text_color="#1f6aa5")
                        lbl_me.pack(anchor="w", pady=2, padx=10)
                        if self.username == self.current_group_creator: ctk.CTkLabel(master=self.users_scrollable,
                                                                                     text="👑 Właściciel",
                                                                                     font=("Roboto", 10),
                                                                                     text_color="#f1c40f").pack(
                            anchor="w", padx=25)
                        continue

                    u_color = "#2ecc71" if user in self.cached_online_users else "#e74c3c"
                    u_font = ("Roboto", 13, "bold") if user in self.cached_online_users else ("Roboto", 13)
                    lbl = ctk.CTkLabel(master=self.users_scrollable, text=f"{user}", font=u_font, text_color=u_color,
                                       cursor="hand2")
                    lbl.bind("<Button-1>", lambda event, u=user: self.switch_chat(u))
                    lbl.pack(anchor="w", pady=2, padx=10)

                    if user == self.current_group_creator: ctk.CTkLabel(master=self.users_scrollable,
                                                                        text="👑 Właściciel", font=("Roboto", 10),
                                                                        text_color="#f1c40f").pack(anchor="w", padx=25)

            else:
                self.lbl_right_title.configure(text="👥 Wszyscy Użytkownicy:")
                self.btn_delete_group.pack_forget()

                lbl_me = ctk.CTkLabel(master=self.users_scrollable, text=f"🔵 {self.username} (Ty)",
                                      font=("Roboto", 13, "bold"), text_color="#1f6aa5")
                lbl_me.pack(anchor="w", pady=2, padx=10)

                for user in self.cached_all_users:
                    if user == self.username: continue

                    unread = self.unread_counts.get(user, 0)
                    u_color = "#f39c12" if unread > 0 else (
                        "#2ecc71" if user in self.cached_online_users else "#e74c3c")
                    u_font = ("Roboto", 13, "bold") if (unread > 0 or user in self.cached_online_users) else ("Roboto",
                                                                                                              13)
                    u_text = f"{user} ({unread})" if unread > 0 else f"{user}"

                    lbl = ctk.CTkLabel(master=self.users_scrollable, text=u_text, font=u_font, text_color=u_color,
                                       cursor="hand2")
                    lbl.bind("<Button-1>", lambda event, u=user: self.switch_chat(u))
                    lbl.pack(anchor="w", pady=2, padx=10)

        self.root.after(0, refresh)

    def handle_join_request(self, group, user):
        ans = messagebox.askyesno("Prośba o dołączenie",
                                  f"Użytkownik '{user}' prosi o dołączenie do Twojej grupy '{group}'.\n\nCzy akceptujesz?")
        req = {"action": "resolve_join", "group": group, "user": user, "accept": ans}
        self.client_socket.sendall((json.dumps(req) + "\n").encode('utf-8'))

    def handle_invite(self, group, admin_name):
        ans = messagebox.askyesno("Zaproszenie do grupy",
                                  f"Otrzymałeś zaproszenie do grupy '{group}' od {admin_name}.\n\nCzy chcesz dołączyć?")
        req = {"action": "resolve_invite", "group": group, "accept": ans}
        self.client_socket.sendall((json.dumps(req) + "\n").encode('utf-8'))

    def ui_invite_to_group(self):
        dialog = ctk.CTkInputDialog(text="Wpisz nick osoby, którą chcesz dodać:", title="Dodaj do grupy")
        user_to_add = dialog.get_input()
        if user_to_add and user_to_add.strip():
            req = {"action": "add_user_to_group", "group": self.current_chat, "user": user_to_add.strip()}
            self.client_socket.sendall((json.dumps(req) + "\n").encode('utf-8'))

    def ui_kick_from_group(self):
        dialog = ctk.CTkInputDialog(text="Wpisz nick osoby, którą chcesz wyrzucić z grupy:", title="Wyrzuć użytkownika")
        user_to_kick = dialog.get_input()
        if user_to_kick and user_to_kick.strip():
            if user_to_kick.strip() == self.username:
                messagebox.showwarning("Uwaga",
                                       "Żeby opuścić grupę, użyj czerwonego przycisku 'Opuść grupę' po lewej stronie.")
                return
            req = {"action": "kick_user", "group": self.current_chat, "user": user_to_kick.strip()}
            self.client_socket.sendall((json.dumps(req) + "\n").encode('utf-8'))

    def mark_unread(self, chat_name):
        if chat_name != self.current_chat:
            self.unread_counts[chat_name] = self.unread_counts.get(chat_name, 0) + 1
            self.refresh_ui()

    def show_notification(self, title, msg):
        if notification:
            def notify_thread():
                try:
                    notification.notify(title=title, message=msg, app_name="Czatroom", timeout=5)
                except:
                    pass

            threading.Thread(target=notify_thread, daemon=True).start()

    def ui_create_group(self):
        dialog = ctk.CTkInputDialog(text="Wpisz nazwę nowej grupy (np. Projekt):", title="Nowa Grupa")
        name = dialog.get_input()
        if name and name.strip():
            formatted_name = "#" + name.strip().replace(" ", "_").replace("#", "")
            self.client_socket.sendall(
                (json.dumps({"action": "create_group", "name": formatted_name}) + "\n").encode('utf-8'))

    def ui_join_group(self):
        dialog = ctk.CTkInputDialog(text="Wpisz nazwę grupy do dołączenia:", title="Dołącz do Grupy")
        name = dialog.get_input()
        if name and name.strip():
            formatted_name = "#" + name.strip().replace(" ", "_").replace("#", "")
            self.client_socket.sendall(
                (json.dumps({"action": "join_group", "name": formatted_name}) + "\n").encode('utf-8'))

    def ui_leave_group(self):
        if self.current_chat.startswith("#"):
            confirm = messagebox.askyesno("Opuść grupę", f"Czy na pewno chcesz opuścić grupę {self.current_chat}?")
            if confirm:
                self.client_socket.sendall(
                    (json.dumps({"action": "leave_group", "name": self.current_chat}) + "\n").encode('utf-8'))
                self.switch_chat("Globalny")
        else:
            messagebox.showinfo("Informacja",
                                "Aby opuścić grupę, najpierw wejdź w jej zakładkę, a następnie kliknij ten przycisk.")

    def delete_current_group(self):
        confirm = messagebox.askyesno("Usuń grupę",
                                      f"UWAGA! Czy na pewno chcesz całkowicie usunąć grupę {self.current_chat}? Tej akcji nie można cofnąć!")
        if confirm:
            self.client_socket.sendall(
                (json.dumps({"action": "delete_group", "group": self.current_chat}) + "\n").encode('utf-8'))

    def switch_chat(self, chat_name):
        self.current_chat = chat_name
        self.lbl_current_chat.configure(text=f"Rozmowa: {chat_name}")
        self.clear_typing_indicator()

        if self.emote_panel_visible:
            self.toggle_emote_panel()

        if chat_name in self.unread_counts and self.unread_counts[chat_name] > 0:
            self.unread_counts[chat_name] = 0

        if chat_name.startswith("#"):
            self.client_socket.sendall(
                (json.dumps({"action": "get_group_info", "group": chat_name}) + "\n").encode('utf-8'))
        else:
            self.refresh_ui()

        self.text_area.configure(state="normal")
        self.text_area.delete("1.0", "end")

        history_text = self.chat_histories.get(chat_name, "")
        for line in history_text.split("\n"):
            if line: self.insert_line_with_buttons(line)

        self.text_area.configure(state="disabled")
        self.text_area.see("end")

    def _insert_text_with_emotes(self, text):
        parts = re.split(r'(:[a-zA-Z0-9_]+:)', text)
        for part in parts:
            if part in EMOTES_DB:
                img = self.get_emote_image(part)
                if img:
                    lbl = ctk.CTkLabel(self.text_area._textbox, text="", image=img)
                    self.text_area._textbox.window_create("end", window=lbl)
                else:
                    self.text_area.insert("end", part)
            else:
                if part:
                    self.text_area.insert("end", part)

    def insert_line_with_buttons(self, line):
        match = re.search(r'\[FILE:(.*?):(.*?)\]', line)
        if match:
            file_id = match.group(1)
            filename = match.group(2)
            before_text = line[:match.start()]
            after_text = line[match.end():]

            if before_text: self._insert_text_with_emotes(before_text)

            btn = ctk.CTkButton(
                self.text_area._textbox,
                text=f"📄 Pobierz: {filename}",
                height=24, fg_color="#8e44ad", hover_color="#732d91", cursor="hand2",
                command=lambda f_id=file_id, f_name=filename: self.request_download(f_id, f_name)
            )
            self.text_area._textbox.window_create("end", window=btn)

            if after_text:
                self._insert_text_with_emotes(after_text + "\n")
            else:
                self.text_area.insert("end", "\n")
        else:
            self._insert_text_with_emotes(line + "\n")

    def append_to_history(self, chat_name, text):
        if chat_name not in self.chat_histories: self.chat_histories[chat_name] = ""
        self.chat_histories[chat_name] += text + "\n"

        if chat_name != "Globalny" and not chat_name.startswith("#"):
            self.refresh_ui()

        if self.current_chat == chat_name:
            self.display_message(text)

    def display_message(self, text):
        self.text_area.configure(state="normal")
        self.insert_line_with_buttons(text)
        self.text_area.configure(state="disabled")
        self.text_area.see("end")

    def send_file(self):
        filepath = filedialog.askopenfilename(title="Wybierz plik do wysłania")
        if not filepath: return
        if os.path.getsize(filepath) > 5 * 1024 * 1024:
            messagebox.showwarning("Za duży plik", "Maksymalny rozmiar to 5MB.")
            return

        filename = os.path.basename(filepath)
        file_id = f"{int(datetime.now().timestamp())}_{self.username}_{filename}"

        try:
            with open(filepath, "rb") as f:
                encoded_string = base64.b64encode(f.read()).decode('utf-8')
            request = {"action": "send_file", "target": self.current_chat, "filename": filename, "file_id": file_id,
                       "data": encoded_string}
            self.client_socket.sendall((json.dumps(request) + "\n").encode('utf-8'))
            now = datetime.now().strftime("%H:%M")
            self.append_to_history(self.current_chat, f"[{now}] [Ty]: [FILE:{file_id}:{filename}]")
        except Exception as e:
            messagebox.showerror("Błąd pliku", f"Nie udało się wysłać pliku: {e}")

    def send_message(self):
        msg_text = self.entry_message.get().strip()
        if msg_text:
            now = datetime.now().strftime("%H:%M")
            encrypted_text = self.cipher.encrypt(msg_text.encode('utf-8')).decode('utf-8')

            if self.current_chat == "Globalny":
                request = {"action": "broadcast_message", "content": encrypted_text}
            elif self.current_chat.startswith("#"):
                request = {"action": "group_message", "group": self.current_chat, "content": encrypted_text}
                self.append_to_history(self.current_chat, f"[{now}] [Ty]: {msg_text}")
            else:
                request = {"action": "private_message", "recipient": self.current_chat, "content": encrypted_text}
                self.append_to_history(self.current_chat, f"[{now}] [Ty]: {msg_text}")

            if self.emote_panel_visible:
                self.toggle_emote_panel()

            try:
                self.client_socket.sendall((json.dumps(request) + "\n").encode('utf-8'))
                self.entry_message.delete(0, "end")
            except Exception as e:
                messagebox.showerror("Błąd", f"Nie udało się wysłać: {e}")

    def request_download(self, file_id, filename):
        req = {"action": "download_request", "file_id": file_id, "filename": filename}
        try:
            self.client_socket.sendall((json.dumps(req) + "\n").encode('utf-8'))
        except:
            messagebox.showerror("Błąd", "Brak połączenia z serwerem.")

    def receive_messages(self):
        try:
            for line in self.socket_file:
                if not line.strip(): continue
                message = json.loads(line)
                action = message.get("action")

                if action == "chat_message":
                    sender = message.get("sender")
                    content = self.decrypt_msg(message.get("content", ""))
                    time_str = message.get("timestamp", "")
                    self.append_to_history("Globalny", f"[{time_str}] [{sender}]: {content}")
                    if sender != self.username and sender != "SYSTEM":
                        self.mark_unread("Globalny")
                        self.root.after(0, self.clear_typing_indicator)

                elif action == "private_message":
                    sender = message.get("sender")
                    content = self.decrypt_msg(message.get("content", ""))
                    time_str = message.get("timestamp", "")
                    self.append_to_history(sender, f"[{time_str}] [{sender}]: {content}")
                    if sender != self.username:
                        self.show_notification(f"Wiadomość od: {sender}",
                                               "Wiadomość tekstowa" if "[FILE:" not in content else "Wysłano plik")
                        self.mark_unread(sender)
                        self.root.after(0, self.clear_typing_indicator)

                elif action == "group_message":
                    sender = message.get("sender")
                    group = message.get("group")
                    content = self.decrypt_msg(message.get("content", ""))
                    time_str = message.get("timestamp", "")
                    self.append_to_history(group, f"[{time_str}] [{sender}]: {content}")
                    if sender != self.username:
                        self.show_notification(f"Grupa {group} ({sender})",
                                               "Wiadomość tekstowa" if "[FILE:" not in content else "Wysłano plik")
                        self.mark_unread(group)
                        self.root.after(0, self.clear_typing_indicator)

                elif action == "typing":
                    sender = message.get("sender")
                    target = message.get("target")
                    should_show = False
                    if target == "Globalny" and self.current_chat == "Globalny":
                        should_show = True
                    elif target.startswith("#") and self.current_chat == target:
                        should_show = True
                    elif target == self.username and self.current_chat == sender:
                        should_show = True
                    if should_show: self.root.after(0, self.show_typing_indicator, sender)

                elif action == "receive_download":
                    filename = message.get("filename")
                    file_data = message.get("data")
                    _, ext = os.path.splitext(filename)
                    filetypes_config = [(f"Oryginalny format ({ext})", f"*{ext}")] if ext else [
                        ("Wszystkie pliki", "*.*")]
                    save_path = filedialog.asksaveasfilename(initialfile=filename, title="Zapisz pobrany plik jako...",
                                                             defaultextension=ext, filetypes=filetypes_config)
                    if save_path:
                        if ext and not save_path.lower().endswith(ext.lower()): save_path += ext
                        try:
                            with open(save_path, "wb") as f:
                                f.write(base64.b64decode(file_data))
                            messagebox.showinfo("Sukces", "Plik został pomyślnie zapisany!")
                        except Exception as e:
                            messagebox.showerror("Błąd", f"Nie udało się zapisać: {e}")

                elif action == "user_list":
                    self.cached_all_users = message.get("all_users", [])
                    self.cached_online_users = message.get("online_users", [])
                    self.refresh_ui()

                elif action == "your_groups":
                    self.cached_groups = message.get("groups", [])
                    self.refresh_ui()

                elif action == "group_info":
                    group = message.get("group")
                    if self.current_chat == group:
                        self.current_group_members = message.get("members", [])
                        self.current_group_creator = message.get("creator")
                        self.refresh_ui()

                elif action == "kicked_from_group":
                    group = message.get("group")
                    messagebox.showwarning("Wyrzucono z grupy",
                                           f"Zostałeś wyrzucony z grupy {group} przez właściciela.")
                    if self.current_chat == group: self.switch_chat("Globalny")

                elif action == "group_deleted":
                    group = message.get("group")
                    messagebox.showinfo("Grupa usunięta", f"Właściciel usunął grupę {group}.")
                    if self.current_chat == group: self.switch_chat("Globalny")

                elif action == "chat_history":
                    history_list = message.get("history", [])
                    for msg in history_list:
                        sender = msg.get("sender")
                        content = self.decrypt_msg(msg.get("content", ""))
                        time_str = msg.get("timestamp", "")
                        self.append_to_history("Globalny", f"[{time_str}] [{sender}]: {content}")

                elif action == "private_history":
                    history_list = message.get("history", [])
                    for msg in history_list:
                        sender = msg.get("sender")
                        recipient = msg.get("recipient")
                        content = self.decrypt_msg(msg.get("content", ""))
                        time_str = msg.get("timestamp", "")
                        chat_partner = recipient if sender == self.username else sender
                        prefix = "Ty" if sender == self.username else sender
                        self.append_to_history(chat_partner, f"[{time_str}] [{prefix}]: {content}")

                elif action == "group_history":
                    group = message.get("group")
                    history_list = message.get("history", [])
                    for msg in history_list:
                        sender = msg.get("sender")
                        content = self.decrypt_msg(msg.get("content", ""))
                        time_str = msg.get("timestamp", "")
                        prefix = "Ty" if sender == self.username else sender
                        self.append_to_history(group, f"[{time_str}] [{prefix}]: {content}")

                elif action == "join_request_received":
                    self.root.after(0, self.handle_join_request, message.get("group"), message.get("user"))

                elif action == "invite_received":
                    self.root.after(0, self.handle_invite, message.get("group"), message.get("admin", "Właściciela"))

                elif action == "pending_requests":
                    invites = message.get("invites", [])
                    join_reqs = message.get("join_reqs", [])
                    for inv in invites: self.root.after(0, self.handle_invite, inv, "Właściciela")
                    for req in join_reqs: self.root.after(0, self.handle_join_request, req['group'], req['user'])

                elif "status" in message:
                    if message["status"] == "error":
                        self.root.after(0, lambda m=message["message"]: messagebox.showerror("Informacja", m))
                    elif message["status"] == "success" and (
                            "Utworzono" in message["message"] or "Dołączono" in message["message"] or "Opuszczono" in
                            message["message"] or "Dodano" in message["message"] or "Zaakceptowano" in message[
                                "message"] or "Wyrzucono" in message["message"]):
                        self.root.after(0, lambda m=message["message"]: messagebox.showinfo("Sukces", m))

        except Exception as e:
            print(f"Błąd odbierania (klient): {e}")

    def run(self):
        self.root.mainloop()


if __name__ == "__main__":
    app = ChatClient()
    app.run()
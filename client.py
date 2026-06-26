import customtkinter as ctk
import os
import base64
import re
import requests
import webbrowser
import threading
from PIL import Image, ImageDraw, ImageFont
import colorsys
from tkinter import messagebox, filedialog
from datetime import datetime

from config import (
    C_BG_LEFT,
    C_BG_MID,
    C_BG_RIGHT,
    C_CHAT_BOX,
    C_INPUT_BG,
    C_PRIMARY,
    C_PRIMARY_HOVER,
    C_TEXT_MAIN,
    C_TEXT_MUTED,
    C_HOVER,
    C_ONLINE,
    C_NOTIFICATION_BG,
    EMOTES_DB,
)
from network import NetworkManager

try:
    from plyer import notification
except ImportError:
    notification = None

ctk.set_appearance_mode("dark")


class ChatClient:
    def __init__(self):
        self.root = ctk.CTk()
        self.root.title("Czatroom - Konfiguracja")
        self.root.geometry("450x500")
        self.root.resizable(False, False)

        self.username = None
        self.server_ip = "127.0.0.1"
        self.server_port = 9999
        self.current_chat = "Globalny"
        self.chat_histories = {"Globalny": ""}
        self.unread_counts = {}
        self.user_public_keys = {}

        self.cached_all_users = []
        self.cached_online_users = []
        self.cached_groups = []
        self.current_group_members = []
        self.current_group_creator = None

        self.last_typing_time = 0
        self.typing_timer = None
        self.last_rendered_sender = None
        self.loaded_emotes = {}
        self.emote_panel = None
        self.emote_panel_visible = False
        self.image_labels = {}

        # Inicjalizacja menedżera sieciowego
        self.net = NetworkManager(
            on_message_callback=self.handle_server_message,
            on_disconnect_callback=self.handle_disconnect
        )

        # Wczytanie ikon
        self.icon_globe = self.load_icon("globe.png")
        self.icon_add = self.load_icon("ADD.png")
        self.icon_join = self.load_icon("join.png")
        self.icon_logout = self.load_icon("logout.png")
        self.icon_attach = self.load_icon("attach.png", size=(22, 22))
        self.icon_mood = self.load_icon("mood.png", size=(22, 22))
        self.icon_delete = self.load_icon("delete.png")

        threading.Thread(target=self.preload_emotes, daemon=True).start()
        self.build_connect_screen()

    def load_icon(self, filename, size=(20, 20)):
        try:
            import sys
            if hasattr(sys, '_MEIPASS'):
                base_dir = sys._MEIPASS
            elif getattr(sys, 'frozen', False):
                base_dir = os.path.dirname(sys.executable)
            else:
                base_dir = os.path.dirname(os.path.abspath(__file__))
            img = Image.open(os.path.join(base_dir, "icons", filename))
            return ctk.CTkImage(light_image=img, dark_image=img, size=size)
        except Exception:
            return None

    def preload_emotes(self):
        for code, url in EMOTES_DB.items():
            name = code.strip(":")
            filepath = os.path.join("Cache_Emotki", f"{name}.png")
            if not os.path.exists(filepath):
                try:
                    response = requests.get(url, timeout=3)
                    if response.status_code == 200:
                        with open(filepath, "wb") as f:
                            f.write(response.content)
                except Exception:
                    pass

    def get_emote_image(self, emote_code):
        if emote_code not in EMOTES_DB:
            return None
        if emote_code in self.loaded_emotes:
            return self.loaded_emotes[emote_code]

        filepath = os.path.join("Cache_Emotki", f"{emote_code.strip(':')}.png")
        if not os.path.exists(filepath):
            return None
        try:
            img = ctk.CTkImage(Image.open(filepath), size=(24, 24))
            self.loaded_emotes[emote_code] = img
            return img
        except Exception:
            return None

    # --- UI: Widoki logowania i połączenia ---

    def build_connect_screen(self):
        self.frame = ctk.CTkFrame(master=self.root, corner_radius=15, fg_color=C_CHAT_BOX)
        self.frame.pack(pady=40, padx=50, fill="both", expand=True)

        ctk.CTkLabel(master=self.frame, text="Serwer", font=("Roboto", 24, "bold"), text_color="white").pack(
            pady=(40, 30))

        self.entry_ip = ctk.CTkEntry(master=self.frame, placeholder_text="Adres IP", width=280, height=40,
                                     fg_color=C_INPUT_BG, border_width=0)
        self.entry_ip.insert(0, "127.0.0.1")
        self.entry_ip.pack(pady=10)

        self.entry_port = ctk.CTkEntry(master=self.frame, placeholder_text="Port", width=280, height=40,
                                       fg_color=C_INPUT_BG, border_width=0)
        self.entry_port.insert(0, "9999")
        self.entry_port.pack(pady=10)

        self.entry_ip.bind("<Return>", lambda event: self.try_connect())
        self.entry_port.bind("<Return>", lambda event: self.try_connect())

        self.btn_connect = ctk.CTkButton(master=self.frame, text="Połącz", width=280, height=40, fg_color=C_PRIMARY,
                                         hover_color=C_PRIMARY_HOVER, command=self.try_connect)
        self.btn_connect.pack(pady=30)

    def try_connect(self):
        ip = self.entry_ip.get().strip()
        port_str = self.entry_port.get().strip()
        if not ip or not port_str.isdigit():
            messagebox.showerror("Błąd", "Podaj prawidłowy adres IP i port.")
            return

        self.server_ip = ip
        self.server_port = int(port_str)

        if self.connect_to_server():
            self.frame.destroy()
            self.build_login_screen()

    def connect_to_server(self):
        if not self.net.client_socket:
            if not self.net.connect(self.server_ip, self.server_port):
                messagebox.showerror("Błąd", f"Nie można połączyć z serwerem:\n{self.server_ip}:{self.server_port}")
                return False
        return True

    def build_login_screen(self):
        self.root.title("Czatroom - Logowanie")
        self.frame = ctk.CTkFrame(master=self.root, corner_radius=15, fg_color=C_CHAT_BOX)
        self.frame.pack(pady=40, padx=50, fill="both", expand=True)

        ctk.CTkLabel(master=self.frame, text="Zaloguj się", font=("Roboto", 24, "bold"), text_color="white").pack(
            pady=(40, 30))

        self.entry_username = ctk.CTkEntry(master=self.frame, placeholder_text="Login", width=280, height=40,
                                           fg_color=C_INPUT_BG, border_width=0)
        self.entry_username.pack(pady=10)

        self.entry_password = ctk.CTkEntry(master=self.frame, placeholder_text="Hasło", width=280, height=40,
                                           fg_color=C_INPUT_BG, border_width=0, show="*")
        self.entry_password.pack(pady=10)

        self.entry_username.bind("<Return>", lambda event: self.login())
        self.entry_password.bind("<Return>", lambda event: self.login())

        self.btn_login = ctk.CTkButton(master=self.frame, text="Zaloguj", width=280, height=40, fg_color=C_PRIMARY,
                                       hover_color=C_PRIMARY_HOVER, command=self.login)
        self.btn_login.pack(pady=(20, 10))

        self.btn_register = ctk.CTkButton(master=self.frame, text="Zarejestruj", width=280, height=40,
                                          fg_color="transparent", hover_color=C_HOVER, command=self.register)
        self.btn_register.pack(pady=5)

    def send_auth_request(self, action):
        username = self.entry_username.get().strip()
        password = self.entry_password.get().strip()
        if not username or not password:
            messagebox.showwarning("Uwaga", "Wprowadź nazwę użytkownika i hasło.")
            return

        if not self.connect_to_server():
            return

        response = self.net.auth_request(action, username, password)

        if response['status'] == 'success':
            if action == 'login':
                self.username = username
                self.net.load_or_generate_keys(username)
                self.net.send({"action": "update_public_key", "public_key": self.net.public_key_pem})
                self.open_chat_window()
            else:
                messagebox.showinfo("Sukces", response['message'])
        else:
            messagebox.showerror("Błąd", response['message'])

    def login(self):
        self.send_auth_request("login")

    def register(self):
        self.send_auth_request("register")

    # --- UI: Główny interfejs aplikacji  ---

    def open_chat_window(self):
        self.frame.destroy()
        self.root.geometry("1200x750")
        self.root.title(f"Czatroom - {self.username}")
        self.root.resizable(True, True)

        self.main_container = ctk.CTkFrame(self.root, fg_color=C_BG_MID, corner_radius=0)
        self.main_container.pack(fill="both", expand=True)
        self.main_container.grid_columnconfigure(1, weight=1)
        self.main_container.grid_rowconfigure(0, weight=1)

        # 1. LEWY PANEL
        self.sidebar = ctk.CTkFrame(self.main_container, width=250, corner_radius=0, fg_color=C_BG_LEFT)
        self.sidebar.grid(row=0, column=0, sticky="nsew")
        self.sidebar.grid_rowconfigure(5, weight=1)
        self.sidebar.grid_columnconfigure(0, weight=1)

        self.app_title = ctk.CTkLabel(self.sidebar, text="Czatroom", font=("Roboto", 20, "bold"), text_color="white",
                                      anchor="w")
        self.app_title.grid(row=0, column=0, padx=20, pady=(20, 0), sticky="ew")

        self.app_subtitle = ctk.CTkLabel(self.sidebar, text=f"{self.username} - Zabezpieczono", font=("Roboto", 11),
                                         text_color=C_TEXT_MUTED, anchor="w")
        self.app_subtitle.grid(row=1, column=0, padx=20, pady=(0, 20), sticky="ew")

        self.btn_global_chat = ctk.CTkButton(self.sidebar, text=" Czat Globalny", image=self.icon_globe, anchor="w",
                                             fg_color=C_PRIMARY, hover_color=C_PRIMARY_HOVER, height=40,
                                             font=("Roboto", 13, "bold"), command=lambda: self.switch_chat("Globalny"))
        self.btn_global_chat.grid(row=2, column=0, padx=15, pady=(0, 10), sticky="ew")

        self.btn_new_group = ctk.CTkButton(self.sidebar, text=" Utwórz grupę", image=self.icon_add, anchor="w",
                                           fg_color="transparent", text_color=C_TEXT_MAIN, hover_color=C_HOVER,
                                           height=35, command=self.ui_create_group)
        self.btn_new_group.grid(row=3, column=0, padx=15, pady=2, sticky="ew")

        self.btn_join_group = ctk.CTkButton(self.sidebar, text=" Dołącz do grupy", image=self.icon_join, anchor="w",
                                            fg_color="transparent", text_color=C_TEXT_MAIN, hover_color=C_HOVER,
                                            height=35, command=self.ui_join_group)
        self.btn_join_group.grid(row=4, column=0, padx=15, pady=2, sticky="ew")

        self.groups_wrapper = ctk.CTkFrame(self.sidebar, fg_color="transparent")
        self.groups_wrapper.grid(row=5, column=0, sticky="nsew", pady=(15, 0))
        self.groups_wrapper.grid_rowconfigure(1, weight=1)
        self.groups_wrapper.grid_columnconfigure(0, weight=1)

        self.lbl_groups = ctk.CTkLabel(self.groups_wrapper, text="📁 TWOJE GRUPY", font=("Roboto", 11, "bold"),
                                       text_color=C_TEXT_MUTED, anchor="w")
        self.lbl_groups.grid(row=0, column=0, padx=20, pady=(0, 5), sticky="ew")

        self.groups_scrollable = ctk.CTkScrollableFrame(self.groups_wrapper, fg_color="transparent")
        self.groups_scrollable.grid(row=1, column=0, padx=5, sticky="nsew")

        self.bottom_sidebar = ctk.CTkFrame(self.sidebar, fg_color="transparent")
        self.bottom_sidebar.grid(row=6, column=0, padx=15, pady=20, sticky="ew")

        self.btn_leave_group = ctk.CTkButton(self.bottom_sidebar, text=" Opuść obecną grupę", image=self.icon_logout,
                                             anchor="w", fg_color="transparent", text_color="#F23F42",
                                             hover_color=C_HOVER, command=self.ui_leave_group)
        self.btn_leave_group.pack(fill="x", pady=2)

        # 2. ŚRODKOWY PANEL
        self.chat_area = ctk.CTkFrame(self.main_container, fg_color=C_BG_MID, corner_radius=0)
        self.chat_area.grid(row=0, column=1, sticky="nsew")
        self.chat_area.grid_rowconfigure(1, weight=1)
        self.chat_area.grid_columnconfigure(0, weight=1)

        self.header = ctk.CTkFrame(self.chat_area, fg_color="transparent", height=60, corner_radius=0)
        self.header.grid(row=0, column=0, sticky="ew", padx=20, pady=10)

        self.lbl_current_chat = ctk.CTkLabel(self.header, text="# Rozmowa: Globalny", font=("Roboto", 18, "bold"),
                                             text_color="white", anchor="w")
        self.lbl_current_chat.pack(side="left")

        self.text_area = ctk.CTkTextbox(self.chat_area, fg_color=C_CHAT_BOX, text_color=C_TEXT_MAIN,
                                        font=("Consolas", 14), corner_radius=8, border_spacing=15)
        self.text_area.grid(row=1, column=0, sticky="nsew", padx=20, pady=(0, 10))

        self.text_area.tag_config("time", foreground="#949BA4")
        self.text_area.tag_config("system", foreground=C_TEXT_MUTED, justify="center")
        self.text_area.tag_config("highlight", background=C_CHAT_BOX)
        self.text_area.tag_config("link", foreground="#5865F2", underline=True)
        self.text_area.tag_bind("link", "<Enter>", lambda _: self.text_area.configure(cursor="hand2"))
        self.text_area.tag_bind("link", "<Leave>", lambda _: self.text_area.configure(cursor=""))
        self.text_area.tag_bind("link", "<Button-1>", self.click_link)

        # Znaczniki formatowania Markdown
        self.text_area._textbox.tag_config("bold", font=("Consolas", 14, "bold"))
        self.text_area._textbox.tag_config("italic", font=("Consolas", 14, "italic"))
        self.text_area._textbox.tag_config("strikethrough", overstrike=True)
        self.text_area._textbox.tag_config("code_inline", font=("Consolas", 13), background="#1E1F22", foreground="#E06C75")

        self.input_area = ctk.CTkFrame(self.chat_area, fg_color="transparent")
        self.input_area.grid(row=2, column=0, sticky="ew", padx=20, pady=(0, 20))

        self.lbl_typing = ctk.CTkLabel(self.input_area, text="", font=("Roboto", 11, "italic"), text_color=C_TEXT_MUTED,
                                       height=15)
        self.lbl_typing.pack(anchor="w", padx=10, pady=(0, 2))

        self.entry_frame = ctk.CTkFrame(self.input_area, fg_color=C_INPUT_BG, corner_radius=8, height=48)
        self.entry_frame.pack(fill="x", expand=True)

        self.btn_attach = ctk.CTkButton(self.entry_frame, text="", image=self.icon_attach, width=40, height=40,
                                        fg_color="transparent", hover_color=C_HOVER, command=self.send_file)
        self.btn_attach.pack(side="left", padx=(5, 0), pady=4)

        self.btn_emotes = ctk.CTkButton(self.entry_frame, text="", image=self.icon_mood, width=40, height=40,
                                        fg_color="transparent", hover_color=C_HOVER, command=self.toggle_emote_panel)
        self.btn_emotes.pack(side="left", padx=0, pady=4)

        self.entry_message = ctk.CTkTextbox(self.entry_frame, fg_color="transparent", text_color=C_TEXT_MAIN, height=40,
                                            wrap="word", font=("Consolas", 14), border_spacing=5)
        self.entry_message.pack(side="left", fill="x", expand=True, padx=5, pady=4)

        self.entry_message.bind("<KeyRelease>", self.auto_resize_input)
        self.entry_message.bind("<Return>", self.handle_return)

        # 3. PRAWY PANEL
        self.right_sidebar = ctk.CTkFrame(self.main_container, width=250, corner_radius=0, fg_color=C_BG_RIGHT)
        self.right_sidebar.grid(row=0, column=2, sticky="ns")
        self.right_sidebar.grid_columnconfigure(0, weight=1)

        self.lbl_right_title = ctk.CTkLabel(self.right_sidebar, text="👥 Wszyscy Użytkownicy",
                                            font=("Roboto", 13, "bold"), text_color="white", anchor="w")
        self.lbl_right_title.grid(row=0, column=0, padx=20, pady=(20, 2), sticky="ew")

        self.lbl_online_count = ctk.CTkLabel(self.right_sidebar, text="Online", font=("Roboto", 11),
                                             text_color=C_TEXT_MUTED, anchor="w")
        self.lbl_online_count.grid(row=1, column=0, padx=20, pady=(0, 10), sticky="ew")

        self.btn_delete_group = ctk.CTkButton(self.right_sidebar, text=" Usuń Grupę", image=self.icon_delete,
                                              fg_color="#DA373C", hover_color="#A1282D", height=35,
                                              command=self.delete_current_group)

        self.users_scrollable = ctk.CTkScrollableFrame(self.right_sidebar, fg_color="transparent")
        self.users_scrollable.grid(row=2, column=0, sticky="nsew", padx=10)
        self.right_sidebar.grid_rowconfigure(2, weight=1)

        self.notification_frame = ctk.CTkFrame(self.root, fg_color=C_NOTIFICATION_BG, border_width=2,
                                               border_color=C_PRIMARY, corner_radius=10)
        self.notification_label = ctk.CTkLabel(self.notification_frame, text="", font=("Roboto", 13), wraplength=200)
        self.notification_label.pack(padx=20, pady=15)

        self.net.start_listening()

    def handle_disconnect(self):
        self.root.after(0, lambda: messagebox.showerror("Błąd krytyczny", "Utracono połączenie z serwerem."))

    # --- UI: Metody pomocnicze interfejsu ---

    def toggle_emote_panel(self):
        if self.emote_panel is None:
            self.emote_panel = ctk.CTkScrollableFrame(master=self.chat_area, height=60, orientation="horizontal",
                                                      fg_color=C_INPUT_BG, corner_radius=10)
        if self.emote_panel_visible:
            self.emote_panel.grid_forget()
            self.emote_panel_visible = False
        else:
            self.emote_panel.grid(row=3, column=0, sticky="ew", padx=20, pady=(0, 10))
            self.emote_panel_visible = True
            self.populate_emote_panel()

    def populate_emote_panel(self):
        for widget in self.emote_panel.winfo_children():
            widget.destroy()
        for code in EMOTES_DB.keys():
            img = self.get_emote_image(code)
            if img:
                btn = ctk.CTkButton(self.emote_panel, text="", image=img, width=40, height=40, fg_color="transparent",
                                    hover_color=C_HOVER, command=lambda c=code: self.insert_emote_code(c))
                btn.pack(side="left", padx=5)
            else:
                btn = ctk.CTkButton(self.emote_panel, text=code, width=50, height=40,
                                    command=lambda c=code: self.insert_emote_code(c))
                btn.pack(side="left", padx=5)

    def insert_emote_code(self, code):
        self.entry_message.insert("end", code + " ")
        self.entry_message.focus()

    def show_typing_indicator(self, sender):
        self.lbl_typing.configure(text=f"{sender} pisze...")
        if self.typing_timer:
            self.root.after_cancel(self.typing_timer)
        self.typing_timer = self.root.after(3000, self.clear_typing_indicator)

    def clear_typing_indicator(self):
        self.lbl_typing.configure(text="")

    def refresh_ui(self):
        def refresh():
            unread_gl = self.unread_counts.get("Globalny", 0)
            self.btn_global_chat.configure(text_color="white" if unread_gl > 0 else C_TEXT_MAIN,
                                           text=f" Czat Globalny ({unread_gl})" if unread_gl > 0 else " Czat Globalny")

            for widget in self.groups_scrollable.winfo_children():
                widget.destroy()
            private_chats = [c for c in self.chat_histories.keys() if c != "Globalny" and not c.startswith("#")]

            for group in self.cached_groups:
                unread = self.unread_counts.get(group, 0)
                g_color = "white" if unread > 0 else C_TEXT_MUTED
                lbl = ctk.CTkLabel(master=self.groups_scrollable,
                                   text=f"#  {group.replace('#', '')} ({unread})" if unread > 0 else f"#  {group.replace('#', '')}",
                                   font=("Roboto", 14), text_color=g_color, cursor="hand2", anchor="w")
                lbl.bind("<Button-1>", lambda event, g=group: self.switch_chat(g))
                lbl.pack(fill="x", pady=2, padx=10)

            for priv in private_chats:
                unread = self.unread_counts.get(priv, 0)
                p_color = "white" if unread > 0 else C_TEXT_MUTED
                lbl = ctk.CTkLabel(master=self.groups_scrollable,
                                   text=f"👤 {priv} ({unread})" if unread > 0 else f"👤 {priv}", font=("Roboto", 14),
                                   text_color=p_color, cursor="hand2", anchor="w")
                lbl.bind("<Button-1>", lambda event, p=priv: self.switch_chat(p))
                lbl.pack(fill="x", pady=2, padx=10)

            for widget in self.users_scrollable.winfo_children():
                widget.destroy()

            if self.current_chat.startswith("#"):
                self.lbl_right_title.configure(text="Członkowie Grupy")
                self.lbl_online_count.configure(text=f"Łącznie: {len(self.current_group_members)}")
                if self.username == self.current_group_creator:
                    ctk.CTkButton(master=self.users_scrollable, text=" Zaproś osobę", image=self.icon_add,
                                  fg_color=C_PRIMARY, hover_color=C_PRIMARY_HOVER,
                                  command=self.ui_invite_to_group).pack(pady=(0, 5), padx=10, fill="x")
                    ctk.CTkButton(master=self.users_scrollable, text=" Wyrzuć osobę", image=self.icon_delete,
                                  fg_color="#DA373C", hover_color="#A1282D", command=self.ui_kick_from_group).pack(
                        pady=(0, 10), padx=10, fill="x")
                    self.btn_delete_group.grid(row=3, column=0, pady=(10, 20), padx=15, sticky="ew")
                else:
                    self.btn_delete_group.grid_forget()

                for user in self.current_group_members:
                    avatar_img = self.get_user_avatar(user)
                    if user == self.username:
                        ctk.CTkLabel(master=self.users_scrollable, text=f" 🟢 {self.username} (Ty)",
                                     image=avatar_img, compound="left",
                                     font=("Roboto", 13, "bold"), text_color="white", anchor="w").pack(fill="x", pady=4,
                                                                                                       padx=5)
                    else:
                        status = "🟢" if user in self.cached_online_users else "⚪"
                        lbl = ctk.CTkLabel(master=self.users_scrollable, text=f" {status} {user}",
                                           image=avatar_img, compound="left", font=("Roboto", 13),
                                           text_color=C_TEXT_MUTED, cursor="hand2", anchor="w")
                        lbl.bind("<Button-1>", lambda event, u=user: self.switch_chat(u))
                        lbl.pack(fill="x", pady=4, padx=5)
            else:
                self.lbl_right_title.configure(text="👥 Wszyscy Użytkownicy")
                self.lbl_online_count.configure(text=f"Online - {len(self.cached_online_users)}")
                self.btn_delete_group.grid_forget()

                avatar_me = self.get_user_avatar(self.username)
                ctk.CTkLabel(master=self.users_scrollable, text=f" 🟢 {self.username} (Ty)",
                             image=avatar_me, compound="left", font=("Roboto", 13, "bold"),
                             text_color="white", anchor="w").pack(fill="x", pady=4, padx=5)

                for user in self.cached_all_users:
                    if user == self.username:
                        continue
                    status = "🟢" if user in self.cached_online_users else "⚪"
                    unread = self.unread_counts.get(user, 0)
                    u_color = "white" if unread > 0 else C_TEXT_MUTED
                    display_text = f" {status} {user} ({unread})" if unread > 0 else f" {status} {user}"

                    avatar_img = self.get_user_avatar(user)
                    lbl = ctk.CTkLabel(master=self.users_scrollable, text=display_text,
                                       image=avatar_img, compound="left",
                                       font=("Roboto", 13, "bold" if unread > 0 else "normal"), text_color=u_color,
                                       cursor="hand2", anchor="w")
                    lbl.bind("<Button-1>", lambda event, u=user: self.switch_chat(u))
                    lbl.pack(fill="x", pady=4, padx=5)

        self.root.after(0, refresh)

    # --- UI: Metody zarządzania grupami dyskusyjnymi ---

    def handle_join_request(self, group, user):
        ans = messagebox.askyesno("Prośba o dołączenie",
                                  f"'{user}' prosi o dołączenie do '{group}'.\n\nCzy akceptujesz?")
        self.net.send({"action": "resolve_join", "group": group, "user": user, "accept": ans})

    def handle_invite(self, group, admin_name):
        ans = messagebox.askyesno("Zaproszenie do grupy",
                                  f"Otrzymałeś zaproszenie do '{group}' od {admin_name}.\n\nCzy chcesz dołączyć?")
        self.net.send({"action": "resolve_invite", "group": group, "accept": ans})

    def ui_invite_to_group(self):
        user_to_add = ctk.CTkInputDialog(text="Wpisz nick osoby, którą chcesz dodać:",
                                         title="Dodaj do grupy").get_input()
        if user_to_add and user_to_add.strip():
            self.net.send({"action": "add_user_to_group", "group": self.current_chat, "user": user_to_add.strip()})

    def ui_kick_from_group(self):
        user_to_kick = ctk.CTkInputDialog(text="Wpisz nick osoby:", title="Wyrzuć użytkownika").get_input()
        if user_to_kick and user_to_kick.strip():
            if user_to_kick.strip() == self.username:
                messagebox.showwarning("Uwaga", "Żeby opuścić grupę, użyj przycisku 'Opuść obecną grupę'.")
                return
            self.net.send({"action": "kick_user", "group": self.current_chat, "user": user_to_kick.strip()})

    def ui_create_group(self):
        name = ctk.CTkInputDialog(text="Wpisz nazwę nowej grupy:", title="Nowa Grupa").get_input()
        if name and name.strip():
            formatted_name = "#" + name.strip().replace(" ", "_").replace("#", "")
            self.net.send({"action": "create_group", "name": formatted_name})

    def ui_join_group(self):
        name = ctk.CTkInputDialog(text="Wpisz nazwę grupy:", title="Dołącz do Grupy").get_input()
        if name and name.strip():
            formatted_name = "#" + name.strip().replace(" ", "_").replace("#", "")
            self.net.send({"action": "join_group", "name": formatted_name})

    def ui_leave_group(self):
        if self.current_chat.startswith("#"):
            if messagebox.askyesno("Opuść grupę", f"Czy na pewno chcesz opuścić {self.current_chat}?"):
                self.net.send({"action": "leave_group", "name": self.current_chat})
                self.switch_chat("Globalny")
        else:
            messagebox.showinfo("Informacja", "Aby opuścić grupę, najpierw wejdź w nią.")

    def delete_current_group(self):
        if messagebox.askyesno("Usuń grupę", f"UWAGA! Usunąć {self.current_chat}? Tej akcji nie można cofnąć!"):
            self.net.send({"action": "delete_group", "group": self.current_chat})

    # ---  formatowanie wiadomości i renderowanie tekstu ---

    def switch_chat(self, chat_name):
        self.current_chat = chat_name
        self.lbl_current_chat.configure(
            text=f"{'# ' if chat_name.startswith('#') else ''}Rozmowa: {chat_name.replace('#', '')}")
        self.clear_typing_indicator()

        if self.emote_panel_visible:
            self.toggle_emote_panel()
        if chat_name in self.unread_counts:
            self.unread_counts[chat_name] = 0

        if chat_name.startswith("#"):
            self.net.send({"action": "get_group_info", "group": chat_name})
        else:
            self.refresh_ui()

        self.text_area.configure(state="normal")
        self.text_area.delete("1.0", "end")
        self.last_rendered_sender = None

        history_text = self.chat_histories.get(chat_name, "")
        for line in history_text.split("\n"):
            if line:
                self.insert_line_with_buttons(line)

        self.text_area.configure(state="disabled")
        self.text_area.see("end")

    def _insert_text_with_emotes(self, text, tag=None):
        self._insert_markdown_text(text, tag)

    def _insert_markdown_text(self, text, tag=None):
        """pogrubienie (**bold** / *bold*), kursywa (_italic_),
        przekreślenie (~strikethrough~) oraz kodu w linii (`code`)."""
        pattern = r'(`[^`\n]+`|\*\*[^*]+?\*\*|\*[^*]+?\*|_[^_]+?_|~[^~]+?~)'
        parts = re.split(pattern, text)
        
        for part in parts:
            if part.startswith('`') and part.endswith('`'):
                self.text_area.insert("end", part[1:-1], "code_inline")
            elif part.startswith('**') and part.endswith('**'):
                self.text_area.insert("end", part[2:-2], "bold")
            elif part.startswith('*') and part.endswith('*'):
                self.text_area.insert("end", part[1:-1], "bold")
            elif part.startswith('_') and part.endswith('_'):
                self.text_area.insert("end", part[1:-1], "italic")
            elif part.startswith('~') and part.endswith('~'):
                self.text_area.insert("end", part[1:-1], "strikethrough")
            else:
                self._insert_text_with_emotes_raw(part, tag)

    def _insert_text_with_emotes_raw(self, text, tag=None):
        url_pattern = r'(https?://[^\s]+)'
        parts = re.split(r'(:[a-zA-Z0-9_]+:)', text)

        for part in parts:
            if part in EMOTES_DB:
                img = self.get_emote_image(part)
                if img:
                    lbl = ctk.CTkLabel(self.text_area._textbox, text="", image=img, bg_color=C_CHAT_BOX)
                    self.text_area._textbox.window_create("end", window=lbl)
                else:
                    self.text_area.insert("end", part, tag) if tag else self.text_area.insert("end", part)
            else:
                sub_parts = re.split(url_pattern, part)
                for sub_part in sub_parts:
                    if re.match(url_pattern, sub_part):
                        self.text_area.insert("end", sub_part, "link")
                    else:
                        self.text_area.insert("end", sub_part, tag) if tag else self.text_area.insert("end", sub_part)

    def _render_text_segment_with_files(self, segment):
        match = re.search(r'\[FILE:(.*?):(.*?)\]', segment)
        if match:
            file_id = match.group(1)
            filename = match.group(2)
            before_text = segment[:match.start()]
            after_text = segment[match.end():]

            if before_text:
                self._insert_text_with_emotes(before_text)

            is_image = filename.lower().endswith(('.png', '.jpg', '.jpeg', '.gif', '.webp'))

            if is_image:
                cache_path = os.path.join("Cache_Obrazki", filename)
                if os.path.exists(cache_path):
                    img = self.load_preview_image(cache_path)
                    if img:
                        lbl = ctk.CTkLabel(self.text_area._textbox, text="", image=img, cursor="hand2")
                        lbl.bind("<Button-1>", lambda e, p=cache_path: Image.open(p).show())
                        self.text_area._textbox.window_create("end", window=lbl)
                    else:
                        self.text_area.insert("end", f"[Uszkodzony obraz: {filename}]")
                else:
                    lbl = ctk.CTkLabel(self.text_area._textbox, text="🖼️ Ładowanie...", fg_color=C_INPUT_BG,
                                       corner_radius=8, padx=10, pady=5)
                    self.text_area._textbox.window_create("end", window=lbl)
                    if not hasattr(self, 'image_labels'):
                        self.image_labels = {}
                    if filename not in self.image_labels:
                        self.image_labels[filename] = []
                    self.image_labels[filename].append(lbl)

                    self.request_download(file_id, filename)
            else:
                btn = ctk.CTkButton(self.text_area._textbox, text=f"📄 {filename}", height=28, fg_color=C_PRIMARY,
                                    hover_color=C_PRIMARY_HOVER, cursor="hand2",
                                    command=lambda f_id=file_id, f_name=filename: self.request_download(f_id, f_name))
                self.text_area._textbox.window_create("end", window=btn)

            if after_text:
                self._insert_text_with_emotes(after_text)
        else:
            self._insert_text_with_emotes(segment)

    def insert_line_with_buttons(self, line):
        prefix_match = re.match(r'^(\[\d{2}:\d{2}\]) (.*?): (.*)$', line)

        if prefix_match:
            time_str = prefix_match.group(1)
            sender = prefix_match.group(2)
            rest_of_line = prefix_match.group(3)

            if sender == "SYSTEM":
                self.last_rendered_sender = None
                self.text_area.insert("end", f"\n— {rest_of_line} —\n\n", "system")
                return

            if sender == getattr(self, 'last_rendered_sender', None):
                indent_length = len(time_str) + 1 + len(sender) + 2 + 4
                self.text_area.insert("end", " " * indent_length)
            else:
                self.last_rendered_sender = sender
                tag_name = f"nick_{sender}"
                fallback_color = C_ONLINE if (
                            sender in self.cached_online_users or sender == self.username) else C_TEXT_MUTED
                
                self.text_area._textbox.tag_config(tag_name, foreground=fallback_color)
                if sender != self.username:
                    self.text_area._textbox.tag_bind(tag_name, "<Enter>", lambda event: self.text_area.configure(cursor="hand2"))
                    self.text_area._textbox.tag_bind(tag_name, "<Leave>", lambda event: self.text_area.configure(cursor=""))
                    self.text_area._textbox.tag_bind(tag_name, "<Button-1>", lambda event, s=sender: self.switch_chat(s))

                self.text_area.insert("end", time_str + " ", "time")
                
                avatar_img = self.get_user_avatar(sender)
                if avatar_img:
                    lbl = ctk.CTkLabel(self.text_area._textbox, text="", image=avatar_img, bg_color=C_CHAT_BOX)
                    if sender != self.username:
                        lbl.configure(cursor="hand2")
                        lbl.bind("<Button-1>", lambda event, s=sender: self.switch_chat(s))
                    self.text_area._textbox.window_create("end", window=lbl)
                    self.text_area.insert("end", " ")
                
                self.text_area.insert("end", sender + ": ", tag_name)
        else:
            self.last_rendered_sender = None
            rest_of_line = line

        code_parts = re.split(r'(```.*?```)', rest_of_line, flags=re.DOTALL)
        for part in code_parts:
            if part.startswith('```') and part.endswith('```'):
                code_content = part[3:-3].strip()
                lines = code_content.split('\n')
                if lines and re.match(r'^[a-zA-Z0-9+#-]+$', lines[0]):
                    code_content = '\n'.join(lines[1:])
                
                container = ctk.CTkFrame(self.text_area._textbox, fg_color="#1E1F22", corner_radius=6, border_color="#2B2D31", border_width=1)
                
                btn_copy = ctk.CTkButton(container, text="Kopiuj", width=50, height=20, font=("Consolas", 10), 
                                         fg_color="#2B2D31", hover_color="#3B3F45", text_color="#A9B1D6",
                                         command=lambda c=code_content: self.copy_to_clipboard(c))
                btn_copy.pack(anchor="ne", padx=10, pady=(5, 5))
                
                num_lines = len(code_content.split('\n'))
                
                import tkinter as tk
                code_box = tk.Text(container, bg="#1E1F22", fg="#ABB2BF", insertbackground="white",
                                   font=("Consolas", 11), bd=0, highlightthickness=0, wrap="word", height=min(num_lines, 12))
                code_box.insert("1.0", code_content)
                code_box.configure(state="disabled")
                code_box.pack(fill="both", expand=True, padx=10, pady=(0, 10))
                
                self.text_area._textbox.window_create("end", window=container)
                self.text_area.insert("end", "\n")
            else:
                self._render_text_segment_with_files(part)
        
        self.text_area.insert("end", "\n")

    def append_to_history(self, chat_name, text):
        if chat_name not in self.chat_histories:
            self.chat_histories[chat_name] = ""
        self.chat_histories[chat_name] += text + "\n"
        if chat_name != "Globalny" and not chat_name.startswith("#"):
            self.refresh_ui()
        if self.current_chat == chat_name:
            self.display_message(text)

    def display_message(self, text):
        self.text_area.configure(state="normal")
        start_idx = self.text_area.index("end-1c")
        self.insert_line_with_buttons(text)
        end_idx = self.text_area.index("end-1c")
        self.text_area.tag_add("highlight", start_idx, end_idx)
        self.text_area.configure(state="disabled")
        self.text_area.see("end")
        self.animate_highlight(start_color="#4E5058")

    # --- Metody obsługi wysyłania wiadomości i plików do 5 MB ---

    def send_file(self):
        filepath = filedialog.askopenfilename(title="Wybierz plik do wysłania")
        if not filepath:
            return
        if os.path.getsize(filepath) > 5 * 1024 * 1024:
            messagebox.showwarning("Za duży plik", "Maksymalny rozmiar to 5MB.")
            return

        filename = os.path.basename(filepath)
        file_id = f"{int(datetime.now().timestamp())}_{self.username}_{filename}"
        try:
            with open(filepath, "rb") as f:
                encoded_string = base64.b64encode(f.read()).decode('utf-8')
            self.net.send({"action": "send_file", "target": self.current_chat, "filename": filename, "file_id": file_id,
                           "data": encoded_string})
            now = datetime.now().strftime("%H:%M")
            self.append_to_history(self.current_chat, f"[{now}] {self.username}: [FILE:{file_id}:{filename}]")
        except Exception as e:
            messagebox.showerror("Błąd pliku", f"Nie udało się wysłać pliku: {e}")

    def auto_resize_input(self, event=None):
        text = self.entry_message.get("1.0", "end-1c")
        lines = text.count('\n') + 1
        self.entry_message.configure(height=min(max(40, lines * 20 + 20), 120))
        if event and event.keysym != "Return" and len(text.strip()) > 0:
            now = datetime.now().timestamp()
            if now - self.last_typing_time > 2:
                self.last_typing_time = now
                self.net.send({"action": "typing", "target": self.current_chat})

    def handle_return(self, event):
        if not event.state & 0x0001:
            self.send_message()
            return "break"

    def send_message(self):
        msg_text = self.entry_message.get("1.0", "end-1c").strip()
        if msg_text:
            now = datetime.now().strftime("%H:%M")
            if self.current_chat == "Globalny":
                encrypted_text = self.net.encrypt(msg_text)
                request = {"action": "broadcast_message", "content": encrypted_text}
            elif self.current_chat.startswith("#"):
                encrypted_text = self.net.encrypt(msg_text)
                request = {"action": "group_message", "group": self.current_chat, "content": encrypted_text}
            else:
                # E2EE
                recipient_pubkey = self.user_public_keys.get(self.current_chat)
                if recipient_pubkey:
                    encrypted_text = self.net.encrypt_e2ee(msg_text, recipient_pubkey)
                else:
                    encrypted_text = self.net.encrypt(msg_text)
                request = {"action": "private_message", "recipient": self.current_chat, "content": encrypted_text}

            self.append_to_history(self.current_chat, f"[{now}] {self.username}: {msg_text}")
            if self.emote_panel_visible:
                self.toggle_emote_panel()

            try:
                self.net.send(request)
                self.entry_message.delete("1.0", "end")
                self.auto_resize_input()
            except Exception as e:
                messagebox.showerror("Błąd", f"Nie udało się wysłać: {e}")

    def request_download(self, file_id, filename):
        self.net.send({"action": "download_request", "file_id": file_id, "filename": filename})

    def mark_unread(self, chat_name):
        if chat_name != self.current_chat:
            self.unread_counts[chat_name] = self.unread_counts.get(chat_name, 0) + 1
            self.refresh_ui()

    def show_notification(self, title, msg):
        if notification:
            threading.Thread(
                target=lambda: notification.notify(title=title, message=msg, app_name="Czatroom", timeout=5),
                daemon=True).start()

    # --- Obsługa komunikatów sieciowych serwera ---

    def handle_server_message(self, message):
        action = message.get("action")

        if action == "chat_message":
            sender = message.get("sender")
            content = self.net.decrypt(message.get("content", ""))
            time_str = message.get("timestamp", "")
            self.append_to_history("Globalny", f"[{time_str}] {sender}: {content}")
            if sender != self.username and sender != "SYSTEM":
                preview = content[:100] + "..." if len(content) > 100 else content
                if "[FILE:" in content:
                    preview = "Wysłano plik"
                self.show_notification(f"Czat Globalny ({sender})", preview)
                self.mark_unread("Globalny")
                self.play_notification_sound()
                self.root.after(0, self.clear_typing_indicator)

        elif action == "private_message":
            sender = message.get("sender")
            sender_pubkey = self.user_public_keys.get(sender)
            if sender_pubkey:
                content = self.net.decrypt_e2ee(message.get("content", ""), sender_pubkey)
            else:
                content = self.net.decrypt(message.get("content", ""))
            time_str = message.get("timestamp", "")
            self.append_to_history(sender, f"[{time_str}] {sender}: {content}")
            if sender != self.username:
                preview = content[:100] + "..." if len(content) > 100 else content
                if "[FILE:" in content:
                    preview = "Wysłano plik"
                self.show_notification(f"Wiadomość od: {sender}", preview)
                self.mark_unread(sender)
                self.play_notification_sound()
                self.root.after(0, self.clear_typing_indicator)

        elif action == "group_message":
            sender = message.get("sender")
            group = message.get("group")
            content = self.net.decrypt(message.get("content", ""))
            time_str = message.get("timestamp", "")
            self.append_to_history(group, f"[{time_str}] {sender}: {content}")
            if sender != self.username:
                preview = content[:100] + "..." if len(content) > 100 else content
                if "[FILE:" in content:
                    preview = "Wysłano plik"
                self.show_notification(f"Grupa {group} ({sender})", preview)
                self.mark_unread(group)
                self.play_notification_sound()
                self.root.after(0, self.clear_typing_indicator)

        elif action == "typing":
            sender, target = message.get("sender"), message.get("target")
            if (target == "Globalny" and self.current_chat == "Globalny") or \
                    (target.startswith("#") and self.current_chat == target) or \
                    (target == self.username and self.current_chat == sender):
                self.root.after(0, self.show_typing_indicator, sender)

        elif action == "receive_download":
            filename, file_data = message.get("filename"), message.get("data")
            if hasattr(self, 'image_labels') and filename in self.image_labels:
                cache_path = os.path.join("Cache_Obrazki", filename)
                try:
                    with open(cache_path, "wb") as f:
                        f.write(base64.b64decode(file_data))
                    img = self.load_preview_image(cache_path)
                    for lbl in self.image_labels[filename]:
                        self.root.after(0, lambda l=lbl, i=img, p=cache_path: self.update_image_label(l, i, p))
                except Exception as e:
                    print(f"Błąd obrazka: {e}")
                del self.image_labels[filename]
            else:
                _, ext = os.path.splitext(filename)
                filetypes_config = [(f"Oryginalny format ({ext})", f"*{ext}")] if ext else [("Wszystkie pliki", "*.*")]
                save_path = filedialog.asksaveasfilename(initialfile=filename, title="Zapisz jako...",
                                                         defaultextension=ext, filetypes=filetypes_config)
                if save_path:
                    if ext and not save_path.lower().endswith(ext.lower()):
                        save_path += ext
                    try:
                        with open(save_path, "wb") as f:
                            f.write(base64.b64decode(file_data))
                        self.root.after(0, lambda: self.show_toast("📄 Plik został zapisany pomyślnie!"))
                    except Exception as e:
                        messagebox.showerror("Błąd", f"Nie zapisanio: {e}")

        elif action == "user_list":
            self.cached_all_users = message.get("all_users", [])
            self.cached_online_users = message.get("online_users", [])
            self.user_public_keys = message.get("public_keys", {})
            self.refresh_ui()

        elif action == "your_groups":
            self.cached_groups = message.get("groups", [])
            self.refresh_ui()

        elif action == "group_info":
            if self.current_chat == message.get("group"):
                self.current_group_members = message.get("members", [])
                self.current_group_creator = message.get("creator")
                self.refresh_ui()

        elif action == "kicked_from_group":
            messagebox.showwarning("Wyrzucono z grupy",
                                   f"Zostałeś wyrzucony z grupy {message.get('group')} przez administratora.")
            if self.current_chat == message.get("group"):
                self.switch_chat("Globalny")

        elif action == "group_deleted":
            messagebox.showinfo("Grupa usunięta", f"Właściciel usunął grupę {message.get('group')}.")
            if self.current_chat == message.get("group"):
                self.switch_chat("Globalny")

        elif action == "chat_history":
            for msg in message.get("history", []):
                self.append_to_history("Globalny",
                                       f"[{msg.get('timestamp')}] {msg.get('sender')}: {self.net.decrypt(msg.get('content', ''))}")

        elif action == "private_history":
            for msg in message.get("history", []):
                sender, recipient = msg.get("sender"), msg.get("recipient")
                chat_partner = recipient if sender == self.username else sender
                partner_pubkey = self.user_public_keys.get(chat_partner)
                if partner_pubkey:
                    content = self.net.decrypt_e2ee(msg.get("content", ""), partner_pubkey)
                else:
                    content = self.net.decrypt(msg.get("content", ""))
                self.append_to_history(chat_partner,
                                       f"[{msg.get('timestamp')}] {sender}: {content}")

        elif action == "group_history":
            for msg in message.get("history", []):
                self.append_to_history(message.get("group"),
                                       f"[{msg.get('timestamp')}] {msg.get('sender')}: {self.net.decrypt(msg.get('content', ''))}")

        elif action == "join_request_received":
            self.root.after(0, self.handle_join_request, message.get("group"), message.get("user"))

        elif action == "invite_received":
            self.root.after(0, self.handle_invite, message.get("group"), message.get("admin", "Właściciela"))

        elif action == "pending_requests":
            for inv in message.get("invites", []):
                self.root.after(0, self.handle_invite, inv, "Właściciela")
            for req in message.get("join_reqs", []):
                self.root.after(0, self.handle_join_request, req['group'], req['user'])

        elif "status" in message:
            if message["status"] == "error":
                self.root.after(0, lambda m=message["message"]: messagebox.showerror("Błąd", m))
            elif message["status"] == "success":
                self.root.after(0, lambda m=message["message"]: self.show_toast(f"✅ {m}"))

    def show_toast(self, message, duration=4000):
        self.notification_label.configure(text=message)
        self.notification_frame.place(relx=0.98, rely=0.95, anchor="se")
        self.root.after(duration, self.notification_frame.place_forget)

    def click_link(self, event):
        idx = self.text_area._textbox.index(f"@{event.x},{event.y}")
        tags_ranges = self.text_area._textbox.tag_ranges("link")
        for i in range(0, len(tags_ranges), 2):
            if self.text_area._textbox.compare(tags_ranges[i], "<=", idx) and self.text_area._textbox.compare(idx, "<=",
                                                                                                               tags_ranges[
                                                                                                                   i + 1]):
                webbrowser.open(self.text_area._textbox.get(tags_ranges[i], tags_ranges[i + 1]).strip())
                break

    def animate_highlight(self, start_color="#40444B", steps=10):
        def hex_to_rgb(hex_c):
            return tuple(int(hex_c.lstrip('#')[i:i + 2], 16) for i in (0, 2, 4))

        def rgb_to_hex(rgb):
            return '#%02x%02x%02x' % rgb

        target_rgb, current_rgb = hex_to_rgb(C_CHAT_BOX), hex_to_rgb(start_color)
        diff = [(t - c) / steps for t, c in zip(target_rgb, current_rgb)]

        def do_step(count):
            if count <= steps:
                new_rgb = tuple(int(current_rgb[i] + diff[i] * count) for i in range(3))
                self.text_area.tag_config("highlight", background=rgb_to_hex(new_rgb))
                self.root.after(50, lambda: do_step(count + 1))
            else:
                self.text_area.tag_config("highlight", background=C_CHAT_BOX)

        do_step(1)

    def load_preview_image(self, path, max_size=250):
        try:
            pil_img = Image.open(path)
            pil_img.thumbnail((max_size, max_size))
            return ctk.CTkImage(pil_img, size=pil_img.size)
        except Exception:
            return None

    def update_image_label(self, label, img, path):
        if img:
            label.configure(image=img, text="", fg_color="transparent", cursor="hand2")
            label.bind("<Button-1>", lambda e: Image.open(path).show())
        else:
            label.configure(text="❌ Błąd obrazu")

    def get_user_avatar(self, username):
        if not hasattr(self, 'avatar_cache'):
            self.avatar_cache = {}
        if username in self.avatar_cache:
            return self.avatar_cache[username]

        os.makedirs("Cache_Avatary", exist_ok=True)
        filepath = os.path.join("Cache_Avatary", f"{username}.png")

        try:
            if not os.path.exists(filepath):
                size = 40
                hue = sum(ord(c) for c in username) % 360
                rgb = colorsys.hsv_to_rgb(hue / 360.0, 0.65, 0.6)
                bg_color = tuple(int(x * 255) for x in rgb)

                img = Image.new("RGBA", (size, size), (0, 0, 0, 0))
                draw = ImageDraw.Draw(img)
                draw.ellipse([0, 0, size, size], fill=bg_color)

                initial = username[0].upper() if username else "?"
                
                font = None
                font_candidates = [
                    "arial.ttf",
                    "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
                    "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
                    "/usr/share/fonts/truetype/liberation/LiberationSans-Regular.ttf",
                    "/usr/share/fonts/truetype/freefont/FreeSans.ttf",
                    "/System/Library/Fonts/Supplemental/Arial.ttf",
                ]
                for font_path in font_candidates:
                    try:
                        font = ImageFont.truetype(font_path, 20)
                        break
                    except Exception:
                        continue
                
                if font is None:
                    font = ImageFont.load_default()

                try:
                    if hasattr(font, 'getbbox'):
                        bbox = font.getbbox(initial)
                        w = bbox[2] - bbox[0]
                        h = bbox[3] - bbox[1]
                    elif hasattr(draw, 'textsize'):
                        w, h = draw.textsize(initial, font=font)
                    else:
                        w, h = 10, 10
                    
                    x = (size - w) / 2
                    y = (size - h) / 2 - 2
                    draw.text((x, y), initial, fill="white", font=font)
                except Exception:
                    draw.text((size / 2, size / 2), initial, fill="white", anchor="mm", font=font)

                img.save(filepath, "PNG")

            pil_img = Image.open(filepath)
            ctk_img = ctk.CTkImage(light_image=pil_img, dark_image=pil_img, size=(24, 24))
            self.avatar_cache[username] = ctk_img
            return ctk_img
        except Exception as e:
            print(f"Błąd generowania awatara dla {username}: {e}")
            return None

    def play_notification_sound(self):
        def play():
            try:
                import sys
                if hasattr(sys, '_MEIPASS'):
                    base_dir = sys._MEIPASS
                elif getattr(sys, 'frozen', False):
                    base_dir = os.path.dirname(sys.executable)
                else:
                    base_dir = os.path.dirname(os.path.abspath(__file__))
                
                sound_path = os.path.join(base_dir, "notification.wav")

                if sys.platform.startswith("win32"):
                    import winsound
                    if os.path.exists(sound_path):
                        winsound.PlaySound(sound_path, winsound.SND_FILENAME | winsound.SND_ASYNC)
                    else:
                        winsound.PlaySound("SystemNotification", winsound.SND_ALIAS | winsound.SND_ASYNC)
                else:
                    if os.path.exists(sound_path):
                        import subprocess
                        for cmd in ["paplay", "pw-play", "aplay"]:
                            try:
                                subprocess.Popen([cmd, sound_path], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
                                break
                            except FileNotFoundError:
                                continue
            except Exception as e:
                print(f"Błąd odtwarzania dźwięku powiadomienia: {e}")
        
        threading.Thread(target=play, daemon=True).start()

    def copy_to_clipboard(self, text):
        try:
            self.root.clipboard_clear()
            self.root.clipboard_append(text)
            messagebox.showinfo("Skopiowano", "Kod został skopiowany do schowka!")
        except Exception as e:
            print(f"Błąd kopiowania do schowka: {e}")

    def run(self):
        self.root.mainloop()

if __name__ == "__main__":
    app = ChatClient()
    app.run()
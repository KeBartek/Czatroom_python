"""
ui.py — warstwa wizualna czatroomu.
Styl: Discord-like, ciemny motyw, akcenty fioletowe.
Komunikuje się z ChatClient przez callbacki.
"""

import customtkinter as ctk
from tkinter import messagebox, filedialog
import threading
import os
import base64
import re
import requests
from datetime import datetime
from PIL import Image

from chat_client import ChatClient

try:
    from plyer import notification as _plyer_notify
except ImportError:
    _plyer_notify = None

# ---------------------------------------------------------------------------
# Paleta kolorów — ciemny motyw (fioletowe akcenty)
# ---------------------------------------------------------------------------

DARK = {
    "bg_app":       "#1a1b1e",
    "bg_sidebar":   "#111214",
    "bg_surface":   "#2a2b35",
    "bg_input":     "#23242a",
    "bg_hover":     "#2e2f3a",
    "bg_message":   "#1e1f26",

    "accent":       "#5b4fcf",
    "accent_hover": "#6d61d9",
    "accent_light": "#a78bfa",
    "accent_muted": "#3c3489",

    "text_primary":   "#e0deff",
    "text_secondary": "#9b9cab",
    "text_muted":     "#52535e",
    "text_online":    "#5dcaa5",
    "text_offline":   "#6b6c7a",

    "border":       "#2a2b30",
    "border_input": "#3a3b45",

    "online_dot":   "#3b6d11",
    "offline_dot":  "#444441",

    "system_text":  "#52535e",
    "lock_color":   "#5dcaa5",
    "unread_bg":    "#5b4fcf",
}

LIGHT = {
    "bg_app":       "#f5f5f7",
    "bg_sidebar":   "#e8e8ec",
    "bg_surface":   "#ffffff",
    "bg_input":     "#ffffff",
    "bg_hover":     "#ededf2",
    "bg_message":   "#ffffff",

    "accent":       "#5b4fcf",
    "accent_hover": "#6d61d9",
    "accent_light": "#7c6fe0",
    "accent_muted": "#e0deff",

    "text_primary":   "#1a1b1e",
    "text_secondary": "#4a4b58",
    "text_muted":     "#9b9cab",
    "text_online":    "#0f6e56",
    "text_offline":   "#888780",

    "border":       "#d0d0da",
    "border_input": "#c0c0cc",

    "online_dot":   "#3b6d11",
    "offline_dot":  "#888780",

    "system_text":  "#9b9cab",
    "lock_color":   "#0f6e56",
    "unread_bg":    "#5b4fcf",
}

# Kolory avatarów — przypisywane deterministycznie po nazwie użytkownika
AVATAR_COLORS = [
    ("#3c3489", "#c4b5fd"),
    ("#085041", "#5dcaa5"),
    ("#712b13", "#f09b7b"),
    ("#185fa5", "#85b7eb"),
    ("#3b6d11", "#97c459"),
    ("#854f0b", "#ef9f27"),
]

EMOTES_DB = {
    ":pepe:":       "https://cdn.frankerfacez.com/emoticon/28087/1",
    ":pog:":        "https://cdn.frankerfacez.com/emoticon/210748/1",
    ":kekw:":       "https://cdn.frankerfacez.com/emoticon/381875/1",
    ":catjam:":     "https://cdn.frankerfacez.com/emoticon/520322/1",
    ":sadge:":      "https://cdn.frankerfacez.com/emoticon/425196/1",
    ":monkas:":     "https://cdn.frankerfacez.com/emoticon/130762/1",
    ":ez:":         "https://cdn.frankerfacez.com/emoticon/108566/1",
    ":ayaya:":      "https://cdn.frankerfacez.com/emoticon/162146/1",
    ":5head:":      "https://cdn.frankerfacez.com/emoticon/239504/1",
    ":pepehands:":  "https://cdn.frankerfacez.com/emoticon/231552/1",
    ":copium:":     "https://cdn.frankerfacez.com/emoticon/564259/1",
    ":poggers:":    "https://cdn.frankerfacez.com/emoticon/214129/1",
    ":weirdchamp:": "https://cdn.frankerfacez.com/emoticon/322196/1",
    ":feelsbadman:":"https://cdn.frankerfacez.com/emoticon/33355/1",
    ":feelsgoodman:":"https://cdn.frankerfacez.com/emoticon/109777/1",
}


def avatar_colors(username: str) -> tuple[str, str]:
    """Zwraca (bg, fg) dla avatara deterministycznie na podstawie nazwy."""
    idx = sum(ord(c) for c in username) % len(AVATAR_COLORS)
    return AVATAR_COLORS[idx]


def initials(username: str) -> str:
    parts = username.replace("_", " ").replace("-", " ").split()
    if len(parts) >= 2:
        return (parts[0][0] + parts[1][0]).upper()
    return username[:2].upper()


# ---------------------------------------------------------------------------
# Główna klasa aplikacji
# ---------------------------------------------------------------------------

class App:
    def __init__(self):
        self.client = ChatClient()
        self._theme = "dark"
        self._T = DARK

        self.root = ctk.CTk()
        self.root.title("Czatroom")
        self.root.geometry("400x500")
        self.root.resizable(False, False)
        ctk.set_appearance_mode("dark")

        self.current_chat = "Globalny"
        self.chat_histories: dict[str, list[dict]] = {"Globalny": []}
        self.unread: dict[str, int] = {}
        self.all_users: list[str] = []
        self.online_users: list[str] = []
        self.groups: list[str] = []
        self.group_members: list[str] = []
        self.group_creator: str | None = None

        self.last_typing_ts = 0.0
        self.typing_timer = None
        self.loaded_emotes: dict = {}
        self.emote_panel_open = False
        self.emote_panel_widget = None

        self._register_callbacks()
        threading.Thread(target=self._preload_emotes, daemon=True).start()
        self._build_connect_screen()

    # ------------------------------------------------------------------
    # Callbacks z ChatClient
    # ------------------------------------------------------------------

    def _register_callbacks(self):
        c = self.client
        c.on('connect_error',   lambda e: messagebox.showerror("Błąd połączenia", e))
        c.on('login_success',   self._on_login_success)
        c.on('login_error',     lambda e: messagebox.showerror("Błąd logowania", e))
        c.on('register_success',lambda m: messagebox.showinfo("Sukces", m))
        c.on('register_error',  lambda e: messagebox.showerror("Błąd rejestracji", e))

        c.on('global_message',  self._on_global_msg)
        c.on('private_message', self._on_private_msg)
        c.on('group_message',   self._on_group_msg)
        c.on('pending_sent',    self._on_pending_sent)
        c.on('chat_history',    self._on_chat_history)
        c.on('private_history', self._on_private_history)
        c.on('group_history',   self._on_group_history)

        c.on('user_list',       self._on_user_list)
        c.on('groups_updated',  self._on_groups_updated)
        c.on('group_info',      self._on_group_info)
        c.on('typing',          self._on_typing)
        c.on('file_received',   self._on_file_received)
        c.on('kicked',          self._on_kicked)
        c.on('group_deleted',   self._on_group_deleted)
        c.on('join_request',    lambda g, u: self.root.after(0, self._dialog_join_request, g, u))
        c.on('invite_received', lambda g, a: self.root.after(0, self._dialog_invite, g, a))
        c.on('error',           lambda m: self.root.after(0, messagebox.showerror, "Błąd", m))
        c.on('success',         self._on_success)
        c.on('disconnected',    lambda e: self.root.after(0, messagebox.showwarning, "Rozłączono", str(e)))

    # ------------------------------------------------------------------
    # Ekran połączenia
    # ------------------------------------------------------------------

    def _build_connect_screen(self):
        T = self._T
        self.root.configure(fg_color=T["bg_app"])
        self._clear_root()

        frame = ctk.CTkFrame(self.root, fg_color=T["bg_sidebar"], corner_radius=16)
        frame.pack(pady=60, padx=40, fill="both", expand=True)

        ctk.CTkLabel(frame, text="Czatroom", font=("Roboto", 26, "bold"),
                     text_color=T["accent_light"]).pack(pady=(30, 4))
        ctk.CTkLabel(frame, text="Połącz z serwerem", font=("Roboto", 13),
                     text_color=T["text_secondary"]).pack(pady=(0, 20))

        self._entry_ip = ctk.CTkEntry(frame, placeholder_text="Adres IP",
                                      width=260, height=38,
                                      fg_color=T["bg_surface"], border_color=T["border_input"],
                                      text_color=T["text_primary"])
        self._entry_ip.insert(0, "127.0.0.1")
        self._entry_ip.pack(pady=6)

        self._entry_port = ctk.CTkEntry(frame, placeholder_text="Port",
                                        width=260, height=38,
                                        fg_color=T["bg_surface"], border_color=T["border_input"],
                                        text_color=T["text_primary"])
        self._entry_port.insert(0, "9999")
        self._entry_port.pack(pady=6)

        btn = ctk.CTkButton(frame, text="Połącz", width=260, height=40,
                            fg_color=T["accent"], hover_color=T["accent_hover"],
                            font=("Roboto", 14, "bold"), command=self._do_connect)
        btn.pack(pady=16)

        self._entry_ip.bind("<Return>", lambda _: self._do_connect())
        self._entry_port.bind("<Return>", lambda _: self._do_connect())

    def _do_connect(self):
        ip = self._entry_ip.get().strip()
        port_str = self._entry_port.get().strip()
        if not ip or not port_str.isdigit():
            messagebox.showerror("Błąd", "Podaj prawidłowy adres IP i port.")
            return
        if self.client.connect(ip, int(port_str)):
            self._build_login_screen()
        # błąd emitowany przez callback

    # ------------------------------------------------------------------
    # Ekran logowania
    # ------------------------------------------------------------------

    def _build_login_screen(self):
        T = self._T
        self.root.configure(fg_color=T["bg_app"])
        self._clear_root()

        frame = ctk.CTkFrame(self.root, fg_color=T["bg_sidebar"], corner_radius=16)
        frame.pack(pady=40, padx=40, fill="both", expand=True)

        ctk.CTkLabel(frame, text="Witaj!", font=("Roboto", 26, "bold"),
                     text_color=T["accent_light"]).pack(pady=(30, 4))
        ctk.CTkLabel(frame, text="Zaloguj się lub zarejestruj", font=("Roboto", 13),
                     text_color=T["text_secondary"]).pack(pady=(0, 20))

        self._entry_user = ctk.CTkEntry(frame, placeholder_text="Nazwa użytkownika",
                                        width=260, height=38,
                                        fg_color=T["bg_surface"], border_color=T["border_input"],
                                        text_color=T["text_primary"])
        self._entry_user.pack(pady=6)

        self._entry_pass = ctk.CTkEntry(frame, placeholder_text="Hasło",
                                        width=260, height=38, show="*",
                                        fg_color=T["bg_surface"], border_color=T["border_input"],
                                        text_color=T["text_primary"])
        self._entry_pass.pack(pady=6)

        ctk.CTkButton(frame, text="Zaloguj się", width=260, height=40,
                      fg_color=T["accent"], hover_color=T["accent_hover"],
                      font=("Roboto", 14, "bold"),
                      command=self._do_login).pack(pady=(16, 6))

        ctk.CTkButton(frame, text="Zarejestruj się", width=260, height=38,
                      fg_color="transparent", border_width=1,
                      border_color=T["border_input"],
                      text_color=T["text_secondary"],
                      hover_color=T["bg_hover"],
                      command=self._do_register).pack()

        self._entry_user.bind("<Return>", lambda _: self._do_login())
        self._entry_pass.bind("<Return>", lambda _: self._do_login())

    def _do_login(self):
        u = self._entry_user.get().strip()
        p = self._entry_pass.get().strip()
        if not u or not p:
            messagebox.showwarning("Uwaga", "Wprowadź nazwę użytkownika i hasło.")
            return
        self.client.login(u, p)

    def _do_register(self):
        u = self._entry_user.get().strip()
        p = self._entry_pass.get().strip()
        if not u or not p:
            messagebox.showwarning("Uwaga", "Wprowadź nazwę użytkownika i hasło.")
            return
        self.client.register(u, p)

    def _on_login_success(self, username: str):
        self.root.after(0, self._build_chat_window)

    # ------------------------------------------------------------------
    # Główne okno czatu
    # ------------------------------------------------------------------

    def _build_chat_window(self):
        T = self._T
        self.root.geometry("1120x680")
        self.root.resizable(True, True)
        self.root.title(f"Czatroom — {self.client.username}")
        self.root.configure(fg_color=T["bg_app"])
        self._clear_root()

        # Layout: sidebar | main | right panel
        outer = ctk.CTkFrame(self.root, fg_color="transparent")
        outer.pack(fill="both", expand=True)

        # --- Sidebar ---
        self._sidebar = ctk.CTkFrame(outer, width=220, fg_color=T["bg_sidebar"], corner_radius=0)
        self._sidebar.pack(side="left", fill="y")
        self._sidebar.pack_propagate(False)
        self._build_sidebar()

        # --- Right panel ---
        self._right = ctk.CTkFrame(outer, width=210, fg_color=T["bg_sidebar"], corner_radius=0)
        self._right.pack(side="right", fill="y")
        self._right.pack_propagate(False)

        # --- Chat area ---
        self._chat_area = ctk.CTkFrame(outer, fg_color=T["bg_app"], corner_radius=0)
        self._chat_area.pack(side="left", fill="both", expand=True)
        self._build_chat_area()

    def _build_sidebar(self):
        T = self._T
        for w in self._sidebar.winfo_children():
            w.destroy()

        # Header
        hdr = ctk.CTkFrame(self._sidebar, fg_color="transparent", height=56)
        hdr.pack(fill="x", padx=12, pady=(12, 0))
        hdr.pack_propagate(False)
        ctk.CTkLabel(hdr, text="Czatroom", font=("Roboto", 15, "bold"),
                     text_color=T["accent_light"]).pack(side="left", anchor="w")

        # Przycisk motywu
        theme_btn = ctk.CTkButton(hdr, text="☀" if self._theme == "dark" else "🌙",
                                  width=32, height=28, fg_color=T["bg_surface"],
                                  hover_color=T["bg_hover"], text_color=T["text_secondary"],
                                  font=("Roboto", 14), command=self._toggle_theme)
        theme_btn.pack(side="right")

        sep = ctk.CTkFrame(self._sidebar, fg_color=T["border"], height=1)
        sep.pack(fill="x")

        # Czat globalny
        self._btn_global = self._sidebar_btn("🌐  Globalny", lambda: self._switch_chat("Globalny"))
        self._btn_global.pack(fill="x", padx=8, pady=(8, 2))

        # Grupy
        self._sidebar_section("GRUPY")
        grp_btns = ctk.CTkFrame(self._sidebar, fg_color="transparent")
        grp_btns.pack(fill="x", padx=8)
        ctk.CTkButton(grp_btns, text="+ Utwórz", width=96, height=28,
                      fg_color=T["accent_muted"], hover_color=T["accent"],
                      text_color=T["accent_light"], font=("Roboto", 11),
                      command=self._ui_create_group).pack(side="left", padx=(0, 4))
        ctk.CTkButton(grp_btns, text="+ Dołącz", width=96, height=28,
                      fg_color=T["bg_surface"], hover_color=T["bg_hover"],
                      text_color=T["text_secondary"], font=("Roboto", 11),
                      command=self._ui_join_group).pack(side="left")

        self._groups_frame = ctk.CTkScrollableFrame(self._sidebar, fg_color="transparent", height=130)
        self._groups_frame.pack(fill="x", padx=4, pady=(4, 0))

        # Wiadomości prywatne
        self._sidebar_section("WIADOMOŚCI")
        self._privates_frame = ctk.CTkScrollableFrame(self._sidebar, fg_color="transparent", height=110)
        self._privates_frame.pack(fill="x", padx=4)

        # Stopka (zalogowany użytkownik)
        foot = ctk.CTkFrame(self._sidebar, fg_color=T["bg_surface"], corner_radius=0, height=52)
        foot.pack(fill="x", side="bottom")
        foot.pack_propagate(False)
        sep2 = ctk.CTkFrame(self._sidebar, fg_color=T["border"], height=1)
        sep2.pack(fill="x", side="bottom")

        av_bg, av_fg = avatar_colors(self.client.username or "?")
        av = ctk.CTkLabel(foot, text=initials(self.client.username or "?"),
                          width=32, height=32, fg_color=av_bg, text_color=av_fg,
                          corner_radius=16, font=("Roboto", 11, "bold"))
        av.pack(side="left", padx=(10, 6), pady=10)
        ctk.CTkLabel(foot, text=self.client.username or "",
                     font=("Roboto", 12, "bold"), text_color=T["accent_light"]).pack(side="left")
        ctk.CTkLabel(foot, text="🔒 E2EE", font=("Roboto", 10),
                     text_color=T["text_online"]).pack(side="right", padx=10)

        self._refresh_sidebar_lists()

    def _sidebar_section(self, label: str):
        T = self._T
        ctk.CTkLabel(self._sidebar, text=label, font=("Roboto", 10, "bold"),
                     text_color=T["text_muted"]).pack(anchor="w", padx=14, pady=(10, 2))

    def _sidebar_btn(self, text: str, cmd) -> ctk.CTkButton:
        T = self._T
        return ctk.CTkButton(self._sidebar, text=text, height=34,
                             fg_color="transparent", hover_color=T["bg_hover"],
                             text_color=T["text_secondary"], anchor="w",
                             font=("Roboto", 13), command=cmd)

    def _refresh_sidebar_lists(self):
        T = self._T

        # Zaktualizuj globalny przycisk
        unread_g = self.unread.get("Globalny", 0)
        self._btn_global.configure(
            text=f"🌐  Globalny{'  (' + str(unread_g) + ')' if unread_g else ''}",
            text_color=T["accent_light"] if self.current_chat == "Globalny" else
                       (T["unread_bg"] if unread_g else T["text_secondary"]),
            fg_color=T["bg_hover"] if self.current_chat == "Globalny" else "transparent"
        )

        # Grupy
        for w in self._groups_frame.winfo_children():
            w.destroy()
        for g in self.groups:
            unread = self.unread.get(g, 0)
            label = f"#  {g[1:]}{'  (' + str(unread) + ')' if unread else ''}"
            color = T["unread_bg"] if unread else (
                T["accent_light"] if self.current_chat == g else T["text_secondary"])
            btn = ctk.CTkButton(self._groups_frame, text=label, height=30,
                                fg_color=T["bg_hover"] if self.current_chat == g else "transparent",
                                hover_color=T["bg_hover"],
                                text_color=color, anchor="w", font=("Roboto", 12),
                                command=lambda grp=g: self._switch_chat(grp))
            btn.pack(fill="x", padx=4, pady=1)

        # Prywatne
        for w in self._privates_frame.winfo_children():
            w.destroy()
        private_chats = [c for c in self.chat_histories if c != "Globalny" and not c.startswith("#")]
        for p in private_chats:
            unread = self.unread.get(p, 0)
            is_online = p in self.online_users
            dot = "● " if is_online else "○ "
            label = f"{dot}{p}{'  (' + str(unread) + ')' if unread else ''}"
            color = T["unread_bg"] if unread else (
                T["accent_light"] if self.current_chat == p else
                (T["text_online"] if is_online else T["text_offline"]))
            btn = ctk.CTkButton(self._privates_frame, text=label, height=30,
                                fg_color=T["bg_hover"] if self.current_chat == p else "transparent",
                                hover_color=T["bg_hover"],
                                text_color=color, anchor="w", font=("Roboto", 12),
                                command=lambda u=p: self._switch_chat(u))
            btn.pack(fill="x", padx=4, pady=1)

    # ------------------------------------------------------------------
    # Prawy panel (użytkownicy / członkowie grupy)
    # ------------------------------------------------------------------

    def _build_right_panel(self):
        T = self._T
        for w in self._right.winfo_children():
            w.destroy()

        is_group = self.current_chat.startswith("#")
        title = f"Członkowie {self.current_chat}" if is_group else "Użytkownicy"
        ctk.CTkLabel(self._right, text=title, font=("Roboto", 11, "bold"),
                     text_color=T["text_muted"]).pack(anchor="w", padx=14, pady=(14, 6))

        sep = ctk.CTkFrame(self._right, fg_color=T["border"], height=1)
        sep.pack(fill="x")

        # Przyciski admina grupy
        if is_group and self.group_creator == self.client.username:
            ab = ctk.CTkFrame(self._right, fg_color="transparent")
            ab.pack(fill="x", padx=8, pady=6)
            ctk.CTkButton(ab, text="+ Zaproś", height=28, width=90,
                          fg_color=T["accent_muted"], hover_color=T["accent"],
                          text_color=T["accent_light"], font=("Roboto", 11),
                          command=self._ui_invite).pack(side="left", padx=(0, 4))
            ctk.CTkButton(ab, text="Wyrzuć", height=28, width=80,
                          fg_color="#3a1a1a", hover_color="#5a2020",
                          text_color="#f09b7b", font=("Roboto", 11),
                          command=self._ui_kick).pack(side="left")
            ctk.CTkButton(self._right, text="🗑 Usuń grupę", height=30,
                          fg_color="#3a1a1a", hover_color="#5a2020",
                          text_color="#f09b7b", font=("Roboto", 11),
                          command=self._ui_delete_group).pack(fill="x", padx=8, pady=(0, 6))

        scroll = ctk.CTkScrollableFrame(self._right, fg_color="transparent")
        scroll.pack(fill="both", expand=True, padx=4)

        users = self.group_members if is_group else self.all_users
        for u in users:
            if u == self.client.username:
                self._user_row(scroll, u, is_self=True,
                               is_creator=(is_group and u == self.group_creator))
            else:
                self._user_row(scroll, u,
                               is_online=u in self.online_users,
                               is_creator=(is_group and u == self.group_creator),
                               on_click=lambda user=u: self._switch_chat(user))

        # Opuść grupę
        if is_group:
            ctk.CTkButton(self._right, text="🚪 Opuść grupę", height=32,
                          fg_color="transparent", border_width=1,
                          border_color=T["border_input"],
                          text_color=T["text_secondary"],
                          hover_color=T["bg_hover"],
                          font=("Roboto", 11), command=self._ui_leave_group).pack(
                fill="x", padx=8, pady=(4, 10), side="bottom")

    def _user_row(self, parent, username: str, is_self=False, is_online=False,
                  is_creator=False, on_click=None):
        T = self._T
        row = ctk.CTkFrame(parent, fg_color="transparent", cursor="hand2" if on_click else "")
        row.pack(fill="x", pady=2, padx=4)

        av_bg, av_fg = avatar_colors(username)
        av = ctk.CTkLabel(row, text=initials(username), width=28, height=28,
                          fg_color=av_bg, text_color=av_fg,
                          corner_radius=14, font=("Roboto", 10, "bold"))
        av.pack(side="left", padx=(4, 6))

        col = ctk.CTkFrame(row, fg_color="transparent")
        col.pack(side="left")

        name_color = T["accent_light"] if is_self else (
            T["text_primary"] if is_online else T["text_offline"])
        name_text = f"{username} (Ty)" if is_self else username
        ctk.CTkLabel(col, text=name_text, font=("Roboto", 12, "bold" if is_self else "normal"),
                     text_color=name_color).pack(anchor="w")

        if is_creator:
            ctk.CTkLabel(col, text="👑 Właściciel", font=("Roboto", 10),
                         text_color=T["text_muted"]).pack(anchor="w")

        if on_click:
            for widget in [row, av, col]:
                widget.bind("<Button-1>", lambda e, fn=on_click: fn())

    # ------------------------------------------------------------------
    # Obszar czatu
    # ------------------------------------------------------------------

    def _build_chat_area(self):
        T = self._T

        # Nagłówek
        self._chat_header = ctk.CTkFrame(self._chat_area, fg_color=T["bg_sidebar"],
                                          height=52, corner_radius=0)
        self._chat_header.pack(fill="x")
        self._chat_header.pack_propagate(False)
        sep = ctk.CTkFrame(self._chat_area, fg_color=T["border"], height=1)
        sep.pack(fill="x")

        self._lbl_chat_title = ctk.CTkLabel(self._chat_header, text="# globalny",
                                             font=("Roboto", 15, "bold"),
                                             text_color=T["text_primary"])
        self._lbl_chat_title.pack(side="left", padx=16)

        self._lbl_e2ee = ctk.CTkLabel(self._chat_header, text="",
                                       font=("Roboto", 11), text_color=T["lock_color"])
        self._lbl_e2ee.pack(side="right", padx=16)

        # Obszar wiadomości
        self._msg_area = ctk.CTkScrollableFrame(self._chat_area, fg_color=T["bg_app"],
                                                 corner_radius=0)
        self._msg_area.pack(fill="both", expand=True)

        # Wskaźnik pisania
        self._lbl_typing = ctk.CTkLabel(self._chat_area, text="",
                                         font=("Roboto", 11, "italic"),
                                         text_color=T["text_muted"])
        self._lbl_typing.pack(anchor="w", padx=16, pady=(2, 0))

        # Panel emotek (ukryty)
        self._emote_panel_frame = ctk.CTkScrollableFrame(
            self._chat_area, height=54, orientation="horizontal",
            fg_color=T["bg_surface"])

        # Pole wprowadzania
        input_row = ctk.CTkFrame(self._chat_area, fg_color=T["bg_sidebar"],
                                  corner_radius=0, height=60)
        input_row.pack(fill="x", side="bottom")
        input_row.pack_propagate(False)
        sep2 = ctk.CTkFrame(self._chat_area, fg_color=T["border"], height=1)
        sep2.pack(fill="x", side="bottom")

        inner = ctk.CTkFrame(input_row, fg_color=T["bg_surface"],
                              corner_radius=10, border_width=1,
                              border_color=T["border_input"])
        inner.pack(fill="x", padx=14, pady=10)

        ctk.CTkButton(inner, text="📎", width=34, height=32, fg_color="transparent",
                      hover_color=T["bg_hover"], text_color=T["text_secondary"],
                      font=("Roboto", 15), command=self._send_file).pack(side="left", padx=(4, 0))
        ctk.CTkButton(inner, text="😀", width=34, height=32, fg_color="transparent",
                      hover_color=T["bg_hover"], text_color=T["text_secondary"],
                      font=("Roboto", 15), command=self._toggle_emote_panel).pack(side="left")

        self._entry_msg = ctk.CTkEntry(inner, placeholder_text="Wpisz wiadomość...",
                                        fg_color="transparent", border_width=0,
                                        text_color=T["text_primary"],
                                        placeholder_text_color=T["text_muted"],
                                        font=("Roboto", 13))
        self._entry_msg.pack(side="left", fill="x", expand=True, padx=6)
        self._entry_msg.bind("<Return>", lambda _: self._send_message())
        self._entry_msg.bind("<KeyRelease>", self._on_key_release)

        ctk.CTkButton(inner, text="Wyślij", width=80, height=32,
                      fg_color=T["accent"], hover_color=T["accent_hover"],
                      text_color=T["text_primary"], font=("Roboto", 12, "bold"),
                      command=self._send_message).pack(side="right", padx=(0, 4))

        self._switch_chat("Globalny")

    # ------------------------------------------------------------------
    # Wyświetlanie wiadomości
    # ------------------------------------------------------------------

    def _render_history(self):
        """Czyści obszar wiadomości i renderuje historię aktualnego czatu."""
        for w in self._msg_area.winfo_children():
            w.destroy()

        history = self.chat_histories.get(self.current_chat, [])
        prev_sender = None
        for entry in history:
            self._render_msg(entry, group_with_prev=(entry["sender"] == prev_sender))
            prev_sender = entry["sender"]

        self._msg_area.after(100, lambda: self._msg_area._parent_canvas.yview_moveto(1.0))

    def _render_msg(self, entry: dict, group_with_prev=False):
        """Renderuje pojedynczą wiadomość (lub kontynuację) w obszarze czatu."""
        T = self._T
        sender = entry.get("sender", "")
        text = entry.get("content", "")
        ts = entry.get("timestamp", "")
        is_e2ee = entry.get("is_e2ee", False)
        is_system = sender == "SYSTEM"

        if is_system:
            row = ctk.CTkFrame(self._msg_area, fg_color="transparent")
            row.pack(fill="x", pady=1)
            ctk.CTkLabel(row, text=f"— {text} —", font=("Roboto", 11, "italic"),
                         text_color=T["system_text"]).pack(pady=2)
            return

        if group_with_prev:
            # Kontynuacja — tylko tekst, bez avatara/nagłówka
            cont = ctk.CTkFrame(self._msg_area, fg_color="transparent")
            cont.pack(fill="x", padx=(58, 16), pady=0)
            self._msg_text_widget(cont, text, T)
            return

        # Nowa grupa wiadomości
        row = ctk.CTkFrame(self._msg_area, fg_color="transparent")
        row.pack(fill="x", padx=12, pady=(6, 0))

        # Avatar
        av_bg, av_fg = avatar_colors(sender)
        av = ctk.CTkLabel(row, text=initials(sender), width=36, height=36,
                          fg_color=av_bg, text_color=av_fg,
                          corner_radius=18, font=("Roboto", 12, "bold"))
        av.pack(side="left", anchor="n", pady=2, padx=(0, 10))

        body = ctk.CTkFrame(row, fg_color="transparent")
        body.pack(side="left", fill="x", expand=True)

        # Nagłówek: imię + czas + kłódka E2EE
        hdr = ctk.CTkFrame(body, fg_color="transparent")
        hdr.pack(fill="x")
        av_bg2, _ = avatar_colors(sender)

        # Kolor nazwy — deterministyczny z palety
        name_color = AVATAR_COLORS[sum(ord(c) for c in sender) % len(AVATAR_COLORS)][1]
        ctk.CTkLabel(hdr, text=sender, font=("Roboto", 13, "bold"),
                     text_color=name_color).pack(side="left")
        ctk.CTkLabel(hdr, text=f"  {ts}", font=("Roboto", 10),
                     text_color=T["text_muted"]).pack(side="left")
        if is_e2ee:
            ctk.CTkLabel(hdr, text=" 🔒", font=("Roboto", 11),
                         text_color=T["lock_color"]).pack(side="left")

        self._msg_text_widget(body, text, T)

    def _msg_text_widget(self, parent, text: str, T: dict):
        """Wstawia tekst wiadomości z obsługą emotek i linków do plików."""
        parts = re.split(r'(\[FILE:[^]]+\]|:[a-zA-Z0-9_]+:)', text)
        line = ctk.CTkFrame(parent, fg_color="transparent")
        line.pack(fill="x", anchor="w")

        for part in parts:
            file_match = re.match(r'\[FILE:(.*?):(.*?)\]', part)
            if file_match:
                fid, fname = file_match.group(1), file_match.group(2)
                btn = ctk.CTkButton(line, text=f"📄 {fname}", height=26,
                                    fg_color=T["accent_muted"],
                                    hover_color=T["accent"],
                                    text_color=T["accent_light"],
                                    font=("Roboto", 11),
                                    command=lambda fi=fid, fn=fname: self.client.request_download(fi, fn))
                btn.pack(side="left", padx=(0, 4))
            elif part in EMOTES_DB:
                img = self._get_emote(part)
                if img:
                    lbl = ctk.CTkLabel(line, text="", image=img)
                    lbl.pack(side="left")
                else:
                    ctk.CTkLabel(line, text=part, font=("Roboto", 12),
                                 text_color=T["text_primary"]).pack(side="left")
            elif part:
                ctk.CTkLabel(line, text=part, font=("Roboto", 13),
                             text_color=T["text_primary"],
                             wraplength=600, justify="left").pack(side="left")

    def _add_msg_to_history(self, chat: str, entry: dict):
        if chat not in self.chat_histories:
            self.chat_histories[chat] = []
        history = self.chat_histories[chat]
        prev_sender = history[-1]["sender"] if history else None
        history.append(entry)

        if chat == self.current_chat:
            self.root.after(0, self._render_msg, entry,
                            entry["sender"] == prev_sender)
            self.root.after(150, lambda: self._msg_area._parent_canvas.yview_moveto(1.0))
        else:
            if entry.get("sender") not in (self.client.username, "SYSTEM"):
                self.unread[chat] = self.unread.get(chat, 0) + 1
                self.root.after(0, self._refresh_sidebar_lists)

    # ------------------------------------------------------------------
    # Przełączanie czatu
    # ------------------------------------------------------------------

    def _switch_chat(self, name: str):
        self.current_chat = name
        self.unread[name] = 0
        self.group_members = []
        self.group_creator = None
        self._clear_typing()

        # Nagłówek
        if name == "Globalny":
            self._lbl_chat_title.configure(text="# globalny")
            self._lbl_e2ee.configure(text="Fernet")
        elif name.startswith("#"):
            self._lbl_chat_title.configure(text=f"# {name[1:]}")
            self._lbl_e2ee.configure(text="Fernet")
            self.client.get_group_info(name)
        else:
            self._lbl_chat_title.configure(text=f"@ {name}")
            self._lbl_e2ee.configure(text="🔒 E2EE")

        if self.emote_panel_open:
            self._toggle_emote_panel()

        self._render_history()
        self._refresh_sidebar_lists()
        self._build_right_panel()

    # ------------------------------------------------------------------
    # Callbacki wiadomości
    # ------------------------------------------------------------------

    def _on_global_msg(self, sender, content, ts):
        self._add_msg_to_history("Globalny", {"sender": sender, "content": content, "timestamp": ts})
        if sender != self.client.username and sender != "SYSTEM":
            self._notify(f"#{sender}", content)

    def _on_private_msg(self, sender, content, ts, is_e2ee):
        self._add_msg_to_history(sender, {"sender": sender, "content": content,
                                           "timestamp": ts, "is_e2ee": is_e2ee})
        if sender != self.client.username:
            self._notify(f"@ {sender}", content)

    def _on_group_msg(self, sender, group, content, ts):
        self._add_msg_to_history(group, {"sender": sender, "content": content, "timestamp": ts})
        if sender != self.client.username and sender != "SYSTEM":
            self._notify(f"{group} ({sender})", content)

    def _on_pending_sent(self, recipient, text, ts):
        self._add_msg_to_history(recipient,
                                  {"sender": self.client.username, "content": text,
                                   "timestamp": ts, "is_e2ee": True})

    def _on_chat_history(self, history):
        for m in history:
            self.chat_histories["Globalny"].append(m)
        if self.current_chat == "Globalny":
            self.root.after(0, self._render_history)

    def _on_private_history(self, history):
        for m in history:
            partner = m["recipient"] if m["sender"] == self.client.username else m["sender"]
            if partner not in self.chat_histories:
                self.chat_histories[partner] = []
            self.chat_histories[partner].append(m)
        if self.current_chat not in ("Globalny",) and not self.current_chat.startswith("#"):
            self.root.after(0, self._render_history)
        self.root.after(0, self._refresh_sidebar_lists)

    def _on_group_history(self, group, history):
        if group not in self.chat_histories:
            self.chat_histories[group] = []
        for m in history:
            self.chat_histories[group].append(m)
        if self.current_chat == group:
            self.root.after(0, self._render_history)

    def _on_user_list(self, all_users, online_users):
        self.all_users = all_users
        self.online_users = online_users
        self.root.after(0, self._refresh_sidebar_lists)
        self.root.after(0, self._build_right_panel)

    def _on_groups_updated(self, groups):
        self.groups = groups
        self.root.after(0, self._refresh_sidebar_lists)

    def _on_group_info(self, group, members, creator):
        if group == self.current_chat:
            self.group_members = members
            self.group_creator = creator
            self.root.after(0, self._build_right_panel)

    def _on_typing(self, sender, target):
        show = (target == "Globalny" and self.current_chat == "Globalny") or \
               (target == self.current_chat) or \
               (target == self.client.username and self.current_chat == sender)
        if show:
            self.root.after(0, self._show_typing, sender)

    def _on_file_received(self, filename, data):
        ext = os.path.splitext(filename)[1]
        path = filedialog.asksaveasfilename(initialfile=filename,
                                            defaultextension=ext,
                                            filetypes=[(f"Plik (*{ext})", f"*{ext}")])
        if path:
            with open(path, "wb") as f:
                f.write(base64.b64decode(data))
            messagebox.showinfo("Pobrano", f"Zapisano: {filename}")

    def _on_kicked(self, group):
        self.root.after(0, messagebox.showwarning, "Wyrzucono",
                        f"Zostałeś wyrzucony z grupy {group}.")
        if self.current_chat == group:
            self.root.after(0, self._switch_chat, "Globalny")

    def _on_group_deleted(self, group):
        self.root.after(0, messagebox.showinfo, "Usunięto",
                        f"Właściciel usunął grupę {group}.")
        if self.current_chat == group:
            self.root.after(0, self._switch_chat, "Globalny")

    def _on_success(self, msg):
        keywords = ("Utworzono", "Dołączono", "Opuszczono", "Zaakceptowano",
                    "Wyrzucono", "Dodano", "Dołączyłeś")
        if any(k in msg for k in keywords):
            self.root.after(0, messagebox.showinfo, "Sukces", msg)

    # ------------------------------------------------------------------
    # Wysyłanie
    # ------------------------------------------------------------------

    def _widget_ok(self, w) -> bool:
        """Sprawdza czy widget nadal istnieje (zabezpieczenie przed TclError)."""
        try:
            return bool(w.winfo_exists())
        except Exception:
            return False

    def _send_message(self):
        if not self._widget_ok(self._entry_msg):
            return
        text = self._entry_msg.get().strip()
        if not text:
            return
        now = datetime.now().strftime("%H:%M")

        if self.current_chat == "Globalny":
            self.client.send_global(text)
            # Własna wiadomość pojawi się przez broadcast z serwera
        elif self.current_chat.startswith("#"):
            self.client.send_group(self.current_chat, text)
            self._add_msg_to_history(self.current_chat,
                                      {"sender": self.client.username, "content": text, "timestamp": now})
        else:
            sent = self.client.send_private(self.current_chat, text)
            if sent:
                self._add_msg_to_history(self.current_chat,
                                          {"sender": self.client.username, "content": text,
                                           "timestamp": now, "is_e2ee": True})
            else:
                messagebox.showinfo("E2EE",
                                    f"Pobieranie klucza {self.current_chat}...\nWiadomość zostanie wysłana za chwilę.")

        self._entry_msg.delete(0, "end")
        if self.emote_panel_open:
            self._toggle_emote_panel()

    def _send_file(self):
        path = filedialog.askopenfilename(title="Wybierz plik")
        if path:
            self.client.send_file(self.current_chat, path)
            now = datetime.now().strftime("%H:%M")
            fname = os.path.basename(path)
            fid = f"{int(datetime.now().timestamp())}_{self.client.username}_{fname}"
            self._add_msg_to_history(self.current_chat,
                                      {"sender": self.client.username,
                                       "content": f"[FILE:{fid}:{fname}]",
                                       "timestamp": now})

    # ------------------------------------------------------------------
    # Typing indicator
    # ------------------------------------------------------------------

    def _on_key_release(self, event):
        if event.keysym == "Return":
            return
        if not self._widget_ok(self._entry_msg):
            return
        if self._entry_msg.get().strip():
            import time
            now = time.time()
            if now - self.last_typing_ts > 2:
                self.last_typing_ts = now
                self.client.send_typing(self.current_chat)

    def _show_typing(self, sender: str):
        self._lbl_typing.configure(text=f"{sender} pisze...")
        if self.typing_timer:
            self.root.after_cancel(self.typing_timer)
        self.typing_timer = self.root.after(3000, self._clear_typing)

    def _clear_typing(self):
        self._lbl_typing.configure(text="")

    # ------------------------------------------------------------------
    # Emotki
    # ------------------------------------------------------------------

    def _preload_emotes(self):
        os.makedirs("Cache_Emotki", exist_ok=True)
        for code, url in EMOTES_DB.items():
            name = code.strip(":")
            fp = os.path.join("Cache_Emotki", f"{name}.png")
            if not os.path.exists(fp):
                try:
                    r = requests.get(url, timeout=3)
                    if r.status_code == 200:
                        with open(fp, "wb") as f:
                            f.write(r.content)
                except Exception:
                    pass

    def _get_emote(self, code: str):
        if code in self.loaded_emotes:
            return self.loaded_emotes[code]
        fp = os.path.join("Cache_Emotki", f"{code.strip(':')}.png")
        if not os.path.exists(fp):
            return None
        try:
            img = ctk.CTkImage(Image.open(fp), size=(22, 22))
            self.loaded_emotes[code] = img
            return img
        except Exception:
            return None

    def _toggle_emote_panel(self):
        T = self._T
        self.emote_panel_open = not self.emote_panel_open
        if self.emote_panel_open:
            self._emote_panel_frame.pack(fill="x", padx=14, pady=(0, 4),
                                          before=self._lbl_typing)
            for w in self._emote_panel_frame.winfo_children():
                w.destroy()
            for code in EMOTES_DB:
                img = self._get_emote(code)
                if img:
                    b = ctk.CTkButton(self._emote_panel_frame, text="", image=img,
                                      width=38, height=38, fg_color="transparent",
                                      hover_color=T["bg_hover"],
                                      command=lambda c=code: self._insert_emote(c))
                    b.pack(side="left", padx=3)
                else:
                    b = ctk.CTkButton(self._emote_panel_frame, text=code, width=50, height=38,
                                      fg_color="transparent", hover_color=T["bg_hover"],
                                      text_color=T["text_secondary"], font=("Roboto", 10),
                                      command=lambda c=code: self._insert_emote(c))
                    b.pack(side="left", padx=2)
        else:
            self._emote_panel_frame.pack_forget()

    def _insert_emote(self, code: str):
        try:
            if self._entry_msg.winfo_exists():
                self._entry_msg.insert("end", code + " ")
                self._entry_msg.focus_set()
        except Exception:
            pass

    # ------------------------------------------------------------------
    # Dialogi grup
    # ------------------------------------------------------------------

    def _ui_create_group(self):
        d = ctk.CTkInputDialog(text="Nazwa nowej grupy:", title="Utwórz grupę")
        name = d.get_input()
        if name and name.strip():
            self.client.create_group(name.strip())

    def _ui_join_group(self):
        d = ctk.CTkInputDialog(text="Nazwa grupy:", title="Dołącz do grupy")
        name = d.get_input()
        if name and name.strip():
            self.client.join_group(name.strip())

    def _ui_leave_group(self):
        if messagebox.askyesno("Opuść grupę", f"Opuścić {self.current_chat}?"):
            self.client.leave_group(self.current_chat)
            self._switch_chat("Globalny")

    def _ui_delete_group(self):
        if messagebox.askyesno("Usuń grupę",
                                f"Trwale usunąć {self.current_chat}? Tej akcji nie można cofnąć."):
            self.client.delete_group(self.current_chat)

    def _ui_invite(self):
        d = ctk.CTkInputDialog(text="Nick użytkownika do zaproszenia:", title="Zaproś")
        user = d.get_input()
        if user and user.strip():
            self.client.invite_to_group(self.current_chat, user.strip())

    def _ui_kick(self):
        d = ctk.CTkInputDialog(text="Nick użytkownika do wyrzucenia:", title="Wyrzuć")
        user = d.get_input()
        if user and user.strip():
            self.client.kick_from_group(self.current_chat, user.strip())

    def _dialog_join_request(self, group, user):
        ans = messagebox.askyesno("Prośba o dołączenie",
                                   f"{user} prosi o dołączenie do {group}. Zaakceptować?")
        self.client.resolve_join(group, user, ans)

    def _dialog_invite(self, group, admin):
        ans = messagebox.askyesno("Zaproszenie",
                                   f"Zaproszenie do grupy {group} od {admin}. Dołączyć?")
        self.client.resolve_invite(group, ans)

    # ------------------------------------------------------------------
    # Motyw
    # ------------------------------------------------------------------

    def _toggle_theme(self):
        self._theme = "light" if self._theme == "dark" else "dark"
        self._T = LIGHT if self._theme == "light" else DARK
        ctk.set_appearance_mode("light" if self._theme == "light" else "dark")
        # Przebuduj UI z nowym motywem
        self._build_sidebar()
        self._build_right_panel()

    # ------------------------------------------------------------------
    # Powiadomienia
    # ------------------------------------------------------------------

    def _notify(self, title: str, msg: str):
        if _plyer_notify:
            threading.Thread(target=lambda: _plyer_notify.notify(
                title=title, message=msg[:80], app_name="Czatroom", timeout=4
            ), daemon=True).start()

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    def _clear_root(self):
        for w in self.root.winfo_children():
            w.destroy()

    def run(self):
        self.root.mainloop()


if __name__ == "__main__":
    App().run()
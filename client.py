import customtkinter as ctk
import socket
import json
import threading
import os
import base64
import re  # NOWOŚĆ: Do przeszukiwania tekstu w klikniętej linijce
import platform  # NOWOŚĆ: Do rozpoznania systemu (Windows/Mac/Linux)
import subprocess  # NOWOŚĆ: Do otwierania plików
from tkinter import messagebox, filedialog
from datetime import datetime

ctk.set_appearance_mode("dark")
ctk.set_default_color_theme("blue")


class ChatClient:
    def __init__(self):
        self.root = ctk.CTk()
        self.root.title("Czatroom - Logowanie")
        self.root.geometry("400x450")
        self.root.resizable(False, False)

        self.client_socket = None
        self.socket_file = None
        self.username = None

        self.current_chat = "Globalny"
        self.chat_histories = {"Globalny": ""}

        self.build_login_screen()

    def build_login_screen(self):
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

    def connect_to_server(self):
        if self.client_socket is None:
            try:
                self.client_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
                self.client_socket.connect(('127.0.0.1', 9999))
                self.socket_file = self.client_socket.makefile('r', encoding='utf-8')
                return True
            except ConnectionRefusedError:
                messagebox.showerror("Błąd", "Nie można połączyć się z serwerem!")
                self.client_socket = None
                return False
        return True

    def send_auth_request(self, action):
        username = self.entry_username.get().strip()
        password = self.entry_password.get().strip()

        if not username or not password:
            messagebox.showwarning("Uwaga", "Wprowadź nazwę użytkownika i hasło.")
            return

        if not self.connect_to_server():
            return

        request = {"action": action, "username": username, "password": password}

        try:
            self.client_socket.sendall((json.dumps(request) + "\n").encode('utf-8'))
            response_line = self.socket_file.readline()
            if not response_line:
                return
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
        self.root.geometry("900x600")
        self.root.title(f"Czatroom - Zalogowany jako: {self.username}")
        self.root.resizable(True, True)

        self.main_container = ctk.CTkFrame(master=self.root, fg_color="transparent")
        self.main_container.pack(fill="both", expand=True, padx=10, pady=10)

        self.sidebar_frame = ctk.CTkFrame(master=self.main_container, width=200)
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

        self.lbl_groups = ctk.CTkLabel(master=self.sidebar_frame, text="📁 Twoje Grupy:", font=("Roboto", 14, "bold"))
        self.lbl_groups.pack(pady=(0, 0), padx=10)
        self.groups_scrollable = ctk.CTkScrollableFrame(master=self.sidebar_frame, width=180, height=100)
        self.groups_scrollable.pack(fill="both", expand=True, padx=5, pady=5)

        self.lbl_online = ctk.CTkLabel(master=self.sidebar_frame, text="🟢 Aktywni:", font=("Roboto", 14, "bold"))
        self.lbl_online.pack(pady=(5, 0), padx=10)
        self.users_scrollable = ctk.CTkScrollableFrame(master=self.sidebar_frame, width=180, height=150)
        self.users_scrollable.pack(fill="both", expand=True, padx=5, pady=5)

        self.chat_frame = ctk.CTkFrame(master=self.main_container)
        self.chat_frame.pack(side="right", fill="both", expand=True)

        self.lbl_current_chat = ctk.CTkLabel(master=self.chat_frame, text="Rozmowa: Globalny",
                                             font=("Roboto", 18, "bold"))
        self.lbl_current_chat.pack(pady=(10, 0))

        self.text_area = ctk.CTkTextbox(master=self.chat_frame, state="disabled", wrap="word", font=("Roboto", 14))
        self.text_area.pack(pady=10, padx=10, fill="both", expand=True)

        # --- NOWOŚĆ: Podpinamy zdarzenie Ctrl + Kliknięcie Lewym Przyciskiem Myszki ---
        # ._textbox to dostęp do natywnego widgetu tk.Text ukrytego w customtkinter
        self.text_area._textbox.bind("<Control-Button-1>", self.on_chat_click)

        self.bottom_frame = ctk.CTkFrame(master=self.chat_frame, fg_color="transparent")
        self.bottom_frame.pack(pady=10, padx=10, fill="x")

        self.btn_attach = ctk.CTkButton(master=self.bottom_frame, text="📎", width=40, command=self.send_file)
        self.btn_attach.pack(side="left", padx=(0, 10))

        self.entry_message = ctk.CTkEntry(master=self.bottom_frame, placeholder_text="Wpisz wiadomość...", width=600)
        self.entry_message.pack(side="left", padx=(0, 10), fill="x", expand=True)
        self.entry_message.bind("<Return>", lambda event: self.send_message())

        self.btn_send = ctk.CTkButton(master=self.bottom_frame, text="Wyślij", width=100, command=self.send_message)
        self.btn_send.pack(side="right")

        threading.Thread(target=self.receive_messages, daemon=True).start()

    # --- NOWOŚĆ: Funkcja reagująca na Ctrl + Kliknięcie ---
    def on_chat_click(self, event):
        try:
            # 1. Sprawdzamy, w który wiersz i literę użytkownik kliknął
            index = self.text_area._textbox.index(f"@{event.x},{event.y}")
            # 2. Pobieramy całą tę linijkę tekstu
            line = self.text_area._textbox.get(f"{index} linestart", f"{index} lineend")

            # 3. Szukamy w niej informacji o otrzymanym pliku
            # Oczekiwany format: [12:34] [Nadawca]: 📎 Zapisano plik: nazwa.png (w Pobrane_Czat)
            match = re.search(r'\[.*?\] \[(.*?)\]: 📎 Zapisano plik: (.*?) \(w Pobrane_Czat\)', line)

            if match:
                sender = match.group(1)
                filename = match.group(2)

                # Budujemy ścieżkę do pliku na dysku
                filepath = os.path.join("Pobrane_Czat", f"{sender}_{filename}")

                if os.path.exists(filepath):
                    # Otwieramy plik domyślnym programem w systemie
                    if platform.system() == "Windows":
                        os.startfile(filepath)
                    elif platform.system() == "Darwin":  # macOS
                        subprocess.call(("open", filepath))
                    else:  # Linux
                        subprocess.call(("xdg-open", filepath))
                else:
                    messagebox.showerror("Błąd", "Nie znaleziono pliku. Mógł zostać usunięty lub przeniesiony.")
        except Exception as e:
            print(f"Błąd kliknięcia: {e}")

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

    def switch_chat(self, chat_name):
        self.current_chat = chat_name
        self.lbl_current_chat.configure(text=f"Rozmowa: {chat_name}")
        self.text_area.configure(state="normal")
        self.text_area.delete("1.0", "end")
        if chat_name not in self.chat_histories:
            self.chat_histories[chat_name] = ""
        self.text_area.insert("end", self.chat_histories[chat_name])
        self.text_area.configure(state="disabled")
        self.text_area.see("end")

    def append_to_history(self, chat_name, text):
        if chat_name not in self.chat_histories:
            self.chat_histories[chat_name] = ""
        self.chat_histories[chat_name] += text + "\n"
        if self.current_chat == chat_name:
            self.display_message(text)

    def send_file(self):
        filepath = filedialog.askopenfilename(title="Wybierz plik do wysłania")
        if not filepath:
            return

        if os.path.getsize(filepath) > 5 * 1024 * 1024:
            messagebox.showwarning("Za duży plik", "Plik jest za duży! Maksymalny rozmiar to 5MB.")
            return

        filename = os.path.basename(filepath)

        try:
            with open(filepath, "rb") as f:
                raw_bytes = f.read()
                encoded_string = base64.b64encode(raw_bytes).decode('utf-8')

            request = {
                "action": "send_file",
                "target": self.current_chat,
                "filename": filename,
                "data": encoded_string
            }

            self.client_socket.sendall((json.dumps(request) + "\n").encode('utf-8'))

            now = datetime.now().strftime("%H:%M")
            self.append_to_history(self.current_chat, f"[{now}] [Ty]: 📎 Wysłano plik: {filename}")

        except Exception as e:
            messagebox.showerror("Błąd pliku", f"Nie udało się wysłać pliku: {e}")

    def send_message(self):
        msg_text = self.entry_message.get().strip()
        if msg_text:
            now = datetime.now().strftime("%H:%M")
            if self.current_chat == "Globalny":
                request = {"action": "broadcast_message", "content": msg_text}
            elif self.current_chat.startswith("#"):
                request = {"action": "group_message", "group": self.current_chat, "content": msg_text}
                self.append_to_history(self.current_chat, f"[{now}] [Ty]: {msg_text}")
            else:
                request = {"action": "private_message", "recipient": self.current_chat, "content": msg_text}
                self.append_to_history(self.current_chat, f"[{now}] [Ty]: {msg_text}")

            try:
                self.client_socket.sendall((json.dumps(request) + "\n").encode('utf-8'))
                self.entry_message.delete(0, "end")
            except Exception as e:
                messagebox.showerror("Błąd", f"Nie udało się wysłać: {e}")

    def receive_messages(self):
        try:
            for line in self.socket_file:
                if not line.strip():
                    continue

                message = json.loads(line)
                action = message.get("action")

                if action == "chat_message":
                    sender = message.get("sender")
                    content = message.get("content")
                    time_str = message.get("timestamp", "")
                    self.append_to_history("Globalny", f"[{time_str}] [{sender}]: {content}")

                elif action == "private_message":
                    sender = message.get("sender")
                    content = message.get("content")
                    time_str = message.get("timestamp", "")
                    self.append_to_history(sender, f"[{time_str}] [{sender}]: {content}")

                elif action == "group_message":
                    sender = message.get("sender")
                    group = message.get("group")
                    content = message.get("content")
                    time_str = message.get("timestamp", "")
                    self.append_to_history(group, f"[{time_str}] [{sender}]: {content}")

                elif action == "file_message":
                    sender = message.get("sender")
                    target = message.get("target")
                    filename = message.get("filename")
                    file_data = message.get("data")
                    time_str = message.get("timestamp", "")

                    download_dir = "Pobrane_Czat"
                    os.makedirs(download_dir, exist_ok=True)

                    save_path = os.path.join(download_dir, f"{sender}_{filename}")
                    with open(save_path, "wb") as f:
                        f.write(base64.b64decode(file_data))

                    chat_tab = "Globalny"
                    if target != "Globalny":
                        if target.startswith("#"):
                            chat_tab = target
                        else:
                            chat_tab = sender

                    info_text = f"[{time_str}] [{sender}]: 📎 Zapisano plik: {filename} (w Pobrane_Czat)"
                    self.append_to_history(chat_tab, info_text)

                elif action == "user_list":
                    online_users = message.get("users", [])
                    self.update_sidebar_users(online_users)

                elif action == "your_groups":
                    my_groups = message.get("groups", [])
                    self.update_sidebar_groups(my_groups)

                elif action == "chat_history":
                    history_list = message.get("history", [])
                    for msg in history_list:
                        sender = msg.get("sender")
                        content = msg.get("content")
                        time_str = msg.get("timestamp", "")
                        self.append_to_history("Globalny", f"[{time_str}] [{sender}]: {content}")

                elif action == "private_history":
                    history_list = message.get("history", [])
                    for msg in history_list:
                        sender = msg.get("sender")
                        recipient = msg.get("recipient")
                        content = msg.get("content")
                        time_str = msg.get("timestamp", "")

                        chat_partner = recipient if sender == self.username else sender
                        prefix = "Ty" if sender == self.username else sender
                        self.append_to_history(chat_partner, f"[{time_str}] [{prefix}]: {content}")

                elif action == "group_history":
                    group = message.get("group")
                    history_list = message.get("history", [])
                    for msg in history_list:
                        sender = msg.get("sender")
                        content = msg.get("content")
                        time_str = msg.get("timestamp", "")
                        prefix = "Ty" if sender == self.username else sender
                        self.append_to_history(group, f"[{time_str}] [{prefix}]: {content}")

                elif "status" in message:
                    if message["status"] == "error":
                        self.root.after(0, lambda m=message["message"]: messagebox.showerror("Informacja", m))
                    elif message["status"] == "success" and (
                            "Utworzono" in message["message"] or "Dołączono" in message["message"]):
                        self.root.after(0, lambda m=message["message"]: messagebox.showinfo("Sukces", m))

        except Exception as e:
            print(f"Błąd odbierania (klient): {e}")

    def update_sidebar_users(self, users_list):
        def refresh():
            for widget in self.users_scrollable.winfo_children():
                widget.destroy()
            for user in users_list:
                if user == self.username:
                    lbl = ctk.CTkLabel(master=self.users_scrollable, text=f"{user} (Ty)", font=("Roboto", 13, "bold"),
                                       text_color="#1f6aa5")
                else:
                    lbl = ctk.CTkLabel(master=self.users_scrollable, text=user, font=("Roboto", 13), cursor="hand2")
                    lbl.bind("<Button-1>", lambda event, u=user: self.switch_chat(u))
                lbl.pack(anchor="w", pady=2, padx=10)

        self.root.after(0, refresh)

    def update_sidebar_groups(self, groups_list):
        def refresh():
            for widget in self.groups_scrollable.winfo_children():
                widget.destroy()
            for group in groups_list:
                lbl = ctk.CTkLabel(master=self.groups_scrollable, text=group, font=("Roboto", 13, "bold"),
                                   text_color="#2b7b4d", cursor="hand2")
                lbl.bind("<Button-1>", lambda event, g=group: self.switch_chat(g))
                lbl.pack(anchor="w", pady=2, padx=10)

        self.root.after(0, refresh)

    def display_message(self, text):
        self.text_area.configure(state="normal")
        self.text_area.insert("end", text + "\n")
        self.text_area.configure(state="disabled")
        self.text_area.see("end")

    def run(self):
        self.root.mainloop()


if __name__ == "__main__":
    app = ChatClient()
    app.run()
import customtkinter as ctk
from datetime import datetime
from tkinter import messagebox
from server_core import ChatServer

ctk.set_appearance_mode("dark")
ctk.set_default_color_theme("blue")


class ServerApp:
    def __init__(self):
        self.root = ctk.CTk()
        self.root.title("Panel Kontrolny Serwera")
        self.root.geometry("450x450")
        self.root.resizable(False, False)

        # Powołanie do życia Czystego Silnika Serwera!
        self.core = ChatServer(log_callback=self.add_log)

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

        # Startujemy silnik z pliku server_core
        if self.core.start(ip, int(port_str)):
            self.entry_ip.configure(state="disabled")
            self.entry_port.configure(state="disabled")
            self.btn_start.pack_forget()
            self.btn_stop.pack(pady=10)
            self.lbl_status.configure(text=f"Status: Działa na {ip}:{port_str} (E2EE Active)", text_color="#2ecc71")
            self.add_log("--- SERWER URUCHOMIONY ---")
        else:
            messagebox.showerror("Błąd", "Nie udało się uruchomić serwera. Sprawdź logi.")

    def stop_server(self):
        self.core.stop()

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
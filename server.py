import socket
import threading
import json
import database
from datetime import datetime

HOST = '127.0.0.1'
PORT = 9999

active_users = {}
database.init_db()


def broadcast(message_dict):
    json_data = (json.dumps(message_dict) + "\n").encode('utf-8')
    for username, conn in list(active_users.items()):
        try:
            conn.sendall(json_data)
        except Exception as e:
            pass


def broadcast_user_list():
    users = list(active_users.keys())
    packet = {"action": "user_list", "users": users}
    broadcast(packet)


def send_to_user(conn, packet):
    try:
        conn.sendall((json.dumps(packet) + "\n").encode('utf-8'))
    except:
        pass


def handle_client(conn, addr):
    print(f"[NOWE POŁĄCZENIE] Klient {addr} połączył się.")
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
                        broadcast(
                            {"action": "chat_message", "sender": "SYSTEM", "content": f"{username} dołączył do czatu.",
                             "timestamp": now})

                        active_users[username] = conn
                        broadcast_user_list()

                        send_to_user(conn, {"action": "chat_history", "history": database.get_global_history()})
                        send_to_user(conn,
                                     {"action": "private_history", "history": database.get_private_history(username)})

                        user_groups = database.get_user_groups(username)
                        send_to_user(conn, {"action": "your_groups", "groups": user_groups})

                        for g in user_groups:
                            send_to_user(conn, {"action": "group_history", "group": g,
                                                "history": database.get_group_history(g)})
                else:
                    send_to_user(conn, {"status": "error", "message": "Błędny login lub hasło."})

            elif action == 'broadcast_message':
                if current_user:
                    tresc = message.get('content')
                    database.save_message(current_user, "Globalny", tresc)
                    now = datetime.now().strftime("%H:%M")
                    broadcast({"action": "chat_message", "sender": current_user, "content": tresc, "timestamp": now})

            elif action == 'private_message':
                if current_user:
                    odbiorca = message.get("recipient")
                    tresc = message.get("content")
                    database.save_message(current_user, odbiorca, tresc)
                    if odbiorca in active_users:
                        now = datetime.now().strftime("%H:%M")
                        send_to_user(active_users[odbiorca],
                                     {"action": "private_message", "sender": current_user, "content": tresc,
                                      "timestamp": now})

            elif action == 'group_message':
                if current_user:
                    group_name = message.get("group")
                    tresc = message.get("content")
                    database.save_message(current_user, group_name, tresc)

                    now = datetime.now().strftime("%H:%M")
                    msg_packet = {"action": "group_message", "sender": current_user, "group": group_name,
                                  "content": tresc, "timestamp": now}

                    members = database.get_group_members(group_name)
                    for m in members:
                        if m in active_users and m != current_user:
                            send_to_user(active_users[m], msg_packet)

            # --- NOWOŚĆ: Przesyłanie plików ---
            elif action == 'send_file':
                if current_user:
                    target = message.get("target")  # "Globalny", nazwa grupy lub nick
                    filename = message.get("filename")
                    file_data = message.get("data")  # Zakodowane w Base64

                    # Zapisujemy do bazy tylko informację tekstową
                    info_text = f"📎 Przesłano plik: {filename}"
                    database.save_message(current_user, target, info_text)

                    now = datetime.now().strftime("%H:%M")
                    msg_packet = {"action": "file_message", "sender": current_user, "target": target,
                                  "filename": filename, "data": file_data, "timestamp": now}

                    if target == "Globalny":
                        # Wysyłamy do wszystkich oprócz nadawcy
                        for m in active_users:
                            if m != current_user:
                                send_to_user(active_users[m], msg_packet)
                    elif target.startswith("#"):
                        # Wysyłamy do członków grupy
                        members = database.get_group_members(target)
                        for m in members:
                            if m in active_users and m != current_user:
                                send_to_user(active_users[m], msg_packet)
                    else:
                        # Prywatna wiadomość z plikiem
                        if target in active_users:
                            send_to_user(active_users[target], msg_packet)

            elif action == 'create_group':
                if current_user:
                    group_name = message.get("name")
                    if database.create_group(group_name, current_user):
                        send_to_user(conn, {"status": "success", "message": f"Utworzono {group_name}!"})
                        send_to_user(conn, {"action": "your_groups", "groups": database.get_user_groups(current_user)})
                    else:
                        send_to_user(conn, {"status": "error", "message": "Taka grupa już istnieje!"})

            elif action == 'join_group':
                if current_user:
                    group_name = message.get("name")
                    res = database.join_group(group_name, current_user)
                    if res == "OK":
                        send_to_user(conn, {"status": "success", "message": f"Dołączono do {group_name}!"})
                        send_to_user(conn, {"action": "your_groups", "groups": database.get_user_groups(current_user)})
                        send_to_user(conn, {"action": "group_history", "group": group_name,
                                            "history": database.get_group_history(group_name)})
                    else:
                        send_to_user(conn, {"status": "error", "message": res})

    except Exception as e:
        print(f"[BŁĄD] {addr}: {e}")
    finally:
        if current_user in active_users:
            del active_users[current_user]
            now = datetime.now().strftime("%H:%M")
            broadcast({"action": "chat_message", "sender": "SYSTEM", "content": f"{current_user} opuścił czat.",
                       "timestamp": now})
            broadcast_user_list()
        conn.close()
        print(f"[ROZŁĄCZONO] Klient {addr} opuścił serwer.")


def start_server():
    server = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    server.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    server.bind((HOST, PORT))
    server.listen()
    print(f"[START] Serwer nasłuchuje na {HOST}:{PORT}...")

    while True:
        conn, addr = server.accept()
        thread = threading.Thread(target=handle_client, args=(conn, addr))
        thread.start()


if __name__ == "__main__":
    start_server()
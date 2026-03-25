import socket
import json
import time


def send_request(client, request_dict):
    # Wysyłamy słownik jako JSON
    client.sendall(json.dumps(request_dict).encode('utf-8'))
    # Czekamy na odpowiedź
    response_data = client.recv(2048)
    if not response_data:
        return "[BŁĄD] Serwer przerwał połączenie bez odpowiedzi."

    # Zwracamy zdekodowaną odpowiedź
    return json.loads(response_data.decode('utf-8'))


def start_client():
    client = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    client.connect(('127.0.0.1', 9999))

    # Logujemy się na konto Bartek (zostało utworzone w poprzednim teście)
    print("[LOGOWANIE]...")
    log_res = send_request(client, {"action": "login", "username": "Bartek", "password": "mojetajnehaslo"})
    print(log_res)

    # Odbieramy wiadomość systemową o dołączeniu (bo serwer wysyła ją do wszystkich, w tym do nas!)
    system_msg = client.recv(2048)
    print(f"[CZAT] {json.loads(system_msg.decode('utf-8'))}")

    time.sleep(1)  # Czekamy sekundę dla lepszego efektu

    # Wysyłamy wiadomość na czat publiczny
    print("\n[WYSYŁANIE WIADOMOŚCI]...")
    chat_res = send_request(client,
                            {"action": "broadcast_message", "content": "Cześć wszystkim, to mój pierwszy test czatu!"})
    print(chat_res)

    # Odbieramy rozesłaną wiadomość
    chat_msg = client.recv(2048)
    print(f"\n[CZAT] {json.loads(chat_msg.decode('utf-8'))}")

    time.sleep(2)
    client.close()


if __name__ == "__main__":
    start_client()
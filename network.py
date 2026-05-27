import socket
import json
import threading
import os
import base64
from cryptography.fernet import Fernet
from cryptography.hazmat.primitives.asymmetric import ec
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.hashes import SHA256
from cryptography.hazmat.primitives.kdf.hkdf import HKDF
from config import CIPHER_KEY


class NetworkManager:
    def __init__(self, on_message_callback, on_disconnect_callback):
        self.cipher = Fernet(CIPHER_KEY)
        self.client_socket = None
        self.socket_file = None

        # Funkcje z GUI, które wywołamy, gdy przyjdzie pakiet
        self.on_message = on_message_callback
        self.on_disconnect = on_disconnect_callback

        # Klucze do szyfrowania End-to-End (E2EE)
        self.private_key = None
        self.public_key_pem = None

    def connect(self, ip, port):
        try:
            self.client_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            self.client_socket.connect((ip, port))
            self.socket_file = self.client_socket.makefile('r', encoding='utf-8')
            return True
        except Exception:
            return False

    def disconnect(self):
        if self.client_socket:
            try:
                self.client_socket.close()
            except:
                pass
        self.client_socket = None

    def encrypt(self, text):
        """Szyfruje tekst przed wysłaniem w sieć."""
        return self.cipher.encrypt(text.encode('utf-8')).decode('utf-8')

    def decrypt(self, enc_text):
        """Odszyfrowuje tekst z sieci."""
        try:
            return self.cipher.decrypt(enc_text.encode('utf-8')).decode('utf-8')
        except:
            return "🔒 [Nieczytelna wiadomość]"

    def send(self, data_dict):
        """Wysyła słownik JSON do serwera."""
        if not self.client_socket:
            return False
        try:
            self.client_socket.sendall((json.dumps(data_dict) + "\n").encode('utf-8'))
            return True
        except:
            return False

    def auth_request(self, action, username, password):
        """Zarządza logowaniem i rejestracją blokując wątek aż do odpowiedzi."""
        req = {"action": action, "username": username, "password": password}
        if self.send(req):
            try:
                response_line = self.socket_file.readline()
                if response_line:
                    return json.loads(response_line)
            except:
                pass
        return {"status": "error", "message": "Brak połączenia z serwerem."}

    def start_listening(self):
        """Odpala nasłuchiwanie w tle."""
        threading.Thread(target=self._listen_loop, daemon=True).start()

    def _listen_loop(self):
        """Pętla parsująca paczki JSON i rzucająca je do GUI."""
        try:
            for line in self.socket_file:
                if not line.strip(): continue
                message = json.loads(line)
                self.on_message(message)
        except Exception as e:
            print(f"Rozłączono z serwerem: {e}")
        finally:
            self.disconnect()
            self.on_disconnect()

    def load_or_generate_keys(self, username):
        """Wczytuje klucze E2EE użytkownika z pliku lub generuje nowe."""
        os.makedirs("keys", exist_ok=True)
        filepath = os.path.join("keys", f"{username}_private.pem")
        try:
            if os.path.exists(filepath):
                with open(filepath, "rb") as f:
                    self.private_key = serialization.load_pem_private_key(f.read(), password=None)
            else:
                self.private_key = ec.generate_private_key(ec.SECP256R1())
                with open(filepath, "wb") as f:
                    f.write(self.private_key.private_bytes(
                        encoding=serialization.Encoding.PEM,
                        format=serialization.PrivateFormat.TraditionalOpenSSL,
                        encryption_algorithm=serialization.NoEncryption()
                    ))
            
            # Pobranie klucza publicznego w formacie PEM
            pub = self.private_key.public_key()
            self.public_key_pem = pub.public_bytes(
                encoding=serialization.Encoding.PEM,
                format=serialization.PublicFormat.SubjectPublicKeyInfo
            ).decode('utf-8')
            return True
        except Exception as e:
            print(f"Błąd kluczy E2EE dla {username}: {e}")
            return False

    def get_shared_key(self, recipient_pubkey_pem):
        """Wylicza klucz symetryczny za pomocą ECDH i HKDF na bazie klucza odbiorcy."""
        if not self.private_key or not recipient_pubkey_pem:
            return None
        try:
            recipient_pubkey = serialization.load_pem_public_key(recipient_pubkey_pem.encode('utf-8'))
            shared_secret = self.private_key.exchange(ec.ECDH(), recipient_pubkey)
            derived_key = HKDF(
                algorithm=SHA256(),
                length=32,
                salt=None,
                info=b'czatroom-e2ee',
            ).derive(shared_secret)
            return base64.urlsafe_b64encode(derived_key)
        except Exception as e:
            print(f"Błąd ECDH: {e}")
            return None

    def encrypt_e2ee(self, plaintext, recipient_pubkey_pem):
        """Szyfruje treść kluczem wyliczonym przez ECDH."""
        shared_key = self.get_shared_key(recipient_pubkey_pem)
        if not shared_key:
            return "🔒 [Błąd szyfrowania E2EE (brak klucza)]"
        try:
            return Fernet(shared_key).encrypt(plaintext.encode('utf-8')).decode('utf-8')
        except Exception as e:
            return f"🔒 [Błąd szyfrowania E2EE: {e}]"

    def decrypt_e2ee(self, ciphertext, sender_pubkey_pem):
        """Odszyfrowuje treść kluczem wyliczonym przez ECDH."""
        shared_key = self.get_shared_key(sender_pubkey_pem)
        if not shared_key:
            return "🔒 [Błąd deszyfrowania E2EE (brak klucza)]"
        try:
            return Fernet(shared_key).decrypt(ciphertext.encode('utf-8')).decode('utf-8')
        except Exception:
            return "🔒 [Nieczytelna wiadomość E2EE]"
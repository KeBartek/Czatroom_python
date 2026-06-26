# 💬 Czatroom Pro — Bezpieczny Komunikator TCP (E2EE)

**Czatroom Pro** to zaawansowana, wielowątkowa aplikacja czatu klient-serwer napisana w języku Python. Projekt oferuje pełne szyfrowanie wiadomości (End-to-End Encryption - E2EE), dynamiczny interfejs użytkownika oparty o bibliotekę `customtkinter` (zgodny z nowoczesnym stylem Dark Mode), system udostępniania plików, obsługę czatów grupowych oraz integrację z emotikonami z zewnętrznych serwisów (CDN).

Aplikacja została zaprojektowana z myślą o pełnej prywatności użytkowników, elastyczności konfiguracji oraz prostocie uruchamiania na systemach Windows i Linux.

---

## ✨ Główne Funkcje Systemu

### 🔒 Bezpieczeństwo i Kryptografia (E2EE)
*   **Szyfrowanie End-to-End (E2EE):** Wiadomości prywatne i grupowe szyfrowane są bezpośrednio u nadawcy i deszyfrowane dopiero u odbiorcy.
*   **Protokół ECDH (Elliptic Curve Diffie-Hellman):** Klucze szyfrujące sesję są uzgadniane dynamicznie przy użyciu krzywej eliptycznej `SECP256R1`. Klucze prywatne użytkowników są generowane lokalnie i przechowywane w bezpiecznym katalogu `keys/`.
*   **Klucze KDF (HKDF-SHA256):** Wspólny sekret Diffiego-Hellmana jest przekształcany w bezpieczny 256-bitowy klucz symetryczny.
*   **Szyfrowanie Symetryczne AES (Fernet):** Bezpośrednia ochrona treści wiadomości za pomocą uznanego standardu Fernet.
*   **Szyfrowanie Systemowe:** Logi systemowe oraz metadane o statusie użytkowników w bazie danych są chronione globalnym kluczem symetrycznym w celu zapobiegania nieautoryzowanemu odczytowi informacji z bazy SQLite (`chat.db`).

### 👥 Komunikacja i Zarządzanie Grupami
*   **Czat Globalny:** Kanał ogólny dostępny dla wszystkich połączonych użytkowników.
*   **Wiadomości Prywatne (DM):** Bezpośrednie rozmowy E2EE pomiędzy dwoma użytkownikami.
*   **Czaty Grupowe (Kanały):** Możliwość tworzenia prywatnych pokoi rozmów (z prefiksem `#`). Założyciel grupy posiada uprawnienia administratora:
    *   Zapraszanie innych użytkowników do grupy.
    *   Akceptowanie lub odrzucanie próśb o dołączenie.
    *   Wyrzucanie członków z grupy (Kick).
    *   Usuwanie grupy.
*   **Statusy aktywności:** Wyświetlanie listy zalogowanych użytkowników (Online/Offline) oraz dynamiczny wskaźnik pisania (*"Użytkownik pisze..."*).

### 📁 Udostępnianie Plików i Multimedia
*   **File Transfer:** Wysyłanie plików wewnątrz czatu. Pliki są kodowane w standardzie Base64, przesyłane na serwer (zapisywane w katalogu `Serwer_Pliki`) i mogą być pobierane przez odbiorców bezpośrednio z poziomu interfejsu graficznego.
*   **Formatowanie Tekstu (Markdown):** Obsługa podstawowego formatowania w oknie czatu (pogrubienie, kursywa, przekreślenie, bloki kodu o stałej szerokości znaków).
*   **Emotikony z CDN:** Wsparcie dla niestandardowych emotek (np. `:pepe:`, `:kekw:`, `:catjam:`) pobieranych dynamicznie z FrankerFacez CDN z wbudowanym systemem lokalnego buforowania w katalogach `Cache_Emotki`/`Cache_Obrazki`.
*   **Dźwiękowe Powiadomienia:** Odtwarzanie dźwięku powiadomienia (`notification.wav`) przy nadejściu nowej wiadomości.

---

## 🛠️ Architektura Projektu i Pliki źródłowe

```
Czatroom_pro/
│
├── client.py            # Kod źródłowy aplikacji klienckiej (Interfejs customtkinter + pętla zdarzeń)
├── server.py            # Panel kontrolny serwera (Graficzny podgląd logów i stanu sieci)
├── server_core.py       # Logika sieciowa serwera (Obsługa połączeń TCP, wątkowanie, routing żądań)
├── network.py           # Menadżer połączeń klienta (Wymiana kluczy ECDH, szyfrowanie/deszyfrowanie, gniazda TCP)
├── database.py          # Moduł SQLite (Przechowywanie użytkowników, haseł SHA-256, historii oraz relacji grupowych)
├── config.py            # Plik konfiguracyjny (Paleta kolorów GUI, baza emotek, klucze systemowe, cache)
│
├── requirements.txt     # Zależności biblioteczne projektu
├── notification.wav     # Plik dźwiękowy powiadomień
│
├── Czatroom_Klient.spec # Plik konfiguracyjny PyInstaller dla Klienta
└── Czatroom_Serwer.spec # Plik konfiguracyjny PyInstaller dla Serwera
```

### Zastosowane technologie:
*   **Język:** Python 3.10+
*   **Interfejs:** CustomTkinter (nakładka na Tkinter oferująca pełny Dark Mode i zaokrąglone widgety)
*   **Baza danych:** SQLite3 (wbudowana baza plikowa `chat.db`)
*   **Kryptografia:** Biblioteka `cryptography` (Fernet, ECDH, HKDF)
*   **Obsługa Audio & Systemowa:** `plyer` (powiadomienia desktopowe) oraz standardowe biblioteki `socket`, `threading`, `json`.

---

## 🚀 Uruchamianie Projektu

### 1. Przygotowanie środowiska i instalacja zależności

Przed pierwszym uruchomieniem należy upewnić się, że zainstalowane są wszystkie wymagane biblioteki:

```bash
pip install -r requirements.txt
```

Zawartość pliku `requirements.txt`:
*   `customtkinter` — Nowoczesny interfejs graficzny.
*   `pillow` — Obsługa obrazków i emotek.
*   `requests` — Pobieranie emotek z zewnętrznych serwerów CDN.
*   `cryptography` — Operacje kryptograficzne (ECDH, Fernet, SHA-256).
*   `plyer` — Powiadomienia w systemie operacyjnym.

### 2. Uruchomienie Serwera

Serwer można uruchomić za pomocą pliku `server.py`. Wyświetli on graficzny interfejs (Panel Kontrolny), umożliwiający konfigurację adresu IP oraz portu nasłuchiwania.

```bash
python server.py
```

*   **Domyślny adres:** `127.0.0.1` (localhost)
*   **Domyślny port:** `9999`
*   Po kliknięciu **Uruchom Serwer** aplikacja zacznie nasłuchiwać nadchodzących połączeń. Podgląd logów w czasie rzeczywistym wyświetli rejestrację, logowania oraz zdarzenia sieciowe.

### 3. Uruchomienie Klienta

Każdy z użytkowników chcących dołączyć do czatu powinien uruchomić aplikację kliencką:

```bash
python client.py
```

*   W oknie startowym należy podać adres IP i port działającego serwera, a następnie zalogować się lub zarejestrować nowe konto.
*   Dane autoryzacyjne (login oraz hash hasła) są przesyłane bezpiecznym połączeniem i zapisywane w bazie danych serwera.

---

## 📦 Budowanie do plików wykonywalnych (.EXE / Standalone)

W projekcie przygotowano dedykowane pliki konfiguracyjne `.spec` dla narzędzia **PyInstaller**. Pozwala to na skompilowanie aplikacji do pojedynczych plików `.exe` (na Windowsie) lub binariów (na Linuxie), które nie wymagają zainstalowanego Pythona u użytkownika końcowego.

Aby zbudować wersje binarne:

1. Zainstaluj PyInstaller:
   ```bash
   pip install pyinstaller
   ```
2. Skompiluj klienta:
   ```bash
   pyinstaller Czatroom_Klient.spec
   ```
3. Skompiluj serwer:
   ```bash
   pyinstaller Czatroom_Serwer.spec
   ```

Gotowe pliki wykonywalne znajdziesz w nowo powstałym katalogu `dist/`.

---

## 🔒 Bezpieczeństwo danych w repozytorium Git — Ważne wskazówki!

Zanim dodasz projekt do zdalnego repozytorium (np. na GitHub), upewnij się, że nie publikujesz wrażliwych danych wygenerowanych w trakcie testów. Plik `.gitignore` w tym projekcie został skonfigurowany tak, aby ignorować:
*   Klucze prywatne użytkowników (`keys/*_private.pem`)
*   Bazę danych SQLite (`chat.db`)
*   Foldery pamięci podręcznej (`Cache_Obrazki/`, `Cache_Emotki/`, `Cache_Avatary/`)
*   Pliki wysyłane na serwer (`Serwer_Pliki/` i `Pobrane_Czat/`)
*   Katalogi kompilacji PyInstallera (`build/`, `dist/`, `.venv/`, `.idea/`)

Wszystkie powyższe pliki i katalogi zostaną automatycznie pominięte przy poleceniu `git add .`.

---

*Projekt stworzony w ramach zaliczenia przedmiotu aplikacji sieciowych / programowania bezpiecznych systemów.*

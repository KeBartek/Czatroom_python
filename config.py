import os

# --- KLUCZE I ZABEZPIECZENIA ---
CIPHER_KEY = b'MDEyMzQ1Njc4OTAxMjM0NTY3ODkwMTIzNDU2Nzg5MDE='

# --- PALETA KOLORÓW ---
C_NOTIFICATION_BG = "#2B2D31"
C_BG_LEFT = "#1E1F22"
C_BG_MID = "#2B2D31"
C_BG_RIGHT = "#2B2D31"
C_CHAT_BOX = "#313338"
C_INPUT_BG = "#383A40"
C_PRIMARY = "#5865F2"
C_PRIMARY_HOVER = "#4752C4"
C_TEXT_MAIN = "#DBDEE1"
C_TEXT_MUTED = "#949BA4"
C_HOVER = "#3F4147"
C_ONLINE = "#23A559"

# --- BAZA EMOTEK ---
EMOTES_DB = {
    ":pepe:": "https://cdn.frankerfacez.com/emoticon/28087/1",
    ":pog:": "https://cdn.frankerfacez.com/emoticon/210748/1",
    ":kekw:": "https://cdn.frankerfacez.com/emoticon/381875/1",
    ":catjam:": "https://cdn.frankerfacez.com/emoticon/520322/1",
    ":sadge:": "https://cdn.frankerfacez.com/emoticon/425196/1",
    ":monkas:": "https://cdn.frankerfacez.com/emoticon/130762/1",
    ":ez:": "https://cdn.frankerfacez.com/emoticon/108566/1"
}

# --- SYSTEM PLIKÓW ---
os.makedirs("Cache_Obrazki", exist_ok=True)
os.makedirs("Cache_Emotki", exist_ok=True)
import os

# Telegram Bot Token
BOT_TOKEN = "8611766126:AAE3QdKQHauKc99qs2D8wmE0GwZpGNyU7hk"
BOT_USERNAME = "@legacydumperbot"

# Admin Information
ADMINS = {
    5707956654: "@legacydevx",
    6049120581: "@legacyxanku"
}

# Hex Patterns from run.py
IMPORTANT_PATTERNS = {
    "HOOK_SIGNATURE": bytes.fromhex("51 00 00 58 20 02 1F D6"),
    "FULL_PATTERN": bytes.fromhex("00 00 80 D2 C0 03 5F D6"),
    "PARTIAL_PATTERN": bytes.fromhex("C0 03 5F D6"),
    "ROOT_BYPASS": bytes.fromhex("20 00 80 D2 C0 03 5F D6")
}

PATCH_ROOT_CHECK = {
    "pattern": bytes.fromhex("20 00 80 D2 C0 03 5F D6"),
    "replacement": bytes.fromhex("00 00 80 D2 C0 03 5F D6")
}

# Library Configuration (Maps detected name to file path)
BASE_LIBS_DIR = os.path.join(os.path.dirname(__file__), "base_libs")

LIBS_CONFIG = {
    "Anogs": "libanogs.so",
    "hdmvp": "libhdmpve.so",
    "TblueData": "libTBlueData.so",
    "UE4": "libUE4.so",
    "AntsVoice": "libAntsVoice.so",
    "RoosterNN": "libRoosterNN.so"
}

# Paths for data and logs
DATA_DIR = os.path.join(os.path.dirname(__file__), "data")
LOGS_DIR = os.path.join(os.path.dirname(__file__), "logs")
# Copying banner to bot folder as well
BANNER_PATH = os.path.join(os.path.dirname(__file__), "banner.jpg")
DATABASE_PATH = os.path.join(DATA_DIR, "legacy_core.db")

# Force Join Configuration
MUST_JOIN_ID = -1003729793140
MUST_JOIN_URL = "https://t.me/+UZEwuXC7b_plZDJl"

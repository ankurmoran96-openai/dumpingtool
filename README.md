# 🛡️ Legacy Dumper Bot

Professional Telegram bot for **BGMI (Battlegrounds Mobile India)** and other Unreal Engine games. Automates the process of scanning, dumping, and patching `.so` libraries to bypass security checks.

## ✨ Features

- ✅ **Auto-Dumping:** Compares original vs. dumped libraries to identify changes.
- ✅ **Hook Detection:** Automatically scans for sensitive security offsets and hook signatures.
- ✅ **Pro Patching:** Built-in logic to patch binaries and bypass Root/Security checks.
- ✅ **Bulk Processing:** Supports `.zip` archives for processing multiple files simultaneously.
- ✅ **Gofile Integration:** Automatically uploads large files to Gofile for easy sharing.
- ✅ **Subscription System:** Built-in key generation and redemption system for user management.

## 🛠️ Components

- **`bot.py`**: The main Telegram bot script.
- **`obfuscate_ultra.py`**: A powerful Lua obfuscation tool for the dumper script.
- **`tools/`**:
  - `LegacyCoreDumper.lua`: The GameGuardian script used to dump memory on the device.
  - `Legacy Guardian.apk`: Recommended Virtual App for non-root users.

## 🚀 Getting Started

### Prerequisites

- Python 3.10+
- A Telegram Bot Token from [@BotFather](https://t.me/BotFather)

### Installation

1. Clone the repository:
   ```bash
   git clone https://github.com/ankurmoran96-openai/dumpingtool.git
   cd dumpingtool
   ```

2. Install dependencies:
   ```bash
   pip install -r requirements.txt
   ```

3. Set up environment variables (optional, defaults are provided in the code):
   ```bash
   export BOT_TOKEN="your_bot_token"
   export COMMUNITY_ID="-100xxxx"
   ```

4. Run the bot:
   ```bash
   python bot.py
   ```

## 🔐 Obfuscation

To protect your Lua script before distribution, use the built-in obfuscator:

```bash
python obfuscate_ultra.py
```

This will apply "Synthetic Neural Sentinel" obfuscation to `tools/LegacyCoreDumper.lua`.

## 👨‍💻 Credits

- **Owner:** @LegacyDevX
- **Developer:** @LegacyxAnku

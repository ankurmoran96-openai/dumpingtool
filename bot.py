import os
import sqlite3
import random
import string
import telebot
from telebot import apihelper
from telebot.types import InlineKeyboardMarkup, InlineKeyboardButton
import requests
from datetime import datetime, timedelta
from urllib.parse import urlparse
import zipfile
import shutil
import re
import mmap
import time

# --- CONFIGURATION ---
BOT_TOKEN = '8611766126:AAE3QdKQHauKc99qs2D8wmE0GwZpGNyU7hk'
COMMUNITY_ID = '-1003729793140'
COMMUNITY_LINK = "https://t.me/+UZEwuXC7b_plZDJl"
ADMIN_IDS = [5707956654, 6049120581]
PROXY_URL = os.environ.get('PROXY_URL')

# Apply proxy if provided for telebot
if PROXY_URL:
    apihelper.proxy = {'https': PROXY_URL, 'http': PROXY_URL}

bot = telebot.TeleBot(BOT_TOKEN)

def get_requests_proxies():
    if PROXY_URL:
        return {'https': PROXY_URL, 'http': PROXY_URL}
    return None

user_states = {}

def init_db():
    conn = sqlite3.connect('dumper.db')
    c = conn.cursor()
    c.execute('''CREATE TABLE IF NOT EXISTS keys (key_text TEXT PRIMARY KEY, duration_days INTEGER)''')
    c.execute('''CREATE TABLE IF NOT EXISTS users (user_id INTEGER PRIMARY KEY, expiry_date TIMESTAMP)''')
    conn.commit()
    conn.close()

init_db()

def is_authorized(user_id):
    if user_id in ADMIN_IDS: return True
    try:
        conn = sqlite3.connect('dumper.db')
        c = conn.cursor()
        c.execute("SELECT expiry_date FROM users WHERE user_id=?", (user_id,))
        result = c.fetchone()
        conn.close()
        if result:
            expiry = datetime.fromisoformat(result[0])
            if datetime.now() < expiry: return True
    except Exception:
        pass
    return False

def check_membership(user_id):
    if COMMUNITY_ID == 'YOUR_CHANNEL_ID_HERE': return True
    try:
        member = bot.get_chat_member(COMMUNITY_ID, user_id)
        return member.status in ['member', 'administrator', 'creator']
    except Exception: return False

def ensure_access(message):
    user_id = message.from_user.id
    if not check_membership(user_id):
        bot.reply_to(message, f"<b>⚠️ Access Denied!</b>\n\nPlease join our community to use this bot.\n👉 {COMMUNITY_LINK}", parse_mode="HTML")
        return False
    if not is_authorized(user_id):
        bot.reply_to(message, "<b>You don't have permission to use this bot, please get keys from authority</b>", parse_mode="HTML")
        return False
    return True

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

def get_auto_range(file_path):
    if os.path.exists(file_path): return 0x0, int(os.path.getsize(file_path) * 0.995)
    return 0x0, 0x0

def is_important_pattern(data, offset):
    for pattern_name, pattern_bytes in IMPORTANT_PATTERNS.items():
        if offset + len(pattern_bytes) <= len(data) and data[offset:offset + len(pattern_bytes)] == pattern_bytes:
            return pattern_name, pattern_bytes
    return None, None

def scan_single_dump_pro(original_path, dump_path, start_offset, end_offset, log_file, lib_name):
    if not os.path.exists(original_path) or not os.path.exists(dump_path): return 0, []

    f1 = open(original_path, "rb")
    f2 = open(dump_path, "rb")

    # Use memory mapping for large files (like libUE4.so)
    try:
        m1 = mmap.mmap(f1.fileno(), 0, access=mmap.ACCESS_READ)
        m2 = mmap.mmap(f2.fileno(), 0, access=mmap.ACCESS_READ)
    except Exception:
        f1.close(); f2.close()
        return 0, []

    file_size = min(len(m1), len(m2), end_offset)
    try:
        with open(log_file, "w", encoding='utf-8') as log:
            log.write(f"=== LEGACY CORE PVT TOOL ===\nLibrary: {lib_name}\nScan Time: {datetime.now()}\nOriginal: {os.path.basename(original_path)}\nDump: {os.path.basename(dump_path)}\n" + "=" * 50 + "\n\n")
    except Exception:
        m1.close(); m2.close()
        f1.close(); f2.close()
        return 0, []

    hooks_found = 0
    extracted_offsets = []
    i = start_offset

    with open(log_file, "a", encoding='utf-8') as log:
        while i < file_size:
            # Check for differences first (fast comparison)
            if m1[i] != m2[i]:
                # If a difference is found, check for important patterns in the dumped file
                pattern_name, pattern_bytes = is_important_pattern(m2, i)
                if pattern_name:
                    if pattern_name == "HOOK_SIGNATURE":
                        log.write(f"0x{i:06X} HOOK OFFSET\n")
                        extracted_offsets.append(f"0x{i:06X} // HOOK_SIGNATURE")
                        hooks_found += 1
                        i += 16 # Skip the rest of the hook signature
                    else:
                        hex_str = ' '.join(f"{m2[i + j]:02X}" for j in range(len(pattern_bytes)))
                        log.write(f"0x{i:06X} {hex_str} // {pattern_name}\n")
                        extracted_offsets.append(f"0x{i:06X} // {pattern_name}")
                        hooks_found += 1
                        i += len(pattern_bytes)
                else: i += 1 # Not an important pattern, just a random difference
            else: i += 1
        log.write(f"\n" + "=" * 50 + f"\nTOTAL IMPORTANT HOOKS: {hooks_found}\nLIBRARY: {lib_name}\nSCAN COMPLETED: {datetime.now()}\n")

    m1.close(); m2.close()
    f1.close(); f2.close()
    return hooks_found, extracted_offsets

def patch_binary_pro(dump_path, output_path):
    if not os.path.exists(dump_path): return False
    try:
        with open(dump_path, "rb") as f: data = bytearray(f.read())
        patched, idx = False, 0
        while idx < len(data):
            idx = data.find(PATCH_ROOT_CHECK["pattern"], idx)
            if idx == -1: break
            data[idx:idx+len(PATCH_ROOT_CHECK["pattern"])] = PATCH_ROOT_CHECK["replacement"]
            patched = True
            idx += len(PATCH_ROOT_CHECK["pattern"])
        if patched:
            os.makedirs(os.path.dirname(output_path), exist_ok=True)
            with open(output_path, "wb") as f: f.write(data)
            return True
        return False
    except Exception: return False

def upload_to_gofile(file_path):
    try:
        proxies = get_requests_proxies()
        server_res = requests.get("https://api.gofile.io/servers", proxies=proxies).json()
        if server_res['status'] != 'ok': return None
        server = server_res['data']['servers'][0]['name']
        with open(file_path, 'rb') as f: upload_res = requests.post(f"https://{server}.gofile.io/contents/uploadfile", files={'file': f}, proxies=proxies).json()
        if upload_res['status'] == 'ok': return upload_res['data']['downloadPage']
        return None
    except Exception: return None

def download_from_url(url, file_path):
    try:
        proxies = get_requests_proxies()
        response = requests.get(url, stream=True, proxies=proxies)
        response.raise_for_status()
        with open(file_path, 'wb') as f:
            for chunk in response.iter_content(chunk_size=8192): f.write(chunk)
        return True
    except Exception: return False

def extract_archive(archive_path, extract_to):
    try:
        with zipfile.ZipFile(archive_path, 'r') as zip_ref:
            zip_ref.extractall(extract_to)
        return True
    except Exception:
        return False

# UI and Key commands
def main_menu_keyboard():
    markup = InlineKeyboardMarkup()
    markup.add(InlineKeyboardButton("👨‍💻 Owner", url="https://t.me/LegacyDevX"), InlineKeyboardButton("👨‍💻 Developer", url="https://t.me/LegacyDevX"))
    markup.add(InlineKeyboardButton("📖 Help & Guide", callback_data="help_menu"))
    markup.add(InlineKeyboardButton("👥 Community", url=COMMUNITY_LINK))
    return markup

def back_keyboard():
    markup = InlineKeyboardMarkup()
    markup.add(InlineKeyboardButton("⬅️ Back to Main", callback_data="back_to_main"))
    return markup

def done_keyboard():
    markup = InlineKeyboardMarkup()
    markup.add(InlineKeyboardButton("✅ Done Dumping", callback_data="dump_done"))
    return markup

@bot.message_handler(commands=['start'])
def start_cmd(message):
    banner_path = "banner.jpg"
    welcome_text = get_welcome_text(message.from_user.id)
    if os.path.exists(banner_path):
        with open(banner_path, 'rb') as photo:
            bot.send_photo(message.chat.id, photo, caption=welcome_text, parse_mode="HTML", reply_markup=main_menu_keyboard())
    else:
        bot.reply_to(message, welcome_text, parse_mode="HTML", reply_markup=main_menu_keyboard())

@bot.callback_query_handler(func=lambda call: True)
def callback_query(call):
    chat_id = call.message.chat.id
    if call.data == "help_menu":
        bot.edit_message_caption(help_text, chat_id=chat_id, message_id=call.message.message_id, parse_mode="HTML", reply_markup=back_keyboard())
    elif call.data == "back_to_main":
        bot.edit_message_caption(get_welcome_text(call.from_user.id), chat_id=chat_id, message_id=call.message.message_id, parse_mode="HTML", reply_markup=main_menu_keyboard())
    elif call.data == "dump_done":
        try: bot.delete_message(chat_id, call.message.message_id)
        except: pass
        user_states[chat_id] = {'step': 'waiting_for_dump'}
        bot.send_message(chat_id, "🚀 <b>Excellent!</b> Now please upload the <b>DUMPED</b> <code>.so</code> file you generated.\n\n<i>You can also send a direct download link.</i>", parse_mode="HTML")

@bot.message_handler(commands=['gen'])
def gen_key(message):
    if message.from_user.id not in ADMIN_IDS: return
    try:
        args = message.text.split()
        if len(args) < 2:
            return bot.reply_to(message, "⚠️ Usage: <code>/gen &lt;name&gt; &lt;days&gt;d</code>\nExample: <code>/gen user1 30d</code>", parse_mode="HTML")
        
        name = args[1]
        days_str = args[2] if len(args) > 2 else "30d"
        days = int(days_str.replace('d', ''))
        
        key = "LEGACY-" + ''.join(random.choices(string.ascii_uppercase + string.digits, k=10))
        
        conn = sqlite3.connect('dumper.db'); c = conn.cursor()
        c.execute("INSERT INTO keys (key_text, duration_days) VALUES (?, ?)", (key, days))
        conn.commit(); conn.close()
        
        bot.reply_to(message, f"🔑 <b>Key Generated Successfully!</b>\n\n👤 Name: <code>{name}</code>\n⏳ Duration: <code>{days} days</code>\n🎟️ Key: <code>{key}</code>\n\n<i>Copy and send to the user.</i>", parse_mode="HTML")
    except Exception as e:
        bot.reply_to(message, f"❌ <b>Error:</b> {str(e)}", parse_mode="HTML")

@bot.message_handler(commands=['redeem'])
def redeem_key(message):
    args = message.text.split()
    if len(args) < 2:
        return bot.reply_to(message, "⚠️ Usage: <code>/redeem &lt;key&gt;</code>\nExample: <code>/redeem LEGACY-ABC123XYZ</code>", parse_mode="HTML")
    
    key = args[1]
    user_id = message.from_user.id
    
    try:
        conn = sqlite3.connect('dumper.db'); c = conn.cursor()
        c.execute("SELECT duration_days FROM keys WHERE key_text=?", (key,))
        result = c.fetchone()
        
        if not result:
            conn.close()
            return bot.reply_to(message, "❌ <b>Invalid or used key!</b>", parse_mode="HTML")
        
        days = result[0]
        c.execute("DELETE FROM keys WHERE key_text=?", (key,))
        
        # Calculate new expiry
        c.execute("SELECT expiry_date FROM users WHERE user_id=?", (user_id,))
        user_res = c.fetchone()
        
        current_expiry = datetime.now()
        if user_res:
            try:
                old_expiry = datetime.fromisoformat(user_res[0])
                if old_expiry > current_expiry: current_expiry = old_expiry
            except: pass
            
        new_expiry = (current_expiry + timedelta(days=days)).isoformat()
        c.execute("INSERT OR REPLACE INTO users (user_id, expiry_date) VALUES (?, ?)", (user_id, new_expiry))
        
        conn.commit(); conn.close()
        bot.reply_to(message, f"✅ <b>Success!</b>\nSubscription activated for <code>{days} days</code>.\n📅 New Expiry: <code>{new_expiry[:10]}</code>", parse_mode="HTML")
    except Exception as e:
        bot.reply_to(message, f"❌ <b>Redeem Error:</b> {str(e)}", parse_mode="HTML")

@bot.message_handler(commands=['del'])
def delete_key(message):
    if message.from_user.id not in ADMIN_IDS: return
    args = message.text.split()
    if len(args) < 2:
        return bot.reply_to(message, "⚠️ Usage: <code>/del &lt;key&gt;</code>", parse_mode="HTML")
    
    key = args[1]
    try:
        conn = sqlite3.connect('dumper.db'); c = conn.cursor()
        c.execute("DELETE FROM keys WHERE key_text=?", (key,))
        conn.commit(); conn.close()
        bot.reply_to(message, f"🗑️ Key <code>{key}</code> deleted from database.", parse_mode="HTML")
    except Exception as e:
        bot.reply_to(message, f"❌ <b>Delete Error:</b> {str(e)}", parse_mode="HTML")

def get_welcome_text(user_id):
    sub_status = "✅ <b>Active</b>" if is_authorized(user_id) else "❌ <b>Inactive</b> (Use /redeem)"
    return f"""<b>🚀 Legacy Core Dumper</b>

This bot is specifically designed for <b>BGMI</b> and other UE4 games. Use the <b>/dump</b> command to get the required tools and start scanning your targeted modded APKs.

<b>🌟 Main Features:</b>
✅ <b>Instant-Scan:</b> No need for original files (6+ Libs Supported).
✅ <b>Memory Mapping:</b> Fast scanning of 200MB+ libraries.
✅ <b>Interactive Workflow:</b> Integrated dumping guide and tools.
✅ <b>One-Step Results:</b> Automated comparison and offset extraction.

<b>🔑 Subscription:</b> {sub_status}

<b>👨‍💻 Credits:</b>
• <b>Owner:</b> @LegacyDevX
• <b>Developer:</b> @LegacyDevX

<i>Use <b>/dump</b> to start!</i>"""

help_text = """<b>📚 How to Use Legacy Core</b>

1️⃣ <b>Initialize:</b> Use the <code>/dump</code> command to get the setup tools.
2️⃣ <b>Dumping:</b> Follow the guide to dump your targeted <code>.so</code> file from memory using the provided Lua script.
3️⃣ <b>Upload:</b> Click "Done" and upload your <b>DUMPED</b> file.
4️⃣ <b>Results:</b> The bot will automatically analyze the file and provide all detected offsets.

🛡️ <b>Support:</b> Contact @LegacyDevX for keys or help."""

admin_cmds_text = """<b>🛡️ Admin Control Panel</b>\n
<b>OWNER: @LegacyDevX</b>
<b>DEVELOPER: @LegacyDevX</b>\n
• <code>/gen &lt;name&gt; &lt;days&gt;d</code> - Generate a new subscription key.
• <code>/del &lt;key&gt;</code> - Delete a specific key from the database.
• <code>/addbase</code> - Upload an official library to the base database.
• <code>/users</code> - View total authorized users."""

@bot.message_handler(commands=['dump'])
def dump_cmd(message):
    if not ensure_access(message): return
    
    instructions = """<b>🛠️ Legacy Core - BGMI Dumping Guide</b>

Please use the tools below to dump your targeted modded APK:

1. <b>MODDED BGMI APK:</b> Ensure your modded APK is installed.
2. <b>VIRTUAL APP:</b> Use the provided "Legacy Guardian" for non-root setup.
3. <b>LUA SCRIPT:</b> Run the obfuscated "LegacyCoreDumper.lua" in GameGuardian.

-------------------------------------------
🚀 <b>INSTRUCTIONS:</b>
• Open the <b>Modded Game</b> inside the Virtual app.
• Select the game process in <b>GameGuardian</b>.
• Execute the <b>LegacyCoreDumper.lua</b> script.
• Your dump will be saved at: <code>/sdcard/dump/</code>

<b>⚠️ Tap the button below ONLY after you have finished dumping!</b>"""

    script_path = "tools/LegacyCoreDumper.lua"
    virtual_path = "tools/Legacy Guardian.apk"
    
    media = []
    files_to_close = []

    try:
        if os.path.exists(script_path):
            f1 = open(script_path, 'rb')
            media.append(telebot.types.InputMediaDocument(f1))
            files_to_close.append(f1)
        
        if os.path.exists(virtual_path):
            f2 = open(virtual_path, 'rb')
            media.append(telebot.types.InputMediaDocument(f2))
            files_to_close.append(f2)

        if media:
            # Add caption to the last file to ensure it shows with the button
            media[-1].caption = instructions
            media[-1].parse_mode = "HTML"
            bot.send_media_group(message.chat.id, media)
            # Send the button separately as media group doesn't support inline buttons on captions well
            bot.send_message(message.chat.id, "⬇️ <b>Setup Complete! Tap when ready:</b>", parse_mode="HTML", reply_markup=done_keyboard())
        else:
            bot.reply_to(message, "⚠️ <b>Error:</b> Tools folder is empty. Contact Admin.", parse_mode="HTML")
            
    except Exception as e:
        bot.reply_to(message, f"❌ <b>Error:</b> {str(e)}", parse_mode="HTML")
    finally:
        for f in files_to_close: f.close()

@bot.message_handler(commands=['addbase'])
def add_base_cmd(message):
    if message.from_user.id not in ADMIN_IDS: return
    user_states[message.chat.id] = {'step': 'waiting_for_base_lib'}
    bot.reply_to(message, "📤 Please upload the <b>OFFICIAL (Clean)</b> <code>.so</code> file to add to the base database.", parse_mode="HTML")

@bot.message_handler(commands=['admincmds'])
def admin_cmds(message):
    if message.from_user.id not in ADMIN_IDS: return
    bot.reply_to(message, admin_cmds_text, parse_mode="HTML", reply_markup=main_menu_keyboard())

@bot.message_handler(commands=['users'])
def list_users(message):
    if message.from_user.id not in ADMIN_IDS: return
    conn = sqlite3.connect('dumper.db'); c = conn.cursor()
    c.execute("SELECT COUNT(*) FROM users")
    total_users = c.fetchone()[0]
    now = datetime.now().isoformat()
    c.execute("SELECT COUNT(*) FROM users WHERE expiry_date > ?", (now,))
    active_users = c.fetchone()[0]
    conn.close()
    bot.reply_to(message, f"📊 <b>User Statistics</b>\n\n👥 Total Users: <code>{total_users}</code>\n✅ Active Users: <code>{active_users}</code>", parse_mode="HTML")

def process_state_file(message, file_name, file_path_or_download_func, is_url=False):
    if not ensure_access(message): return
    chat_id = message.chat.id
    
    # Handle Admin adding base lib
    if chat_id in user_states and user_states[chat_id].get('step') == 'waiting_for_base_lib':
        if not file_name.endswith('.so'):
            return bot.reply_to(message, "❌ Please upload a <code>.so</code> file for the base database.", parse_mode="HTML")
        os.makedirs('base_libs', exist_ok=True)
        base_path = f"base_libs/{file_name}"
        success = file_path_or_download_func(base_path)
        if success:
            bot.reply_to(message, f"✅ <b>{file_name}</b> has been added to the Official Base Database.", parse_mode="HTML")
            user_states[chat_id] = {'step': 'waiting_for_original'}
        else:
            bot.reply_to(message, "❌ Failed to save base library.")
        return

    if chat_id not in user_states: user_states[chat_id] = {'step': 'waiting_for_original'}
    state = user_states[chat_id]
    os.makedirs('tmp_files', exist_ok=True)
    
    is_zip = file_name.lower().endswith('.zip')
    
    # Check if a base library exists for this file
    if state['step'] == 'waiting_for_original' and not is_zip:
        base_lib_path = f"base_libs/{file_name}"
        if os.path.exists(base_lib_path):
            msg = bot.reply_to(message, f"🔍 <b>Base Match Found!</b>\nDownloading your dump: <code>{file_name}</code>...", parse_mode="HTML")
            dump_path = f"tmp_files/dump_{chat_id}_{file_name}"
            success = file_path_or_download_func(dump_path)
            if success:
                state['original_path'] = base_lib_path
                state['dump_path'] = dump_path
                state['step'] = 'processing'
                
                # Animated Processing
                bot.edit_message_text("🔄 <b>Comparing libs...</b>", chat_id=chat_id, message_id=msg.message_id, parse_mode="HTML")
                time.sleep(1)
                bot.edit_message_text("🔍 <b>Analyzing offsets...</b>", chat_id=chat_id, message_id=msg.message_id, parse_mode="HTML")
                time.sleep(1)
                bot.edit_message_text("⚙️ <b>Finishing up...</b>", chat_id=chat_id, message_id=msg.message_id, parse_mode="HTML")
                
                process_files(chat_id, msg)
                return
            else:
                return bot.edit_message_text("❌ Download failed.", chat_id=chat_id, message_id=msg.message_id)

    msg = bot.reply_to(message, f"⏳ Downloading <code>{file_name}</code>...", parse_mode="HTML")
    
    if state['step'] == 'waiting_for_original':
        file_path = f"tmp_files/orig_{chat_id}_{file_name}"
        success = file_path_or_download_func(file_path)
        if success:
            state['original_path'] = file_path
            state['is_zip'] = is_zip
            state['step'] = 'waiting_for_dump'
            bot.edit_message_text(f"✅ Received <b>ORIGINAL</b> {'Archive' if is_zip else 'File'}: <code>{file_name}</code>\n\nNow, send me the <b>DUMPED</b> {'Archive' if is_zip else 'File'} (Link or Upload).\n\n💡 Use <b>/dump</b> for tools.", chat_id=chat_id, message_id=msg.message_id, parse_mode="HTML")
        else: bot.edit_message_text("❌ Download failed.", chat_id=chat_id, message_id=msg.message_id)
            
    elif state['step'] == 'waiting_for_dump':
        if is_zip != state.get('is_zip', False):
            return bot.edit_message_text("⚠️ Format mismatch! Send a ZIP if you sent a ZIP originally.", chat_id=chat_id, message_id=msg.message_id)
            
        file_path = f"tmp_files/dump_{chat_id}_{file_name}"
        success = file_path_or_download_func(file_path)
        if success:
            state['dump_path'] = file_path
            state['step'] = 'processing'
            bot.edit_message_text("🔄 <b>Comparing libs...</b>", chat_id=chat_id, message_id=msg.message_id, parse_mode="HTML")
            time.sleep(1)
            bot.edit_message_text("⚙️ <b>Processing results...</b>", chat_id=chat_id, message_id=msg.message_id, parse_mode="HTML")
            if is_zip: process_zip_files(chat_id, msg)
            else: process_files(chat_id, msg)
        else: bot.edit_message_text("❌ Download failed.", chat_id=chat_id, message_id=msg.message_id)

@bot.message_handler(func=lambda m: m.text and (m.text.startswith('http://') or m.text.startswith('https://')))
def handle_urls(message):
    url = message.text.strip()
    file_name = os.path.basename(urlparse(url).path)
    if not file_name or (not file_name.endswith('.so') and not file_name.endswith('.zip')): file_name = "downloaded.so"
    def download(path): return download_from_url(url, path)
    process_state_file(message, file_name, download, True)

@bot.message_handler(content_types=['document'])
def handle_docs(message):
    if message.document.file_size > 500 * 1024 * 1024: return bot.reply_to(message, "<b>⚠️ File too large!</b>\nSend a <b>direct download link</b>.", parse_mode="HTML")
    file_name = message.document.file_name
    # Support .so, .bin, and .cpp extensions for dumps
    valid_exts = ('.so', '.bin', '.cpp', '.zip')
    if not file_name.lower().endswith(valid_exts): 
        return bot.reply_to(message, "⚠️ Please upload a <code>.so</code>, <code>.bin</code>, <code>.cpp</code> or <code>.zip</code> file.", parse_mode="HTML")
    
    def download(path):
        file_info = bot.get_file(message.document.file_id)
        downloaded = bot.download_file(file_info.file_path)
        with open(path, 'wb') as f: f.write(downloaded)
        return True
    process_state_file(message, file_name, download, False)

def get_all_files(directory):
    files = []
    for root, _, filenames in os.walk(directory):
        for filename in filenames:
            if filename.lower().endswith(('.so', '.bin', '.cpp')):
                files.append(os.path.join(root, filename))
    return files

def format_offsets_for_telegram(lib_name, offsets):
    if not offsets: return ""
    header = f"🚀 <b>OFFSETS DETECTED</b>\n📦 Library: <code>{lib_name}</code>\n\n"
    content = ""
    for offset in offsets:
        content += f"{offset}\n"
    full_msg = header + "<blockquote><pre>" + content + "</pre></blockquote>"
    full_msg += "\n\n<b>Analyzed By @LegacyDevX</b>"
    return full_msg

def process_files(chat_id, status_message):
    state = user_states.get(chat_id)
    if not state: return
    orig_path, dump_path = state['original_path'], state['dump_path']
    # Clean up filename for display
    lib_name = os.path.basename(dump_path).replace('dump_', '').split('_', 1)[-1]
    
    log_file = f"tmp_files/Dump_{lib_name}.cpp"
    start_addr, end_addr = get_auto_range(orig_path)
    
    hooks_found, extracted_offsets = scan_single_dump_pro(orig_path, dump_path, start_addr, end_addr, log_file, lib_name)
    offset_msg = format_offsets_for_telegram(lib_name, extracted_offsets)

    if os.path.exists(log_file):
        # Update status to done
        bot.edit_message_text("✅ <b>Analysis Complete!</b> Sending results...", chat_id=chat_id, message_id=status_message.message_id, parse_mode="HTML")
        
        caption = f"📝 <b>Analysis Log: {lib_name}</b>\n\n<b>Hooks Found:</b> <code>{hooks_found}</code>\n\n<b>Dumped By @LegacyDevX</b>"
        with open(log_file, 'rb') as f:
            bot.send_document(chat_id, f, caption=caption, parse_mode="HTML")
        
        if extracted_offsets:
            send_long_message(chat_id, offset_msg)
    else:
        bot.edit_message_text("❌ <b>Analysis Failed:</b> No differences found between original and dump.", chat_id=chat_id, message_id=status_message.message_id, parse_mode="HTML")
    
    # Cleanup
    for p in [dump_path, log_file]:
        if os.path.exists(p) and "base_libs" not in p: os.remove(p)
    if "tmp_files/orig_" in orig_path and os.path.exists(orig_path): os.remove(orig_path)
    
    user_states[chat_id] = {'step': 'waiting_for_original'}


if __name__ == '__main__':
    print("🤖 Legacy Dumper Bot is starting up...")
    # Add timeouts for better reliability on environments like Railway
    bot.infinity_polling(timeout=10, long_polling_timeout=5)

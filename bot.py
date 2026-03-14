import os
import sqlite3
import random
import string
import telebot
from telebot.types import InlineKeyboardMarkup, InlineKeyboardButton
import requests
from datetime import datetime, timedelta
from urllib.parse import urlparse

# --- CONFIGURATION ---
BOT_TOKEN = os.environ.get('BOT_TOKEN', '8611766126:AAE3QdKQHauKc99qs2D8wmE0GwZpGNyU7hk')
COMMUNITY_ID = os.environ.get('COMMUNITY_ID', '-1003729793140')
COMMUNITY_LINK = "https://t.me/+UZEwuXC7b_plZDJl"
ADMIN_IDS = [5707956654, 6049120581]

bot = telebot.TeleBot(BOT_TOKEN)

# Dictionary to keep track of user states
user_states = {}

# --- DATABASE SETUP ---
def init_db():
    conn = sqlite3.connect('dumper.db')
    c = conn.cursor()
    c.execute('''CREATE TABLE IF NOT EXISTS keys (key_text TEXT PRIMARY KEY, duration_days INTEGER)''')
    c.execute('''CREATE TABLE IF NOT EXISTS users (user_id INTEGER PRIMARY KEY, expiry_date TIMESTAMP)''')
    conn.commit()
    conn.close()

init_db()

# --- AUTH & SUBSCRIPTION LOGIC ---
def is_authorized(user_id):
    if user_id in ADMIN_IDS:
        return True
    
    conn = sqlite3.connect('dumper.db')
    c = conn.cursor()
    c.execute("SELECT expiry_date FROM users WHERE user_id=?", (user_id,))
    result = c.fetchone()
    conn.close()
    
    if result:
        expiry = datetime.fromisoformat(result[0])
        if datetime.now() < expiry:
            return True
    return False

def check_membership(user_id):
    if COMMUNITY_ID == 'YOUR_CHANNEL_ID_HERE':
        return True
    try:
        member = bot.get_chat_member(COMMUNITY_ID, user_id)
        if member.status in ['member', 'administrator', 'creator']:
            return True
        return False
    except Exception as e:
        return False

def ensure_access(message):
    user_id = message.from_user.id
    if not check_membership(user_id):
        bot.reply_to(message, f"<b>⚠️ Access Denied!</b>\n\nPlease join our community to use this bot.\n👉 {COMMUNITY_LINK}", parse_mode="HTML")
        return False
    if not is_authorized(user_id):
        bot.reply_to(message, "<b>⛔ Subscription Required!</b>\n\nYou need an active subscription to use Legacy Dumper.\nPlease ask admins for a key and redeem it using <code>/redeem &lt;KEY&gt;</code>", parse_mode="HTML")
        return False
    return True

# --- PRO VERSION SMART PATTERNS ---
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
    if os.path.exists(file_path):
        file_size = os.path.getsize(file_path)
        safe_end = int(file_size * 0.995)
        return 0x0, safe_end
    return 0x0, 0x0

def is_important_pattern(data, offset):
    for pattern_name, pattern_bytes in IMPORTANT_PATTERNS.items():
        if offset + len(pattern_bytes) <= len(data):
            if data[offset:offset + len(pattern_bytes)] == pattern_bytes:
                return pattern_name, pattern_bytes
    return None, None

def scan_single_dump_pro(original_path, dump_path, start_offset, end_offset, log_file, lib_name):
    if not os.path.exists(original_path) or not os.path.exists(dump_path): return 0
    try:
        with open(original_path, "rb") as f1: original_data = f1.read()
        with open(dump_path, "rb") as f2: dump_data = f2.read()
    except Exception as e:
        return 0

    file_size = min(len(original_data), len(dump_data), end_offset)
    try:
        with open(log_file, "w", encoding='utf-8') as log:
            log.write(f"=== LEGACY DUMPER PVT TOOL ===\nLibrary: {lib_name}\nScan Time: {datetime.now()}\nOriginal: {os.path.basename(original_path)}\nDump: {os.path.basename(dump_path)}\n" + "=" * 50 + "\n\n")
    except Exception: return 0

    hooks_found = 0
    i = start_offset
    with open(log_file, "a", encoding='utf-8') as log:
        while i < file_size:
            if original_data[i] != dump_data[i]:
                pattern_name, pattern_bytes = is_important_pattern(dump_data, i)
                if pattern_name:
                    if pattern_name == "HOOK_SIGNATURE":
                        end = i + 16
                        log.write(f"0x{i:06X} HOOK OFFSET\n")
                        hooks_found += 1
                        i = end
                    else:
                        hex_str = ' '.join(f"{dump_data[i + j]:02X}" for j in range(len(pattern_bytes)))
                        log.write(f"0x{i:06X} {hex_str} // {pattern_name}\n")
                        hooks_found += 1
                        i += len(pattern_bytes)
                else: i += 1
            else: i += 1
                
        log.write(f"\n" + "=" * 50 + f"\nTOTAL IMPORTANT HOOKS: {hooks_found}\nLIBRARY: {lib_name}\nSCAN COMPLETED: {datetime.now()}\n")
    return hooks_found

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
            with open(output_path, "wb") as f: f.write(data)
            return True
        return False
    except Exception: return False

def upload_to_gofile(file_path):
    try:
        server_res = requests.get("https://api.gofile.io/servers").json()
        if server_res['status'] != 'ok': return None
        server = server_res['data']['servers'][0]['name']
        url = f"https://{server}.gofile.io/contents/uploadfile"
        with open(file_path, 'rb') as f: upload_res = requests.post(url, files={'file': f}).json()
        if upload_res['status'] == 'ok': return upload_res['data']['downloadPage']
        return None
    except Exception: return None

def download_from_url(url, file_path):
    try:
        response = requests.get(url, stream=True)
        response.raise_for_status()
        with open(file_path, 'wb') as f:
            for chunk in response.iter_content(chunk_size=8192): f.write(chunk)
        return True
    except Exception: return False


# --- TELEGRAM BOT LOGIC & UI ---

def main_menu_keyboard():
    markup = InlineKeyboardMarkup()
    btn1 = InlineKeyboardButton("👨‍💻 Developer", url="https://t.me/legacyxAnku")
    btn2 = InlineKeyboardButton("👥 Community", url=COMMUNITY_LINK)
    btn3 = InlineKeyboardButton("📖 Help & Guide", callback_data="help_menu")
    markup.add(btn1, btn2)
    markup.add(btn3)
    return markup

def back_keyboard():
    markup = InlineKeyboardMarkup()
    btn = InlineKeyboardButton("🔙 Back to Main Menu", callback_data="main_menu")
    markup.add(btn)
    return markup

def get_welcome_text(user_id):
    sub_status = "✅ <b>Active</b>" if is_authorized(user_id) else "❌ <b>Inactive</b> (Use /redeem)"
    return f"""<b>🚀 Welcome to Legacy Dumper!</b>
<i>@legacydumperbot - The ultimate tool for cracking libs.</i>

<b>🔑 Subscription Status:</b> {sub_status}

<b>⚠️ Important Notice for Large Files:</b>
If your library file (like <code>libUE4.so</code>) is larger than <b>20MB</b>, please send a <b>Direct Download Link</b> instead of uploading directly.

<b>✨ Features:</b>
• Smart Hook Scanning
• Auto Root-Check Bypassing
• Large File Support (>50MB via Cloud)

👇 <b>Please select an option below to get started:</b>"""

help_text = """<b>📚 Legacy Dumper - User Guide</b>

<i>Master the ultimate lib cracking tool in just a few steps!</i>

<b>1️⃣ Small Files (< 20MB)</b>
• Simply upload your <b>ORIGINAL</b> <code>.so</code> file directly here.
• Then, upload the <b>DUMPED</b> <code>.so</code> file.

<b>2️⃣ Large Files (> 20MB e.g., UE4)</b>
• Upload your files to a fast cloud storage (like Mediafire, Discord, etc).
• Send the <b>Direct Download Link</b> (must end in .so or trigger download).
• Send the original link first, then the dump link.

<b>⚙️ What happens next?</b>
The bot will automatically scan for hooks, generate a <code>.cpp</code> offsets log, and patch any root/emulator checks. If the patched file is too big, it will be uploaded to a secure cloud drive for you!

<i>Ready? Go back and send your first file!</i>"""

# --- KEY SYSTEM COMMANDS ---

@bot.message_handler(commands=['gen'])
def generate_key(message):
    if message.from_user.id not in ADMIN_IDS:
        return
        
    args = message.text.split()
    if len(args) != 3:
        bot.reply_to(message, "⚠️ Usage: <code>/gen &lt;key_name&gt; &lt;duration_in_days&gt;d</code>\nExample: <code>/gen VIP 30d</code>", parse_mode="HTML")
        return
        
    key_name = args[1]
    duration_str = args[2].lower()
    
    if not duration_str.endswith('d'):
        bot.reply_to(message, "⚠️ Duration must end with 'd' (e.g., 30d).")
        return
        
    try:
        duration_days = int(duration_str[:-1])
    except ValueError:
        bot.reply_to(message, "⚠️ Invalid duration format.")
        return
        
    random_str = ''.join(random.choices(string.ascii_uppercase + string.digits, k=8))
    key_text = f"LGC-{key_name}-{random_str}"
    
    conn = sqlite3.connect('dumper.db')
    c = conn.cursor()
    c.execute("INSERT INTO keys (key_text, duration_days) VALUES (?, ?)", (key_text, duration_days))
    conn.commit()
    conn.close()
    
    bot.reply_to(message, f"✅ <b>Key Generated Successfully!</b>\n\n🔑 <code>{key_text}</code>\n⏱️ Duration: {duration_days} days\n\nUsers can redeem this using:\n<code>/redeem {key_text}</code>", parse_mode="HTML")

@bot.message_handler(commands=['redeem'])
def redeem_key(message):
    if not check_membership(message.from_user.id):
        bot.reply_to(message, f"<b>⚠️ Access Denied!</b>\n\nPlease join our community to use this bot.\n👉 {COMMUNITY_LINK}", parse_mode="HTML")
        return

    args = message.text.split()
    if len(args) != 2:
        bot.reply_to(message, "⚠️ Usage: <code>/redeem &lt;YOUR_KEY&gt;</code>", parse_mode="HTML")
        return
        
    key_text = args[1]
    user_id = message.from_user.id
    
    conn = sqlite3.connect('dumper.db')
    c = conn.cursor()
    c.execute("SELECT duration_days FROM keys WHERE key_text=?", (key_text,))
    result = c.fetchone()
    
    if result:
        duration_days = result[0]
        c.execute("DELETE FROM keys WHERE key_text=?", (key_text,))
        
        c.execute("SELECT expiry_date FROM users WHERE user_id=?", (user_id,))
        user_res = c.fetchone()
        
        now = datetime.now()
        if user_res and datetime.fromisoformat(user_res[0]) > now:
            new_expiry = datetime.fromisoformat(user_res[0]) + timedelta(days=duration_days)
        else:
            new_expiry = now + timedelta(days=duration_days)
            
        c.execute("INSERT OR REPLACE INTO users (user_id, expiry_date) VALUES (?, ?)", (user_id, new_expiry.isoformat()))
        conn.commit()
        conn.close()
        
        bot.reply_to(message, f"🎉 <b>Key Redeemed Successfully!</b>\n\nYou now have access to Legacy Dumper until <b>{new_expiry.strftime('%Y-%m-%d %H:%M:%S')}</b>.", parse_mode="HTML")
    else:
        conn.close()
        bot.reply_to(message, "❌ <b>Invalid or already used key!</b>", parse_mode="HTML")


@bot.message_handler(commands=['start', 'help'])
def send_welcome(message):
    if not check_membership(message.from_user.id):
        bot.reply_to(message, f"<b>⚠️ Access Denied!</b>\n\nPlease join our community to use this bot.\n👉 {COMMUNITY_LINK}", parse_mode="HTML")
        return

    user_states[message.chat.id] = {'step': 'waiting_for_original'}
    welcome = get_welcome_text(message.from_user.id)
    
    if os.path.exists("banner.jpg"):
        with open("banner.jpg", "rb") as photo:
            bot.send_photo(message.chat.id, photo, caption=welcome, parse_mode="HTML", reply_markup=main_menu_keyboard())
    else:
        bot.reply_to(message, welcome, parse_mode="HTML", reply_markup=main_menu_keyboard())

@bot.callback_query_handler(func=lambda call: True)
def callback_query(call):
    if call.data == "help_menu":
        if call.message.content_type == 'photo':
            bot.edit_message_caption(caption=help_text, chat_id=call.message.chat.id, message_id=call.message.message_id, parse_mode="HTML", reply_markup=back_keyboard())
        else:
            bot.edit_message_text(text=help_text, chat_id=call.message.chat.id, message_id=call.message.message_id, parse_mode="HTML", reply_markup=back_keyboard())
    elif call.data == "main_menu":
        welcome = get_welcome_text(call.from_user.id)
        if call.message.content_type == 'photo':
            bot.edit_message_caption(caption=welcome, chat_id=call.message.chat.id, message_id=call.message.message_id, parse_mode="HTML", reply_markup=main_menu_keyboard())
        else:
            bot.edit_message_text(text=welcome, chat_id=call.message.chat.id, message_id=call.message.message_id, parse_mode="HTML", reply_markup=main_menu_keyboard())

# Handle Text messages (URLs)
@bot.message_handler(func=lambda message: message.text and (message.text.startswith('http://') or message.text.startswith('https://')))
def handle_urls(message):
    if not ensure_access(message): return

    chat_id = message.chat.id
    url = message.text.strip()
    
    if chat_id not in user_states: user_states[chat_id] = {'step': 'waiting_for_original'}
    state = user_states[chat_id]
    
    parsed_url = urlparse(url)
    file_name = os.path.basename(parsed_url.path)
    if not file_name or not file_name.endswith('.so'): file_name = "lib_downloaded.so"

    msg = bot.reply_to(message, f"🔗 <b>Link detected!</b>\nDownloading <code>{file_name}</code>...", parse_mode="HTML")
    os.makedirs('tmp_files', exist_ok=True)
    
    if state['step'] == 'waiting_for_original':
        file_path = f"tmp_files/orig_{chat_id}_{file_name}"
        if download_from_url(url, file_path):
            state['original_path'] = file_path
            state['lib_name'] = file_name.replace('.so', '')
            state['step'] = 'waiting_for_dump'
            bot.edit_message_text(f"✅ Received <b>ORIGINAL</b> file: <code>{file_name}</code>\n\nNow, send me the <b>DUMPED</b> file (upload or link).", chat_id=chat_id, message_id=msg.message_id, parse_mode="HTML")
        else: bot.edit_message_text("❌ Failed to download.", chat_id=chat_id, message_id=msg.message_id, parse_mode="HTML")
            
    elif state['step'] == 'waiting_for_dump':
        file_path = f"tmp_files/dump_{chat_id}_{file_name}"
        if download_from_url(url, file_path):
            state['dump_path'] = file_path
            state['step'] = 'processing'
            bot.edit_message_text("✅ Dump downloaded! ⚙️ Processing files...", chat_id=chat_id, message_id=msg.message_id, parse_mode="HTML")
            process_files(chat_id, msg)
        else: bot.edit_message_text("❌ Failed to download.", chat_id=chat_id, message_id=msg.message_id, parse_mode="HTML")

# Handle Documents (Direct Uploads)
@bot.message_handler(content_types=['document'])
def handle_docs(message):
    if not ensure_access(message): return

    chat_id = message.chat.id
    if chat_id not in user_states: user_states[chat_id] = {'step': 'waiting_for_original'}
    state = user_states[chat_id]
    
    if message.document.file_size > 20 * 1024 * 1024:
        bot.reply_to(message, "<b>⚠️ File is too large!</b>\nPlease send a <b>direct download link</b> instead.", parse_mode="HTML")
        return

    if not message.document.file_name.endswith('.so'):
        bot.reply_to(message, "⚠️ Please upload a valid <code>.so</code> library file.", parse_mode="HTML")
        return

    msg = bot.reply_to(message, "⏳ Downloading file...")
    file_name = message.document.file_name
    file_info = bot.get_file(message.document.file_id)
    downloaded_file = bot.download_file(file_info.file_path)

    os.makedirs('tmp_files', exist_ok=True)
    if state['step'] == 'waiting_for_original':
        file_path = f"tmp_files/orig_{chat_id}_{file_name}"
        with open(file_path, 'wb') as new_file: new_file.write(downloaded_file)
        state['original_path'] = file_path
        state['lib_name'] = file_name.replace('.so', '')
        state['step'] = 'waiting_for_dump'
        bot.edit_message_text(f"✅ Received <b>ORIGINAL</b> file: <code>{file_name}</code>\n\nNow, send me the <b>DUMPED</b> file.", chat_id=chat_id, message_id=msg.message_id, parse_mode="HTML")
        
    elif state['step'] == 'waiting_for_dump':
        file_path = f"tmp_files/dump_{chat_id}_{file_name}"
        with open(file_path, 'wb') as new_file: new_file.write(downloaded_file)
        state['dump_path'] = file_path
        state['step'] = 'processing'
        bot.edit_message_text("⚙️ Processing files... Please wait.", chat_id=chat_id, message_id=msg.message_id, parse_mode="HTML")
        process_files(chat_id, msg)

def process_files(chat_id, status_message):
    state = user_states.get(chat_id)
    if not state: return

    orig_path, dump_path, lib_name = state['original_path'], state['dump_path'], state['lib_name']
    start_addr, end_addr = get_auto_range(orig_path)
    
    log_file, patched_file = f"tmp_files/Dump_{lib_name}_{chat_id}.cpp", f"tmp_files/PRO_{lib_name}_{chat_id}.so"
    
    bot.edit_message_text("🔍 Scanning for important hooks...", chat_id=chat_id, message_id=status_message.message_id, parse_mode="HTML")
    hooks_found = scan_single_dump_pro(orig_path, dump_path, start_addr, end_addr, log_file, lib_name)
    bot.edit_message_text(f"🔨 Scanning complete! Found <b>{hooks_found}</b> hooks.\nNow patching binary...", chat_id=chat_id, message_id=status_message.message_id, parse_mode="HTML")
    
    is_patched = patch_binary_pro(dump_path, patched_file)
    bot.edit_message_text("✅ Processing finished! Preparing results...", chat_id=chat_id, message_id=status_message.message_id, parse_mode="HTML")
    
    if os.path.exists(log_file):
        with open(log_file, 'rb') as f: bot.send_document(chat_id, f, caption=f"📝 Offset Log ({hooks_found} hooks found)")
            
    if is_patched and os.path.exists(patched_file):
        if os.path.getsize(patched_file) > 49 * 1024 * 1024:
            bot.edit_message_text("☁️ File too large (>50MB). Uploading to cloud...", chat_id=chat_id, message_id=status_message.message_id, parse_mode="HTML")
            download_link = upload_to_gofile(patched_file)
            if download_link: bot.send_message(chat_id, f"🛡️ <b>Patched Dump</b>\n\n👉 {download_link}", parse_mode="HTML")
            else: bot.send_message(chat_id, "❌ Error: Cloud upload failed.", parse_mode="HTML")
        else:
            bot.send_chat_action(chat_id, 'upload_document')
            with open(patched_file, 'rb') as f: bot.send_document(chat_id, f, caption="🛡️ Patched Dump (Root Check Bypassed)")
        bot.delete_message(chat_id, status_message.message_id)
    else: bot.send_message(chat_id, "⚠️ No root check patterns found to patch.", parse_mode="HTML")
        
    for p in [orig_path, dump_path, log_file, patched_file]:
        if os.path.exists(p): os.remove(p)
        
    user_states[chat_id] = {'step': 'waiting_for_original'}
    bot.send_message(chat_id, "🔄 Send another <b>ORIGINAL</b> library file or link to start over.", parse_mode="HTML")

if __name__ == '__main__':
    print("🤖 Legacy Dumper Bot is starting up...")
    bot.infinity_polling()
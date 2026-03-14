import os
import sqlite3
import random
import string
import telebot
from telebot.types import InlineKeyboardMarkup, InlineKeyboardButton
import requests
from datetime import datetime, timedelta
from urllib.parse import urlparse
import zipfile
import shutil
import re

# --- CONFIGURATION ---
BOT_TOKEN = os.environ.get('BOT_TOKEN', '8611766126:AAE3QdKQHauKc99qs2D8wmE0GwZpGNyU7hk')
COMMUNITY_ID = os.environ.get('COMMUNITY_ID', '-1003729793140')
COMMUNITY_LINK = "https://t.me/+UZEwuXC7b_plZDJl"
ADMIN_IDS = [5707956654, 6049120581]

bot = telebot.TeleBot(BOT_TOKEN)

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
    conn = sqlite3.connect('dumper.db')
    c = conn.cursor()
    c.execute("SELECT expiry_date FROM users WHERE user_id=?", (user_id,))
    result = c.fetchone()
    conn.close()
    if result and datetime.now() < datetime.fromisoformat(result[0]): return True
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
        bot.reply_to(message, "<b>⛔ Subscription Required!</b>\n\nYou need an active subscription to use Legacy Dumper.\nPlease ask admins for a key and redeem it using <code>/redeem &lt;KEY&gt;</code>", parse_mode="HTML")
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
    try:
        with open(original_path, "rb") as f1: original_data = f1.read()
        with open(dump_path, "rb") as f2: dump_data = f2.read()
    except Exception: return 0, []

    file_size = min(len(original_data), len(dump_data), end_offset)
    try:
        with open(log_file, "w", encoding='utf-8') as log:
            log.write(f"=== LEGACY DUMPER PVT TOOL ===\nLibrary: {lib_name}\nScan Time: {datetime.now()}\nOriginal: {os.path.basename(original_path)}\nDump: {os.path.basename(dump_path)}\n" + "=" * 50 + "\n\n")
    except Exception: return 0, []

    hooks_found = 0
    extracted_offsets = []
    i = start_offset
    with open(log_file, "a", encoding='utf-8') as log:
        while i < file_size:
            if original_data[i] != dump_data[i]:
                pattern_name, pattern_bytes = is_important_pattern(dump_data, i)
                if pattern_name:
                    if pattern_name == "HOOK_SIGNATURE":
                        log.write(f"0x{i:06X} HOOK OFFSET\n")
                        extracted_offsets.append(f"0x{i:06X} // HOOK_SIGNATURE")
                        hooks_found += 1
                        i += 16
                    else:
                        hex_str = ' '.join(f"{dump_data[i + j]:02X}" for j in range(len(pattern_bytes)))
                        log.write(f"0x{i:06X} {hex_str} // {pattern_name}\n")
                        extracted_offsets.append(f"0x{i:06X} // {pattern_name}")
                        hooks_found += 1
                        i += len(pattern_bytes)
                else: i += 1
            else: i += 1
        log.write(f"\n" + "=" * 50 + f"\nTOTAL IMPORTANT HOOKS: {hooks_found}\nLIBRARY: {lib_name}\nSCAN COMPLETED: {datetime.now()}\n")
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
        server_res = requests.get("https://api.gofile.io/servers").json()
        if server_res['status'] != 'ok': return None
        server = server_res['data']['servers'][0]['name']
        with open(file_path, 'rb') as f: upload_res = requests.post(f"https://{server}.gofile.io/contents/uploadfile", files={'file': f}).json()
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
    markup.add(InlineKeyboardButton("👨‍💻 Developer", url="https://t.me/legacyxAnku"), InlineKeyboardButton("👥 Community", url=COMMUNITY_LINK))
    markup.add(InlineKeyboardButton("📖 Help & Guide", callback_data="help_menu"))
    return markup

def back_keyboard():
    markup = InlineKeyboardMarkup()
    markup.add(InlineKeyboardButton("🔙 Back to Main Menu", callback_data="main_menu"))
    return markup

def get_welcome_text(user_id):
    sub_status = "✅ <b>Active</b>" if is_authorized(user_id) else "❌ <b>Inactive</b> (Use /redeem)"
    return f"""<b>🚀 Welcome to Legacy Dumper!</b>
<i>@legacydumperbot - The ultimate tool for cracking libs.</i>\n\n<b>🔑 Subscription Status:</b> {sub_status}\n
<b>✨ Features:</b>
• Smart Hook Scanning
• Auto Root-Check Bypassing
• Multi-file Support via ZIP
• Tap-to-Copy Offsets in Chat\n
👇 <b>Please select an option below to get started:</b>"""

help_text = """<b>📚 Legacy Dumper - User Guide</b>\n
<b>1️⃣ Single Library (.so)</b>
• Upload your <b>ORIGINAL</b> <code>.so</code> file directly here or send a direct link.
• Then, upload the <b>DUMPED</b> <code>.so</code> file or send a link.\n
<b>2️⃣ Multiple Libraries (ZIP Archive) 🌟 NEW</b>
• Zip all your <b>ORIGINAL</b> <code>.so</code> files and send it.
• Zip all your <b>DUMPED</b> <code>.so</code> files and send it.
• The bot will automatically map and scan all of them!\n
<i>Ready? Go back and send your first file or archive!</i>"""

@bot.message_handler(commands=['gen'])
def generate_key(message):
    if message.from_user.id not in ADMIN_IDS: return
    args = message.text.split()
    if len(args) != 3 or not args[2].lower().endswith('d'):
        bot.reply_to(message, "⚠️ Usage: <code>/gen &lt;name&gt; &lt;days&gt;d</code>", parse_mode="HTML")
        return
    try: duration_days = int(args[2][:-1])
    except ValueError: return bot.reply_to(message, "⚠️ Invalid duration.")
    key_text = f"LGC-{args[1]}-{''.join(random.choices(string.ascii_uppercase + string.digits, k=8))}"
    conn = sqlite3.connect('dumper.db'); c = conn.cursor()
    c.execute("INSERT INTO keys (key_text, duration_days) VALUES (?, ?)", (key_text, duration_days)); conn.commit(); conn.close()
    bot.reply_to(message, f"✅ <b>Key Generated!</b>\n\n🔑 <code>{key_text}</code>\n⏱️ {duration_days} days\n<code>/redeem {key_text}</code>", parse_mode="HTML")

@bot.message_handler(commands=['redeem'])
def redeem_key(message):
    if not check_membership(message.from_user.id): return bot.reply_to(message, f"<b>⚠️ Join our community!</b>\n👉 {COMMUNITY_LINK}", parse_mode="HTML")
    args = message.text.split()
    if len(args) != 2: return bot.reply_to(message, "⚠️ Usage: <code>/redeem &lt;KEY&gt;</code>", parse_mode="HTML")
    conn = sqlite3.connect('dumper.db'); c = conn.cursor()
    c.execute("SELECT duration_days FROM keys WHERE key_text=?", (args[1],)); result = c.fetchone()
    if result:
        c.execute("DELETE FROM keys WHERE key_text=?", (args[1],))
        c.execute("SELECT expiry_date FROM users WHERE user_id=?", (message.from_user.id,))
        user_res = c.fetchone()
        now = datetime.now()
        new_expiry = (datetime.fromisoformat(user_res[0]) if user_res and datetime.fromisoformat(user_res[0]) > now else now) + timedelta(days=result[0])
        c.execute("INSERT OR REPLACE INTO users (user_id, expiry_date) VALUES (?, ?)", (message.from_user.id, new_expiry.isoformat()))
        conn.commit(); conn.close()
        bot.reply_to(message, f"🎉 <b>Redeemed!</b> Access until <b>{new_expiry.strftime('%Y-%m-%d %H:%M:%S')}</b>.", parse_mode="HTML")
    else: conn.close(); bot.reply_to(message, "❌ <b>Invalid or used key!</b>", parse_mode="HTML")

@bot.message_handler(commands=['start', 'help'])
def send_welcome(message):
    if not check_membership(message.from_user.id): return bot.reply_to(message, f"<b>⚠️ Join our community!</b>\n👉 {COMMUNITY_LINK}", parse_mode="HTML")
    user_states[message.chat.id] = {'step': 'waiting_for_original'}
    welcome = get_welcome_text(message.from_user.id)
    if os.path.exists("banner.jpg"):
        with open("banner.jpg", "rb") as photo: bot.send_photo(message.chat.id, photo, caption=welcome, parse_mode="HTML", reply_markup=main_menu_keyboard())
    else: bot.reply_to(message, welcome, parse_mode="HTML", reply_markup=main_menu_keyboard())

@bot.callback_query_handler(func=lambda call: True)
def callback_query(call):
    if call.data == "help_menu":
        if call.message.content_type == 'photo': bot.edit_message_caption(caption=help_text, chat_id=call.message.chat.id, message_id=call.message.message_id, parse_mode="HTML", reply_markup=back_keyboard())
        else: bot.edit_message_text(text=help_text, chat_id=call.message.chat.id, message_id=call.message.message_id, parse_mode="HTML", reply_markup=back_keyboard())
    elif call.data == "main_menu":
        welcome = get_welcome_text(call.from_user.id)
        if call.message.content_type == 'photo': bot.edit_message_caption(caption=welcome, chat_id=call.message.chat.id, message_id=call.message.message_id, parse_mode="HTML", reply_markup=main_menu_keyboard())
        else: bot.edit_message_text(text=welcome, chat_id=call.message.chat.id, message_id=call.message.message_id, parse_mode="HTML", reply_markup=main_menu_keyboard())

def process_state_file(message, file_name, file_path_or_download_func, is_url=False):
    if not ensure_access(message): return
    chat_id = message.chat.id
    if chat_id not in user_states: user_states[chat_id] = {'step': 'waiting_for_original'}
    state = user_states[chat_id]
    os.makedirs('tmp_files', exist_ok=True)
    msg = bot.reply_to(message, f"⏳ Downloading <code>{file_name}</code>...", parse_mode="HTML")
    
    is_zip = file_name.lower().endswith('.zip')
    
    if state['step'] == 'waiting_for_original':
        file_path = f"tmp_files/orig_{chat_id}_{file_name}"
        success = file_path_or_download_func(file_path)
        if success:
            state['original_path'] = file_path
            state['is_zip'] = is_zip
            state['step'] = 'waiting_for_dump'
            bot.edit_message_text(f"✅ Received <b>ORIGINAL</b> {'Archive' if is_zip else 'File'}: <code>{file_name}</code>\n\nNow, send me the <b>DUMPED</b> {'Archive' if is_zip else 'File'} (Link or Upload).", chat_id=chat_id, message_id=msg.message_id, parse_mode="HTML")
        else: bot.edit_message_text("❌ Download failed.", chat_id=chat_id, message_id=msg.message_id)
            
    elif state['step'] == 'waiting_for_dump':
        if is_zip != state.get('is_zip', False):
            return bot.edit_message_text("⚠️ Format mismatch! Send a ZIP if you sent a ZIP originally.", chat_id=chat_id, message_id=msg.message_id)
            
        file_path = f"tmp_files/dump_{chat_id}_{file_name}"
        success = file_path_or_download_func(file_path)
        if success:
            state['dump_path'] = file_path
            state['step'] = 'processing'
            bot.edit_message_text("✅ Dump received! ⚙️ Processing...", chat_id=chat_id, message_id=msg.message_id, parse_mode="HTML")
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
    if message.document.file_size > 20 * 1024 * 1024: return bot.reply_to(message, "<b>⚠️ File too large!</b>\nSend a <b>direct download link</b>.", parse_mode="HTML")
    file_name = message.document.file_name
    if not (file_name.endswith('.so') or file_name.endswith('.zip')): return bot.reply_to(message, "⚠️ Please upload a <code>.so</code> or <code>.zip</code> file.", parse_mode="HTML")
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
            if filename.endswith('.so'):
                files.append(os.path.join(root, filename))
    return files

def format_offsets_for_telegram(lib_name, offsets):
    if not offsets: return ""
    display_offsets = offsets[:25] 
    text = f"🎯 <b>Offsets for {lib_name}</b> (Tap to copy):\n\n"
    for offset in display_offsets: text += f"<code>{offset}</code>\n"
    if len(offsets) > 25: text += f"\n<i>...and {len(offsets) - 25} more in .cpp log.</i>\n"
    return text

def process_zip_files(chat_id, status_message):
    state = user_states.get(chat_id)
    if not state: return
    orig_zip, dump_zip = state['original_path'], state['dump_path']
    orig_dir = f"tmp_files/orig_dir_{chat_id}"
    dump_dir = f"tmp_files/dump_dir_{chat_id}"
    out_dir = f"tmp_files/out_dir_{chat_id}"
    os.makedirs(orig_dir, exist_ok=True); os.makedirs(dump_dir, exist_ok=True); os.makedirs(out_dir, exist_ok=True)
    extract_archive(orig_zip, orig_dir); extract_archive(dump_zip, dump_dir)
    orig_files, dump_files = get_all_files(orig_dir), get_all_files(dump_dir)
    bot.edit_message_text("🔍 Extracting and matching libraries...", chat_id=chat_id, message_id=status_message.message_id)
    results = []; all_extracted_text = ""
    for orig_so in orig_files:
        filename = os.path.basename(orig_so)
        matching_dump = next((d for d in dump_files if os.path.basename(d) == filename), None)
        if matching_dump:
            lib_name = filename.replace('.so', '')
            start_addr, end_addr = get_auto_range(orig_so)
            log_file, patched_file = os.path.join(out_dir, f"Dump_{lib_name}.cpp"), os.path.join(out_dir, f"PRO_{lib_name}.so")
            hooks, extracted_offsets = scan_single_dump_pro(orig_so, matching_dump, start_addr, end_addr, log_file, lib_name)
            is_patched = patch_binary_pro(matching_dump, patched_file)
            results.append((filename, hooks, is_patched))
            if extracted_offsets: all_extracted_text += format_offsets_for_telegram(lib_name, extracted_offsets) + "\n"
    if not results: bot.edit_message_text("⚠️ No matching .so files found.", chat_id=chat_id, message_id=status_message.message_id)
    else:
        summary = "✅ Done:\n" + "\n".join([f"📦 {f}: {h} hooks | Patched: {'Yes' if p else 'No'}" for f, h, p in results])
        bot.edit_message_text(f"⚙️ Zipping results...\n{summary}", chat_id=chat_id, message_id=status_message.message_id)
        if all_extracted_text:
            if len(all_extracted_text) > 4000: all_extracted_text = all_extracted_text[:4000] + "\n... (truncated)"
            bot.send_message(chat_id, all_extracted_text, parse_mode="HTML")
        out_zip = f"tmp_files/Results_{chat_id}.zip"
        with zipfile.ZipFile(out_zip, 'w') as zf:
            for root, _, files in os.walk(out_dir):
                for file in files: zf.write(os.path.join(root, file), file)
        if os.path.getsize(out_zip) > 49 * 1024 * 1024:
            link = upload_to_gofile(out_zip)
            if link: bot.send_message(chat_id, f"🛡️ <b>Results ZIP</b>\n👉 {link}", parse_mode="HTML")
        else:
            with open(out_zip, 'rb') as f: bot.send_document(chat_id, f, caption=summary)
        bot.delete_message(chat_id, status_message.message_id)
    shutil.rmtree(orig_dir, ignore_errors=True); shutil.rmtree(dump_dir, ignore_errors=True); shutil.rmtree(out_dir, ignore_errors=True)
    for p in [orig_zip, dump_zip, out_zip] if 'out_zip' in locals() else [orig_zip, dump_zip]:
        if os.path.exists(p): os.remove(p)
    user_states[chat_id] = {'step': 'waiting_for_original'}

def process_files(chat_id, status_message):
    state = user_states.get(chat_id)
    if not state: return
    orig_path, dump_path = state['original_path'], state['dump_path']
    lib_name = os.path.basename(orig_path).replace('.so', '').replace('orig_', '').split('_', 1)[-1]
    start_addr, end_addr = get_auto_range(orig_path)
    log_file, patched_file = f"tmp_files/Dump_{lib_name}_{chat_id}.cpp", f"tmp_files/PRO_{lib_name}_{chat_id}.so"
    bot.edit_message_text(f"🔍 Scanning {lib_name}...", chat_id=chat_id, message_id=status_message.message_id)
    hooks_found, extracted_offsets = scan_single_dump_pro(orig_path, dump_path, start_addr, end_addr, log_file, lib_name)
    is_patched = patch_binary_pro(dump_path, patched_file)
    if extracted_offsets: bot.send_message(chat_id, format_offsets_for_telegram(lib_name, extracted_offsets), parse_mode="HTML")
    if os.path.exists(log_file):
        with open(log_file, 'rb') as f: bot.send_document(chat_id, f, caption=f"📝 {lib_name} Log ({hooks_found} hooks)")
    if is_patched and os.path.exists(patched_file):
        if os.path.getsize(patched_file) > 49 * 1024 * 1024:
            link = upload_to_gofile(patched_file)
            if link: bot.send_message(chat_id, f"🛡️ <b>Patched</b>\n👉 {link}", parse_mode="HTML")
        else:
            with open(patched_file, 'rb') as f: bot.send_document(chat_id, f, caption="🛡️ Patched (Root Bypassed)")
        bot.delete_message(chat_id, status_message.message_id)
    else: bot.send_message(chat_id, "⚠️ No root check patterns found.")
    for p in [orig_path, dump_path, log_file, patched_file]:
        if os.path.exists(p): os.remove(p)
    user_states[chat_id] = {'step': 'waiting_for_original'}

if __name__ == '__main__':
    print("🤖 Legacy Dumper Bot is starting up...")
    bot.infinity_polling()

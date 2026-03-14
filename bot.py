import os
import telebot
from telebot.types import InlineKeyboardMarkup, InlineKeyboardButton
import requests
from datetime import datetime
from urllib.parse import urlparse

# Get token from environment variable (best practice for Railway)
BOT_TOKEN = os.environ.get('BOT_TOKEN', 'YOUR_BOT_TOKEN_HERE')

if BOT_TOKEN == 'YOUR_BOT_TOKEN_HERE':
    print("⚠️ Warning: You haven't set the BOT_TOKEN environment variable. The bot might not work.")

bot = telebot.TeleBot(BOT_TOKEN)

# --- CONFIGURATION ---
# IMPORTANT: You must get your Community Channel ID (e.g. -100123456789) for the bot to check membership.
# The bot MUST be an admin in that channel.
COMMUNITY_ID = os.environ.get('COMMUNITY_ID', '-1003729793140')
COMMUNITY_LINK = "https://t.me/+UZEwuXC7b_plZDJl"

# Dictionary to keep track of user states (who is uploading what)
user_states = {} # chat_id: {'original_path': ..., 'dump_path': ..., 'lib_name': ...}

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
    if not os.path.exists(original_path) or not os.path.exists(dump_path):
        return 0

    try:
        with open(original_path, "rb") as f1:
            original_data = f1.read()
        with open(dump_path, "rb") as f2:
            dump_data = f2.read()
    except Exception as e:
        print(f"Error reading: {e}")
        return 0

    file_size = min(len(original_data), len(dump_data), end_offset)
    
    try:
        with open(log_file, "w", encoding='utf-8') as log:
            log.write(f"=== VenomDevX BRO DUMP PVT TOOL ===\n")
            log.write(f"Library: {lib_name}\n")
            log.write(f"Scan Time: {datetime.now()}\n")
            log.write(f"Original: {os.path.basename(original_path)}\n")
            log.write(f"Dump: {os.path.basename(dump_path)}\n")
            log.write("=" * 50 + "\n\n")
    except Exception as e:
        print(f"Error writing header: {e}")
        return 0

    hooks_found = 0
    i = start_offset
    
    with open(log_file, "a", encoding='utf-8') as log:
        while i < file_size:
            if original_data[i] != dump_data[i]:
                pattern_name, pattern_bytes = is_important_pattern(dump_data, i)
                if pattern_name:
                    if pattern_name == "HOOK_SIGNATURE":
                        end = i + 16
                        log_line = f"0x{i:06X} HOOK OFFSET"
                        log.write(log_line + "\n")
                        hooks_found += 1
                        i = end
                    else:
                        hex_str = ' '.join(f"{dump_data[i + j]:02X}" for j in range(len(pattern_bytes)))
                        log_line = f"0x{i:06X} {hex_str} // {pattern_name}"
                        log.write(log_line + "\n")
                        hooks_found += 1
                        i += len(pattern_bytes)
                else:
                    i += 1
            else:
                i += 1
                
        log.write(f"\n" + "=" * 50 + "\n")
        log.write(f"TOTAL IMPORTANT HOOKS: {hooks_found}\n")
        log.write(f"LIBRARY: {lib_name}\n")
        log.write(f"SCAN COMPLETED: {datetime.now()}\n")

    return hooks_found

def patch_binary_pro(dump_path, output_path):
    if not os.path.exists(dump_path):
        return False
    try:
        with open(dump_path, "rb") as f:
            data = bytearray(f.read())

        patched = False
        pattern = PATCH_ROOT_CHECK["pattern"]
        replacement = PATCH_ROOT_CHECK["replacement"]
        
        idx = 0
        while idx < len(data):
            idx = data.find(pattern, idx)
            if idx == -1:
                break
            data[idx:idx+len(pattern)] = replacement
            patched = True
            idx += len(pattern)

        if patched:
            with open(output_path, "wb") as f:
                f.write(data)
            return True
        else:
            return False
    except Exception as e:
        print(f"Patching failed: {e}")
        return False

# --- LARGE FILE HANDLING (Gofile API) ---
def upload_to_gofile(file_path):
    try:
        server_res = requests.get("https://api.gofile.io/servers").json()
        if server_res['status'] != 'ok': return None
        server = server_res['data']['servers'][0]['name']
        
        url = f"https://{server}.gofile.io/contents/uploadfile"
        with open(file_path, 'rb') as f:
            upload_res = requests.post(url, files={'file': f}).json()
            
        if upload_res['status'] == 'ok':
            return upload_res['data']['downloadPage']
        return None
    except Exception as e:
        print(f"Gofile upload error: {e}")
        return None

def download_from_url(url, file_path):
    try:
        response = requests.get(url, stream=True)
        response.raise_for_status()
        with open(file_path, 'wb') as f:
            for chunk in response.iter_content(chunk_size=8192):
                f.write(chunk)
        return True
    except Exception as e:
        print(f"Download error: {e}")
        return False


# --- TELEGRAM BOT LOGIC & UI ---

def check_membership(user_id):
    if COMMUNITY_ID == 'YOUR_CHANNEL_ID_HERE':
        # Bypass if not configured so the bot doesn't completely break
        print("⚠️ Warning: COMMUNITY_ID is not configured. Bypassing check.")
        return True
    try:
        member = bot.get_chat_member(COMMUNITY_ID, user_id)
        if member.status in ['member', 'administrator', 'creator']:
            return True
        return False
    except Exception as e:
        print(f"Membership check failed: {e}")
        # If the bot is not admin in the channel, it will throw an error here.
        return False

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

welcome_text = """<b>🚀 Welcome to VenomDevX Dump Tool!</b>

<i>The most advanced and professional memory dump analyzer & patcher.</i>

<b>⚠️ Important Notice for Large Files:</b>
If your library file (like <code>libUE4.so</code>) is larger than <b>20MB</b>, please send a <b>Direct Download Link</b> instead of uploading directly.

<b>✨ Features:</b>
• Smart Hook Scanning
• Auto Root-Check Bypassing
• Large File Support (>50MB via Cloud)

👇 <b>Please select an option below to get started:</b>"""

help_text = """<b>📚 VenomDevX Tool - User Guide</b>

<i>Master the ultimate patching tool in just a few steps!</i>

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


@bot.message_handler(commands=['start', 'help'])
def send_welcome(message):
    if not check_membership(message.from_user.id):
        bot.reply_to(message, f"<b>⚠️ Access Denied!</b>\n\nPlease join our community to use this bot.\n👉 {COMMUNITY_LINK}", parse_mode="HTML")
        return

    user_states[message.chat.id] = {'step': 'waiting_for_original'}
    
    # Check if a banner image exists in the same directory
    if os.path.exists("banner.jpg"):
        with open("banner.jpg", "rb") as photo:
            bot.send_photo(message.chat.id, photo, caption=welcome_text, parse_mode="HTML", reply_markup=main_menu_keyboard())
    else:
        bot.reply_to(message, welcome_text, parse_mode="HTML", reply_markup=main_menu_keyboard())

@bot.callback_query_handler(func=lambda call: True)
def callback_query(call):
    if call.data == "help_menu":
        if call.message.content_type == 'photo':
            bot.edit_message_caption(caption=help_text, chat_id=call.message.chat.id, message_id=call.message.message_id, parse_mode="HTML", reply_markup=back_keyboard())
        else:
            bot.edit_message_text(text=help_text, chat_id=call.message.chat.id, message_id=call.message.message_id, parse_mode="HTML", reply_markup=back_keyboard())
    elif call.data == "main_menu":
        if call.message.content_type == 'photo':
            bot.edit_message_caption(caption=welcome_text, chat_id=call.message.chat.id, message_id=call.message.message_id, parse_mode="HTML", reply_markup=main_menu_keyboard())
        else:
            bot.edit_message_text(text=welcome_text, chat_id=call.message.chat.id, message_id=call.message.message_id, parse_mode="HTML", reply_markup=main_menu_keyboard())

# Handle Text messages (URLs)
@bot.message_handler(func=lambda message: message.text and (message.text.startswith('http://') or message.text.startswith('https://')))
def handle_urls(message):
    if not check_membership(message.from_user.id):
        bot.reply_to(message, f"<b>⚠️ Access Denied!</b>\n\nPlease join our community to use this bot.\n👉 {COMMUNITY_LINK}", parse_mode="HTML")
        return

    chat_id = message.chat.id
    url = message.text.strip()
    
    if chat_id not in user_states:
        user_states[chat_id] = {'step': 'waiting_for_original'}

    state = user_states[chat_id]
    
    parsed_url = urlparse(url)
    file_name = os.path.basename(parsed_url.path)
    if not file_name or not file_name.endswith('.so'):
        file_name = "lib_downloaded.so"

    msg = bot.reply_to(message, f"🔗 <b>Link detected!</b>\nDownloading <code>{file_name}</code>... (This might take a minute)", parse_mode="HTML")
    
    os.makedirs('tmp_files', exist_ok=True)
    
    if state['step'] == 'waiting_for_original':
        file_path = f"tmp_files/orig_{chat_id}_{file_name}"
        if download_from_url(url, file_path):
            state['original_path'] = file_path
            state['lib_name'] = file_name.replace('.so', '')
            state['step'] = 'waiting_for_dump'
            bot.edit_message_text(f"✅ Received <b>ORIGINAL</b> file from link: <code>{file_name}</code>\n\nNow, send me the <b>DUMPED</b> file (upload or link).", chat_id=chat_id, message_id=msg.message_id, parse_mode="HTML")
        else:
            bot.edit_message_text("❌ Failed to download. Ensure it is a direct download link!", chat_id=chat_id, message_id=msg.message_id, parse_mode="HTML")
            
    elif state['step'] == 'waiting_for_dump':
        file_path = f"tmp_files/dump_{chat_id}_{file_name}"
        if download_from_url(url, file_path):
            state['dump_path'] = file_path
            state['step'] = 'processing'
            bot.edit_message_text("✅ Dump downloaded! ⚙️ Processing files... Please wait.", chat_id=chat_id, message_id=msg.message_id, parse_mode="HTML")
            process_files(chat_id, msg)
        else:
            bot.edit_message_text("❌ Failed to download. Ensure it is a direct download link!", chat_id=chat_id, message_id=msg.message_id, parse_mode="HTML")

# Handle Documents (Direct Uploads)
@bot.message_handler(content_types=['document'])
def handle_docs(message):
    if not check_membership(message.from_user.id):
        bot.reply_to(message, f"<b>⚠️ Access Denied!</b>\n\nPlease join our community to use this bot.\n👉 {COMMUNITY_LINK}", parse_mode="HTML")
        return

    chat_id = message.chat.id
    
    if chat_id not in user_states:
        user_states[chat_id] = {'step': 'waiting_for_original'}

    state = user_states[chat_id]
    
    if message.document.file_size > 20 * 1024 * 1024:
        bot.reply_to(message, "<b>⚠️ File is too large!</b>\n\nTelegram bots can only download files up to 20MB directly. Please send a <b>direct download link</b> instead.", parse_mode="HTML")
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
        with open(file_path, 'wb') as new_file:
            new_file.write(downloaded_file)
            
        state['original_path'] = file_path
        state['lib_name'] = file_name.replace('.so', '')
        state['step'] = 'waiting_for_dump'
        
        bot.edit_message_text(f"✅ Received <b>ORIGINAL</b> file: <code>{file_name}</code>\n\nNow, send me the <b>DUMPED</b> file.", chat_id=chat_id, message_id=msg.message_id, parse_mode="HTML")
        
    elif state['step'] == 'waiting_for_dump':
        file_path = f"tmp_files/dump_{chat_id}_{file_name}"
        with open(file_path, 'wb') as new_file:
            new_file.write(downloaded_file)
            
        state['dump_path'] = file_path
        state['step'] = 'processing'
        
        bot.edit_message_text("⚙️ Processing files... Please wait.", chat_id=chat_id, message_id=msg.message_id, parse_mode="HTML")
        process_files(chat_id, msg)

def process_files(chat_id, status_message):
    state = user_states.get(chat_id)
    if not state:
        return

    orig_path = state['original_path']
    dump_path = state['dump_path']
    lib_name = state['lib_name']
    
    start_addr, end_addr = get_auto_range(orig_path)
    
    log_file = f"tmp_files/Dump_{lib_name}_{chat_id}.cpp"
    patched_file = f"tmp_files/PRO_{lib_name}_{chat_id}.so"
    
    bot.edit_message_text("🔍 Scanning for important hooks...", chat_id=chat_id, message_id=status_message.message_id, parse_mode="HTML")
    
    hooks_found = scan_single_dump_pro(orig_path, dump_path, start_addr, end_addr, log_file, lib_name)
    
    bot.edit_message_text(f"🔨 Scanning complete! Found <b>{hooks_found}</b> hooks.\nNow patching binary...", chat_id=chat_id, message_id=status_message.message_id, parse_mode="HTML")
    
    is_patched = patch_binary_pro(dump_path, patched_file)
    
    bot.edit_message_text("✅ Processing finished! Preparing results...", chat_id=chat_id, message_id=status_message.message_id, parse_mode="HTML")
    
    if os.path.exists(log_file):
        with open(log_file, 'rb') as f:
            bot.send_document(chat_id, f, caption=f"📝 Offset Log ({hooks_found} hooks found)")
            
    if is_patched and os.path.exists(patched_file):
        file_size = os.path.getsize(patched_file)
        if file_size > 49 * 1024 * 1024:
            bot.edit_message_text("☁️ Patched file is too large for Telegram (>50MB). Uploading to cloud... please wait.", chat_id=chat_id, message_id=status_message.message_id, parse_mode="HTML")
            download_link = upload_to_gofile(patched_file)
            
            if download_link:
                bot.send_message(chat_id, f"🛡️ <b>Patched Dump (Root Check Bypassed)</b>\n\n"
                                          f"⚠️ File was too large for Telegram, so I uploaded it here:\n"
                                          f"👉 {download_link}", parse_mode="HTML")
            else:
                bot.send_message(chat_id, "❌ Error: Patched file is too large and cloud upload failed.", parse_mode="HTML")
        else:
            bot.send_chat_action(chat_id, 'upload_document')
            with open(patched_file, 'rb') as f:
                bot.send_document(chat_id, f, caption="🛡️ Patched Dump (Root Check Bypassed)")
                
        bot.delete_message(chat_id, status_message.message_id)
    else:
        bot.send_message(chat_id, "⚠️ No root check patterns found to patch. The dumped binary is unchanged.", parse_mode="HTML")
        
    try:
        os.remove(orig_path)
        os.remove(dump_path)
        if os.path.exists(log_file): os.remove(log_file)
        if os.path.exists(patched_file): os.remove(patched_file)
    except Exception as e:
        pass
        
    user_states[chat_id] = {'step': 'waiting_for_original'}
    bot.send_message(chat_id, "🔄 Send another <b>ORIGINAL</b> library file or link to start over.", parse_mode="HTML")

if __name__ == '__main__':
    print("🤖 Professional Bot is starting up...")
    bot.infinity_polling()
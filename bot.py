import os
import time
import sqlite3
from multiprocessing import Process
from http.server import HTTPServer, BaseHTTPRequestHandler
import telebot
from telebot import types

# ----------------- خادم ويب خفيف لإبقاء السيرفر نشطاً على Render -----------------
class HealthCheckHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        self.send_response(200)
        self.send_header("Content-type", "text/plain")
        self.end_headers()
        self.wfile.write(b"OK")

    def do_HEAD(self):
        self.send_response(200)
        self.end_headers()

def run_web_server():
    port = int(os.environ.get("PORT", 10000))
    server = HTTPServer(("0.0.0.0", port), HealthCheckHandler)
    server.serve_forever()

# ----------------- الإعدادات والتوكن الجديد -----------------
TOKEN = "8804442574:AAFIGwOIF2ApYGHLgsriri3MpW8m0Z3YJmo"
ADMIN_ID = 6569755457

GROUP_CHAT_ID = "@pro_ge"
GROUP_INVITE_LINK = "https://t.me/pro_ge"

DEFAULT_REQUIRED_REFS = 2
AFFILIATE_URL = "https://www.gamsgo.com/partner/RgRWm"
FREE_GEMINI_URL = "https://gemini.google.com"

bot = telebot.TeleBot(TOKEN, threaded=True)

# ----------------- قاعدة البيانات -----------------
conn = sqlite3.connect('referral_bot.db', check_same_thread=False)
cursor = conn.cursor()

cursor.execute('''
CREATE TABLE IF NOT EXISTS users (
    user_id INTEGER PRIMARY KEY,
    first_name TEXT,
    referrer_id INTEGER,
    referral_count INTEGER DEFAULT 0,
    reward_claimed INTEGER DEFAULT 0,
    joined_date TIMESTAMP DEFAULT CURRENT_TIMESTAMP
)
''')

cursor.execute('''
CREATE TABLE IF NOT EXISTS settings (
    key TEXT PRIMARY KEY,
    value TEXT
)
''')

cursor.execute("INSERT OR IGNORE INTO settings (key, value) VALUES ('affiliate_link', ?)", (AFFILIATE_URL,))
cursor.execute("INSERT OR IGNORE INTO settings (key, value) VALUES ('free_link', ?)", (FREE_GEMINI_URL,))
cursor.execute("INSERT OR IGNORE INTO settings (key, value) VALUES ('required_refs', ?)", (str(DEFAULT_REQUIRED_REFS),))
conn.commit()

def get_setting(key, default):
    cursor.execute("SELECT value FROM settings WHERE key = ?", (key,))
    row = cursor.fetchone()
    return row[0] if row else default

def set_setting(key, value):
    cursor.execute("INSERT OR REPLACE INTO settings (key, value) VALUES (?, ?)", (key, str(value)))
    conn.commit()

# ----------------- دوال مساعدة -----------------
def is_member(user_id):
    if user_id == ADMIN_ID:
        return True
    try:
        member = bot.get_chat_member(GROUP_CHAT_ID, user_id)
        return member.status in ['creator', 'administrator', 'member']
    except Exception:
        return False

def main_keyboard():
    markup = types.ReplyKeyboardMarkup(resize_keyboard=True, row_width=2)
    markup.add(types.KeyboardButton("🔗 My Referral Link"), types.KeyboardButton("📊 My Progress"))
    markup.add(types.KeyboardButton("🎁 Claim Reward"))
    return markup

def reward_keyboard():
    affiliate_url = get_setting('affiliate_link', AFFILIATE_URL)
    free_url = get_setting('free_link', FREE_GEMINI_URL)
    markup = types.InlineKeyboardMarkup(row_width=1)
    markup.add(
        types.InlineKeyboardButton("✨ Get Gemini Free Access", url=free_url),
        types.InlineKeyboardButton("💎 Upgrade to Gemini Pro (Discounted)", url=affiliate_url)
    )
    return markup

def send_dashboard(user_id, first_name):
    bot_info = bot.get_me()
    ref_link = f"https://t.me/{bot_info.username}?start={user_id}"
    req_refs = int(get_setting('required_refs', DEFAULT_REQUIRED_REFS))

    cursor.execute("SELECT referral_count FROM users WHERE user_id = ?", (user_id,))
    row = cursor.fetchone()
    my_count = row[0] if row else 0

    markup = types.InlineKeyboardMarkup(row_width=1)
    share_url = f"https://t.me/share/url?url={ref_link}&text=Unlock%20Google%20Gemini%20access!"
    markup.add(types.InlineKeyboardButton("🚀 Share Referral Link", url=share_url))

    if my_count >= req_refs:
        affiliate_url = get_setting('affiliate_link', AFFILIATE_URL)
        free_url = get_setting('free_link', FREE_GEMINI_URL)
        markup.add(
            types.InlineKeyboardButton("✨ Get Gemini Free Access", url=free_url),
            types.InlineKeyboardButton("💎 Upgrade to Gemini Pro (Discounted)", url=affiliate_url)
        )

    progress_bar = "█" * min(my_count, req_refs) + "░" * max(0, req_refs - my_count)

    text = (
        f"👋 **Welcome, {first_name}!**\n\n"
        f"Unlock **Google Gemini Access** in 2 easy steps:\n"
        f"1️⃣ Stay inside our group: [Join Group]({GROUP_INVITE_LINK})\n"
        f"2️⃣ Invite **{req_refs} active friends** using your personal link.\n\n"
        f"📊 **Your Progress:** `[{progress_bar}] {my_count}/{req_refs}`\n"
        f"🔗 **Your Unique Referral Link:**\n`{ref_link}`"
    )

    if my_count >= req_refs:
        text += "\n\n🎉 **Target Reached!** Choose your access option below:"

    bot.send_message(user_id, text, parse_mode="Markdown", reply_markup=markup)

admin_state = {}

# ----------------- أوامر المشرف (ADMIN) -----------------
@bot.message_handler(commands=['admin'])
def cmd_admin(message):
    if message.from_user.id != ADMIN_ID:
        return

    markup = types.InlineKeyboardMarkup(row_width=2)
    markup.add(
        types.InlineKeyboardButton("📊 Stats Overview", callback_data="adm_stats"),
        types.InlineKeyboardButton("🔗 Edit Affiliate URL", callback_data="adm_link")
    )
    markup.add(
        types.InlineKeyboardButton("🎯 Set Required Refs", callback_data="adm_refs"),
        types.InlineKeyboardButton("📢 Send Broadcast", callback_data="adm_bc")
    )

    current_refs = get_setting('required_refs', DEFAULT_REQUIRED_REFS)
    bot.send_message(
        ADMIN_ID,
        f"🛠 **Admin Dashboard**\nCurrent Goal: `{current_refs} referrals`",
        reply_markup=markup,
        parse_mode="Markdown"
    )

@bot.callback_query_handler(func=lambda call: call.data.startswith('adm_'))
def handle_admin_queries(call):
    if call.from_user.id != ADMIN_ID:
        return

    action = call.data

    if action == "adm_stats":
        cursor.execute("SELECT COUNT(*) FROM users")
        total_users = cursor.fetchone()[0]
        cursor.execute("SELECT SUM(referral_count) FROM users")
        total_invites = cursor.fetchone()[0] or 0
        req_refs = int(get_setting('required_refs', DEFAULT_REQUIRED_REFS))
        cursor.execute("SELECT COUNT(*) FROM users WHERE referral_count >= ?", (req_refs,))
        completed = cursor.fetchone()[0]

        res = (
            f"📊 **Statistics:**\n"
            f"👥 Total Users: `{total_users}`\n"
            f"🔗 Total Referrals: `{total_invites}`\n"
            f"🏆 Completed: `{completed}`\n"
            f"🎯 Target Required: `{req_refs}`"
        )
        bot.edit_message_text(res, chat_id=ADMIN_ID, message_id=call.message.message_id, parse_mode="Markdown")

    elif action == "adm_refs":
        markup = types.InlineKeyboardMarkup(row_width=4)
        markup.add(
            types.InlineKeyboardButton("1", callback_data="set_1"),
            types.InlineKeyboardButton("2", callback_data="set_2"),
            types.InlineKeyboardButton("3", callback_data="set_3"),
            types.InlineKeyboardButton("5", callback_data="set_5")
        )
        bot.edit_message_text("🎯 **Select Required Referrals Count:**", chat_id=ADMIN_ID, message_id=call.message.message_id, reply_markup=markup, parse_mode="Markdown")

    elif action == "adm_link":
        admin_state[ADMIN_ID] = "awaiting_link"
        bot.send_message(ADMIN_ID, "✍ Send the new affiliate URL (starting with https://):")

    elif action == "adm_bc":
        admin_state[ADMIN_ID] = "awaiting_bc"
        bot.send_message(ADMIN_ID, "✍️ Send the message you want to broadcast:")

@bot.callback_query_handler(func=lambda call: call.data.startswith('set_'))
def handle_set_number(call):
    if call.from_user.id != ADMIN_ID:
        return
    num = call.data.split('_')[1]
    set_setting("required_refs", num)
    bot.answer_callback_query(call.id, f"Target set to {num}!", show_alert=True)
    bot.edit_message_text(f"✅ Required referrals target updated to: `{num}`", chat_id=ADMIN_ID, message_id=call.message.message_id, parse_mode="Markdown")

@bot.message_handler(func=lambda m: m.from_user.id == ADMIN_ID and admin_state.get(ADMIN_ID) is not None)
def handle_admin_text(message):
    st = admin_state.get(ADMIN_ID)
    if st == "awaiting_link":
        url = message.text.strip()
        if url.startswith("http"):
            set_setting("affiliate_link", url)
            bot.send_message(ADMIN_ID, f"✅ URL updated:\n{url}")
        else:
            bot.send_message(ADMIN_ID, "❌ Invalid format.")
        admin_state[ADMIN_ID] = None
    elif st == "awaiting_bc":
        cursor.execute("SELECT user_id FROM users")
        users = cursor.fetchall()
        count = 0
        for u in users:
            try:
                bot.send_message(u[0], message.text)
                count += 1
                time.sleep(0.05)
            except Exception:
                pass
        bot.send_message(ADMIN_ID, f"✅ Broadcast sent to `{count}` users.", parse_mode="Markdown")
        admin_state[ADMIN_ID] = None

# ----------------- أمر البدء والمستخدمين العاديين -----------------
@bot.message_handler(commands=['start'])
def handle_user_start(message):
    user_id = message.from_user.id
    first_name = message.from_user.first_name or "Friend"
    parts = message.text.split()
    req_refs = int(get_setting('required_refs', DEFAULT_REQUIRED_REFS))

    cursor.execute("SELECT * FROM users WHERE user_id = ?", (user_id,))
    user = cursor.fetchone()

    if not user:
        ref_id = None
        if len(parts) > 1 and parts[1].isdigit():
            cid = int(parts[1])
            if cid != user_id:
                ref_id = cid

        cursor.execute("INSERT INTO users (user_id, first_name, referrer_id) VALUES (?, ?, ?)", (user_id, first_name, ref_id))
        conn.commit()

        if ref_id:
            cursor.execute("UPDATE users SET referral_count = referral_count + 1 WHERE user_id = ?", (ref_id,))
            conn.commit()
            try:
                cursor.execute("SELECT referral_count FROM users WHERE user_id = ?", (ref_id,))
                c = cursor.fetchone()[0]
                bot.send_message(ref_id, f"🎉 A friend joined using your link! Progress: `{c}/{req_refs}`", parse_mode="Markdown")
                if c >= req_refs:
                    bot.send_message(ref_id, "🏆 Target achieved! Claim your reward below:", reply_markup=reward_keyboard())
            except Exception:
                pass

    if not is_member(user_id):
        markup = types.InlineKeyboardMarkup()
        markup.add(types.InlineKeyboardButton("👥 Join Group First", url=GROUP_INVITE_LINK))
        markup.add(types.InlineKeyboardButton("✅ I Have Joined (Verify)", callback_data="verify_join"))
        bot.send_message(user_id, f"Hello {first_name}! 🚀\nPlease join our group to activate the bot:", reply_markup=markup)
        return

    bot.send_message(user_id, "✅ Community membership verified!", reply_markup=main_keyboard())
    send_dashboard(user_id, first_name)

@bot.callback_query_handler(func=lambda call: call.data == "verify_join")
def verify_join_callback(call):
    user_id = call.from_user.id
    first_name = call.from_user.first_name or "Friend"
    if is_member(user_id):
        try:
            bot.delete_message(user_id, call.message.message_id)
        except Exception:
            pass
        bot.send_message(user_id, "🎉 Verified successfully!", reply_markup=main_keyboard())
        send_dashboard(user_id, first_name)
    else:
        bot.answer_callback_query(call.id, "❌ Please join the group first!", show_alert=True)

# ----------------- أزرار الكيبورد السفلية -----------------
@bot.message_handler(func=lambda msg: True and not msg.text.startswith('/'))
def handle_menu_clicks(message):
    user_id = message.from_user.id
    first_name = message.from_user.first_name or "Friend"
    text = message.text.lower()
    req_refs = int(get_setting('required_refs', DEFAULT_REQUIRED_REFS))

    if not is_member(user_id):
        handle_user_start(message)
        return

    if 'claim' in text:
        cursor.execute("SELECT referral_count FROM users WHERE user_id = ?", (user_id,))
        row = cursor.fetchone()
        count = row[0] if row else 0

        if count >= req_refs:
            bot.send_message(user_id, "🎉 Choose your access option below:", reply_markup=reward_keyboard())
        else:
            bot.send_message(user_id, f"🔒 Locked! You need **{req_refs - count} more referral(s)**.", parse_mode="Markdown")
    else:
        send_dashboard(user_id, first_name)

# ----------------- نقطة التشغيل -----------------
if __name__ == "__main__":
    proc = Process(target=run_web_server)
    proc.daemon = True
    proc.start()

    bot.remove_webhook()
    print("Bot is polling with new token...")
    bot.infinity_polling(skip_pending=True)

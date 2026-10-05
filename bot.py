import os
import sqlite3
from multiprocessing import Process
from http.server import HTTPServer, BaseHTTPRequestHandler
import telebot
from telebot import types

# ----------------- خادم ويب مستقل خفيف جداً يمنع الانهيار -----------------
class SimpleHealthCheck(BaseHTTPRequestHandler):
    def do_GET(self):
        self.send_response(200)
        self.send_header("Content-type", "text/plain")
        self.end_headers()
        self.wfile.write(b"Bot is active")

    def do_HEAD(self):
        self.send_response(200)
        self.end_headers()

def start_server():
    port = int(os.environ.get("PORT", 10000))
    server = HTTPServer(("0.0.0.0", port), SimpleHealthCheck)
    server.serve_forever()

# ----------------- Configuration -----------------
TOKEN = "8804442574:AAGyi9gNetSUAe80IXOpZbBq_jzAaTqWdm4"
ADMIN_ID = 6569755457
REQUIRED_REFERRALS = 3

bot = telebot.TeleBot(TOKEN, threaded=False)

# ----------------- Database Setup -----------------
conn = sqlite3.connect('referral_bot.db', check_same_thread=False)
cursor = conn.cursor()

cursor.execute('''
CREATE TABLE IF NOT EXISTS users (
    user_id INTEGER PRIMARY KEY,
    first_name TEXT,
    referrer_id INTEGER,
    referral_count INTEGER DEFAULT 0,
    reward_claimed INTEGER DEFAULT 0
)
''')

cursor.execute('''
CREATE TABLE IF NOT EXISTS settings (
    key TEXT PRIMARY KEY,
    value TEXT
)
''')

cursor.execute("INSERT OR IGNORE INTO settings (key, value) VALUES ('reward_link', 'https://whop.com/')")
conn.commit()

def get_reward_link():
    cursor.execute("SELECT value FROM settings WHERE key = 'reward_link'")
    row = cursor.fetchone()
    return row[0] if row else "https://whop.com/"

def set_reward_link(new_link):
    cursor.execute("UPDATE settings SET value = ? WHERE key = 'reward_link'", (new_link,))
    conn.commit()

admin_states = {}

# ----------------- User Commands -----------------
@bot.message_handler(commands=['start'])
def start(message):
    user_id = message.from_user.id
    first_name = message.from_user.first_name
    args = message.text.split()

    cursor.execute("SELECT * FROM users WHERE user_id = ?", (user_id,))
    user = cursor.fetchone()

    if not user:
        referrer_id = None
        if len(args) > 1:
            try:
                potential_referrer = int(args[1])
                if potential_referrer != user_id:
                    referrer_id = potential_referrer
            except ValueError:
                pass

        cursor.execute("INSERT INTO users (user_id, first_name, referrer_id) VALUES (?, ?, ?)",
                       (user_id, first_name, referrer_id))
        conn.commit()

        if referrer_id:
            cursor.execute("UPDATE users SET referral_count = referral_count + 1 WHERE user_id = ?", (referrer_id,))
            conn.commit()
            
            cursor.execute("SELECT referral_count, reward_claimed FROM users WHERE user_id = ?", (referrer_id,))
            ref_data = cursor.fetchone()
            if ref_data:
                count, claimed = ref_data
                try:
                    bot.send_message(referrer_id, f"🎉 A new user joined via your link!\n👥 Total Invites: {count}/{REQUIRED_REFERRALS}")
                    if count >= REQUIRED_REFERRALS and claimed == 0:
                        cursor.execute("UPDATE users SET reward_claimed = 1 WHERE user_id = ?", (referrer_id,))
                        conn.commit()
                        bot.send_message(referrer_id, f"🎁 Congratulations! You unlocked the secret reward:\n{get_reward_link()}")
                except Exception:
                    pass

    bot_username = bot.get_me().username
    ref_link = f"https://t.me/{bot_username}?start={user_id}"

    cursor.execute("SELECT referral_count FROM users WHERE user_id = ?", (user_id,))
    user_count = cursor.fetchone()
    my_count = user_count[0] if user_count else 0

    markup = types.InlineKeyboardMarkup()
    btn_share = types.InlineKeyboardButton("🔗 Share Link", url=f"https://t.me/share/url?url={ref_link}&text=Join%20now%20to%20get%20exclusive%20access!")
    markup.add(btn_share)

    welcome_text = (
        f"Welcome {first_name}! 🚀\n\n"
        f"Invite {REQUIRED_REFERRALS} friends to unlock the exclusive blueprint for free.\n\n"
        f"🔗 **Your Unique Referral Link:**\n`{ref_link}`\n\n"
        f"👥 **Your Current Invites:** {my_count} / {REQUIRED_REFERRALS}"
    )
    bot.send_message(user_id, welcome_text, parse_mode="Markdown", reply_markup=markup)

# ----------------- Admin Panel -----------------
@bot.message_handler(commands=['admin'])
def admin_panel(message):
    if message.from_user.id != ADMIN_ID:
        return

    markup = types.InlineKeyboardMarkup(row_width=2)
    btn_stats = types.InlineKeyboardButton("📊 Statistics", callback_data="admin_stats")
    btn_link = types.InlineKeyboardButton("⚙️ Update Reward Link", callback_data="admin_setlink")
    btn_broadcast = types.InlineKeyboardButton("📢 Broadcast Message", callback_data="admin_broadcast")
    
    markup.add(btn_stats, btn_link)
    markup.add(btn_broadcast)

    bot.send_message(ADMIN_ID, "⚙️ **Admin Control Panel:**\nSelect an option below to manage the bot:", reply_markup=markup, parse_mode="Markdown")

@bot.callback_query_handler(func=lambda call: call.data.startswith('admin_'))
def handle_admin_callbacks(call):
    if call.from_user.id != ADMIN_ID:
        return

    if call.data == "admin_stats":
        cursor.execute("SELECT COUNT(*) FROM users")
        total_users = cursor.fetchone()[0]

        cursor.execute("SELECT SUM(referral_count) FROM users")
        total_refs = cursor.fetchone()[0] or 0

        cursor.execute("SELECT COUNT(*) FROM users WHERE reward_claimed = 1")
        total_claimed = cursor.fetchone()[0]

        stats_text = (
            f"📊 **Current Community Stats:**\n\n"
            f"👤 Total Users: `{total_users}`\n"
            f"🔗 Total Referrals: `{total_refs}`\n"
            f"🎁 Rewards Claimed: `{total_claimed}`\n"
            f"🌐 Current Reward Link:\n{get_reward_link()}"
        )
        bot.edit_message_text(stats_text, chat_id=ADMIN_ID, message_id=call.message.message_id, parse_mode="Markdown")

    elif call.data == "admin_setlink":
        admin_states[ADMIN_ID] = "waiting_for_link"
        bot.send_message(ADMIN_ID, "✍️ Send the new reward URL (must start with https://):")

    elif call.data == "admin_broadcast":
        admin_states[ADMIN_ID] = "waiting_for_broadcast"
        bot.send_message(ADMIN_ID, "✍️ Send the message you want to broadcast to all members:")

@bot.message_handler(func=lambda msg: msg.from_user.id == ADMIN_ID and admin_states.get(ADMIN_ID) is not None)
def handle_admin_inputs(message):
    state = admin_states.get(ADMIN_ID)

    if state == "waiting_for_link":
        new_url = message.text.strip()
        if new_url.startswith("http://") or new_url.startswith("https://"):
            set_reward_link(new_url)
            bot.send_message(ADMIN_ID, f"✅ Reward link updated successfully:\n{new_url}")
        else:
            bot.send_message(ADMIN_ID, "❌ Invalid URL. Make sure it includes https://")
        admin_states[ADMIN_ID] = None

    elif state == "waiting_for_broadcast":
        broadcast_text = message.text
        cursor.execute("SELECT user_id FROM users")
        all_users = cursor.fetchall()
        
        sent_count = 0
        bot.send_message(ADMIN_ID, "⏳ Broadcasting message to all users...")
        
        for user in all_users:
            uid = user[0]
            try:
                bot.send_message(uid, broadcast_text)
                sent_count += 1
            except Exception:
                pass
        
        bot.send_message(ADMIN_ID, f"✅ Broadcast sent successfully to `{sent_count}` users!")
        admin_states[ADMIN_ID] = None

# ----------------- Start Execution -----------------
if __name__ == "__main__":
    web_proc = Process(target=start_server)
    web_proc.daemon = True
    web_proc.start()

    print("Bot is successfully running...")
    bot.infinity_polling(timeout=10, long_polling_timeout=5)

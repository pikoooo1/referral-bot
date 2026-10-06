import os
import time
import sqlite3
from multiprocessing import Process
from http.server import HTTPServer, BaseHTTPRequestHandler
import telebot
from telebot import types
from telebot.apihelper import ApiTelegramException

# ----------------- خادم ويب خفيف لإبقاء البوت نشطاً على Render -----------------
class HealthCheckHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        self.send_response(200)
        self.send_header("Content-type", "text/plain")
        self.end_headers()
        self.wfile.write(b"Bot is active and running.")

    def do_HEAD(self):
        self.send_response(200)
        self.end_headers()

def run_web_server():
    port = int(os.environ.get("PORT", 10000))
    server = HTTPServer(("0.0.0.0", port), HealthCheckHandler)
    server.serve_forever()

# ----------------- الإعدادات والروابط -----------------
TOKEN = "8804442574:AAGyi9gNetSUAe80IXOpZbBq_jzAaTqWdm4"
ADMIN_ID = 6569755457

GROUP_CHAT_ID = "@pro_ge"
GROUP_INVITE_LINK = "https://t.me/pro_ge"

DEFAULT_REQUIRED_REFS = 2
AFFILIATE_URL = "https://www.gamsgo.com/partner/RgRWm"
FREE_GEMINI_URL = "https://gemini.google.com"
STARS_PRICE = 2  # السعر المحدث: نجمتان فقط (2 ⭐)

bot = telebot.TeleBot(TOKEN, threaded=False)

# ----------------- إعداد قاعدة البيانات -----------------
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
# تحديث السعر تلقائياً إلى 2 نجوم في قاعدة البيانات
cursor.execute("INSERT OR REPLACE INTO settings (key, value) VALUES ('stars_price', ?)", (str(STARS_PRICE),))
conn.commit()

def get_setting(key, default):
    cursor.execute("SELECT value FROM settings WHERE key = ?", (key,))
    row = cursor.fetchone()
    return row[0] if row else default

def set_setting(key, value):
    cursor.execute("INSERT OR REPLACE INTO settings (key, value) VALUES (?, ?)", (key, str(value)))
    conn.commit()

# ----------------- الدوال المساعدة -----------------
def is_member_of_group(chat_id, user_id):
    if user_id == ADMIN_ID:
        return True
    try:
        member = bot.get_chat_member(chat_id, user_id)
        if member.status in ['creator', 'administrator', 'member']:
            return True
        return False
    except Exception:
        return False

def get_main_keyboard():
    markup = types.ReplyKeyboardMarkup(resize_keyboard=True, row_width=2)
    btn_link = types.KeyboardButton("🔗 My Referral Link")
    btn_status = types.KeyboardButton("📊 My Progress")
    btn_claim = types.KeyboardButton("🎁 Claim Reward")
    btn_buy = types.KeyboardButton("⚡ Buy Instant Access (2 ⭐)")
    markup.add(btn_link, btn_status)
    markup.add(btn_claim, btn_buy)
    return markup

def get_reward_markup():
    affiliate_url = get_setting('affiliate_link', AFFILIATE_URL)
    free_url = get_setting('free_link', FREE_GEMINI_URL)

    markup = types.InlineKeyboardMarkup(row_width=1)
    btn_free = types.InlineKeyboardButton("✨ Get Gemini Free Access (Instant)", url=free_url)
    btn_pro = types.InlineKeyboardButton("💎 Upgrade to Gemini Pro (Partner Discount)", url=affiliate_url)
    markup.add(btn_free, btn_pro)
    return markup

def send_dashboard(user_id, first_name):
    bot_username = bot.get_me().username
    ref_link = f"https://t.me/{bot_username}?start={user_id}"
    req_refs = int(get_setting('required_refs', DEFAULT_REQUIRED_REFS))
    stars = get_setting('stars_price', STARS_PRICE)

    cursor.execute("SELECT referral_count, reward_claimed FROM users WHERE user_id = ?", (user_id,))
    row = cursor.fetchone()
    my_count = row[0] if row else 0
    claimed = row[1] if row else 0

    share_url = f"https://t.me/share/url?url={ref_link}&text=Unlock%20Google%20Gemini%20access%20for%20free!"

    markup = types.InlineKeyboardMarkup(row_width=1)
    btn_share = types.InlineKeyboardButton("🚀 Share Referral Link", url=share_url)
    markup.add(btn_share)

    if my_count >= req_refs or claimed == 1:
        affiliate_url = get_setting('affiliate_link', AFFILIATE_URL)
        free_url = get_setting('free_link', FREE_GEMINI_URL)
        markup.add(
            types.InlineKeyboardButton("✨ Get Gemini Free Access", url=free_url),
            types.InlineKeyboardButton("💎 Upgrade to Gemini Pro (Discounted)", url=affiliate_url)
        )
    else:
        btn_buy_instant = types.InlineKeyboardButton(f"⚡ Skip & Unlock Instantly ({stars} ⭐)", callback_data="buy_stars_invoice")
        markup.add(btn_buy_instant)

    progress_bar = "█" * min(my_count, req_refs) + "░" * max(0, req_refs - my_count)

    msg = (
        f"👋 **Welcome, {first_name}!**\n\n"
        f"Unlock **Google Gemini Access** in 2 easy steps:\n"
        f"1️⃣ Stay inside our group: [Join Group]({GROUP_INVITE_LINK})\n"
        f"2️⃣ Invite **{req_refs} active friends** using your personal link.\n\n"
        f"📊 **Your Progress:** `[{progress_bar}] {my_count}/{req_refs}`\n"
        f"🔗 **Your Unique Referral Link:**\n`{ref_link}`\n\n"
        f"💡 *Don't want to wait? You can unlock instant access for just {stars} ⭐!*"
    )

    if my_count >= req_refs or claimed == 1:
        msg += "\n\n🎉 **Access Unlocked!** Choose your access option below:"

    bot.send_message(user_id, msg, parse_mode="Markdown", reply_markup=markup)

admin_states = {}

# ----------------- لوحة تحكم المشرف (أولوية قصوى) -----------------
@bot.message_handler(commands=['admin'])
def handle_admin(message):
    if message.from_user.id != ADMIN_ID:
        return

    markup = types.InlineKeyboardMarkup(row_width=2)
    btn_stats = types.InlineKeyboardButton("📊 Stats Overview", callback_data="admin_stats")
    btn_link = types.InlineKeyboardButton("🔗 Edit Affiliate URL", callback_data="admin_setlink")
    btn_refs = types.InlineKeyboardButton("🎯 Set Required Refs", callback_data="admin_choose_refs")
    btn_broadcast = types.InlineKeyboardButton("📢 Send Broadcast", callback_data="admin_broadcast")

    markup.add(btn_stats)
    markup.add(btn_link, btn_refs)
    markup.add(btn_broadcast)

    current_refs = get_setting('required_refs', DEFAULT_REQUIRED_REFS)
    bot.send_message(
        ADMIN_ID,
        f"🛠 **Admin Control Panel**\n\n"
        f"🎯 Current Goal: `{current_refs} referrals`\n"
        f"Choose an option below to manage the bot:",
        reply_markup=markup,
        parse_mode="Markdown"
    )

@bot.callback_query_handler(func=lambda call: call.data.startswith('admin_'))
def handle_admin_actions(call):
    if call.from_user.id != ADMIN_ID:
        return

    action = call.data

    if action == "admin_stats":
        cursor.execute("SELECT COUNT(*) FROM users")
        total_users = cursor.fetchone()[0]

        cursor.execute("SELECT SUM(referral_count) FROM users")
        total_invites = cursor.

import os
import sqlite3
from multiprocessing import Process
from http.server import HTTPServer, BaseHTTPRequestHandler
import telebot
from telebot import types

# ----------------- Lightweight Health Check Web Server -----------------
class HealthCheckHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        self.send_response(200)
        self.send_header("Content-type", "text/plain")
        self.end_headers()
        self.wfile.write(b"Gemini Referral Bot is alive and healthy.")

    def do_HEAD(self):
        self.send_response(200)
        self.end_headers()

def run_web_server():
    port = int(os.environ.get("PORT", 10000))
    server = HTTPServer(("0.0.0.0", port), HealthCheckHandler)
    server.serve_forever()

# ----------------- Configurations -----------------
TOKEN = "8804442574:AAGyi9gNetSUAe80IXOpZbBq_jzAaTqWdm4"
ADMIN_ID = 6569755457

GROUP_CHAT_ID = "@pro_ge"
GROUP_INVITE_LINK = "https://t.me/pro_ge"

DEFAULT_REQUIRED_REFS = 2
DEFAULT_REWARD_URL = "https://gemini.google.com/advanced"

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

cursor.execute("INSERT OR IGNORE INTO settings (key, value) VALUES ('reward_link', ?)", (DEFAULT_REWARD_URL,))
cursor.execute("INSERT OR IGNORE INTO settings (key, value) VALUES ('required_refs', ?)", (str(DEFAULT_REQUIRED_REFS),))
conn.commit()

def get_setting(key, default):
    cursor.execute("SELECT value FROM settings WHERE key = ?", (key,))
    row = cursor.fetchone()
    return row[0] if row else default

def set_setting(key, value):
    cursor.execute("INSERT OR REPLACE INTO settings (key, value) VALUES (?, ?)", (key, str(value)))
    conn.commit()

# ----------------- Helper Functions -----------------
def is_member_of_group(chat_id, user_id):
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
    btn_help = types.KeyboardButton("ℹ️ Rules & Help")
    markup.add(btn_link, btn_status)
    markup.add(btn_claim, btn_help)
    return markup

def send_dashboard(user_id, first_name):
    bot_username = bot.get_me().username
    ref_link = f"https://t.me/{bot_username}?start={user_id}"
    req_refs = int(get_setting('required_refs', DEFAULT_REQUIRED_REFS))

    cursor.execute("SELECT referral_count, reward_claimed FROM users WHERE user_id = ?", (user_id,))
    row = cursor.fetchone()
    my_count = row[0] if row else 0

    share_text = f"🔥 Unlock Google Gemini Pro for free! Join through my link: {ref_link}"
    share_url = f"https://t.me/share/url?url={ref_link}&text=Unlock%20Google%20Gemini%20Pro%20for%20free!"

    markup = types.InlineKeyboardMarkup()
    btn_share = types.InlineKeyboardButton("🚀 Share Referral Link", url=share_url)
    markup.add(btn_share)

    if my_count >= req_refs:
        reward_url = get_setting('reward_link', DEFAULT_REWARD_URL)
        btn_claim = types.InlineKeyboardButton("🎁 Claim Gemini Pro Access", url=reward_url)
        markup.add(btn_claim)

    progress_bar = "█" * min(my_count, req_refs) + "░" * max(0, req_refs - my_count)

    msg = (
        f"👋 **Welcome, {first_name}!**\n\n"
        f"Get exclusive free access to **Google Gemini Pro** by completing 2 easy steps:\n"
        f"1️⃣ Join our official discussion group: [Join Group]({GROUP_INVITE_LINK})\n"
        f"2️⃣ Invite **{req_refs} active friends** using your unique invitation link.\n\n"
        f"📊 **Your Progress:** `[{progress_bar}] {my_count}/{req_refs}`\n"
        f"🔗 **Your Unique Referral Link:**\n`{ref_link}`"
    )

    if my_count >= req_refs:
        msg += "\n\n🎉 **Congratulations! Target Achieved.**\nClick the button below to claim your Gemini Pro access now!"

    bot.send_message(user_id, msg, parse_mode="Markdown", reply_markup=markup)

admin_states = {}

# ----------------- User Message Handlers -----------------
@bot.message_handler(commands=['start'])
def handle_start(message):
    user_id = message.from_user.id
    first_name = message.from_user.first_name or "Friend"
    args = message.text.split()
    req_refs = int(get_setting('required_refs', DEFAULT_REQUIRED_REFS))

    cursor.execute("SELECT * FROM users WHERE user_id = ?", (user_id,))
    existing_user = cursor.fetchone()

    if not existing_user:
        referrer_id = None
        if len(args) > 1:
            try:
                candidate_id = int(args[1])
                if candidate_id != user_id:
                    referrer_id = candidate_id
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
                    bar = "█" * min(count, req_refs) + "░" * max(0, req_refs - count)
                    bot.send_message(
                        referrer_id,
                        f"🎉 **New Referral Joined!**\n"
                        f"A new friend joined via your invite link.\n\n"
                        f"📊 Progress: `[{bar}] {count}/{req_refs}`"
                    )
                    if count >= req_refs and claimed == 0:
                        reward_link = get_setting('reward_link', DEFAULT_REWARD_URL)
                        bot.send_message(
                            referrer_id,
                            f"🏆 **Goal Achieved!**\n"
                            f"You have successfully referred {req_refs} friends.\n"
                            f"🎁 Click here to claim your Gemini Pro: {reward_link}"
                        )
                except Exception:
                    pass

    # Verification: Mandatory Group Membership Check
    if not is_member_of_group(GROUP_CHAT_ID, user_id):
        markup = types.InlineKeyboardMarkup()
        btn_group = types.InlineKeyboardButton("👥 Join Group First", url=GROUP_INVITE_LINK)
        btn_verify = types.InlineKeyboardButton("✅ I Have Joined (Verify)", callback_data="verify_group")
        markup.add(btn_group)
        markup.add(btn_verify)

        verification_text = (
            f"Hello {first_name}! 🚀\n\n"
            f"⚠️ **Access Required:**\n"
            f"You must join our community group before activating the bot:\n\n"
            f"1. Tap the button below to join the group.\n"
            f"2. Return here and tap **I Have Joined (Verify)**."
        )
        bot.send_message(user_id, verification_text, parse_mode="Markdown", reply_markup=markup)
        return

    bot.send_message(user_id, "✅ Community membership verified!", reply_markup=get_main_keyboard())
    send_dashboard(user_id, first_name)

@bot.callback_query_handler(func=lambda call: call.data == "verify_group")
def handle_verification_callback(call):
    user_id = call.from_user.id
    first_name = call.from_user.first_name or "Friend"

    if is_member_of_group(GROUP_CHAT_ID, user_id):
        try:
            bot.delete_message(chat_id=user_id, message_id=call.message.message_id)
        except Exception:
            pass
        bot.send_message(user_id, "🎉 Verified successfully!", reply_markup=get_main_keyboard())
        send_dashboard(user_id, first_name)
    else:
        bot.answer_callback_query(call.id, "❌ You haven't joined yet. Please join the group and retry.", show_alert=True)

# ----------------- Quick Reply Keyboard Actions -----------------
@bot.message_handler(func=lambda msg: msg.text in ["🔗 My Referral Link", "📊 My Progress", "🎁 Claim Reward", "ℹ️ Rules & Help"])
def handle_quick_buttons(message):
    user_id = message.from_user.id
    first_name = message.from_user.first_name or "Friend"
    req_refs = int(get_setting('required_refs', DEFAULT_REQUIRED_REFS))

    if not is_member_of_group(GROUP_CHAT_ID, user_id):
        handle_start(message)
        return

    cursor.execute("SELECT referral_count FROM users WHERE user_id = ?", (user_id,))
    row = cursor.fetchone()
    count = row[0] if row else 0

    if message.text in ["🔗 My Referral Link", "📊 My Progress"]:
        send_dashboard(user_id, first_name)

    elif message.text == "🎁 Claim Reward":
        if count >= req_refs:
            reward_url = get_setting('reward_link', DEFAULT_REWARD_URL)
            markup = types.InlineKeyboardMarkup()
            markup.add(types.InlineKeyboardButton("🎁 Access Gemini Pro", url=reward_url))
            bot.send_message(user_id, "🎉 **Congratulations!** Here is your reward:", reply_markup=markup, parse_mode="Markdown")
        else:
            remaining = req_refs - count
            bot.send_message(
                user_id,
                f"🔒 **Locked!** You need **{remaining} more referral(s)** to unlock the Gemini Pro subscription.",
                parse_mode="Markdown"
            )

    elif message.text == "ℹ️ Rules & Help":
        help_text = (
            "📌 **How it works:**\n\n"
            f"1. Stay active in our group: {GROUP_INVITE_LINK}\n"
            f"2. Invite {req_refs} genuine friends with your personal invite link.\n"
            f"3. Instant reward unlocked upon reaching {req_refs} referrals.\n\n"
            "⚠️️ Note: Fake or duplicate accounts will be automatically excluded."
        )
        bot.send_message(user_id, help_text, parse_mode="Markdown")

# ----------------- Admin Panel -----------------
@bot.message_handler(commands=['admin'])
def handle_admin(message):
    if message.from_user.id != ADMIN_ID:
        return

    markup = types.InlineKeyboardMarkup(row_width=2)
    btn_stats = types.InlineKeyboardButton("📊 Stats Overview", callback_data="admin_stats")
    btn_link = types.InlineKeyboardButton("🔗 Edit Reward URL", callback_data="admin_setlink")
    btn_refs = types.InlineKeyboardButton("🎯 Edit Required Refs", callback_data="admin_setrefs")
    btn_broadcast = types.InlineKeyboardButton("📢 Send Broadcast", callback_data="admin_broadcast")

    markup.add(btn_stats)
    markup.add(btn_link, btn_refs)
    markup.add(btn_broadcast)

    bot.send_message(
        ADMIN_ID,
        "🛠 **Admin Management Dashboard**\nSelect an operation below to manage the bot:",
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
        total_invites = cursor.fetchone()[0] or 0

        req_refs = int(get_setting('required_refs', DEFAULT_REQUIRED_REFS))
        cursor.execute("SELECT COUNT(*) FROM users WHERE referral_count >= ?", (req_refs,))
        eligible = cursor.fetchone()[0]

        stats_summary = (
            f"📊 **System Statistics:**\n\n"
            f"👥 Total Registered Users: `{total_users}`\n"
            f"🔗 Total Valid Invitations: `{total_invites}`\n"
            f"🏆 Users Unlocked Reward: `{eligible}`\n\n"
            f"🎯 Target Required: `{req_refs} invites`\n"
            f"🌐 Current Reward Link:\n{get_setting('reward_link', DEFAULT_REWARD_URL)}"
        )
        bot.edit_message_text(stats_summary, chat_id=ADMIN_ID, message_id=call.message.message_id, parse_mode="Markdown")

    elif action == "admin_setlink":
        admin_states[ADMIN_ID] = "awaiting_link"
        bot.send_message(ADMIN_ID, "✍️ Send the new reward URL (must begin with https://):")

    elif action == "admin_setrefs":
        admin_states[ADMIN_ID] = "awaiting_refs"
        bot.send_message(ADMIN_ID, "✍️ Send the new required referrals number (e.g. 2 or 3):")

    elif action == "admin_broadcast":
        admin_states[ADMIN_ID] = "awaiting_broadcast"
        bot.send_message(ADMIN_ID, "✍️️ Send the message you want to broadcast to all bot members:")

@bot.message_handler(func=lambda msg: msg.from_user.id == ADMIN_ID and admin_states.get(ADMIN_ID) is not None)
def handle_admin_state_input(message):
    state = admin_states.get(ADMIN_ID)

    if state == "awaiting_link":
        url = message.text.strip()
        if url.startswith("http://") or url.startswith("https://"):
            set_setting("reward_link", url)
            bot.send_message(ADMIN_ID, f"✅ Reward URL successfully updated:\n{url}")
        else:
            bot.send_message(ADMIN_ID, "❌ Invalid format. Please ensure it begins with https://")
        admin_states[ADMIN_ID] = None

    elif state == "awaiting_refs":
        try:
            val = int(message.text.strip())
            if val > 0:
                set_setting("required_refs", str(val))
                bot.send_message(ADMIN_ID, f"✅ Required referrals target updated to: `{val}`", parse_mode="Markdown")
            else:
                bot.send_message(ADMIN_ID, "❌ Number must be greater than 0.")
        except ValueError:
            bot.send_message(ADMIN_ID, "❌ Please enter a valid number.")
        admin_states[ADMIN_ID] = None

    elif state == "awaiting_broadcast":
        content = message.text
        cursor.execute("SELECT user_id FROM users")
        members = cursor.fetchall()
        delivered = 0

        bot.send_message(ADMIN_ID, "⏳ Broadcasting message...")
        for row in members:
            try:
                bot.send_message(row[0], content)
                delivered += 1
            except Exception:
                pass

        bot.send_message(ADMIN_ID, f"✅ Broadcast delivered successfully to `{delivered}` members!", parse_mode="Markdown")
        admin_states[ADMIN_ID] = None

# ----------------- Main Execution Entry Point -----------------
if __name__ == "__main__":
    # Force kill and reset previous hanging webhook/polling sessions to eliminate Error 409
    try:
        bot.remove_webhook(drop_pending_updates=True)
    except Exception:
        pass

    # Launch background keep-alive server
    proc = Process(target=run_web_server)
    proc.daemon = True
    proc.start()

    print("Gemini Referral Bot started successfully.")
    bot.infinity_polling(skip_pending=True, timeout=20, long_polling_timeout=10)

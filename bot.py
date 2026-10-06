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
STARS_PRICE = 2

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

# ----------------- لوحة تحكم المشرف -----------------
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
        total_invites = cursor.fetchone()[0] or 0

        req_refs = int(get_setting('required_refs', DEFAULT_REQUIRED_REFS))
        cursor.execute("SELECT COUNT(*) FROM users WHERE referral_count >= ? OR reward_claimed = 1", (req_refs,))
        eligible = cursor.fetchone()[0]

        stats_summary = (
            f"📊 **System Statistics:**\n\n"
            f"👥 Total Users: `{total_users}`\n"
            f"🔗 Total Referrals: `{total_invites}`\n"
            f"🏆 Unlocked Rewards: `{eligible}`\n\n"
            f"🎯 Target Required: `{req_refs} invites`\n"
            f"🌐 Current Affiliate URL:\n{get_setting('affiliate_link', AFFILIATE_URL)}"
        )
        bot.edit_message_text(stats_summary, chat_id=ADMIN_ID, message_id=call.message.message_id, parse_mode="Markdown")

    elif action == "admin_choose_refs":
        markup = types.InlineKeyboardMarkup(row_width=4)
        btn_1 = types.InlineKeyboardButton("1 Ref", callback_data="setref_1")
        btn_2 = types.InlineKeyboardButton("2 Refs", callback_data="setref_2")
        btn_3 = types.InlineKeyboardButton("3 Refs", callback_data="setref_3")
        btn_5 = types.InlineKeyboardButton("5 Refs", callback_data="setref_5")
        btn_custom = types.InlineKeyboardButton("✏ Custom Number", callback_data="setref_custom")
        markup.add(btn_1, btn_2, btn_3, btn_5)
        markup.add(btn_custom)

        bot.edit_message_text(
            "🎯 **Select Required Referrals Count:**\nChoose a quick option or enter a custom number:",
            chat_id=ADMIN_ID,
            message_id=call.message.message_id,
            reply_markup=markup,
            parse_mode="Markdown"
        )

    elif action == "admin_setlink":
        admin_states[ADMIN_ID] = "awaiting_link"
        bot.send_message(ADMIN_ID, "✍️ Send the new affiliate URL (must start with https://):")

    elif action == "admin_broadcast":
        admin_states[ADMIN_ID] = "awaiting_broadcast"
        bot.send_message(ADMIN_ID, "✍️ Send the message you want to broadcast to all members:")

@bot.callback_query_handler(func=lambda call: call.data.startswith('setref_'))
def handle_setref_buttons(call):
    if call.from_user.id != ADMIN_ID:
        return

    val_str = call.data.split('_')[1]
    if val_str == "custom":
        admin_states[ADMIN_ID] = "awaiting_refs"
        bot.send_message(ADMIN_ID, "✍️ Send the custom required referrals number:")
    else:
        num = int(val_str)
        set_setting("required_refs", str(num))
        bot.answer_callback_query(call.id, f"✅ Set to {num} referrals!", show_alert=True)
        bot.edit_message_text(
            f"✅ **Target Updated Successfully!**\nNow every user needs **{num} referral(s)** to unlock rewards.",
            chat_id=ADMIN_ID,
            message_id=call.message.message_id,
            parse_mode="Markdown"
        )

@bot.message_handler(func=lambda msg: msg.from_user.id == ADMIN_ID and admin_states.get(ADMIN_ID) is not None)
def handle_admin_text_inputs(message):
    state = admin_states.get(ADMIN_ID)

    if state == "awaiting_link":
        url = message.text.strip()
        if url.startswith("http://") or url.startswith("https://"):
            set_setting("affiliate_link", url)
            bot.send_message(ADMIN_ID, f"✅ Affiliate URL updated:\n{url}")
        else:
            bot.send_message(ADMIN_ID, "❌ Invalid URL format.")
        admin_states[ADMIN_ID] = None

    elif state == "awaiting_refs":
        try:
            val = int(message.text.strip())
            if val > 0:
                set_setting("required_refs", str(val))
                bot.send_message(ADMIN_ID, f"✅ Target updated to: `{val}` referral(s)", parse_mode="Markdown")
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

        bot.send_message(ADMIN_ID, "⏳ Broadcasting...")
        for row in members:
            try:
                bot.send_message(row[0], content)
                delivered += 1
                time.sleep(0.05)
            except Exception:
                pass

        bot.send_message(ADMIN_ID, f"✅ Broadcast sent to `{delivered}` users!", parse_mode="Markdown")
        admin_states[ADMIN_ID] = None

# ----------------- الدفع بنجوم تيليجرام -----------------
def send_invoice(chat_id):
    price_stars = int(get_setting('stars_price', STARS_PRICE))
    prices = [types.LabeledPrice(label="Instant Gemini Access", amount=price_stars)]
    try:
        bot.send_invoice(
            chat_id=chat_id,
            title="⚡ Instant Gemini Access",
            description=f"Skip inviting friends and unlock instant Gemini access for only {price_stars} Stars!",
            invoice_payload="instant_access_payload",
            provider_token="",
            currency="XTR",
            prices=prices,
            start_parameter="instant-access"
        )
    except Exception:
        bot.send_message(chat_id, "⚠️ Error creating payment invoice. Please try again later.")

@bot.callback_query_handler(func=lambda call: call.data == "buy_stars_invoice")
def handle_buy_invoice_callback(call):
    send_invoice(call.from_user.id)
    bot.answer_callback_query(call.id)

@bot.pre_checkout_query_handler(func=lambda query: True)
def process_pre_checkout(pre_checkout_query):
    bot.answer_pre_checkout_query(pre_checkout_query.id, ok=True)

@bot.message_handler(content_types=['successful_payment'])
def process_successful_payment(message):
    user_id = message.from_user.id
    cursor.execute("UPDATE users SET reward_claimed = 1 WHERE user_id = ?", (user_id,))
    conn.commit()

    bot.send_message(
        user_id,
        "🎉 **Payment Successful!**\n\n"
        "Your access has been unlocked instantly without inviting friends.\n"
        "Select your access option below:",
        reply_markup=get_reward_markup(),
        parse_mode="Markdown"
    )

# ----------------- الترحيب في المجموعة -----------------
@bot.message_handler(content_types=['new_chat_members'])
def handle_new_group_member(message):
    bot_username = bot.get_me().username
    for user in message.new_chat_members:
        if user.is_bot:
            continue
        try:
            bot.send_message(
                message.chat.id,
                f"👋 Welcome {user.first_name}!\n\n"
                f"🎁 Want free Google Gemini access? Start our official bot now:\n"
                f"👉 @{bot_username}"
            )
        except Exception:
            pass

# ----------------- أمر البداية -----------------
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
                        f"A friend joined via your invite link.\n\n"
                        f"📊 Progress: `[{bar}] {count}/{req_refs}`"
                    )
                    if count >= req_refs and claimed == 0:
                        bot.send_message(
                            referrer_id,
                            f"🏆 **Goal Achieved!**\n"
                            f"You have referred {req_refs} friends.\n"
                            f"Select your access option below:",
                            reply_markup=get_reward_markup()
                        )
                except Exception:
                    pass

    if not is_member_of_group(GROUP_CHAT_ID, user_id):
        markup = types.InlineKeyboardMarkup()
        btn_group = types.InlineKeyboardButton("👥 Join Group First", url=GROUP_INVITE_LINK)
        btn_verify = types.InlineKeyboardButton("✅ I Have Joined (Verify)", callback_data="verify_group")
        markup.add(btn_group)
        markup.add(btn_verify)

        verification_text = (
            f"Hello {first_name}! 🚀\n\n"
            f"⚠️️ **Access Required:**\n"
            f"Please join our community group before activating the bot:\n\n"
            f"1. Click the button below to join the group.\n"
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

# ----------------- أزرار الكيبورد -----------------
@bot.message_handler(func=lambda msg: msg.text and any(w in msg.text.lower() for w in ['referral', 'progress', 'claim', 'buy']))
def handle_quick_buttons(message):
    user_id = message.from_user.id
    first_name = message.from_user.first_name or "Friend"
    text = message.text.lower()
    req_refs = int(get_setting('required_refs', DEFAULT_REQUIRED_REFS))

    if not is_member_of_group(GROUP_CHAT_ID, user_id):
        handle_start(message)
        return

    cursor.execute("SELECT referral_count, reward_claimed FROM users WHERE user_id = ?", (user_id,))
    row = cursor.fetchone()
    count = row[0] if row else 0
    claimed = row[1] if row else 0

    if 'buy' in text:
        send_invoice(user_id)

    elif 'claim' in text:
        if count >= req_refs or claimed == 1:
            bot.send_message(
                user_id,
                "🎉 **Congratulations!** Your reward options are unlocked.\n\n"
                "• **Free Access:** Start using Google Gemini directly.\n"
                "• **Gemini Pro:** Exclusive partner offer for Pro upgrades.",
                reply_markup=get_reward_markup(),
                parse_mode="Markdown"
            )
        else:
            remaining = req_refs - count
            stars = get_setting('stars_price', STARS_PRICE)
            markup = types.InlineKeyboardMarkup()
            markup.add(types.InlineKeyboardButton(f"⚡ Skip & Buy Instantly ({stars} ⭐)", callback_data="buy_stars_invoice"))
            bot.send_message(
                user_id,
                f"🔒 **Locked!** You need **{remaining} more referral(s)** to unlock access.\n\n"
                f"Or you can unlock it immediately using Telegram Stars:",
                reply_markup=markup,
                parse_mode="Markdown"
            )
    else:
        send_dashboard(user_id, first_name)

# ----------------- تشغيل السيرفر -----------------
if __name__ == "__main__":
    proc = Process(target=run_web_server)
    proc.daemon = True
    proc.start()

    print("Bot is starting up...")

    while True:
        try:
            bot.remove_webhook(drop_pending_updates=True)
            bot.polling(none_stop=True, skip_pending=True, timeout=20)
        except ApiTelegramException as e:
            if e.error_code == 409:
                print("Old instance still active, waiting 5 seconds...")
                time.sleep(5)
            else:
                time.sleep(3)
        except Exception:
            time.sleep(3)

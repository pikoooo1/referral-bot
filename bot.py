import os
import sqlite3
from multiprocessing import Process
from http.server import HTTPServer, BaseHTTPRequestHandler
import telebot
from telebot import types

# ----------------- خادم ويب لإبقاء السيرفر نشطاً -----------------
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

# ----------------- الإعدادات الأساسية -----------------
TOKEN = "8804442574:AAGyi9gNetSUAe80IXOpZbBq_jzAaTqWdm4"
ADMIN_ID = 6569755457

# معلومات مجموعتك
GROUP_CHAT_ID = "@pro_ge"
GROUP_INVITE_LINK = "https://t.me/pro_ge"

REQUIRED_REFERRALS = 2  # عدد الدعوات المطلوب: شخصين

bot = telebot.TeleBot(TOKEN, threaded=False)

# ----------------- قاعدة البيانات -----------------
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

# رابط الهدية الافتراضي لـ Gemini Pro
cursor.execute("INSERT OR IGNORE INTO settings (key, value) VALUES ('reward_link', 'https://gemini.google.com/advanced')")
conn.commit()

def get_reward_link():
    cursor.execute("SELECT value FROM settings WHERE key = 'reward_link'")
    row = cursor.fetchone()
    return row[0] if row else "https://gemini.google.com/advanced"

def set_reward_link(new_link):
    cursor.execute("UPDATE settings SET value = ? WHERE key = 'reward_link'", (new_link,))
    conn.commit()

# دالة فحص الانضمام إلى المجموعة
def is_user_in_group(chat_id, user_id):
    try:
        member = bot.get_chat_member(chat_id, user_id)
        if member.status in ['creator', 'administrator', 'member']:
            return True
        return False
    except Exception:
        return False

admin_states = {}

# ----------------- لوحة المستخدم -----------------
def send_user_dashboard(user_id, first_name):
    bot_username = bot.get_me().username
    ref_link = f"https://t.me/{bot_username}?start={user_id}"

    cursor.execute("SELECT referral_count, reward_claimed FROM users WHERE user_id = ?", (user_id,))
    data = cursor.fetchone()
    my_count = data[0] if data else 0

    markup = types.InlineKeyboardMarkup()
    btn_share = types.InlineKeyboardButton("🔗 مشاركة رابط الدعوة", url=f"https://t.me/share/url?url={ref_link}&text=احصل%20على%20اشتراك%20Gemini%20Pro%20مجاناً%20الآن!")
    markup.add(btn_share)

    if my_count >= REQUIRED_REFERRALS:
        btn_claim = types.InlineKeyboardButton("🎁 استلام حساب Gemini Pro مجاناً", url=get_reward_link())
        markup.add(btn_claim)

    status_msg = (
        f"أهلاً بك يا {first_name}! 🤖✨\n\n"
        f"للحصول على رابط **Gemini Pro مجاناً**:\n"
        f"قم بدعوة **{REQUIRED_REFERRALS} أصدقاء** فقط عبر رابطك الخاص!\n\n"
        f"🔗 **رابط الدعوة الخاص بك:**\n`{ref_link}`\n\n"
        f"👥 **عدد الذين دعوتهم:** `{my_count} / {REQUIRED_REFERRALS}`"
    )

    if my_count >= REQUIRED_REFERRALS:
        status_msg += f"\n\n🎉 **مبروك! لقد أكملت الشروط بنجاح:**\nاضغط على الزر بالأسفل لاستلام اشتراكك الآن 👇"

    bot.send_message(user_id, status_msg, parse_mode="Markdown", reply_markup=markup)

# ----------------- أمر البداية -----------------
@bot.message_handler(commands=['start'])
def start(message):
    user_id = message.from_user.id
    first_name = message.from_user.first_name
    args = message.text.split()

    cursor.execute("SELECT * FROM users WHERE user_id = ?", (user_id,))
    user = cursor.fetchone()

    # إذا كان المستخدم جديداً
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
                    bot.send_message(referrer_id, f"🎉 انضم صديق جديد عبر رابطك!\n👥 إجمالي دعواتك: {count}/{REQUIRED_REFERRALS}")
                    if count >= REQUIRED_REFERRALS and claimed == 0:
                        bot.send_message(referrer_id, f"🎁 مبروك! لقد أتممت دعوة شخصين بنجاح، يمكنك الآن استلام حساب Gemini Pro مباشرة من البوت!")
                except Exception:
                    pass

    # التحقق من شرط الانضمام للمجموعة أولاً
    if not is_user_in_group(GROUP_CHAT_ID, user_id):
        markup = types.InlineKeyboardMarkup()
        btn_group = types.InlineKeyboardButton("👥 انضم إلى المجموعة أولاً", url=GROUP_INVITE_LINK)
        btn_check = types.InlineKeyboardButton("✅ تم الانضمام، تحقق الآن", callback_data="check_group")
        markup.add(btn_group)
        markup.add(btn_check)

        bot.send_message(
            user_id,
            f"مرحباً {first_name} 👋\n\n"
            f"⚠️ **يجب عليك الانضمام إلى مجموعتنا أولاً** للمتابعة والحصول على Gemini Pro مجاناً:\n\n"
            f"1. اضغط على الزر بالأسفل وانضم للمجموعة.\n"
            f"2. ارجع واضغط على زر **تم الانضمام، تحقق الآن**.",
            reply_markup=markup,
            parse_mode="Markdown"
        )
        return

    # إذا كان منضماً بالفعل، اعرض لوحة الدعوات
    send_user_dashboard(user_id, first_name)

# زر التحقق من الانضمام
@bot.callback_query_handler(func=lambda call: call.data == "check_group")
def callback_check_group(call):
    user_id = call.from_user.id
    first_name = call.from_user.first_name

    if is_user_in_group(GROUP_CHAT_ID, user_id):
        bot.delete_message(chat_id=user_id, message_id=call.message.message_id)
        send_user_dashboard(user_id, first_name)
    else:
        bot.answer_callback_query(call.id, "❌ لم تنضم إلى المجموعة بعد! الرجاء الانضمام أولاً ثم المحاولة مجدداً.", show_alert=True)

# ----------------- لوحة تحكم المشرف (Admin) -----------------
@bot.message_handler(commands=['admin'])
def admin_panel(message):
    if message.from_user.id != ADMIN_ID:
        return

    markup = types.InlineKeyboardMarkup(row_width=2)
    btn_stats = types.InlineKeyboardButton("📊 الإحصائيات", callback_data="admin_stats")
    btn_link = types.InlineKeyboardButton("⚙️ تعديل رابط الهدية", callback_data="admin_setlink")
    btn_broadcast = types.InlineKeyboardButton("📢 إذاعة رسالة للجميع", callback_data="admin_broadcast")
    
    markup.add(btn_stats, btn_link)
    markup.add(btn_broadcast)

    bot.send_message(ADMIN_ID, "⚙️ **لوحة تحكم المسؤول:**\nاختر من الأزرار بالأسفل لإدارة البوت:", reply_markup=markup, parse_mode="Markdown")

@bot.callback_query_handler(func=lambda call: call.data.startswith('admin_'))
def handle_admin_callbacks(call):
    if call.from_user.id != ADMIN_ID:
        return

    if call.data == "admin_stats":
        cursor.execute("SELECT COUNT(*) FROM users")
        total_users = cursor.fetchone()[0]

        cursor.execute("SELECT SUM(referral_count) FROM users")
        total_refs = cursor.fetchone()[0] or 0

        cursor.execute("SELECT COUNT(*) FROM users WHERE referral_count >= 2")
        total_eligible = cursor.fetchone()[0]

        stats_text = (
            f"📊 **إحصائيات البوت الحالية:**\n\n"
            f"👤 إجمالي الأعضاء: `{total_users}`\n"
            f"🔗 إجمالي الدعوات: `{total_refs}`\n"
            f"🎁 المؤهلين للهدية (أتموا شخصين): `{total_eligible}`\n"
            f"🌐 رابط الهدية الحالي:\n{get_reward_link()}"
        )
        bot.edit_message_text(stats_text, chat_id=ADMIN_ID, message_id=call.message.message_id, parse_mode="Markdown")

    elif call.data == "admin_setlink":
        admin_states[ADMIN_ID] = "waiting_for_link"
        bot.send_message(ADMIN_ID, "✍️ أرسل الآن رابط Gemini Pro الجديد (يجب أن يبدأ بـ https://):")

    elif call.data == "admin_broadcast":
        admin_states[ADMIN_ID] = "waiting_for_broadcast"
        bot.send_message(ADMIN_ID, "✍ أرسل نص الرسالة التي تريد إذاعتها لجميع الأعضاء:")

@bot.message_handler(func=lambda msg: msg.from_user.id == ADMIN_ID and admin_states.get(ADMIN_ID) is not None)
def handle_admin_inputs(message):
    state = admin_states.get(ADMIN_ID)

    if state == "waiting_for_link":
        new_url = message.text.strip()
        if new_url.startswith("http://") or new_url.startswith("https://"):
            set_reward_link(new_url)
            bot.send_message(ADMIN_ID, f"✅ تم تحديث رابط الهدية بنجاح:\n{new_url}")
        else:
            bot.send_message(ADMIN_ID, "❌ رابط غير صحيح! تأكد من تضمين https://")
        admin_states[ADMIN_ID] = None

    elif state == "waiting_for_broadcast":
        broadcast_text = message.text
        cursor.execute("SELECT user_id FROM users")
        all_users = cursor.fetchall()
        
        sent_count = 0
        bot.send_message(ADMIN_ID, "⏳ جاري الإرسال إلى جميع المستخدمين...")
        
        for user in all_users:
            uid = user[0]
            try:
                bot.send_message(uid, broadcast_text)
                sent_count += 1
            except Exception:
                pass
        
        bot.send_message(ADMIN_ID, f"✅ تم إرسال الإذاعة بنجاح إلى `{sent_count}` مستخدم!")
        admin_states[ADMIN_ID] = None

# ----------------- بدء التشغيل -----------------
if __name__ == "__main__":
    web_proc = Process(target=start_server)
    web_proc.daemon = True
    web_proc.start()

    print("Bot is successfully running...")
    bot.infinity_polling(timeout=10, long_polling_timeout=5)

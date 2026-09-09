import sqlite3
import threading
import time
from contextlib import contextmanager
import telebot
from telebot.types import (
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    KeyboardButton,
    ReplyKeyboardMarkup,
)

# توکن ربات شما
TOKEN = '8917136162:AAF73BDlVRCbHhmzvIG_Jq_LBqCGQ6_m2C0'
bot = telebot.TeleBot(TOKEN, threaded=True)

# کانال گزارش‌گیری و کانال عضویت اجباری
CHANNEL_USERNAME = '@andksaox'
FORCED_CHANNEL = '@Rbnwei'
user_states = {}

# سیستم مدیریت دیتابیس فوق‌پیشرفته با Context Manager برای سرعت و پایداری حداکثری
@contextmanager
def get_db():
    conn = sqlite3.connect('bot_database.db', timeout=30.0, check_same_thread=False)
    conn.execute("PRAGMA journal_mode=WAL;")  # فعال‌سازی حالت Write-Ahead Logging برای افزایش سرعت خواندن و نوشتن همزمان
    conn.execute("PRAGMA synchronous=NORMAL;")
    try:
        yield conn
    finally:
        conn.close()

def init_db():
    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS users (
                user_id INTEGER PRIMARY KEY,
                username TEXT,
                first_name TEXT,
                balance REAL DEFAULT 0.0,
                refs INTEGER DEFAULT 0,
                wallet TEXT DEFAULT 'ثبت نشده ❌',
                invited_by INTEGER
            )
        ''')
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS referred_users (
                referrer_id INTEGER,
                referred_id INTEGER,
                PRIMARY KEY (referrer_id, referred_id)
            )
        ''')
        conn.commit()

init_db()

def get_user(user_id):
    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute('SELECT user_id, balance, refs, wallet, invited_by FROM users WHERE user_id = ?', (user_id,))
        row = cursor.fetchone()
    if row:
        return {
            'balance': row[1],
            'refs': row[2],
            'wallet': row[3],
            'invited_by': row[4]
        }
    return None

def create_user(user_id, username, first_name):
    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute('''
            INSERT OR IGNORE INTO users (user_id, username, first_name, balance, refs, wallet, invited_by)
            VALUES (?, ?, ?, 0.0, 0, 'ثبت نشده ❌', NULL)
        ''', (user_id, username, first_name))
        conn.commit()

def update_user_balance_refs(referrer_id, new_balance, new_refs, referred_id):
    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute('UPDATE users SET balance = ?, refs = ? WHERE user_id = ?', (new_balance, new_refs, referrer_id))
        cursor.execute('UPDATE users SET invited_by = ? WHERE user_id = ?', (referrer_id, referred_id))
        cursor.execute('INSERT OR IGNORE INTO referred_users (referrer_id, referred_id) VALUES (?, ?)', (referrer_id, referred_id))
        conn.commit()

def update_user_wallet(user_id, wallet):
    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute('UPDATE users SET wallet = ? WHERE user_id = ?', (wallet, user_id))
        conn.commit()

def is_already_referred(referrer_id, referred_id):
    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute('SELECT 1 FROM referred_users WHERE referrer_id = ? AND referred_id = ?', (referrer_id, referred_id))
        row = cursor.fetchone()
    return row is not None

def colored_menu():
    markup = ReplyKeyboardMarkup(resize_keyboard=True, row_width=2)
    btn_account = KeyboardButton('👤 حساب کاربری')
    btn_withdraw = KeyboardButton('💳 برداشت')
    btn_refs = KeyboardButton('👥 زیرمجموعه گیری')
    btn_help = KeyboardButton('❓ راهنما')
    markup.add(btn_account)
    markup.add(btn_withdraw, btn_refs)
    markup.add(btn_help)
    return markup

def check_membership(user_id):
    try:
        member = bot.get_chat_member(FORCED_CHANNEL, user_id)
        if member.status in ['member', 'creator', 'administrator']:
            return True
    except Exception as e:
        print(f"Error checking membership: {e}")
    return False

def forced_sub_markup():
    markup = InlineKeyboardMarkup(row_width=1)
    markup.add(
        InlineKeyboardButton('🔗 عضویت در Rbnwei', url='https://t.me/Rbnwei'),
        InlineKeyboardButton('✅ عضو شدم', callback_data='check_sub')
    )
    return markup

@bot.message_handler(commands=['start'])
def send_welcome(message):
    try:
        user_id = message.from_user.id
        if not check_membership(user_id):
            stylish_text = "⚠️ جوین اجباری !\n\nبرای استفاده باید عضو کانال‌ها باشید"
            bot.send_message(message.chat.id, stylish_text, reply_markup=forced_sub_markup())
            return
        process_start_after_sub(message)
    except Exception as e:
        print(f"Error in start: {e}")

def process_start_after_sub(message):
    user_id = message.from_user.id
    username = message.from_user.username
    first_name = message.from_user.first_name or "کاربر"
    
    if username:
        user_display_name = f"@{username}"
    else:
        user_display_name = f"[{first_name}](tg://user?id={user_id})"

    user_data = get_user(user_id)
    is_new_user = user_data is None

    if is_new_user:
        create_user(user_id, username, first_name)
        user_data = get_user(user_id)

    args = message.text.split()
    
    if len(args) > 1 and user_data['invited_by'] is None:
        try:
            referrer_id = int(args[1])
            referrer_data = get_user(referrer_id)
            
            if referrer_id != user_id and referrer_data and not is_already_referred(referrer_id, user_id):
                new_balance = referrer_data['balance'] + 8.0
                new_refs = referrer_data['refs'] + 1
                
                update_user_balance_refs(referrer_id, new_balance, new_refs, user_id)
                
                # ارسال پیام دقیق به معرف
                try:
                    notify_referrer_text = f"کاربر {user_display_name} با موفقیت به زیرمجموعه شما اضافه شد ✅"
                    bot.send_message(referrer_id, notify_referrer_text, parse_mode='Markdown')
                except Exception as ex:
                    print(f"Could not message referrer: {ex}")
                
                # ارسال گزارش به کانال
                try:
                    ref_log_text = (
                        "🤝 **زیرمجموعه جدید ثبت شد!**\n\n"
                        f"👤 معرف (دعوت‌کننده): `{referrer_id}`\n"
                        f"👥 دعوت‌شده: {user_display_name} (`{user_id}`)"
                    )
                    bot.send_message(CHANNEL_USERNAME, ref_log_text, parse_mode='Markdown')
                except Exception as ex:
                    print(f"Error sending ref log: {ex}")
        except ValueError:
            pass

    welcome_text = "سلام 👀\nبه ربات ما خوش‌اومدی.\n\nخدمات مورد نظرت رو انتخاب کن 👇"
    bot.send_message(message.chat.id, welcome_text, reply_markup=colored_menu())

@bot.message_handler(func=lambda message: True)
def handle_messages(message):
    try:
        user_id = message.from_user.id
        if not check_membership(user_id):
            stylish_text = "⚠️ جوین اجباری !\n\nبرای استفاده باید عضو کانال‌ها باشید"
            bot.send_message(message.chat.id, stylish_text, reply_markup=forced_sub_markup())
            return

        text = message.text
        user_data = get_user(user_id)
        if not user_data:
            create_user(user_id, message.from_user.username, message.from_user.first_name or "کاربر")
            user_data = get_user(user_id)

        if user_states.get(user_id) == 'waiting_for_bnb_wallet':
            wallet_address = text.strip()
            user_states[user_id] = None
            update_user_wallet(user_id, wallet_address)
            
            withdraw_amount = 75.0
            channel_text = (
                "🔔 **درخواست برداشت جدید!**\n\n"
                f"👤 **آیدی کاربر:** `{user_id}`\n"
                f"💵 **مبلغ درخواستی:** `${withdraw_amount}`\n"
                f"👥 **تعداد زیرمجموعه‌ها:** `{user_data['refs']} نفر`\n"
                f"💳 **آدرس ولت BEP20 کاربر:**\n`{wallet_address}`\n\n"
                "👇 مدیر محترم، پس از واریز به ولت شخص، روی دکمه تایید کلیک کنید:"
            )
            markup = InlineKeyboardMarkup()
            markup.add(InlineKeyboardButton('✅ تایید و ارسال واریزی', callback_data=f'pay_done_{user_id}'))
            
            try:
                bot.send_message(CHANNEL_USERNAME, channel_text, reply_markup=markup, parse_mode='Markdown')
            except Exception as ex:
                print(f"Error sending to channel: {ex}")

            success_withdraw_text = "درخواست برداشت شما با موفقیت ثبت شد ✅\n\nآدرس ولت شما دریافت شد. پس از بررسی و واریز مدیریت، تاییدیه به شما اعلام می‌گردد 🔜"
            bot.send_message(message.chat.id, success_withdraw_text, reply_markup=colored_menu())
            return

        if text == '👤 حساب کاربری':
            bot_username = bot.get_me().username
            invite_link = f"https://t.me/{bot_username}?start={user_id}"
            account_text = (
                "📢 با دعوت دوستانت درآمد کسب کن! \n\n"
                "دوستانت را به ربات دعوت کن و به ازای هر نفری که دعوت می‌کنی 8.0$ پاداش بگیر و درآمد واقعی داشته باش! 🎁 \n\n"
                f"🔗 لینک اختصاصی دعوت شما:\n{invite_link}\n\n"
                "⏳ فرصت را از دست نده! هرچه افراد بیشتری را دعوت کنی، سریع‌تر موجودی‌ات را افزایش می‌دهی و می‌توانی آن را برداشت کنی. ✅"
            )
            bot.send_message(message.chat.id, account_text)

        elif text == '💳 برداشت':
            balance = user_data['balance']
            refs = user_data['refs']
            if balance < 75.0:
                error_text = "❌ موجودی شما کمتر از حداقل برداشت است.\nحداقل برداشت : 75.0$"
                bot.send_message(message.chat.id, error_text)
            elif refs < 9:
                bot.send_message(message.chat.id, '❌ برای برداشت باید حداقل ۹ نفر را دعوت کرده باشید.')
            else:
                user_states[user_id] = 'waiting_for_bnb_wallet'
                bot.send_message(
                    message.chat.id,
                    '🌐 ادرس شبکه bep20 خودتون رو طبق آموزش از تراست ولت ارسال کنید :',
                    reply_markup=ReplyKeyboardMarkup(resize_keyboard=True).add(KeyboardButton('❌ انصراف'))
                )

        elif text == '❌ انصراف':
            user_states[user_id] = None
            bot.send_message(message.chat.id, 'عملیات لغو شد.', reply_markup=colored_menu())

        elif text == '👥 زیرمجموعه گیری':
            balance = user_data['balance']
            refs = user_data['refs']
            bot_username = bot.get_me().username
            invite_link = f"https://t.me/{bot_username}?start={user_id}"
            invite_text = (
                f"👤 آیدی شما : {user_id}\n"
                f"💰 موجودی شما : ${balance}\n"
                f"👥 تعداد زیرمجموعه های شما : {refs}\n"
                f"💸 حداقل مبلغ برداشت : 75.0$\n\n"
                f"لینک زیرمجموعه گیری شما:\n{invite_link}"
            )
            markup = InlineKeyboardMarkup()
            markup.add(InlineKeyboardButton('📝 کپی لینک دعوت 📋', callback_data='copy_invite_link'))
            bot.send_message(message.chat.id, invite_text, reply_markup=markup)

        elif text == '❓ راهنما':
            help_text = (
                "🌐 آموزش دریافت آدرس شبکه BEP20 از تراست ولت\n\n"
                "برای برداشت وجه، باید آدرس کیف پول خودتون با شبکه‌ی BEP20 (BSC) رو ارسال کنید. مراحل زیر رو دنبال کنید:\n\n"
                "۱. اپلیکیشن Trust Wallet رو باز کنید\n"
                "۲. دکمه‌ی Receive (دریافت) رو بزنید\n"
                "۳. ارز BNB رو انتخاب کنید (شبکه‌ش به‌صورت پیش‌فرض BEP20 هست)\n"
                "✅ آدرسی که نمایش داده می‌شه رو کپی کنید (با آیکون کپی کنار آدرس)\n\n"
                "🔗 توجه داشته باشید آدرس شبکه‌ی BEP20 برای همه‌ی ارزها یکسانه.\n\n"
                "❌ مهم: اگه شبکه‌ی اشتباه (مثل ERC20 یا TRC20) رو انتخاب کنید، امکان واریز وجود نداره و ممکنه دارایی‌تون از دست بره.\n\n"
                "بعد از کپی کردن آدرس، اون رو دقیقاً همون‌طور که کپی کردید (بدون فاصله یا کاراکتر اضافه) برای ربات ارسال کنید."
            )
            bot.send_message(message.chat.id, help_text)

    except Exception as e:
        print(f"Error handling message: {e}")

@bot.callback_query_handler(func=lambda call: True)
def callback_inline(call):
    try:
        user_id = call.from_user.id
        data = call.data

        if data == 'check_sub':
            if check_membership(user_id):
                bot.answer_callback_query(call.id, "عضویت شما با موفقیت تایید شد! ✅", show_alert=False)
                try:
                    bot.delete_message(call.message.chat.id, call.message.message_id)
                except:
                    pass
                welcome_text = "سلام 👀\nبه ربات ما خوش‌اومدی.\n\nخدمات مورد نظرت رو انتخاب کن 👇"
                bot.send_message(call.message.chat.id, welcome_text, reply_markup=colored_menu())
            else:
                bot.answer_callback_query(call.id, "❌ شما هنوز در کانال عضو نشده‌اید!", show_alert=True)

        elif data == 'copy_invite_link':
            bot_username = bot.get_me().username
            invite_link = f"https://t.me/{bot_username}?start={user_id}"
            bot.answer_callback_query(call.id, "لینک دعوت شما آماده شد 👇")
            bot.send_message(
                call.message.chat.id,
                f"🔗 لینک دعوت اختصاصی شما:\n`{invite_link}`\n\n(برای کپی کردن روی لینک بالا ضربه بزنید)",
                parse_mode='Markdown'
            )

        elif data.startswith('pay_done_'):
            target_user_id = int(data.split('_')[2])
            bot.answer_callback_query(call.id, "تایید شد. پیام واریزی با تاخیر ۱ دقیقه به کاربر ارسال می‌شود.")
            try:
                bot.edit_message_text(
                    chat_id=call.message.chat.id,
                    message_id=call.message.message_id,
                    text=call.message.text + "\n\n✅ **وضعیت: واریز انجام شد و تایید گردید!**",
                    parse_mode='Markdown'
                )
            except Exception as ex:
                print(f"Error updating channel message: {ex}")

            def send_success_with_delay():
                time.sleep(60)
                success_paid_text = "✅ پرداخت شما با موفقیت انجام شد!\n\nمبلغ درخواستی به ولت شما واریز گردید."
                try:
                    bot.send_message(target_user_id, success_paid_text)
                except Exception as ex:
                    print(f"Could not message user after delay: {ex}")

            threading.Thread(target=send_success_with_delay).start()

    except Exception as e:
        print(f"Error in callback: {e}")

print("Ultra High-Speed Enterprise-Grade Bot is running flawlessly...")
bot.infinity_polling(skip_pending=True, timeout=60, long_polling_timeout=60)

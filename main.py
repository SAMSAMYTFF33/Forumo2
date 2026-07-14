import asyncio
import os
import re
import logging
from collections import deque
from functools import wraps

from telethon import TelegramClient, events
from telegram import Update
from telegram.ext import Application, CommandHandler, ContextTypes

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# --- إعدادات Telethon (يفضّل وضعها كمتغيرات بيئة عند النشر على الاستضافة) ---
API_ID = int(os.getenv("API_ID", "31568734"))
API_HASH = os.getenv("API_HASH", "7286e8c92ccc4dc698d771664bf71700")
PHONE = os.getenv("PHONE", "+212718450902")
CONTROL_BOT_TOKEN = os.getenv("CONTROL_BOT_TOKEN", "8769711531:AAHML0z9xgdsPnzpsbQP6VwPeathADN01L8")

tclient = TelegramClient('my_session', API_ID, API_HASH)

OWNER_ID = None  # يُملأ تلقائيًا بأول مستخدم يرسل /start

# --- إعدادات المراقبة ---
CHANNEL = 'alihasanivip'
TARGET_BOT = 'maestro'
BUTTON_TEXT = '0.00268 ETH'
CONTRACT_PATTERN = re.compile(r'0x[a-fA-F0-9]{20,}')

# نحتفظ فقط بآخر 200 معرف رسالة بدل تخزينها كلها للأبد (توفير ذاكرة على استضافة مجانية)
_sent_ids = deque(maxlen=200)
_sent_ids_set = set()


def is_sent(msg_id: int) -> bool:
    return msg_id in _sent_ids_set


def mark_sent(msg_id: int) -> None:
    if len(_sent_ids) == _sent_ids.maxlen:
        oldest = _sent_ids[0]
        _sent_ids_set.discard(oldest)
    _sent_ids.append(msg_id)
    _sent_ids_set.add(msg_id)


is_monitoring = False
control_chat_id = None  # الشات اللي يوصله إشعارات المراقبة
app_ref = None  # مرجع لبوت التحكم عشان نقدر نرسل رسائل من داخل event handler


# ---------------- حماية: تقييد الأوامر بصاحب البوت فقط ----------------

def owner_only(func):
    @wraps(func)
    async def wrapper(update: Update, context: ContextTypes.DEFAULT_TYPE):
        if OWNER_ID is not None and update.effective_chat.id != OWNER_ID:
            await update.message.reply_text("هذا البوت خاص، غير مصرح لك باستخدامه.")
            return
        return await func(update, context)
    return wrapper


async def click_bot_button(wait_seconds=2, retries=5):
    for _ in range(retries):
        await asyncio.sleep(wait_seconds)
        messages = await tclient.get_messages(TARGET_BOT, limit=1)
        last_message = messages[0]
        if last_message.buttons:
            for row in last_message.buttons:
                for button in row:
                    if BUTTON_TEXT in button.text:
                        await last_message.click(text=button.text)
                        return True
    return False


@tclient.on(events.NewMessage(chats=CHANNEL))
async def on_new_channel_message(event):
    """يُستدعى تلقائيًا فور وصول رسالة جديدة في القناة — لا يوجد أي فحص دوري."""
    if not is_monitoring or control_chat_id is None or app_ref is None:
        return

    msg = event.message
    if is_sent(msg.id):
        return
    mark_sent(msg.id)

    try:
        text = msg.text or ''
        match = CONTRACT_PATTERN.search(text)
        if not match:
            return

        contract_address = match.group()
        await app_ref.bot.send_message(control_chat_id, f"وُجد عقد: {contract_address}")

        if msg.media:
            await tclient.send_file(TARGET_BOT, msg.media, caption=text)
        else:
            await tclient.send_message(TARGET_BOT, text)

        clicked = await click_bot_button()
        status = "تم الضغط على الزر" if clicked else "لم يُعثر على الزر"
        await app_ref.bot.send_message(control_chat_id, status)
    except Exception as e:
        logger.exception("خطأ أثناء معالجة رسالة القناة")
        await app_ref.bot.send_message(control_chat_id, f"خطأ: {e}")


# ---------------- أوامر بوت التحكم ----------------

async def start_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    global OWNER_ID
    if OWNER_ID is None:
        OWNER_ID = update.effective_chat.id

    await tclient.connect()
    authorized = await tclient.is_user_authorized()

    if not authorized:
        await update.message.reply_text(
            "أهلاً. حسابك غير مسجل الدخول بعد.\n"
            "أرسل /login للبدء بتسجيل الدخول."
        )
        return

    await update.message.reply_text(
        "أهلاً. الحساب مسجل الدخول بالفعل. الأوامر المتاحة:\n"
        "/run - بدء المراقبة\n"
        "/stop - إيقاف المراقبة\n"
        "/status - حالة الاتصال والمراقبة"
    )


@owner_only
async def login_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await tclient.connect()
    if await tclient.is_user_authorized():
        await update.message.reply_text("الحساب مسجل دخول بالفعل.")
        return
    await tclient.send_code_request(PHONE)
    await update.message.reply_text("أرسل الكود عبر: /code 12345")


@owner_only
async def code_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not context.args:
        await update.message.reply_text("استخدم: /code 12345")
        return
    code = context.args[0]
    try:
        await tclient.sign_in(PHONE, code)
        await update.message.reply_text("تم تسجيل الدخول بنجاح.")
    except Exception as e:
        await update.message.reply_text(
            f"خطأ في تسجيل الدخول: {e}\nإذا كان حسابك يستخدم كلمة مرور (2FA) استخدم: /pass كلمتك"
        )


@owner_only
async def pass_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not context.args:
        await update.message.reply_text("استخدم: /pass كلمة_المرور")
        return
    password = context.args[0]
    try:
        await tclient.sign_in(password=password)
        await update.message.reply_text("تم تسجيل الدخول بنجاح.")
    except Exception as e:
        await update.message.reply_text(f"خطأ: {e}")


@owner_only
async def run_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    global is_monitoring, control_chat_id
    if not await tclient.is_user_authorized():
        await update.message.reply_text("سجّل الدخول أولاً باستخدام /login")
        return
    if is_monitoring:
        await update.message.reply_text("المراقبة تعمل بالفعل.")
        return
    control_chat_id = update.effective_chat.id
    is_monitoring = True
    await update.message.reply_text(
        "تم تفعيل المراقبة — بيتم الاستماع للقناة مباشرة، بدون أي فحص دوري."
    )


@owner_only
async def stop_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    global is_monitoring
    is_monitoring = False
    await update.message.reply_text("تم إيقاف المراقبة.")


@owner_only
async def status_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    authorized = await tclient.is_user_authorized()
    await update.message.reply_text(
        f"تسجيل الدخول: {'نعم' if authorized else 'لا'}\n"
        f"المراقبة: {'تعمل' if is_monitoring else 'متوقفة'}"
    )


async def main():
    global app_ref

    # نتصل بحساب Telethon أولاً حتى يبدأ استقبال أحداث القناة فور توفر الجلسة المسجّلة
    await tclient.connect()

    app = Application.builder().token(CONTROL_BOT_TOKEN).build()
    app_ref = app
    app.add_handler(CommandHandler("start", start_cmd))
    app.add_handler(CommandHandler("login", login_cmd))
    app.add_handler(CommandHandler("code", code_cmd))
    app.add_handler(CommandHandler("pass", pass_cmd))
    app.add_handler(CommandHandler("run", run_cmd))
    app.add_handler(CommandHandler("stop", stop_cmd))
    app.add_handler(CommandHandler("status", status_cmd))

    await app.initialize()
    await app.start()
    await app.updater.start_polling()
    logger.info("بوت التحكم يعمل...")
    await asyncio.Event().wait()


if __name__ == '__main__':
    asyncio.run(main())

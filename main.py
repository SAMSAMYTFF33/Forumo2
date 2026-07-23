import asyncio
import os
import re
import logging
from functools import wraps

from telethon import TelegramClient, events
from telethon.sessions import StringSession
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    Application,
    CommandHandler,
    CallbackQueryHandler,
    MessageHandler,
    ContextTypes,
    filters,
)

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# --- جلسة النص (StringSession) ---
SESSION_STRING = os.getenv("SESSION_STRING", "1BJWap1sBu3JY9awpmqTkj51uBuZiJyagDto0DjpRJjeLaUuJTQ69d2FQSfHy-in4KKoE7ig6SAmsGn8yQXeF3DzCtBkGBm53VL1meYxuBvigY95Amdu5jbFwc4zI0cl1b8lp7jcmgmGsazTUmr7vb05IXualVliMkRWLanVcnBu9aaPbKtOObXmSDdOn13WJE78OCJhoWXXOEhkqQ-q6KskZf2xyg6pPPBj0rUAvaFka5DvMY0cdi1E1rBrQfkJ_JVPLT8jiYqiM3kV1Q--Y3sRKhjnn-WZillqh6u8fRmzujkz9TUrPYfoKpZtCZ0UMSoA3dUMqCNnSpziHrg_ggIdXGDlI1Y0=")

# --- إعدادات API (تقرأ من متغيرات البيئة) ---
API_ID = int(os.getenv("API_ID", "31568734"))
API_HASH = os.getenv("API_HASH", "7286e8c92ccc4dc698d771664bf71700")
CONTROL_BOT_TOKEN = os.getenv("CONTROL_BOT_TOKEN", "8769711531:AAHML0z9xgdsPnzpsbQP6VwPeathADN01L8")

tclient = TelegramClient(StringSession(SESSION_STRING), API_ID, API_HASH)

OWNER_ID = None  # يُملأ تلقائيًا بأول مستخدم يرسل /start

# --- إعدادات المراقبة ---
CHANNEL = 'alihasanivip'
TARGET_BOT = 'maestro'
CONTRACT_PATTERN = re.compile(r'0x[a-fA-F0-9]{20,}')

# ---------------- تخصيص السعر ----------------
BUTTON_TEXT = os.getenv("BUTTON_TEXT", "0.00268 ETH")
BUY_UNIT = os.getenv("BUY_UNIT", "ETH")

_awaiting_price_input = False

is_monitoring = False
_control_context: ContextTypes.DEFAULT_TYPE = None
_control_chat_id = None


# ---------------- حماية: تقييد الأوامر بصاحب البوت فقط ----------------

def owner_only(func):
    @wraps(func)
    async def wrapper(update: Update, context: ContextTypes.DEFAULT_TYPE):
        if OWNER_ID is not None and update.effective_chat.id != OWNER_ID:
            await update.message.reply_text("هذا البوت خاص، غير مصرح لك باستخدامه.")
            return
        return await func(update, context)
    return wrapper


def owner_only_callback(func):
    @wraps(func)
    async def wrapper(update: Update, context: ContextTypes.DEFAULT_TYPE):
        query = update.callback_query
        if OWNER_ID is not None and query.message.chat.id != OWNER_ID:
            await query.answer("غير مصرح لك.", show_alert=True)
            return
        return await func(update, context)
    return wrapper


async def click_bot_button(timeout_seconds=10):
    done = asyncio.Event()
    result = {"clicked": False}

    async def target_reply_handler(event):
        message = event.message
        if message.buttons:
            for row in message.buttons:
                for button in row:
                    if BUTTON_TEXT in button.text:
                        await message.click(text=button.text)
                        result["clicked"] = True
                        done.set()
                        return

    tclient.add_event_handler(
        target_reply_handler,
        events.NewMessage(chats=TARGET_BOT)
    )

    try:
        await asyncio.wait_for(done.wait(), timeout=timeout_seconds)
    except asyncio.TimeoutError:
        pass
    finally:
        tclient.remove_event_handler(target_reply_handler, events.NewMessage(chats=TARGET_BOT))

    return result["clicked"]


# ---------------- المستمع الفوري (event-driven) ----------------

@tclient.on(events.NewMessage(chats=CHANNEL))
async def on_new_channel_message(event):
    if not is_monitoring:
        return
    if _control_context is None or _control_chat_id is None:
        return

    await _control_context.bot.send_message(_control_chat_id, "📩 القناة أرسلت رسالة جديدة.")

    text = event.raw_text or ''
    match = CONTRACT_PATTERN.search(text)
    if not match:
        return

    contract_address = match.group()
    await _control_context.bot.send_message(_control_chat_id, f"🔍 وُجد عقد: {contract_address}")

    try:
        if event.message.media:
            await tclient.send_file(TARGET_BOT, event.message.media, caption=text)
        else:
            await tclient.send_message(TARGET_BOT, text)

        clicked = await click_bot_button()
        if clicked:
            await _control_context.bot.send_message(
                _control_chat_id,
                f"✅ تم إتمام الأمر بنجاح (السعر المستخدم: {BUTTON_TEXT}).\nالعقد: {contract_address}"
            )
        else:
            await _control_context.bot.send_message(
                _control_chat_id,
                f"⚠️ لم يُعثر على الزر المطلوب ({BUTTON_TEXT}) لدى {TARGET_BOT}. لم يتم تنفيذ الأمر.\nالعقد: {contract_address}"
            )
    except Exception as e:
        logger.exception("خطأ أثناء معالجة الرسالة")
        await _control_context.bot.send_message(_control_chat_id, f"❌ خطأ: {e}")


# ---------------- أوامر بوت التحكم ----------------

async def start_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    global OWNER_ID
    if OWNER_ID is None:
        OWNER_ID = update.effective_chat.id

    if not tclient.is_connected():
        await tclient.connect()
    authorized = await tclient.is_user_authorized()

    if not authorized:
        await update.message.reply_text(
            "أهلاً. الجلسة غير صالحة أو منتهية الصلاحية.\n"
            "يجب توليد جلسة جديدة وإعادة تشغيل البوت."
        )
        return

    keyboard = [[InlineKeyboardButton("🔧 تخصيص السعر", callback_data="ask_price")]]
    await update.message.reply_text(
        "أهلاً. الحساب مسجل دخول. الأوامر المتاحة:\n"
        "/run - بدء المراقبة الفورية\n"
        "/stop - إيقاف المراقبة\n"
        "/status - حالة الاتصال والمراقبة",
        reply_markup=InlineKeyboardMarkup(keyboard)
    )


@owner_only
async def run_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    global is_monitoring, _control_context, _control_chat_id
    if not await tclient.is_user_authorized():
        await update.message.reply_text("الجلسة غير صالحة. يجب تحديث SESSION_STRING.")
        return
    if is_monitoring:
        await update.message.reply_text("المراقبة تعمل بالفعل.")
        return

    _control_context = context
    _control_chat_id = update.effective_chat.id
    is_monitoring = True
    await update.message.reply_text("تم تشغيل المراقبة الفورية بنجاح.")


@owner_only
async def stop_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    global is_monitoring
    is_monitoring = False
    await update.message.reply_text("تم إيقاف المراقبة.")


@owner_only
async def status_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    authorized = await tclient.is_user_authorized()
    keyboard = [[InlineKeyboardButton("🔧 تخصيص السعر", callback_data="ask_price")]]
    await update.message.reply_text(
        f"تسجيل الدخول: {'نعم' if authorized else 'لا'}\n"
        f"المراقبة: {'تعمل (فورية)' if is_monitoring else 'متوقفة'}\n"
        f"السعر الحالي (نص الزر): {BUTTON_TEXT}",
        reply_markup=InlineKeyboardMarkup(keyboard)
    )


@owner_only
async def setbuy_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    keyboard = [[InlineKeyboardButton("🔧 تخصيص السعر", callback_data="ask_price")]]
    await update.message.reply_text(
        f"السعر الحالي (نص الزر): {BUTTON_TEXT}\n"
        f"عند الضغط على الزر، تكتب رقمًا فقط وسيُضاف {BUY_UNIT} تلقائيًا.",
        reply_markup=InlineKeyboardMarkup(keyboard)
    )


@owner_only_callback
async def ask_price_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    global _awaiting_price_input
    query = update.callback_query
    _awaiting_price_input = True
    await query.answer()
    await query.message.reply_text(
        f"السعر الحالي: {BUTTON_TEXT}\n"
        f"أرسل الآن الرقم فقط بدون كتابة {BUY_UNIT} (مثال: 0.005) وسيتم إضافة {BUY_UNIT} تلقائيًا."
    )


async def receive_price_text(update: Update, context: ContextTypes.DEFAULT_TYPE):
    global BUTTON_TEXT, _awaiting_price_input

    if not _awaiting_price_input:
        return

    if OWNER_ID is not None and update.effective_chat.id != OWNER_ID:
        return

    raw_value = (update.message.text or "").strip()
    normalized = raw_value.replace(",", ".").replace(BUY_UNIT, "").strip()

    try:
        number = float(normalized)
    except ValueError:
        await update.message.reply_text(
            f"⚠️ يجب إرسال رقم فقط (مثال: 0.005) بدون كتابة {BUY_UNIT}، حاول مجددًا."
        )
        return

    formatted_number = f"{number:.10f}".rstrip("0").rstrip(".")
    if formatted_number == "" or formatted_number == "-":
        formatted_number = "0"

    BUTTON_TEXT = f"{formatted_number} {BUY_UNIT}"
    _awaiting_price_input = False
    await update.message.reply_text(f"✅ تم تعيين السعر الجديد إلى: {BUTTON_TEXT}")


async def main():
    await tclient.start()
    logger.info("Telethon client متصل، بانتظار رسائل القناة...")

    app = Application.builder().token(CONTROL_BOT_TOKEN).build()
    app.add_handler(CommandHandler("start", start_cmd))
    app.add_handler(CommandHandler("run", run_cmd))
    app.add_handler(CommandHandler("stop", stop_cmd))
    app.add_handler(CommandHandler("status", status_cmd))
    app.add_handler(CommandHandler("setbuy", setbuy_cmd))
    app.add_handler(CallbackQueryHandler(ask_price_callback, pattern="^ask_price$"))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, receive_price_text))

    await app.initialize()
    await app.start()
    await app.updater.start_polling()
    logger.info("بوت التحكم يعمل...")

    await tclient.run_until_disconnected()


if __name__ == '__main__':
    asyncio.run(main())

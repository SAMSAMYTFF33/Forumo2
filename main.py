import os
import telebot
from telebot.types import InlineKeyboardMarkup, InlineKeyboardButton

# ضع توكن البوت الخاص بك هنا
BOT_TOKEN = "8769711531:AAHML0z9xgdsPnzpsbQP6VwPeathADN01L8"
bot = telebot.TeleBot(BOT_TOKEN)

# 1. عند ضغط /start أو تشغيل البوت
@bot.message_handler(commands=['start'])
def send_welcome(message):
    filename = "TEST.txt"

    # التحقق من وجود الملف
    if os.path.exists(filename):
        bot.reply_to(message, f"✅ تم العثور على الملف `{filename}` بنجاح على الاستضافة!", parse_mode="Markdown")
    else:
        # إنشاء أزرار تفاعلية (نعم / لا)
        markup = InlineKeyboardMarkup()
        btn_yes = InlineKeyboardButton("نعم، أنشئ الملف", callback_data="create_test_yes")
        btn_no = InlineKeyboardButton("لا، شكراً", callback_data="create_test_no")
        markup.add(btn_yes, btn_no)

        bot.reply_to(
            message, 
            f"❌ لم أجد الملف `{filename}` على الاستضافة المجانية.\n\nهل تود إنشاء ملف `{filename}` الآن؟", 
            reply_markup=markup,
            parse_mode="Markdown"
        )

# 2. الاستجابة لأزرار نعم / لا
@bot.callback_query_handler(func=lambda call: call.data in ["create_test_yes", "create_test_no"])
def handle_test_creation(call):
    if call.data == "create_test_yes":
        try:
            with open("TEST.txt", "w", encoding="utf-8") as f:
                f.write("هذا ملف اختبار لبيانات البوت.\n")
            bot.edit_message_text("✅ تم إنشاء الملف `TEST.txt` بنجاح على الاستضافة!", call.message.chat.id, call.message.message_id, parse_mode="Markdown")
        except Exception as e:
            bot.edit_message_text(f"❌ حدث خطأ أثناء إنشاء الملف: {e}", call.message.chat.id, call.message.message_id)
    elif call.data == "create_test_no":
        bot.edit_message_text("تم إلغاء عملية إنشاء الملف.", call.message.chat.id, call.message.message_id)

# 3. البحث عن أي ملف بالأمر: /search filename.txt
@bot.message_handler(commands=['search'])
def search_file(message):
    try:
        # استخراج اسم الملف من الأمر
        args = message.text.split(maxsplit=1)
        if len(args) < 2:
            bot.reply_to(message, "⚠️ يرجى كتابة اسم الملف بعد الأمر، مثال:\n`/search data.txt`", parse_mode="Markdown")
            return

        filename = args[1].strip()
        if os.path.exists(filename):
            bot.reply_to(message, f"🔍 الملف `{filename}` **موجود** على الاستضافة.", parse_mode="Markdown")
        else:
            markup = InlineKeyboardMarkup()
            btn_create = InlineKeyboardButton(f"إنشاء {filename}", callback_data=f"custom_create:{filename}")
            markup.add(btn_create)
            bot.reply_to(message, f"❌ الملف `{filename}` **غير موجود**.\nهل تريد إنشاؤه؟", reply_markup=markup, parse_mode="Markdown")
    except Exception as e:
        bot.reply_to(message, f"حدث خطأ: {e}")

# معالج الاستجابة لإنشاء ملف مخصص
@bot.callback_query_handler(func=lambda call: call.data.startswith("custom_create:"))
def handle_custom_creation(call):
    filename = call.data.split("custom_create:")[1]
    try:
        with open(filename, "w", encoding="utf-8") as f:
            f.write(f"ملف مخصص: {filename}\n")
        bot.edit_message_text(f"✅ تم إنشاء الملف `{filename}` بنجاح!", call.message.chat.id, call.message.message_id, parse_mode="Markdown")
    except Exception as e:
        bot.edit_message_text(f"❌ تعذر إنشاء الملف: {e}", call.message.chat.id, call.message.message_id)

# 4. استقبال الملفات المرفقة وحفظها على الاستضافة
@bot.message_handler(content_types=['document'])
def handle_docs(message):
    try:
        file_info = bot.get_file(message.document.file_id)
        downloaded_file = bot.download_file(file_info.file_path)

        file_name = message.document.file_name

        # حفظ الملف في مجلد الاستضافة بنفس الاسم الأصلي
        with open(file_name, 'wb') as new_file:
            new_file.write(downloaded_file)

        bot.reply_to(message, f"📁 تم حفظ الملف `{file_name}` بنجاح على سيرفر الاستضافة!", parse_mode="Markdown")
    except Exception as e:
        bot.reply_to(message, f"❌ فشل حفظ الملف: {e}")

# تشغيل البوت بشكل مستمر
print("البوت يعمل الآن...")
bot.infinity_polling()
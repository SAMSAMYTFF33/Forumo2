import telebot

# ضع التوكن الخاص بك هنا
BOT_TOKEN = "8769711531:AAHML0z9xgdsPnzpsbQP6VwPeathADN01L8"
bot = telebot.TeleBot(BOT_TOKEN)

# الاستجابة لكل أنواع الرسائل
@bot.message_handler(func=lambda message: True, content_types=['text', 'audio', 'document', 'photo', 'sticker', 'video', 'voice', 'location', 'contact'])
def reply_hello(message):
    bot.reply_to(message, "مرحبا")

# تشغيل البوت
print("البوت يعمل الآن...")
bot.infinity_polling()

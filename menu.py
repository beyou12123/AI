import os
import asyncio
import httpx
from telegram import Update
from telegram.constants import ParseMode
from telegram.ext import Application, CommandHandler, MessageHandler, filters, ContextTypes

# --- الإعدادات (التوكن والمفاتيح) ---
BOT_TOKEN = "8399888762:AAGnUZWmHqaU6s0EE7-bnGsIE7PTUx7hRIE"
# يمكنك إضافة مصفوفة مفاتيح هنا للتدوير مستقبلاً
GROQ_API_KEY = "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"

async def ask_groq(prompt):
    """ استدعاء منصة Groq باستخدام الموديل المستقر """
    url = "https://api.groq.com/openai/v1/chat/completions"
    headers = {
        "Authorization": f"Bearer {GROQ_API_KEY}",
        "Content-Type": "application/json"
    }
    data = {
        "model": "llama-3.3-70b-versatile", # موديل قوي وسريع جداً
        "messages": [
            {"role": "system", "content": "أنت مبرمج خبير. رد باللغة العربية واستخدم حاويات الأكواد ```."},
            {"role": "user", "content": prompt}
        ]
    }
    
    async with httpx.AsyncClient(timeout=30.0) as client:
        try:
            response = await client.post(url, headers=headers, json=data)
            if response.status_code == 200:
                res_json = response.json()
                return res_json['choices'][0]['message']['content']
            else:
                err = response.json().get('error', {}).get('message', 'خطأ في المنصة')
                return f"❌ خطأ من Groq: {err}"
        except Exception as e:
            return f"⚠️ فشل الاتصال: {str(e)}"

async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not update.message or not update.message.text: return
    
    query = update.message.text
    # أمر الفحص السريع
    if query == "/test":
        await update.message.reply_text("🔎 جاري تجربة مفتاح Groq الآن...")
        res = await ask_groq("Hello, are you working?")
        await update.message.reply_text(f"تقرير الحالة:\n{res}")
        return

    await update.message.reply_chat_action("typing")
    response = await ask_groq(query)
    await update.message.reply_text(response, parse_mode=ParseMode.MARKDOWN)

def main():
    # تنظيف الجلسات القديمة لضمان عدم وجود Conflict
    app = Application.builder().token(BOT_TOKEN).build()
    
    app.add_handler(CommandHandler("start", lambda u,c: u.message.reply_text("🚀 بوت Groq جاهز!\nأرسل أي سؤال أو استخدم /test لفحص المفتاح.")))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))
    
    print("🔄 البوت يعمل الآن باستخدام Groq...")
    app.run_polling(drop_pending_updates=True)

if __name__ == "__main__":
    main()

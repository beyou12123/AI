import os
import asyncio
import httpx
import json
from telegram import Update
from telegram.constants import ParseMode
from telegram.ext import Application, CommandHandler, MessageHandler, filters, ContextTypes

# --- الإعدادات (ضع بياناتك الجديدة هنا) ---
BOT_TOKEN = "8399888762:AAGnUZWmHqaU6s0EE7-bnGsIE7PTUx7hRIE"
API_KEYS = [
    "AIzaSyCU1guXTcpzNKBsiwjS-3PgCcIUSLkG52s",
    "AIzaSyBxyIpy-w8RK9GUapuTCnxumaePI7K-Q1E",
    "AIzaSyADN4UmlnMq3wWW5Yoei6aRxRWAeYxD43g",
    "AIzaSyCaz7YVDwoGOtOc5Ao993Blt6pKI5Ryta0"
]

current_key_index = 0

async def verify_single_key(key, index):
    """ فحص مفتاح واحد وإعطاء تقرير دقيق """
    url = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-1.5-flash:generateContent?key={key}"
    payload = {"contents": [{"parts": [{"text": "test"}]}]}
    async with httpx.AsyncClient(timeout=10.0) as client:
        try:
            r = await client.post(url, json=payload)
            if r.status_code == 200:
                return f"✅ المفتاح {index}: سليم وشغال."
            else:
                error_detail = r.json().get('error', {}).get('message', 'خطأ مجهول')
                return f"❌ المفتاح {index}: معطل (السبب: {error_detail})"
        except Exception as e:
            return f"⚠️ المفتاح {index}: فشل اتصال ({str(e)})"

async def ask_gemini(prompt):
    global current_key_index
    # محاولة التنقل بين المفاتيح عند الفشل
    for _ in range(len(API_KEYS)):
        key = API_KEYS[current_key_index]
        url = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-2.0-flash:generateContent?key={key}"
        payload = {"contents": [{"parts": [{"text": prompt}]}]}
        
        async with httpx.AsyncClient(timeout=30.0) as client:
            try:
                r = await client.post(url, json=payload)
                if r.status_code == 200:
                    return r.json()['candidates'][0]['content']['parts'][0]['text'], current_key_index + 1
                elif r.status_code == 429:
                    current_key_index = (current_key_index + 1) % len(API_KEYS)
                    continue
            except:
                current_key_index = (current_key_index + 1) % len(API_KEYS)
                continue
    return "⚠️ جميع المفاتيح استنفدت حصتها حالياً.", None

async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not update.message or not update.message.text: return
    
    query = update.message.text
    if query == "/test":
        await update.message.reply_text("🔎 جاري فحص كافة المفاتيح الآن...")
        reports = []
        for i, k in enumerate(API_KEYS):
            res = await verify_single_key(k, i+1)
            reports.append(res)
        await update.message.reply_text("\n".join(reports))
        return

    await update.message.reply_chat_action("typing")
    response, key_num = await ask_gemini(query)
    
    msg = f"<b>الرد:</b>\n{response}\n\n<i>تم باستخدام المفتاح رقم: {key_num}</i>" if key_num else response
    await update.message.reply_text(msg, parse_mode=ParseMode.HTML)

def main():
    # [span_1](start_span)drop_pending_updates=True تضمن عدم وجود تصادم مع أي بوت قديم[span_1](end_span)
    app = Application.builder().token(BOT_TOKEN).build()
    
    app.add_handler(CommandHandler("start", lambda u,c: u.message.reply_text("🚀 بوت الاختبار جاهز.\nأرسل أي رسالة للتجربة أو /test لفحص المفاتيح.")))
    app.add_handler(CommandHandler("test", handle_message))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))
    
    print("🔄 البوت بدأ العمل بنظام تنظيف الجلسات...")
    app.run_polling(drop_pending_updates=True)

if __name__ == "__main__":
    main()

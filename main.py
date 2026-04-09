import os
import asyncio
import httpx
import json
from telegram import Update
from telegram.constants import ParseMode
from telegram.ext import Application, CommandHandler, MessageHandler, filters, ContextTypes

# --- الإعدادات (التوكن والمفاتيح) ---
BOT_TOKEN = "8399888762:AAGnUZWmHqaU6s0EE7-bnGsIE7PTUx7hRIE"
GROQ_API_KEY = "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"

# --- المتغيرات العالمية والذاكرة ---
STORAGE_DIR = "stored_files"
user_context = {}
file_chunks = {}
upload_queue = asyncio.Queue()
GROQ_KEYS = [GROQ_API_KEY]
current_key_index = 0

# إنشاء المجلد إذا لم يوجد
if not os.path.exists(STORAGE_DIR):
    os.makedirs(STORAGE_DIR)

# --- وظائف الذاكرة وتحميل الملفات ---
def load_stored_files():
    """ تحميل الملفات المخزنة عند التشغيل """
    for fname in os.listdir(STORAGE_DIR):
        path = os.path.join(STORAGE_DIR, fname)
        try:
            with open(path, "r", encoding="utf-8", errors="ignore") as f:
                content = f.read()
                # تقسيم الملف إلى أجزاء (Chunks) للبحث الذكي
                file_chunks[fname] = [content[i:i+1000] for i in range(0, len(content), 1000)]
        except:
            pass
    print(f"✅ تم تحميل {len(file_chunks)} ملفات إلى الذاكرة.")

load_stored_files()

# --- محرك Groq (الأصلي والمطور) ---
async def ask_groq(prompt):
    """ الوظيفة الأصلية لاستدعاء Groq """
    url = "https://api.groq.com/openai/v1/chat/completions"
    headers = {
        "Authorization": f"Bearer {GROQ_API_KEY}",
        "Content-Type": "application/json"
    }
    data = {
        "model": "llama-3.3-70b-versatile",
        "messages": [
            {"role": "system", "content": "أنت مبرمج خبير. رد باللغة العربية واستخدم حاويات الأكواد ```."},
            {"role": "user", "content": prompt}
        ]
    }
    async with httpx.AsyncClient(timeout=30.0) as client:
        try:
            response = await client.post(url, headers=headers, json=data)
            if response.status_code == 200:
                return response.json()['choices'][0]['message']['content']
            return f"❌ خطأ من Groq: {response.text}"
        except Exception as e:
            return f"⚠️ فشل الاتصال: {str(e)}"

async def ask_groq_advanced(prompt, context_msgs=None):
    """ الوظيفة المطورة مع تدوير المفاتيح والسياق """
    global current_key_index
    url = "[https://api.groq.com/openai/v1/chat/completions](https://api.groq.com/openai/v1/chat/completions)"
    
    for _ in range(len(GROQ_KEYS)):
        key = GROQ_KEYS[current_key_index]
        headers = {"Authorization": f"Bearer {key}", "Content-Type": "application/json"}
        
        messages = [{"role": "system", "content": "أنت مبرمج خبير. حلل الكود بدقة واستخدم ```."}]
        if context_msgs:
            messages.extend(context_msgs)
        messages.append({"role": "user", "content": prompt})

        data = {"model": "llama-3.3-70b-versatile", "messages": messages}

        async with httpx.AsyncClient(timeout=30.0) as client:
            try:
                res = await client.post(url, headers=headers, json=data)
                if res.status_code == 200:
                    return res.json()['choices'][0]['message']['content']
                current_key_index = (current_key_index + 1) % len(GROQ_KEYS)
            except:
                current_key_index = (current_key_index + 1) % len(GROQ_KEYS)
    return "❌ جميع المفاتيح فشلت"

# --- إدارة السياق والبحث ---
def update_context(user_id, role, content):
    if user_id not in user_context:
        user_context[user_id] = []
    user_context[user_id].append({"role": role, "content": content})
    user_context[user_id] = user_context[user_id][-6:] # حفظ آخر 6 رسائل

def search_chunks(query):
    """ البحث الذكي البسيط """
    results = []
    for fname, chunks in file_chunks.items():
        for chunk in chunks:
            score = sum(1 for word in query.split() if word in chunk)
            if score > 0:
                results.append((score, fname, chunk))
    results.sort(key=lambda x: x[0], reverse=True)
    return results[:3]

# --- معالجة الأوامر والملفات ---
async def restore_files(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """ أمر /d لاسترجاع الملفات """
    files = os.listdir(STORAGE_DIR)
    if not files:
        await update.message.reply_text("📂 لا توجد ملفات محفوظة")
        return
    for f in files:
        path = os.path.join(STORAGE_DIR, f)
        try:
            with open(path, "rb") as doc:
                await update.message.reply_document(document=doc)
        except:
            pass

async def handle_file(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """ استلام وحفظ الملفات """
    file = update.message.document
    path = os.path.join(STORAGE_DIR, file.file_name)
    new_file = await context.bot.get_file(file.file_id)
    await new_file.download_to_drive(path)
    await upload_queue.put(path)
    await update.message.reply_text(f"⏳ جاري تحليل `{file.file_name}`...")

async def process_queue():
    """ عامل الطابور (Worker) """
    while True:
        path = await upload_queue.get()
        try:
            with open(path, "r", encoding="utf-8", errors="ignore") as f:
                content = f.read()
                file_chunks[os.path.basename(path)] = [content[i:i+1000] for i in range(0, len(content), 1000)]
        except:
            pass
        upload_queue.task_done()

# --- معالجة الرسائل النصية ---
async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not update.message or not update.message.text: return
    query = update.message.text
    user_id = update.message.from_user.id

    if query == "/test":
        await update.message.reply_text("🔎 جاري تجربة مفتاح Groq الآن...")
        res = await ask_groq("Hello, are you working?")
        await update.message.reply_text(f"تقرير الحالة:\n{res}")
        return

    await update.message.reply_chat_action("typing")

    # 1. مناداة ملف مباشر
    for fname in file_chunks:
        if fname in query:
            content = "\n".join(file_chunks[fname])[:6000]
            full_prompt = f"هذا محتوى الملف {fname}:\n{content}\n\nالسؤال: {query}"
            response = await ask_groq_advanced(full_prompt, user_context.get(user_id))
            update_context(user_id, "user", query)
            update_context(user_id, "assistant", response)
            await update.message.reply_text(response, parse_mode=ParseMode.MARKDOWN)
            return

    # 2. بحث ذكي
    chunks = search_chunks(query)
    context_text = "\n\n".join([c[2] for c in chunks])
    full_prompt = f"المعلومات التالية من ملفاتك:\n{context_text}\n\nالسؤال: {query}"

    response = await ask_groq_advanced(full_prompt, user_context.get(user_id))
    update_context(user_id, "user", query)
    update_context(user_id, "assistant", response)
    
    try:
        await update.message.reply_text(response, parse_mode=ParseMode.MARKDOWN)
    except:
        await update.message.reply_text(response)

# --- التشغيل الرئيسي ---
def main():
    app = Application.builder().token(BOT_TOKEN).build()

    app.add_handler(CommandHandler("start", lambda u,c: u.message.reply_text("🚀 بوت Groq جاهز!")))
    app.add_handler(CommandHandler("d", restore_files))
    app.add_handler(MessageHandler(filters.Document.ALL, handle_file))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))

    # بدء عامل الطابور كخلفية
    asyncio.get_event_loop().create_task(process_queue())

    print("🔄 البوت يعمل الآن باستخدام Groq...")
    app.run_polling(drop_pending_updates=True)

if __name__ == "__main__":
    main()

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

STORAGE_DIR = "stored_files"
user_context = {}
file_chunks = {}
upload_queue = asyncio.Queue()

# إنشاء المجلد فوراً
if not os.path.exists(STORAGE_DIR):
    os.makedirs(STORAGE_DIR)

# --- وظائف الذاكرة وتحميل الملفات ---
def load_stored_files():
    """ قراءة الملفات من المجلد عند تشغيل البوت """
    for fname in os.listdir(STORAGE_DIR):
        path = os.path.join(STORAGE_DIR, fname)
        try:
            with open(path, "r", encoding="utf-8", errors="ignore") as f:
                content = f.read()
                file_chunks[fname] = [content[i:i+1000] for i in range(0, len(content), 1000)]
        except:
            pass

load_stored_files()

# --- طريقة الاتصال الأصلية التي طلبتها (بدون تغيير) ---
async def ask_groq(prompt, context_msgs=None):
    """ استدعاء منصة Groq باستخدام الموديل المستقر """
    url = "https://api.groq.com/openai/v1/chat/completions"
    headers = {
        "Authorization": f"Bearer {GROQ_API_KEY}",
        "Content-Type": "application/json"
    }
    
    # بناء الرسائل مع الحفاظ على الـ System Prompt والذاكرة
    messages = [{"role": "system", "content": "أنت مبرمج خبير. رد باللغة العربية واستخدم حاويات الأكواد ```."}]
    if context_msgs:
        messages.extend(context_msgs)
    messages.append({"role": "user", "content": prompt})

    data = {
        "model": "llama-3.3-70b-versatile",
        "messages": messages
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

# --- وظائف البحث وإدارة السياق ---
def update_context(user_id, role, content):
    if user_id not in user_context:
        user_context[user_id] = []
    user_context[user_id].append({"role": role, "content": content})
    user_context[user_id] = user_context[user_id][-6:] # حفظ آخر 6 رسائل

def search_chunks(query):
    results = []
    for fname, chunks in file_chunks.items():
        for chunk in chunks:
            score = sum(1 for word in query.split() if word in chunk)
            if score > 0:
                results.append((score, fname, chunk))
    results.sort(key=lambda x: x[0], reverse=True)
    return results[:3]

# --- معالجة الملفات والأوامر ---
async def restore_files(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """ أمر /d لاسترجاع الملفات من المجلد """
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
    """ استلام وحفظ الملفات في المجلد المخصص """
    file = update.message.document
    path = os.path.join(STORAGE_DIR, file.file_name)
    new_file = await context.bot.get_file(file.file_id)
    await new_file.download_to_drive(path)
    await upload_queue.put(path)
    await update.message.reply_text(f"⏳ جاري تحليل وحفظ `{file.file_name}` في المجلد...")

async def process_queue():
    """ معالج طابور الملفات المرفوعة """
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

    # 1. البحث عن "مناداة" ملف مباشر
    context_text = ""
    for fname in file_chunks:
        if fname in query:
            context_text = f"محتوى الملف {fname}:\n" + "\n".join(file_chunks[fname])[:5000]
            break

    # 2. إذا لم تكن مناداة، استخدم البحث الذكي
    if not context_text:
        chunks = search_chunks(query)
        context_text = "معلومات من ملفاتك:\n" + "\n\n".join([c[2] for c in chunks])

    full_prompt = f"{context_text}\n\nالسؤال: {query}"
    response = await ask_groq(full_prompt, user_context.get(user_id))
    
    update_context(user_id, "user", query)
    update_context(user_id, "assistant", response)
    
    try:
        await update.message.reply_text(response, parse_mode=ParseMode.MARKDOWN)
    except:
        await update.message.reply_text(response)

def main():
    app = Application.builder().token(BOT_TOKEN).build()
    
    app.add_handler(CommandHandler("start", lambda u,c: u.message.reply_text("🚀 بوت Groq جاهز بكافة وظائف الملفات والذاكرة!")))
    app.add_handler(CommandHandler("d", restore_files))
    app.add_handler(MessageHandler(filters.Document.ALL, handle_file))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))
    
    # تشغيل معالج الملفات كخلفية
    asyncio.get_event_loop().create_task(process_queue())
    
    print("🔄 البوت يعمل الآن باستخدام Groq المعتمد لديك...")
    app.run_polling(drop_pending_updates=True)

if __name__ == "__main__":
    main()

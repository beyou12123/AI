import os
import asyncio
import httpx
import json
from telegram import Update
from telegram.constants import ParseMode
from telegram.ext import Application, CommandHandler, MessageHandler, filters, ContextTypes
from langchain_community.retrievers import BM25Retriever
from langchain_text_splitters import RecursiveCharacterTextSplitter
from langchain_core.documents import Document

# --- الإعدادات (التوكن ومفاتيح Groq) ---
BOT_TOKEN = "8399888762:AAGnUZWmHqaU6s0EE7-bnGsIE7PTUx7hRIE"
# أضف مفاتيح Groq هنا للتدوير تلقائياً
API_KEYS = [
    "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"
]

TOKEN = BOT_TOKEN
current_key_index = 0
STORAGE_DIR = "stored_files"
if not os.path.exists(STORAGE_DIR):
    os.makedirs(STORAGE_DIR)

all_docs = []
upload_lock = asyncio.Lock()
batch_success_files = []

SYSTEM_PROMPT = "أنت مبرمج خبير. حلل الكود بدقة واستخدم حاويات الأكواد ``` للتنسيق."

async def verify_keys():
    """ فحص سلامة مفاتيح Groq عند التشغيل """
    print(f"🔍 تم العثور على {len(API_KEYS)} مفاتيح Groq. جاري الفحص...")
    valid_keys = []
    url = "[https://api.groq.com/openai/v1/chat/completions](https://api.groq.com/openai/v1/chat/completions)"
    
    async with httpx.AsyncClient(timeout=15.0) as client:
        for idx, key in enumerate(API_KEYS):
            headers = {"Authorization": f"Bearer {key}", "Content-Type": "application/json"}
            data = {
                "model": "llama-3.3-70b-versatile",
                "messages": [{"role": "user", "content": "hi"}],
                "max_tokens": 10
            }
            try:
                response = await client.post(url, headers=headers, json=data)
                if response.status_code == 200:
                    print(f"✅ المفتاح رقم {idx+1}: سليم وشغال.")
                    valid_keys.append(key)
                else:
                    print(f"❌ المفتاح رقم {idx+1}: معطل.")
            except:
                print(f"⚠️ المفتاح رقم {idx+1}: فشل اتصال.")
    return valid_keys

def load_files_into_memory():
    """ تحميل الملفات المخزنة سابقاً إلى الذاكرة """
    global all_docs
    all_docs = []
    text_splitter = RecursiveCharacterTextSplitter(chunk_size=800, chunk_overlap=150)
    if not os.path.exists(STORAGE_DIR): return
    for filename in os.listdir(STORAGE_DIR):
        file_path = os.path.join(STORAGE_DIR, filename)
        try:
            with open(file_path, 'r', encoding='utf-8', errors='ignore') as f:
                content = f.read()
                splits = text_splitter.create_documents([content], metadatas=[{"source": filename}])
                all_docs.extend(splits)
        except: pass
    print("✅ تم تحميل الذاكرة بنجاح.")

load_files_into_memory()

async def ask_groq(prompt, context_data=""):
    """ استدعاء محرك Groq مع دعم السياق ونظام التدوير """
    global current_key_index
    if not API_KEYS: return "❌ لا توجد مفاتيح Groq مسجلة."

    url = "[https://api.groq.com/openai/v1/chat/completions](https://api.groq.com/openai/v1/chat/completions)"
    full_content = f"سياق الملفات:\n{context_data[:3000]}\n\nسؤال المستخدم: {prompt}"
    
    for _ in range(len(API_KEYS)):
        key = API_KEYS[current_key_index]
        headers = {"Authorization": f"Bearer {key}", "Content-Type": "application/json"}
        data = {
            "model": "llama-3.3-70b-versatile",
            "messages": [
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": full_content}
            ]
        }
        
        async with httpx.AsyncClient(timeout=40.0) as client:
            try:
                response = await client.post(url, headers=headers, json=data)
                if response.status_code == 200:
                    return response.json()['choices'][0]['message']['content']
                elif response.status_code == 429:
                    current_key_index = (current_key_index + 1) % len(API_KEYS)
                    await asyncio.sleep(1)
                    continue
            except:
                current_key_index = (current_key_index + 1) % len(API_KEYS)
                continue
    return "⚠️ جميع المحركات مضغوطة حالياً."

async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not update.message or not update.message.text: return
    query = update.message.text
    context_data = ""

    # ميزة البحث في الملفات بالمناداة أو الاسترجاع الذكي
    for f_name in os.listdir(STORAGE_DIR):
        if f_name in query:
            with open(os.path.join(STORAGE_DIR, f_name), 'r', encoding='utf-8', errors='ignore') as f:
                context_data = f.read()
            break

    if not context_data and all_docs:
        try:
            retriever = BM25Retriever.from_documents(all_docs)
            relevant = retriever.get_relevant_documents(query)
            context_data = "\n".join([d.page_content for d in relevant[:3]])
        except: pass

    await update.message.reply_chat_action("typing")
    res = await ask_groq(query, context_data)
    try:
        await update.message.reply_text(res, parse_mode=ParseMode.MARKDOWN)
    except:
        await update.message.reply_text(res)

async def handle_docs(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """ استلام وتحليل الملفات البرمجية """
    doc = update.message.document
    if not doc: return
    global batch_success_files
    async with upload_lock:
        try:
            await asyncio.sleep(1.5)
            f_path = os.path.join(STORAGE_DIR, doc.file_name)
            t_file = await context.bot.get_file(doc.file_id)
            await t_file.download_to_drive(f_path)
            
            with open(f_path, 'r', encoding='utf-8', errors='ignore') as f:
                content = f.read()
                text_splitter = RecursiveCharacterTextSplitter(chunk_size=800, chunk_overlap=150)
                all_docs.extend(text_splitter.create_documents([content], metadatas=[{"source": doc.file_name}]))
            
            if doc.file_name not in batch_success_files: batch_success_files.append(doc.file_name)
            
            if context.job_queue:
                j_name = f"fin_{update.effective_chat.id}"
                for j in context.job_queue.get_jobs_by_name(j_name): j.schedule_removal()
                context.job_queue.run_once(send_final_report, 5, chat_id=update.effective_chat.id, name=j_name)
        except Exception as e:
            await update.message.reply_text(f"❌ خطأ في الملف: {str(e)}")

async def send_final_report(context: ContextTypes.DEFAULT_TYPE):
    global batch_success_files
    if batch_success_files:
        report = "📦 *تم تحليل الملفات بنجاح:* " + ", ".join([f"`{n}`" for n in batch_success_files])
        await context.bot.send_message(chat_id=context.job.chat_id, text=report, parse_mode=ParseMode.MARKDOWN)
        batch_success_files = []

async def post_init(application: Application):
    global API_KEYS
    API_KEYS = await verify_keys()
    print(f"🚀 البوت جاهز للعمل بـ {len(API_KEYS)} مفاتيح Groq.")

def main():
    if not TOKEN: return
    app = Application.builder().token(TOKEN).post_init(post_init).build()
    app.add_handler(CommandHandler("start", lambda u,c: u.message.reply_text("🚀 أهلاً بك! بوت المبرمج الذكي (Groq Edition) جاهز للخدمة.")))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))
    app.add_handler(MessageHandler(filters.Document.ALL, handle_docs))
    app.run_polling(drop_pending_updates=True)

if __name__ == "__main__":
    main()

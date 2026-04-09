import os
import asyncio
import httpx
from telegram import Update
from telegram.constants import ParseMode
from telegram.ext import Application, CommandHandler, MessageHandler, filters, ContextTypes
from langchain_community.retrievers import BM25Retriever
from langchain_text_splitters import RecursiveCharacterTextSplitter
from langchain_core.documents import Document

# --- الإعدادات الأساسية ---
# تأكد من وضع التوكن والمفتاح في Variables أو استبدالهما هنا مباشرة
TOKEN = os.getenv("BOT_TOKEN") or "8399888762:AAGnUZWmHqaU6s0EE7-bnGsIE7PTUx7hRIE"
GROQ_API_KEY = os.getenv("GROQ_API_KEY") or "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"

STORAGE_DIR = "stored_files" 
if not os.path.exists(STORAGE_DIR):
    os.makedirs(STORAGE_DIR)

all_docs = []
chat_histories = {}
batch_success_files = []
upload_lock = asyncio.Lock()

SYSTEM_PROMPT = (
    "أنت مبرمج خبير. وظيفتك تحليل الكود فقط. "
    "يجب عليك تغليف أي كود برمجي ترسله باستخدام علامات الثلاثة (```) مع ذكر اسم اللغة لضمان ظهور زر النسخ. "
    "استخدم السياق المرفق وتاريخ المحادثة بدقة للإجابة."
)

def load_files_into_memory():
    global all_docs
    all_docs = []
    text_splitter = RecursiveCharacterTextSplitter(chunk_size=1000, chunk_overlap=150)
    if not os.path.exists(STORAGE_DIR): return
    for filename in os.listdir(STORAGE_DIR):
        file_path = os.path.join(STORAGE_DIR, filename)
        try:
            with open(file_path, 'r', encoding='utf-8', errors='ignore') as f:
                content = f.read()
                splits = text_splitter.create_documents([content], metadatas=[{"source": filename}])
                all_docs.extend(splits)
        except Exception as e:
            print(f"Error loading {filename}: {e}")
    print(f"✅ تم تحميل {len(all_docs)} جزء من الملفات المخزنة.")

load_files_into_memory()

async def ask_groq(prompt, context_data="", chat_history=None):
    if chat_history is None: chat_history = []
    url = "[https://api.groq.com/openai/v1/chat/completions](https://api.groq.com/openai/v1/chat/completions)"
    headers = {
        "Authorization": f"Bearer {GROQ_API_KEY}",
        "Content-Type": "application/json"
    }
    
    # بناء الرسائل مع السياق والتاريخ
    messages = [{"role": "system", "content": f"{SYSTEM_PROMPT}\n\nسياق من ملفاتك:\n{context_data}"}]
    # إضافة آخر 6 رسائل من التاريخ للحفاظ على تركيز البوت
    messages.extend(chat_history[-6:])
    messages.append({"role": "user", "content": prompt})

    data = {
        "model": "llama-3.3-70b-versatile",
        "messages": messages,
        "temperature": 0.5
    }

    async with httpx.AsyncClient(timeout=40.0) as client:
        try:
            response = await client.post(url, headers=headers, json=data)
            if response.status_code == 200:
                answer = response.json()['choices'][0]['message']['content']
                chat_history.append({"role": "user", "content": prompt})
                chat_history.append({"role": "assistant", "content": answer})
                return answer
            return f"⚠️ خطأ من Groq: {response.text}"
        except Exception as e:
            return f"⚠️ خطأ في الاتصال: {str(e)}"

async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not update.message or not update.message.text: return
    user_id = update.message.from_user.id
    query = update.message.text
    if user_id not in chat_histories: chat_histories[user_id] = []
    
    context_data = ""
    target_file = None
    stored_files = os.listdir(STORAGE_DIR)
    
    # 1. نظام "المناداة" - البحث عن اسم ملف محدد في رسالة المستخدم
    for f_name in stored_files:
        if f_name in query:
            target_file = f_name
            break

    if target_file:
        file_path = os.path.join(STORAGE_DIR, target_file)
        with open(file_path, 'r', encoding='utf-8', errors='ignore') as f:
            context_data = f"محتوى ملف {target_file} الكامل:\n{f.read()}"
    elif all_docs:
        # 2. نظام الـ RAG - البحث الذكي في الأجزاء إذا لم يذكر اسماً محدداً
        try:
            retriever = BM25Retriever.from_documents(all_docs)
            relevant_docs = retriever.get_relevant_documents(query)
            context_data = "\n".join([d.page_content for d in relevant_docs[:3]])
        except: pass

    await update.message.reply_chat_action("typing")
    response = await ask_groq(query, context_data, chat_histories[user_id])
    try:
        await update.message.reply_text(response, parse_mode=ParseMode.MARKDOWN)
    except:
        await update.message.reply_text(response)

async def handle_docs(update: Update, context: ContextTypes.DEFAULT_TYPE):
    doc = update.message.document
    if not doc: return
    global batch_success_files

    async with upload_lock:
        try:
            await asyncio.sleep(1.5) # حماية من السبام
            file_path = os.path.join(STORAGE_DIR, doc.file_name)
            telegram_file = await context.bot.get_file(doc.file_id)
            await telegram_file.download_to_drive(file_path)
            
            # تحديث الذاكرة الحية فوراً
            with open(file_path, 'r', encoding='utf-8', errors='ignore') as f:
                content = f.read()
                text_splitter = RecursiveCharacterTextSplitter(chunk_size=1000, chunk_overlap=150)
                new_splits = text_splitter.create_documents([content], metadatas=[{"source": doc.file_name}])
                all_docs.extend(new_splits)
            
            if doc.file_name not in batch_success_files:
                batch_success_files.append(doc.file_name)
            
            # إدارة تقرير الدفعة عبر JobQueue
            if context.job_queue:
                job_name = f"final_msg_{update.effective_chat.id}"
                for job in context.job_queue.get_jobs_by_name(job_name): job.schedule_removal()
                context.job_queue.run_once(send_final_report, 5, chat_id=update.effective_chat.id, name=job_name)
            else:
                await update.message.reply_text(f"✅ تم حفظ وتحليل: `{doc.file_name}`")

        except Exception as e:
            await update.message.reply_text(f"❌ خطأ في معالجة `{doc.file_name}`: {str(e)}")

async def send_final_report(context: ContextTypes.DEFAULT_TYPE):
    global batch_success_files
    if batch_success_files:
        files_list = "\n".join([f"✅ `{name}`" for name in batch_success_files])
        report = f"📦 *تم اكتمال معالجة الدفعة:*\n\n{files_list}"
        await context.bot.send_message(chat_id=context.job.chat_id, text=report, parse_mode=ParseMode.MARKDOWN)
        batch_success_files = []

async def download_stored_files(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """ استرجاع الملفات المخزنة في المجلد """
    files = os.listdir(STORAGE_DIR)
    if not files:
        await update.message.reply_text("📁 المجلد فارغ حالياً.")
        return
    await update.message.reply_text(f"📁 جاري إرسال {len(files)} ملفاً من المجلد...")
    for filename in files:
        file_path = os.path.join(STORAGE_DIR, filename)
        try:
            with open(file_path, 'rb') as f:
                await update.message.reply_document(document=f)
        except: pass

async def start_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_histories[update.message.from_user.id] = []
    await update.message.reply_text("🚀 أهلاً دكتور عبدالله! البوت يعمل الآن بمحرك Groq العالمي. أرسل ملفاتك أو اسألني عما تشاء.")

def main():
    if not TOKEN: return
    application = Application.builder().token(TOKEN).build()
    
    application.add_handler(CommandHandler("start", start_command))
    application.add_handler(CommandHandler("d", download_stored_files))
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))
    application.add_handler(MessageHandler(filters.Document.ALL, handle_docs))
    
    print("🔄 البوت يعمل بنظام Groq المتكامل وحماية التصادم...")
    application.run_polling(drop_pending_updates=True)

if __name__ == "__main__":
    main()

import os
import asyncio
import httpx
import json
from telegram import Update
from telegram.constants import ParseMode
from telegram.ext import Application, CommandHandler, MessageHandler, filters, ContextTypes
from langchain_community.retrievers import BM25Retriever
from langchain_text_splitters import RecursiveCharacterTextSplitter

# --- الإعدادات ---
BOT_TOKEN = "8399888762:AAGnUZWmHqaU6s0EE7-bnGsIE7PTUx7hRIE"

def get_all_keys():
    """ جلب المفاتيح من الكود أو من Variables لضمان التشغيل """
    keys = []
    # 1. المفاتيح المكتوبة يدوياً (أضف مفاتيحك هنا)
    manual_keys = [
        "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"
    ]
    keys.extend(manual_keys)
    
    # 2. جلب أي مفاتيح تبدأ بـ GROQ_ من إعدادات Railway
    for i in range(1, 11):
        k = os.getenv(f"GROQ_KEY{i}")
        if k: keys.append(k.strip())
    
    # تنظيف المصفوفة
    return list(set([k for k in keys if k and len(k) > 10]))

API_KEYS = get_all_keys()
current_key_index = 0
STORAGE_DIR = "stored_files"
if not os.path.exists(STORAGE_DIR): os.makedirs(STORAGE_DIR)

all_docs = []
upload_lock = asyncio.Lock()
batch_success_files = []

async def ask_groq(prompt, context_data=""):
    global current_key_index
    # تحديث القائمة في كل طلب للتأكد من وجودها
    active_keys = get_all_keys()
    if not active_keys: 
        return "❌ خطأ: لم يتم العثور على أي مفتاح Groq في الكود أو الإعدادات."

    url = "https://api.groq.com/openai/v1/chat/completions"
    full_content = f"سياق:\n{context_data[:2500]}\n\nسؤال: {prompt}"
    
    for _ in range(len(active_keys)):
        key = active_keys[current_key_index]
        headers = {"Authorization": f"Bearer {key}", "Content-Type": "application/json"}
        data = {
            "model": "llama-3.3-70b-versatile",
            "messages": [
                {"role": "system", "content": "أنت مبرمج خبير. حلل الكود بدقة واستخدم ```."},
                {"role": "user", "content": full_content}
            ]
        }
        
        async with httpx.AsyncClient(timeout=40.0) as client:
            try:
                response = await client.post(url, headers=headers, json=data)
                if response.status_code == 200:
                    return response.json()['choices'][0]['message']['content']
                current_key_index = (current_key_index + 1) % len(active_keys)
            except:
                current_key_index = (current_key_index + 1) % len(active_keys)
                continue
    return "⚠️ جميع المفاتيح مضغوطة حالياً."

async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not update.message or not update.message.text: return
    query = update.message.text
    context_data = ""

    # نظام البحث الذكي في الملفات
    if all_docs:
        try:
            retriever = BM25Retriever.from_documents(all_docs)
            relevant = retriever.get_relevant_documents(query)
            context_data = "\n".join([d.page_content for d in relevant[:3]])
        except: pass

    await update.message.reply_chat_action("typing")
    res = await ask_groq(query, context_data)
    await update.message.reply_text(res, parse_mode=ParseMode.MARKDOWN)

def main():
    if not BOT_TOKEN: return
    # طباعة عدد المفاتيح عند التشغيل للتأكد
    print(f"✅ تم العثور على {len(API_KEYS)} مفاتيح Groq.")
    
    app = Application.builder().token(BOT_TOKEN).build()
    app.add_handler(CommandHandler("start", lambda u,c: u.message.reply_text("🚀 البوت يعمل الآن بمحرك Groq!")))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))
    app.run_polling(drop_pending_updates=True)

if __name__ == "__main__":
    main()

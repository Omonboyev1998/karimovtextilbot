import telebot
from telebot import types
from flask import Flask, request
import config
from database import Database
import json
import os
import logging

# Loglarni sozlash
logging.basicConfig(level=logging.INFO)

app = Flask(__name__)
bot = telebot.TeleBot(config.BOT_TOKEN, threaded=False)

# --- UTILS ---
def send_msg(chat_id, text, markup=None):
    try:
        bot.send_message(chat_id, text, reply_markup=markup, parse_mode='HTML')
    except Exception as e:
        logging.error(f"Xabar yuborishda xato: {e}")

# --- KEYBOARDS ---
def get_admin_keyboard():
    markup = types.ReplyKeyboardMarkup(row_width=2, resize_keyboard=True)
    markup.add("📦 Tovar Turlari", "⚙️ Rastenka/Detallar")
    markup.add("➕ Yangi Zakaz", "📊 Hisobotlar")
    return markup

def get_chevar_keyboard():
    markup = types.ReplyKeyboardMarkup(row_width=1, resize_keyboard=True)
    markup.add("📥 Ish Topshirish")
    return markup

def get_types_inline(prefix):
    types_list = Database.fetch_all("SELECT * FROM product_types")
    markup = types.InlineKeyboardMarkup()
    for t in types_list:
        markup.add(types.InlineKeyboardButton(t['name'], callback_data=f"{prefix}:{t['id']}"))
    return markup

# --- START COMMAND ---
@bot.message_handler(commands=['start'])
def start(message):
    try:
        chat_id = message.chat.id
        first_name = message.from_user.first_name
        role = 'admin' if chat_id == config.ADMIN_ID else 'chevar'
        
        Database.execute("INSERT INTO users (chat_id, first_name, role) VALUES (%s, %s, %s) ON DUPLICATE KEY UPDATE first_name = VALUES(first_name)", 
                   (chat_id, first_name, role))
        
        Database.execute("INSERT INTO user_states (chat_id, state) VALUES (%s, 'main_menu') ON DUPLICATE KEY UPDATE state = 'main_menu'", (chat_id,))
        
        welcome = f"Xush kelibsiz, <b>{first_name}</b>! Bot Railway-da muvaffaqiyatli ishga tushdi."
        kb = get_admin_keyboard() if role == 'admin' else get_chevar_keyboard()
        send_msg(chat_id, welcome, kb)
    except Exception as e:
        logging.error(f"Startda xato: {e}")

# --- GLOBAL HANDLER (OSILIB QOLMASLIK UCHUN) ---
@bot.message_handler(func=lambda m: True)
def global_handler(message):
    try:
        chat_id = message.chat.id
        text = message.text
        # Batafsil logika shu yerda bo'ladi...
        if text == "📦 Tovar Turlari":
            # ...
            pass
        send_msg(chat_id, "Hozircha logika ishlab chiqilmoqda...")
    except Exception as e:
        logging.error(f"Logikada xato: {e}")
        send_msg(message.chat.id, "❌ Tizimda vaqtincha uzilish. Iltimos, keyinroq urinib ko'ring.")

# --- FLASK WEBHOOK ---
@app.route('/' + config.BOT_TOKEN, methods=['POST'])
def getMessage():
    try:
        json_string = request.get_data().decode('utf-8')
        update = telebot.types.Update.de_json(json_string)
        bot.process_new_updates([update])
        return "!", 200
    except Exception as e:
        logging.error(f"Webhook POSTda xato: {e}")
        return "Error", 500

@app.route("/init")
def init():
    try:
        res = Database.init_db()
        if res:
            return "Ma'lumotlar bazasi muvaffaqiyatli qurildi!", 200
        return "Bazani qurishda xatolik yuz berdi. Loglarni tekshiring.", 500
    except Exception as e:
        return f"Kritik xato: {str(e)}", 500

@app.route("/")
def webhook():
    try:
        bot.remove_webhook()
        if config.WEBHOOK_URL:
            bot.set_webhook(url=config.WEBHOOK_URL + '/' + config.BOT_TOKEN)
            return f"Webhook o'rnatildi: {config.WEBHOOK_URL}", 200
        return "WEBHOOK_URL sozlanmagan!", 400
    except Exception as e:
        return str(e), 500

if __name__ == '__main__':
    # Railway PORT logic
    port = int(os.environ.get('PORT', 5000))
    app.run(host='0.0.0.0', port=port)

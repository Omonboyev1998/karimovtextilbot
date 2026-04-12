import telebot
from telebot import types
from flask import Flask, request
import config
from database import Database
import json
import os
import logging

app = Flask(__name__)
bot = telebot.TeleBot(config.BOT_TOKEN, threaded=False)
db = Database()

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
    chat_id = message.chat.id
    first_name = message.from_user.first_name
    role = 'admin' if chat_id == config.ADMIN_ID else 'chevar'
    
    Database.execute("INSERT IGNORE INTO users (chat_id, first_name, role) VALUES (%s, %s, %s)", 
               (chat_id, first_name, role))
    
    # State boshqarish (database.py da set_state qo'shilishi kerak)
    Database.execute("INSERT INTO user_states (chat_id, state) VALUES (%s, 'main_menu') ON DUPLICATE KEY UPDATE state = 'main_menu'", (chat_id,))
    
    welcome = f"Xush kelibsiz, <b>{first_name}</b>! Railway-da bot ishga tushdi."
    kb = get_admin_keyboard() if role == 'admin' else get_chevar_keyboard()
    send_msg(chat_id, welcome, kb)

# --- WEBHOOK ---
@app.route('/' + config.BOT_TOKEN, methods=['POST'])
def getMessage():
    json_string = request.get_data().decode('utf-8')
    update = telebot.types.Update.de_json(json_string)
    bot.process_new_updates([update])
    return "!", 200

@app.route("/")
def webhook():
    bot.remove_webhook()
    # Railway-da web-app manzilini bu yerga qo'yishingiz kerak
    if config.WEBHOOK_URL:
        bot.set_webhook(url=config.WEBHOOK_URL + '/' + config.BOT_TOKEN)
        return "Webhook set successfully!", 200
    return "Webhook URL not set. Please add WEBHOOK_URL to Environment Variables.", 400

if __name__ == '__main__':
    Database.init_db()
    # Railway beradigan PORT orqali ishga tushiramiz
    port = int(os.environ.get('PORT', 5000))
    app.run(host='0.0.0.0', port=port)

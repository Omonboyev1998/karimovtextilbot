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

def get_user_state(chat_id):
    state = Database.fetch_one("SELECT * FROM user_states WHERE chat_id = %s", (chat_id,))
    if state:
        state['data'] = json.loads(state['data']) if state['data'] else {}
        return state
    return None

def set_user_state(chat_id, state_name, data=None):
    data_json = json.dumps(data) if data else None
    Database.execute("""
        INSERT INTO user_states (chat_id, state, data) 
        VALUES (%s, %s, %s) 
        ON DUPLICATE KEY UPDATE state = VALUES(state), data = VALUES(data)
    """, (chat_id, state_name, data_json))

# --- KEYBOARDS ---
def get_main_keyboard(role):
    markup = types.ReplyKeyboardMarkup(row_width=2, resize_keyboard=True)
    if role == 'admin':
        markup.add("📦 Tovar Turlari", "⚙️ Rastenka/Detallar")
        markup.add("➕ Yangi Zakaz", "📊 Hisobotlar")
    else:
        markup.add("📥 Ish Topshirish")
    return markup

def get_cancel_keyboard():
    markup = types.ReplyKeyboardMarkup(resize_keyboard=True)
    markup.add("❌ Bekor qilish")
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
        
        set_user_state(chat_id, 'main_menu')
        
        welcome = f"Xush kelibsiz, <b>{first_name}</b>! \nLoyiha: <b>Karimov Textile</b>."
        send_msg(chat_id, welcome, get_main_keyboard(role))
    except Exception as e:
        logging.error(f"Startda xato: {e}")

# --- ADMIN HANDLERS ---
@bot.message_handler(func=lambda m: m.chat.id == config.ADMIN_ID)
def admin_handler(message):
    try:
        chat_id = message.chat.id
        text = message.text
        state_info = get_user_state(chat_id)
        state = state_info['state'] if state_info else 'main_menu'

        if text == "❌ Bekor qilish":
            set_user_state(chat_id, 'main_menu')
            return send_msg(chat_id, "Bekor qilindi.", get_main_keyboard('admin'))

        # --- TOVAR TURLARI ---
        if text == "📦 Tovar Turlari":
            types_list = Database.fetch_all("SELECT * FROM product_types")
            resp = "📂 <b>Mavjud tovar turlari:</b>\n\n"
            for t in types_list:
                resp += f"• {t['name']}\n"
            resp += "\n<i>Yangi tur qo'shish uchun nomini yuboring.</i>"
            set_user_state(chat_id, 'add_product_type')
            send_msg(chat_id, resp, get_cancel_keyboard())

        elif state == 'add_product_type':
            Database.execute("INSERT IGNORE INTO product_types (name) VALUES (%s)", (text,))
            set_user_state(chat_id, 'main_menu')
            send_msg(chat_id, f"✅ Tur '{text}' qo'shildi.", get_main_keyboard('admin'))

        # --- RASTENKA ---
        elif text == "⚙️ Rastenka/Detallar":
            types_list = Database.fetch_all("SELECT * FROM product_types")
            if not types_list: return send_msg(chat_id, "Avval tovar turini qo'shing!")
            
            markup = types.InlineKeyboardMarkup()
            for t in types_list:
                markup.add(types.InlineKeyboardButton(t['name'], callback_data=f"rastenka_type:{t['id']}"))
            send_msg(chat_id, "Qaysi tur uchun detal qo'shamiz?", markup)

        # --- YANGI ZAKAZ ---
        elif text == "➕ Yangi Zakaz":
            types_list = Database.fetch_all("SELECT * FROM product_types")
            if not types_list: return send_msg(chat_id, "Avval tovar turini qo'shing!")
            
            markup = types.InlineKeyboardMarkup()
            for t in types_list:
                markup.add(types.InlineKeyboardButton(t['name'], callback_data=f"batch_type:{t['id']}"))
            send_msg(chat_id, "Zakaz turini tanlang:", markup)

        else:
            if state == 'main_menu':
                send_msg(chat_id, "Iltimos, menyudan tanlang.", get_main_keyboard('admin'))
            elif state == 'enter_operation_price':
                try:
                    price = float(text)
                    data = state_info['data']
                    Database.execute("INSERT INTO operations (product_type_id, name, price) VALUES (%s, %s, %s)", 
                               (data['type_id'], data['name'], price))
                    set_user_state(chat_id, 'main_menu')
                    send_msg(chat_id, f"✅ Detal qo'shildi: {data['name']} - {price} so'm", get_main_keyboard('admin'))
                except:
                    send_msg(chat_id, "Faqat son kiriting (masalan: 500.50)")

    except Exception as e:
        logging.error(f"Admin handlerda xato: {e}")

# --- CALLBACK HANDLERS ---
@bot.callback_query_handler(func=lambda call: True)
def callback_query(call):
    try:
        chat_id = call.message.chat.id
        data = call.data

        if data.startswith("rastenka_type:"):
            type_id = data.split(":")[1]
            set_user_state(chat_id, 'enter_operation_name', {'type_id': type_id})
            bot.answer_callback_query(call.id)
            send_msg(chat_id, "Detal/Operatsiya nomini yuboring (masalan: Yoqa tikish):", get_cancel_keyboard())

        elif data.startswith("batch_type:"):
            type_id = data.split(":")[1]
            set_user_state(chat_id, 'enter_batch_name', {'type_id': type_id})
            bot.answer_callback_query(call.id)
            send_msg(chat_id, "Zakaz nomini yuboring (masalan: Zakaz #101):", get_cancel_keyboard())

    except Exception as e:
        logging.error(f"Callbackda xato: {e}")

# --- CHEVAR HANDLERS ---
@bot.message_handler(func=lambda m: True)
def chevar_handler(message):
    try:
        chat_id = message.chat.id
        text = message.text
        # Chevar logikasi...
        if text == "📥 Ish Topshirish":
            send_msg(chat_id, "Hozircha faqat Admin funksiyalari faol. Chevar qismi yakunlanmoqda...")
        else:
            send_msg(chat_id, "Botdan foydalanish uchun /start bosing.")
    except Exception as e:
        logging.error(f"Chevar handlerda xato: {e}")

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
    return Database.init_db() and "Ok" or "Error"

@app.route("/")
def webhook():
    bot.remove_webhook()
    if config.WEBHOOK_URL:
        bot.set_webhook(url=config.WEBHOOK_URL + '/' + config.BOT_TOKEN)
        return "Webhook set", 200
    return "Error", 400

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5000))
    app.run(host='0.0.0.0', port=port)
